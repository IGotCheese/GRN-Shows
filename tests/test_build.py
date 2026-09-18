import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

spec = importlib.util.spec_from_file_location('grn_builder', Path(__file__).parents[1] / 'build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class BuildTests(unittest.TestCase):
    def test_repository_installation_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            output = builder.build('https://shows.example.test/kodi', directory)
            payload = (output / 'addons.xml').read_bytes()
            self.assertEqual(hashlib.md5(payload).hexdigest(), (output / 'addons.xml.md5').read_text())
            index = ET.fromstring(payload)
            for addon in index:
                addon_id = addon.attrib['id']
                path = output / 'zips' / addon_id / ('%s-%s.zip' % (addon_id, addon.attrib['version']))
                with ZipFile(path) as archive:
                    self.assertIsNone(archive.testzip())
                    names = archive.namelist()
                    self.assertTrue(all(name.startswith(addon_id + '/') and '\\' not in name for name in names))
                    self.assertFalse(any('__pycache__' in name or 'lumina' in name for name in names))
                    manifest = ET.fromstring(archive.read(addon_id + '/addon.xml'))
                    for asset in manifest.findall('./extension/assets/*'):
                        # third-party manifests carry empty elements such as
                        # <screenshot></screenshot>; nothing to check there
                        if not asset.text:
                            continue
                        self.assertIn(addon_id + '/' + asset.text, names)
            repo = index.find("./addon[@id='repository.grnshows']")
            self.assertEqual(repo.find('./extension/dir/info').text, 'https://shows.example.test/kodi/addons.xml')

    def test_every_dependency_is_resolvable_from_this_repository(self):
        """A fresh Kodi installing GRN Shows and nothing else must be able to
        satisfy its imports here. Missing script.module.cocoscrapers is what
        made the lounge box report "no external scrapers": the add-on names it
        as its scraper module, and a clean Kodi has never heard of it."""
        with tempfile.TemporaryDirectory() as directory:
            output = builder.build('https://shows.example.test/kodi', directory)
            index = ET.fromstring((output / 'addons.xml').read_bytes())
            advertised = {addon.attrib['id'] for addon in index}
            addon = index.find("./addon[@id='plugin.video.grnshows']")
            # xbmc.python and Kodi's own bundled modules come from Kodi itself
            supplied_by_kodi = {'xbmc.python', 'script.module.requests',
                                'script.module.certifi', 'script.module.chardet',
                                'script.module.idna', 'script.module.urllib3',
                                'script.module.six', 'script.module.pil'}
            for dependency in addon.findall('./requires/import'):
                name = dependency.attrib['addon']
                if name in supplied_by_kodi or dependency.attrib.get('optional') == 'true':
                    continue
                with self.subTest(name):
                    self.assertIn(name, advertised,
                                  '%s is a hard dependency but this repository does not serve it' % name)
                    zips = list((output / 'zips' / name).glob('*.zip'))
                    self.assertTrue(zips, 'no zip published for %s' % name)

    def test_invalid_base_url_rejected(self):
        for url in ('file:///tmp/repo', 'https://user:secret@example.test', 'https://example.test/?x=1'):
            with self.assertRaises(ValueError):
                builder.build(url)

    REGISTRY = 'resources/lib/caches/settings_cache.py'
    SKIN = 'resources/skins/Default/1080i/settings_manager.xml'

    def test_keys_are_baked_into_the_zip_not_the_tree(self):
        tree = Path(builder.ROOT) / 'plugin.video.grnshows'
        tree_copy = (tree / self.REGISTRY).read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as directory:
            keys_file = Path(directory) / 'keys.json'
            keys_file.write_text(json.dumps({'TMDB_API_KEY': 'tmdb-value', 'TRAKT_CLIENT_ID': 'id-value',
                                             'TRAKT_CLIENT_SECRET': 'secret-value'}), encoding='utf-8')
            output = builder.build('https://shows.example.test/kodi', directory, keys_file)
            zip_path = next((output / 'zips' / 'plugin.video.grnshows').glob('*.zip'))
            with ZipFile(zip_path) as archive:
                packaged = archive.read('plugin.video.grnshows/' + self.REGISTRY).decode('utf-8')
                skin = archive.read('plugin.video.grnshows/' + self.SKIN).decode('utf-8')
        self.assertIn("'setting_default': 'tmdb-value'", packaged)
        self.assertIn("'setting_default': 'secret-value'", packaged)
        self.assertIn('class SettingsCache', packaged)  # the rest of the module survives
        self.assertNotIn('@@', packaged)
        # the settings window compares against the same key, so it is baked too
        self.assertIn('tmdb-value', skin)
        self.assertNotIn('@@', skin)
        self.assertNotIn('tmdb-value', tree_copy)
        # exactly the three credential rows change, nothing else in the registry
        changed = [a for a, b in zip(packaged.splitlines(), tree_copy.splitlines()) if a != b]
        self.assertEqual(len(changed), 3, changed)

    def test_missing_keys_file_still_builds(self):
        with tempfile.TemporaryDirectory() as directory:
            output = builder.build('https://shows.example.test/kodi', directory, Path(directory) / 'absent.json')
            zip_path = next((output / 'zips' / 'plugin.video.grnshows').glob('*.zip'))
            with ZipFile(zip_path) as archive:
                packaged = archive.read('plugin.video.grnshows/' + self.REGISTRY).decode('utf-8')
        self.assertIn("{'setting_id': 'tmdb_api', 'setting_type': 'string', 'setting_default': 'empty_setting'}",
                      packaged, 'with no key the add-on has to see its own "unset" sentinel')
        self.assertNotIn('@@', packaged, 'an unfilled token would be sent to TMDb as a key')

    def test_every_directory_is_browsable_by_kodi(self):
        # Kodi installs from a web source by browsing it like a folder. nginx
        # produced those listings itself, but GitHub Pages lists nothing and
        # answers 404, so build.py writes them. This used to assert the
        # opposite - no index.html - because a human-readable index.html served
        # in place of nginx's listing left Kodi with an empty source. The
        # listing written now IS in nginx's format, so it is browsable whether a
        # server serves it or lists the directory itself.
        import re
        with tempfile.TemporaryDirectory() as directory:
            output = builder.build('https://shows.example.test/kodi', directory)
            self.assertTrue((output / 'info.html').is_file())
            self.assertTrue((output / '.nojekyll').is_file(),
                            'GitHub Pages would run Jekyll and drop files')
            for folder in [output, *[p for p in output.rglob('*') if p.is_dir()]]:
                listing = folder / 'index.html'
                self.assertTrue(listing.is_file(), '%s has no listing' % folder)
                anchors = re.findall(r'<a href="([^"]+)">([^<]+)</a>',
                                     listing.read_text(encoding='utf-8'))
                shown = {href for href, text in anchors}
                # Kodi only counts an anchor as an entry when its text matches
                # its target; anything else is treated as a navigation link.
                for href, text in anchors:
                    self.assertEqual(href, text, 'Kodi would skip %r in %s' % (href, folder))
                for child in folder.iterdir():
                    if child.name in ('index.html', 'info.html', '.nojekyll'):
                        continue
                    expected = child.name + '/' if child.is_dir() else child.name
                    self.assertIn(expected, shown, '%s is missing from %s' % (expected, folder))
            # The ZIP the install guide tells people to click must be at the root.
            root = (output / 'index.html').read_text(encoding='utf-8')
            self.assertRegex(root, r'href="repository\.grnshows-[0-9.]+\.zip"')

    def test_repository_zip_is_also_at_the_source_root(self):
        with tempfile.TemporaryDirectory() as directory:
            output = builder.build('https://shows.example.test/kodi', directory)
            index = ET.fromstring((output / 'addons.xml').read_bytes())
            version = index.find("./addon[@id='repository.grnshows']").attrib['version']
            root_zip = output / ('repository.grnshows-%s.zip' % version)
            nested = output / 'zips' / 'repository.grnshows' / root_zip.name
            self.assertTrue(root_zip.is_file(), 'Kodi opens the source root; the repo ZIP must be there')
            self.assertEqual(root_zip.read_bytes(), nested.read_bytes())
            self.assertFalse(list(output.glob('plugin.video.grnshows-*.zip')), 'only the repo ZIP belongs at the root')

    def test_superseded_zips_are_kept(self):
        # A client that cached addons.xml before a rebuild still asks for the
        # version it saw. Deleting it gives that client a 404 and Kodi reports
        # "could not be downloaded".
        with tempfile.TemporaryDirectory() as directory:
            older = Path(directory) / 'zips' / 'plugin.video.grnshows'
            older.mkdir(parents=True)
            (older / 'plugin.video.grnshows-0.9.0.zip').write_bytes(b'previous release')
            output = builder.build('https://shows.example.test/kodi', directory)
            names = sorted(path.name for path in (output / 'zips' / 'plugin.video.grnshows').glob('*.zip'))
        self.assertIn('plugin.video.grnshows-0.9.0.zip', names)
        self.assertEqual(len(names), 2)

    def test_unknown_key_names_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            keys_file = Path(directory) / 'keys.json'
            keys_file.write_text(json.dumps({'TMDB_API_KEY': 'x', 'NOT_A_KEY': 'y'}), encoding='utf-8')
            with self.assertRaises(ValueError):
                builder.load_keys(keys_file)

    def test_environment_overrides_the_file(self):
        with tempfile.TemporaryDirectory() as directory:
            keys_file = Path(directory) / 'keys.json'
            keys_file.write_text(json.dumps({'TMDB_API_KEY': 'from-file'}), encoding='utf-8')
            os.environ['GRNSHOWS_TMDB_API_KEY'] = 'from-env'
            try:
                self.assertEqual(builder.load_keys(keys_file)['TMDB_API_KEY'], 'from-env')
            finally:
                del os.environ['GRNSHOWS_TMDB_API_KEY']
