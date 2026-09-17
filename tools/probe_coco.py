"""Run the CocoScrapers torrent providers the way the add-on runs them.

modules/sources.py calls cocoscrapers.sources(specified_folders=['torrents'],
ret_all=...) and then each provider's .sources(). Every failure in that chain
is swallowed by a bare `except`, so inside Kodi an empty result and a broken
import look identical. This reproduces the chain outside Kodi and reports
per provider.

    py -3 tools/probe_coco.py --title "The Matrix" --year 1999
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_hosters import ADDONS, stub_kodi  # noqa: E402

COCO = ADDONS / 'script.module.cocoscrapers'


def prepare_path():
    for module_id in ('script.module.six', 'script.module.kodi-six', 'script.module.simplejson',
                      'script.module.requests', 'script.module.certifi', 'script.module.chardet',
                      'script.module.idna', 'script.module.urllib3', 'script.module.resolveurl'):
        for folder in ('lib', 'libs'):
            candidate = ADDONS / module_id / folder
            if candidate.is_dir():
                sys.path.insert(0, str(candidate))
                break
    sys.path.insert(0, str(COCO / 'lib'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--title', default='The Matrix')
    parser.add_argument('--year', default='1999')
    parser.add_argument('--imdb', default='tt0133093')
    parser.add_argument('--all', action='store_true',
                        help='ignore each provider\'s enabled flag, like ret_all=True')
    args = parser.parse_args()

    stub_kodi()
    use_real_settings()
    prepare_path()
    import cocoscrapers

    enabled = cocoscrapers.sources(specified_folders=['torrents'])
    every = cocoscrapers.sources(specified_folders=['torrents'], ret_all=True)
    print('providers enabled in CocoScrapers settings: %d' % len(enabled))
    print('providers shipped in the torrents folder:   %d' % len(every))
    if not enabled:
        print('\n>>> This is the failure: the add-on asks for ENABLED providers only,\n'
              '    and CocoScrapers reports none. Sources will always come back empty.')
    chosen = every if args.all or not enabled else enabled

    # data dict the providers expect; omit show keys for a movie, because
    # providers branch on `if 'tvshowtitle' in data`, a key-presence check
    data = {'imdb': args.imdb, 'title': args.title, 'localtitle': args.title,
            'aliases': [], 'year': args.year}

    total, working = 0, []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {}
        for entry in chosen:
            try:
                provider = entry[1]() if isinstance(entry, tuple) else entry.source()
            except Exception:
                continue
            futures[pool.submit(probe_one, provider, data)] = describe(entry)
        for future in as_completed(futures, timeout=180):
            label = futures[future]
            try:
                count = future.result()
            except Exception as exc:
                print('  %-22s raised %s: %s' % (label, type(exc).__name__, str(exc)[:60]))
                continue
            total += count
            if count:
                working.append((label, count))
    print('\nWORKING %d providers, %d sources total' % (len(working), total))
    for label, count in sorted(working, key=lambda x: -x[1]):
        print('   %-22s %d' % (label, count))


def use_real_settings():
    """Answer getSetting() from CocoScrapers' own settings.xml.

    Returning a constant makes enabledCheck() report every provider as
    disabled, which looks exactly like a real "no providers enabled" fault.
    Reading the file the add-on actually reads avoids inventing that failure.
    """
    import xml.etree.ElementTree as ET
    import xbmcaddon
    values = {}
    settings_file = (ADDONS.parent / 'userdata' / 'addon_data' /
                     'script.module.cocoscrapers' / 'settings.xml')
    if settings_file.is_file():
        for node in ET.parse(settings_file).getroot().findall('setting'):
            values[node.attrib.get('id', '')] = (node.text or '').strip()
    print('read %d real CocoScrapers settings from %s'
          % (len(values), settings_file.name if settings_file.is_file() else 'nowhere'))

    class RealAddon:
        def __init__(self, *a, **k):
            pass

        def getAddonInfo(self, key):
            return {'path': str(COCO), 'profile': str(settings_file.parent)}.get(key, '')

        def getSetting(self, key):
            return values.get(key, '0')

        def getSettingString(self, key):
            return values.get(key, '')

        def getSettingBool(self, key):
            return values.get(key, '') == 'true'

        def getSettingInt(self, key):
            try:
                return int(values.get(key, '0'))
            except ValueError:
                return 0

        def setSetting(self, *a):
            pass

        def openSettings(self):
            pass

        def getLocalizedString(self, _):
            return ''

    xbmcaddon.Addon = lambda *a, **k: RealAddon()


def describe(entry):
    if isinstance(entry, tuple):
        return str(entry[0])
    return getattr(entry, '__name__', str(entry))


def probe_one(provider, data):
    """CocoScrapers providers take the data dict straight into sources().

    Unlike the Scrubs-style providers there is no movie()/tvshow() step that
    builds a url first.
    """
    return len(provider.sources(data, []) or [])


if __name__ == '__main__':
    main()
