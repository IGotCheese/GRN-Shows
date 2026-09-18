"""Invariants of the FenLightAM port.

These are the failures that only show up as a stack trace inside Kodi, where
the message is usually an unhelpful "Error Contacting Add-on". Checking them
here means a re-port either passes or fails at the command line.
"""
import ast
import importlib.util
import re
import hashlib
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / 'plugin.video.grnshows'
LIB = ADDON / 'resources' / 'lib'
SKIN = ADDON / 'resources' / 'skins' / 'Default'

spec = importlib.util.spec_from_file_location('grn_port', ROOT / 'tools' / 'port_fenlight.py')
port = importlib.util.module_from_spec(spec)
spec.loader.exec_module(port)

PNG_MAGIC = bytes([0x89]) + b'PNG' + bytes([0x0d, 0x0a, 0x1a, 0x0a])

PYTHON_FILES = sorted(LIB.rglob('*.py'))
TEXT_FILES = sorted(p for p in ADDON.rglob('*') if p.is_file() and p.suffix in {'.py', '.xml', '.txt'})


class RebrandTests(unittest.TestCase):
    def test_no_upstream_identifier_survives(self):
        offenders = []
        for path in TEXT_FILES:
            for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
                if port.RESIDUE.search(line):
                    offenders.append('%s:%d %s' % (path.relative_to(ADDON), number, line.strip()[:80]))
        self.assertEqual(offenders, [])

    def test_no_upstream_name_in_any_path(self):
        self.assertEqual([str(p.relative_to(ADDON)) for p in ADDON.rglob('*')
                          if port.RESIDUE.search(p.name)], [])

    def test_class_names_did_not_get_a_space(self):
        """'FenLight' becomes 'GRN Shows' for display, which would be a syntax
        error inside FenLightPlayer. The closed-up form has to win there."""
        source = (LIB / 'modules' / 'player.py').read_text(encoding='utf-8')
        self.assertIn('class GRNShowsPlayer(', source)
        self.assertIn('class GRNShowsMonitor(', (LIB / 'service.py').read_text(encoding='utf-8'))

    def test_everything_parses(self):
        for path in PYTHON_FILES:
            with self.subTest(path.relative_to(ADDON)):
                ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))

    def test_the_port_is_not_empty(self):
        self.assertGreater(len(PYTHON_FILES), 80, 'the upstream tree is ~91 modules')


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = ET.parse(ADDON / 'addon.xml').getroot()

    def test_identity(self):
        self.assertEqual(self.manifest.attrib['id'], 'plugin.video.grnshows')
        self.assertEqual(self.manifest.attrib['name'], 'GRN Shows')

    def test_declared_entry_points_exist(self):
        for extension in self.manifest.findall('extension'):
            library = extension.attrib.get('library')
            if library and library.endswith('.py'):
                self.assertTrue((ADDON / library).is_file(), library)

    def test_lib_is_the_python_module_root(self):
        """resources/lib has to be on sys.path or `from modules.router import
        routing` fails on the very first line of the entry point."""
        points = {e.attrib['point']: e.attrib.get('library') for e in self.manifest.findall('extension')}
        self.assertEqual(points.get('xbmc.python.module'), 'resources/lib/')

    def test_assets_exist(self):
        assets = self.manifest.findall('./extension/assets/*')
        self.assertTrue(assets)
        for asset in assets:
            self.assertTrue((ADDON / asset.text).is_file(), asset.text)

    def test_pil_is_optional(self):
        """script.module.pil is not in every repository and is used by one
        feature. A hard requirement makes the add-on uninstallable."""
        pil = self.manifest.find("./requires/import[@addon='script.module.pil']")
        self.assertIsNotNone(pil)
        self.assertEqual(pil.attrib.get('optional'), 'true')
        source = (LIB / 'modules' / 'utils.py').read_text(encoding='utf-8')
        self.assertIn('except ImportError:', source.split('def make_image')[1][:600])


class SkinTests(unittest.TestCase):
    def test_every_window_xml_parses(self):
        files = sorted((SKIN / '1080i').glob('*.xml'))
        self.assertGreaterEqual(len(files), 17)
        for path in files:
            with self.subTest(path.name):
                ET.parse(path)

    def test_every_window_class_has_its_xml(self):
        available = {p.name for p in (SKIN / '1080i').glob('*.xml')}
        for path in sorted((LIB / 'windows').glob('*.py')):
            for name in re.findall(r"['\"]([a-z_]+\.xml)['\"]", path.read_text(encoding='utf-8')):
                with self.subTest('%s -> %s' % (path.name, name)):
                    self.assertIn(name, available)

    def test_every_referenced_texture_shipped(self):
        missing = []
        for path in sorted((SKIN / '1080i').glob('*.xml')):
            body = path.read_text(encoding='utf-8')
            for ref in sorted(set(re.findall(r'(grnshows_[a-z]+/[A-Za-z0-9_\-]+\.png)', body))):
                if not (SKIN / 'media' / ref).is_file():
                    missing.append('%s -> %s' % (path.name, ref))
        self.assertEqual(missing, [])

    def test_media_directories_were_renamed(self):
        names = {p.name for p in (SKIN / 'media').iterdir() if p.is_dir()}
        self.assertEqual(names, {'grnshows_buttons', 'grnshows_common',
                                 'grnshows_diffuse', 'grnshows_flags'})


class UpdaterTests(unittest.TestCase):
    """The built-in updater installs code, so where it looks is fixed in code.

    It used to build its address from two user-editable settings that named a
    GitHub account nobody owned; registering that name would have put an
    "update" in front of every install.
    """
    def test_updater_reads_our_published_repository(self):
        updater = (LIB / 'modules' / 'updater.py').read_text(encoding='utf-8')
        self.assertIn("'https://igotcheese.github.io/GRN-Shows/zips/plugin.video.grnshows/%s'", updater)
        self.assertNotIn('github.com', updater.replace('.github.io', ''))

    def test_nothing_reads_an_update_location_setting(self):
        for path in sorted((ADDON / 'resources').rglob('*')):
            if path.is_file() and path.suffix in ('.py', '.xml'):
                self.assertNotRegex(path.read_text(encoding='utf-8-sig'), r'update\.(?:username|location)',
                                    path.relative_to(ADDON).as_posix())

    def test_build_publishes_what_the_updater_reads(self):
        import tempfile
        spec = importlib.util.spec_from_file_location('build', ROOT / 'build.py')
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        version = ET.parse(ADDON / 'addon.xml').getroot().attrib['version']
        with tempfile.TemporaryDirectory() as output:
            build.build('https://example.test/grn-shows', output)
            folder = Path(output) / 'zips' / 'plugin.video.grnshows'
            self.assertEqual((folder / 'grnshowsam_version').read_text(encoding='utf-8'), version)
            self.assertIn(version, (folder / 'grnshowsam_changes').read_text(encoding='utf-8'))
            listing = (folder / 'index.html').read_text(encoding='utf-8')
            self.assertIn('href="plugin.video.grnshows-%s.zip"' % version, listing)


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.registry = (LIB / 'caches' / 'settings_cache.py').read_text(encoding='utf-8-sig')
        self.window = (SKIN / '1080i' / 'settings_manager.xml').read_text(encoding='utf-8-sig')

    def test_tree_holds_no_key(self):
        """Only tokens live in the tree; build.py fills them from keys.json."""
        for token in port.CREDENTIAL_SETTINGS.values():
            self.assertIn(token, self.registry)

    def test_the_settings_window_compares_against_the_same_token(self):
        """The window decides whether to offer a clear/reset row by comparing
        the live value against the shipped default. Tokenising only the
        registry leaves that row stuck on."""
        for token in port.CREDENTIAL_SETTINGS.values():
            self.assertIn(token, self.window)

    # The upstream keys are identified by hash, never written out.
    #
    # FenLightAM 2.2.03 shipped its author's own TMDb and Trakt credentials,
    # and this test exists to prove none of them survived the port. Pasting
    # them into a public repository would republish someone else's keys and
    # trip secret scanning, so every 32 or 64 character hex string in the
    # tree is hashed and the digests are compared instead.
    UPSTREAM_KEY_DIGESTS = frozenset({
        '09e9d6a99794253af2540b2918060e79f71bc133047970892e02ba2fa20686de',
        'd63260fe6d210ce0ac387fae20c1f5d381197c77f750513f98ad360200b3d20a',
        '46bbe828368cb558131cfe53171b8ca5833dad4569a1144d4f84cdb1dbf84bc4',
    })

    def test_no_upstream_author_key_anywhere(self):
        candidate = re.compile(r'[0-9a-f]{32}(?:[0-9a-f]{32})?')
        for path in TEXT_FILES:
            body = path.read_text(encoding='utf-8-sig')
            for found in candidate.findall(body):
                digest = hashlib.sha256(found.encode()).hexdigest()
                self.assertNotIn(digest, self.UPSTREAM_KEY_DIGESTS,
                                 '%s still contains an upstream key' % path.name)


class IconTests(unittest.TestCase):
    """The upstream add-on fetched every menu icon from a GitHub account that
    now 404s, so stock FenLightAM renders icon-less today. Ours are bundled."""

    MEDIA = ADDON / 'resources' / 'media'

    def test_the_whole_icon_set_is_bundled(self):
        self.assertGreaterEqual(len(list((self.MEDIA / 'icons').glob('*.png'))), 99)
        for folder, least in (('flags', 4), ('results', 3), ('network_icons', 70)):
            with self.subTest(folder):
                self.assertGreaterEqual(len(list((self.MEDIA / folder).glob('*'))), least)

    def test_every_requested_icon_exists(self):
        """get_icon(name, folder) 404ing is invisible at runtime: the row just
        renders blank. Check the names the code asks for against what shipped."""
        missing = []
        for path in sorted(LIB.rglob('*.py')):
            body = path.read_text(encoding='utf-8-sig')
            for name, folder in re.findall(r"get_icon\(\s*'([A-Za-z0-9_]+)'\s*(?:,\s*'([a-z_]+)')?", body):
                target = self.MEDIA / (folder or 'icons') / ('%s.png' % name)
                if not target.is_file():
                    missing.append('%s -> %s' % (path.name, target.relative_to(self.MEDIA)))
        self.assertEqual(sorted(set(missing)), [])

    def test_the_audio_icon_typo_is_fixed(self):
        """Upstream saved icons/audio.png as audiopng.png, so get_icon('audio')
        404s in FenLightAM itself."""
        self.assertTrue((self.MEDIA / 'icons' / 'audio.png').is_file())

    def test_get_icon_prefers_the_bundled_file(self):
        source = (LIB / 'modules' / 'kodi_utils.py').read_text(encoding='utf-8')
        body = source.split('def get_icon(')[1].split('\ndef ')[0]
        self.assertIn('if os.path.exists(bundled): return bundled', body)
        # the remote URL stays as the fallback for names not in the cache
        self.assertIn('raw.githubusercontent.com', body)

    def test_bundled_icons_are_real_pngs(self):
        for path in sorted((self.MEDIA / 'icons').glob('*.png')):
            with self.subTest(path.name):
                self.assertEqual(path.read_bytes()[:8], PNG_MAGIC)

    def test_the_addon_icon_is_ours(self):
        """A failed port once left the upstream icon in place. The port tool
        checks this too; so does the suite, because it ships to users."""
        icon = (self.MEDIA / 'addon_icons' / 'grnshows_icon_01.png').read_bytes()
        self.assertEqual(icon, (self.MEDIA / 'icon.png').read_bytes())
        self.assertEqual(icon[:8], PNG_MAGIC)


class OutOfBoxTests(unittest.TestCase):
    """What a brand-new install gets before the user touches anything.

    This add-on is published for other people, so "works once you connect your
    own account" is the bar. Upstream fails it: it ships every source off, no
    scraper module, and no OAuth client id, which is why authorising
    Real-Debrid used to answer "Please set a valid Real-Debrid Client ID".
    """

    def setUp(self):
        self.registry = (LIB / 'caches' / 'settings_cache.py').read_text(encoding='utf-8-sig')

    def default_for(self, setting_id):
        match = re.search(r"\{'setting_id': '%s',[^}]*'setting_default': '([^']*)'"
                          % re.escape(setting_id), self.registry)
        self.assertIsNotNone(match, '%s is not in the settings registry' % setting_id)
        return match.group(1)

    def test_debrid_authorisation_can_start_unattended(self):
        """Public device-flow client ids, verified live against both services."""
        self.assertEqual(self.default_for('rd.client_id'), 'X245A4XAIBGVM')
        self.assertEqual(self.default_for('pm.client_id'), '888228107')

    def test_no_account_token_is_shipped(self):
        """Client ids identify the application; tokens are per user and must
        never be baked into a public build."""
        for setting_id in ('rd.token', 'pm.token', 'ad.token', 'tb.token',
                           'rd.secret', 'trakt.token', 'easynews_user', 'easynews_password'):
            with self.subTest(setting_id):
                self.assertIn(self.default_for(setting_id), ('empty_setting', '', '0'))

    def test_accounts_start_disabled(self):
        """Nothing is "connected" until the user actually authorises it."""
        for setting_id in ('rd.enabled', 'pm.enabled', 'ad.enabled', 'tb.enabled'):
            with self.subTest(setting_id):
                self.assertEqual(self.default_for(setting_id), 'false')

    def test_sources_are_on_by_default(self):
        """The cloud providers only engage once their debrid is authorised and
        enabled, so switching them on costs nothing and means a freshly
        connected account is searched immediately."""
        for setting_id in ('provider.external', 'provider.rd_cloud', 'provider.pm_cloud',
                           'provider.ad_cloud', 'provider.tb_cloud'):
            with self.subTest(setting_id):
                self.assertEqual(self.default_for(setting_id), 'true')

    def test_a_scraper_module_is_chosen(self):
        self.assertEqual(self.default_for('external_scraper.module'), 'script.module.cocoscrapers')

    def test_the_scraper_module_is_required(self):
        """Not optional any more: the add-on points its scraper module at
        CocoScrapers and finds nothing without it, and the GRN repository now
        carries it so a fresh Kodi can resolve it. Optional would let Kodi
        install the add-on in a state where no source ever works."""
        manifest = ET.parse(ADDON / 'addon.xml').getroot()
        coco = manifest.find("./requires/import[@addon='script.module.cocoscrapers']")
        self.assertIsNotNone(coco)
        self.assertNotEqual(coco.attrib.get('optional'), 'true')


class SubstitutionTests(unittest.TestCase):
    def test_identifiers_stay_valid(self):
        self.assertEqual(port.rebrand('from modules.player import FenLightPlayer', 'u', 'r'),
                         'from modules.player import GRNShowsPlayer')

    def test_display_name_keeps_its_space(self):
        self.assertEqual(port.rebrand('Autostart FenLight When Kodi Starts', 'u', 'r'),
                         'Autostart GRN Shows When Kodi Starts')

    def test_github_identifiers_do_not_double_substitute(self):
        self.assertEqual(port.rebrand('FenlightAnonyMouse', 'grn-user', 'grn-repo'), 'grn-user')
        self.assertEqual(port.rebrand('FenlightAnonyMouse.github.io', 'grn-user', 'grn-repo'), 'grn-repo')

    def test_plugin_url_is_rewritten(self):
        self.assertEqual(port.rebrand('plugin://plugin.video.fenlight/?', 'u', 'r'),
                         'plugin://plugin.video.grnshows/?')


if __name__ == '__main__':
    unittest.main()
