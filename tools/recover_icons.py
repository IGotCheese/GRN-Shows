"""Recover the FenLightAM menu icon set out of Kodi's texture cache.

get_icon() in kodi_utils.py builds a raw.githubusercontent.com URL for every
menu row, every dialog button and every notification. The account it points at
(FenlightAnonyMouse) returns 404 on every path now, so upstream FenLightAM
renders with no icons at all today, and a fresh port pointed at a GitHub repo
we have not created yet renders the same way.

This machine ran FenLightAM before the account went away, so Kodi downloaded
and cached those PNGs. Textures13.db maps the original URL to a file under
userdata/Thumbnails. That cache is the only surviving copy we know of, same as
the add-on itself.

Recovered files land in the add-on under resources/media/icons/, which
tools/port_fenlight.py then preserves across a re-port and patches get_icon()
to prefer.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

KODI = Path(os.environ.get('LOCALAPPDATA', '')) / \
    'Packages/XBMCFoundation.Kodi_4n2hpmxwrvr6p/LocalCache/Roaming/Kodi'
PATTERN = '%FenlightAnonyMouse%'


def recover(kodi_root: Path, destination: Path) -> dict:
    databases = sorted((kodi_root / 'userdata' / 'Database').glob('Textures*.db'))
    if not databases:
        raise SystemExit('no texture database under %s' % (kodi_root / 'userdata' / 'Database'))
    thumbnails = kodi_root / 'userdata' / 'Thumbnails'
    found, written, missing = {}, 0, []
    for database in databases:
        # read-only: Kodi is probably running and holds this open
        connection = sqlite3.connect('file:%s?mode=ro' % database.as_posix(), uri=True)
        try:
            rows = connection.execute(
                'SELECT url, cachedurl FROM texture WHERE url LIKE ?', (PATTERN,)).fetchall()
        except sqlite3.DatabaseError as exc:
            print('%s unreadable: %s' % (database.name, exc))
            continue
        finally:
            connection.close()
        for url, cached in rows:
            # .../main/packages/media/<folder>/<name>.png
            parts = url.split('/packages/media/')
            if len(parts) != 2:
                continue
            relative = parts[1].split('?')[0]
            source = thumbnails / cached
            if not source.is_file():
                missing.append(relative)
                continue
            found[relative] = source
    for relative, source in sorted(found.items()):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # Kodi caches as .png regardless of the cached file's extension here;
        # the bytes are what the skin needs, so copy them unchanged.
        target.write_bytes(source.read_bytes())
        written += 1
    return {'written': written, 'missing': sorted(set(missing)),
            'folders': sorted({r.split('/')[0] for r in found})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kodi', type=Path, default=KODI)
    parser.add_argument('--into', type=Path, required=True,
                        help='destination for the media tree, e.g. .../resources/media')
    args = parser.parse_args()
    result = recover(args.kodi, args.into)
    print('recovered %d icons into %s' % (result['written'], args.into))
    print('folders:', ', '.join(result['folders']) or '(none)')
    if result['missing']:
        print('%d cached entries had no file on disk: %s'
              % (len(result['missing']), ', '.join(result['missing'][:10])))
    if not result['written']:
        raise SystemExit('nothing recovered')


if __name__ == '__main__':
    main()
