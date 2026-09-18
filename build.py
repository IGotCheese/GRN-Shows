"""Build a Kodi repository on Linux or Windows using Python 3.8+."""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
# Third-party add-ons this repository carries so Kodi can resolve GRN Shows'
# dependencies without the user first installing somebody else's repository.
VENDOR = ROOT / 'vendor'
KEY_FIELDS = ('TMDB_API_KEY', 'TRAKT_CLIENT_ID', 'TRAKT_CLIENT_SECRET')
# tools/port_fenlight.py leaves an @@FIELD@@ token everywhere the upstream
# add-on had a hardcoded credential: the setting default in the registry, and
# the literal the settings window compares against to offer a "reset to
# default" row. Both are filled here, so the working tree never holds a key.
KEY_TOKEN = re.compile(r'@@(%s)@@' % '|'.join(KEY_FIELDS))
TOKEN_SUFFIXES = ('.py', '.xml', '.txt')


def load_keys(path=None):
    """Read keys.json, then let GRNSHOWS_* environment variables win.

    Keeping the values out of the tree is the whole point, so a missing file is
    not an error: the add-on just falls back to user-entered settings.
    """
    source = Path(path) if path else ROOT / 'keys.json'
    values = {field: '' for field in KEY_FIELDS}
    if source.is_file():
        data = json.loads(source.read_text(encoding='utf-8-sig'))
        unknown = set(data) - set(KEY_FIELDS)
        if unknown:
            raise ValueError('Unknown keys in %s: %s' % (source, ', '.join(sorted(unknown))))
        values.update({field: str(data.get(field) or '') for field in KEY_FIELDS})
    for field in KEY_FIELDS:
        values[field] = os.environ.get('GRNSHOWS_' + field, values[field]).strip()
    return values


# What the add-on stores for a setting nobody has filled in. A field we have no
# value for has to come out as this, not as an empty string and certainly not
# as a leftover @@TOKEN@@, or the add-on will send that text to TMDb as a key.
UNSET = 'empty_setting'


def render_keys(values, template):
    """Substitute every @@FIELD@@ token with its value."""
    return KEY_TOKEN.sub(lambda match: values[match.group(1)] or UNSET, template)


def write_listings(output):
    """Write an index.html into every directory, in nginx's autoindex format.

    Kodi installs from a web source by BROWSING it like a folder: Add source,
    then Install from zip file, reads the source root as a directory listing.
    nginx produced those listings itself (autoindex on). GitHub Pages does not
    list directories at all and answers 404, which leaves Kodi with an empty
    source and every new install stuck at the first step, while updates for
    existing users still work because Kodi fetches addons.xml directly. So the
    listings are written as files instead.

    The format copies nginx exactly, because Kodi's parser is tuned for it: an
    anchor only counts as an entry when its text matches its target, which is
    how Kodi skips navigation links, and a trailing slash marks a directory.
    nginx here is configured to ignore index files, so these change nothing on
    a self-hosted server.
    """
    for directory in [output, *sorted(p for p in output.rglob('*') if p.is_dir())]:
        relative = directory.relative_to(output).as_posix()
        title = '/' if relative == '.' else '/%s/' % relative
        entries = [] if directory == output else ['../']
        for child in sorted(directory.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower())):
            if child.name in ('index.html', 'info.html', '.nojekyll'):
                continue
            entries.append(child.name + '/' if child.is_dir() else child.name)
        rows = ''.join('<a href="%s">%s</a>\n' % (html.escape(e, quote=True), html.escape(e))
                       for e in entries)
        (directory / 'index.html').write_text(
            '<html>\n<head><title>Index of %s</title></head>\n<body>\n'
            '<h1>Index of %s</h1><hr><pre>%s</pre><hr></body>\n</html>\n'
            % (html.escape(title), html.escape(title), rows), encoding='utf-8')
    # GitHub Pages runs Jekyll by default, which drops files and folders it does
    # not recognise. This marker turns that off so every ZIP is served as-is.
    (output / '.nojekyll').write_text('', encoding='ascii')


def build(base_url, output=None, keys_file=None):
    base_url = base_url.rstrip('/')
    parsed = urlsplit(base_url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('Base URL must be an HTTP(S) repository address without credentials, query, or fragment')
    output = Path(output) if output else ROOT / 'dist'
    output.mkdir(parents=True, exist_ok=True)
    keys = load_keys(keys_file)
    baked = set()
    index = ET.Element('addons')
    links = []
    for addon_id in ('plugin.video.grnshows', 'repository.grnshows'):
        source = ROOT / addon_id
        manifest = source / ('addon.xml.template' if addon_id.startswith('repository.') else 'addon.xml')
        xml = manifest.read_text(encoding='utf-8-sig').replace('{{BASE_URL}}', html.escape(base_url, quote=True))
        element = ET.fromstring(xml)
        if element.attrib['id'] != addon_id:
            raise ValueError('Manifest ID does not match directory')
        index.append(element)
        destination = output / 'zips' / addon_id
        destination.mkdir(parents=True, exist_ok=True)
        filename = '%s-%s.zip' % (addon_id, element.attrib['version'])
        # Superseded versions stay. A client that refreshed addons.xml before a
        # rebuild still resolves the OLD version number from its cache, and
        # deleting that ZIP turns its next update into "could not be
        # downloaded". Kodi's own "install previous version" needs them too.
        with ZipFile(destination / filename, 'w', ZIP_DEFLATED) as archive:
            archive.writestr(addon_id + '/addon.xml', xml)
            for path in sorted(source.rglob('*')):
                relative = path.relative_to(source)
                if not path.is_file() or path.is_symlink() or '__pycache__' in relative.parts or 'lumina' in relative.parts:
                    continue
                if path.name in ('addon.xml', 'addon.xml.template') or path.suffix in ('.pyc', '.pyo'):
                    continue
                if path.suffix in TOKEN_SUFFIXES:
                    body = path.read_text(encoding='utf-8-sig')
                    if KEY_TOKEN.search(body):
                        # The packaged copy carries the real values; the tree keeps tokens.
                        archive.writestr(addon_id + '/' + relative.as_posix(), render_keys(keys, body))
                        baked.add(relative.as_posix())
                        continue
                archive.write(path, addon_id + '/' + relative.as_posix())
        for asset in element.findall('./extension/assets/*'):
            shutil.copyfile(source / asset.text, destination / Path(asset.text).name)
        links.append('<li><a href="zips/%s/%s">%s</a></li>' % (addon_id, filename, html.escape(element.attrib['name'])))
        if addon_id.startswith('repository.'):
            # Kodi's "Install from zip file" browser opens at the source root. Keeping
            # a copy of the repository ZIP there turns a four-click dig through
            # zips/repository.grnshows/ into one click, which is how every other
            # Kodi repository people have used before behaves.
            shutil.copyfile(destination / filename, output / filename)
    # Vendored dependencies: copied through untouched and advertised in
    # addons.xml, so `installing GRN Shows` pulls them in automatically.
    newest = {}
    for archive_path in sorted(VENDOR.glob('*.zip')):
        try:
            with ZipFile(archive_path) as archive:
                manifest = next(name for name in archive.namelist()
                                if name.count('/') == 1 and name.endswith('/addon.xml'))
                element = ET.fromstring(archive.read(manifest))
        except (BadZipFile, KeyError, OSError, StopIteration, ET.ParseError) as error:
            raise ValueError('%s is not a usable add-on zip: %s' % (archive_path.name, error))
        # Only the newest of each id: vendoring picks up every published version,
        # and advertising several of a DEPENDENCY just gives Kodi a choice it has
        # no reason to make.
        def version_key(text):
            return tuple(int(part) if part.isdigit() else part
                         for part in re.split(r'[.-]', text))
        current = newest.get(element.attrib['id'])
        if current is None or version_key(element.attrib['version']) > version_key(current[0]):
            newest[element.attrib['id']] = (element.attrib['version'], archive_path, element)

    for vendor_id, (_, archive_path, element) in sorted(newest.items()):
        destination = output / 'zips' / vendor_id
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(archive_path, destination / archive_path.name)
        index.append(element)
        links.append('<li><a href="zips/%s/%s">%s (bundled dependency)</a></li>'
                     % (vendor_id, archive_path.name, html.escape(element.attrib['name'])))

    # Kodi's "Versions" dialog lists whatever addons.xml advertises for an id.
    # Advertising only the newest leaves that dialog empty, so every ZIP still
    # on disk gets an entry, newest first.
    for addon_id in ('plugin.video.grnshows', 'repository.grnshows'):
        current = index.find("./addon[@id='%s']" % addon_id)
        if current is None:
            continue
        for archive_path in sorted((output / 'zips' / addon_id).glob(addon_id + '-*.zip'), reverse=True):
            version = archive_path.stem[len(addon_id) + 1:]
            if version == current.attrib['version']:
                continue
            try:
                with ZipFile(archive_path) as archive:
                    older = ET.fromstring(archive.read(addon_id + '/addon.xml'))
            except (BadZipFile, KeyError, OSError, ET.ParseError):
                continue  # an unreadable ZIP must not stop the build
            if older.attrib.get('id') == addon_id:
                index.append(older)
    payload = ET.tostring(index, encoding='utf-8', xml_declaration=True)
    (output / 'addons.xml').write_bytes(payload)
    (output / 'addons.xml.md5').write_text(hashlib.md5(payload).hexdigest(), encoding='ascii')
    # The human-readable summary is info.html. index.html in every directory
    # is the machine listing Kodi browses; see write_listings().
    # instead of the file listing it needs to browse the source.
    (output / 'info.html').write_text(
        '<!doctype html><html><head><meta charset="utf-8"><title>GRN Shows</title></head>'
        '<body><h1>GRN Shows</h1><p>Kodi source: %s</p><ul>%s</ul></body></html>'
        % (html.escape(base_url), ''.join(links)), encoding='utf-8')
    if not baked:
        raise ValueError('No @@KEY@@ token found in the add-on tree; re-run tools/port_fenlight.py')
    write_listings(output)
    missing = [field for field in KEY_FIELDS if not keys[field]]
    if missing:
        print('WARNING: no value for %s. Users of this build must enter their own.' % ', '.join(missing))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True, help='Address reachable from your Kodi devices')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--keys', type=Path, help='JSON file with TMDB_API_KEY, TRAKT_CLIENT_ID, TRAKT_CLIENT_SECRET')
    args = parser.parse_args()
    print('Built GRN Shows repository:', build(args.base_url, args.output, args.keys))
