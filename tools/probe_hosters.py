"""Measure which free hoster scrapers still return anything.

FenLightAM has no free sources at all: its only scrapers are Easynews, the four
debrid clouds, your own folders, and cocoscrapers, which ships nothing but
torrents and therefore needs a debrid account to be playable. Scrubs v2 works
without debrid because it carries ~60 scrapers that read streaming sites and
hand the links to ResolveURL.

Porting that layer is only worth doing if the providers still work, and most
scrapers of this kind rot as the sites they target die or move behind
Cloudflare. This runs them outside Kodi against a real title and reports, per
provider, whether it returned links, returned nothing, or raised.

    py -3 tools/probe_hosters.py --title "The Matrix" --year 1999

Kodi's own modules are stubbed, because the providers only touch them for
settings and logging.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ADDONS = Path(os.environ['LOCALAPPDATA']) / \
    'Packages/XBMCFoundation.Kodi_4n2hpmxwrvr6p/LocalCache/Roaming/Kodi/addons'
SCRUBS = ADDONS / 'plugin.video.scrubsv2'


class _Any:
    """Accepts any construction and any method call, returning another _Any."""

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, _):
        return _Any()

    def __call__(self, *a, **k):
        return _Any()

    def __bool__(self):
        return False

    def __str__(self):
        return ''


# kodi_six re-exports with `from xbmcplugin import *`, so its namespace ends up
# holding exactly what __all__ lists. A module-level __getattr__ does not help
# there: anything missing from __all__ is missing from kodi_six.xbmcplugin too.
# So every name a caller might touch has to be named up front.
EXTRA_NAMES = {
    'xbmc': ('getSupportedMedia getRegion getGlobalIdleTime getCleanMovieTitle getCacheThumbName '
             'getDVDState getFreeMem getInfoImage getIPAddress getUserAgent makeLegalFilename '
             'validatePath startServer audioSuspend audioResume convertLanguage restart shutdown '
             'stopSFX playSFX enableNavSounds skinHasImage LOGCRITICAL LOGSEVERE TRADITIONAL_FORMAT '
             'ISO_FORMAT LONG_FORMAT SERVER_WEBSERVER PLAYLIST_MUSIC PLAYLIST_VIDEO').split(),
    'xbmcplugin': ('setProperty getSetting setSetting setPluginFanart setSortMethod '
                   'SORT_METHOD_LABEL SORT_METHOD_TITLE SORT_METHOD_DATE SORT_METHOD_SIZE '
                   'SORT_METHOD_FILE SORT_METHOD_GENRE SORT_METHOD_VIDEO_YEAR '
                   'SORT_METHOD_VIDEO_RATING SORT_METHOD_DATEADDED SORT_METHOD_EPISODE '
                   'SORT_METHOD_DURATION SORT_METHOD_PLAYCOUNT SORT_METHOD_LABEL_IGNORE_THE '
                   'SORT_METHOD_TITLE_IGNORE_THE SORT_METHOD_PROGRAM_COUNT').split(),
    'xbmcgui': ('DialogBusy ControlButton ControlList ControlGroup ControlTextBox ControlEdit '
                'ControlFadeLabel ControlProgress ControlSlider ControlRadioButton ControlSpin '
                'Action getCurrentWindowDialogId NOTIFICATION_INFO NOTIFICATION_WARNING '
                'NOTIFICATION_ERROR INPUT_NUMERIC INPUT_DATE INPUT_TIME INPUT_IPADDRESS '
                'INPUT_PASSWORD ALPHANUM_DEFAULT PASSWORD_VERIFY').split(),
    'xbmcvfs': ('mkdir rename rmdir validatePath makeLegalFilename Stat deleteFile copyFile'.split()),
    'xbmcaddon': [],
}


def _module(name, **members):
    """A stub module whose __all__ covers everything callers reach for."""
    module = types.ModuleType(name)
    for key in EXTRA_NAMES.get(name, ()):
        members.setdefault(key, _Any())
    for key, value in members.items():
        setattr(module, key, value)
    module.__all__ = list(members)
    return module


def stub_kodi():
    """Just enough xbmc* for the scraper and resolver modules to import."""
    xbmc = _module(
        'xbmc',
        log=lambda *a, **k: None,
        LOGINFO=0, LOGERROR=0, LOGDEBUG=0, LOGWARNING=0, LOGFATAL=0, LOGNONE=0,
        translatePath=str,
        # Scrubs does int(getInfoLabel('System.BuildVersion').split('.')[0])
        # at import time, so an empty string kills every provider
        getInfoLabel=lambda label: '21.2 (21.2.0)' if 'BuildVersion' in label else '',
        getCondVisibility=lambda _: False,
        getLocalizedString=lambda _: '',
        getSkinDir=lambda: 'skin.estuary',
        getLanguage=lambda *a, **k: 'English',
        getSupportedMedia=lambda _: '.mp4|.mkv|.avi|.mov|.m4v|.ts|.m3u8|.webm|.flv|.wmv|.mpg',
        getRegion=lambda _: '',
        getGlobalIdleTime=lambda: 0,
        executebuiltin=lambda *a, **k: None,
        # ResolveURL asks Kodi at import time whether debug logging is on
        executeJSONRPC=lambda command: '{"result":{"value":false}}',
        sleep=lambda ms: time.sleep(ms / 1000.0),
        Monitor=_Any, Player=_Any, Keyboard=_Any, PlayList=_Any, InfoTagVideo=_Any,
    )

    class Addon:
        def __init__(self, *a, **k):
            pass

        def getAddonInfo(self, key):
            return {'path': str(SCRUBS), 'profile': str(SCRUBS),
                    'id': 'plugin.video.scrubsv2', 'version': '1.0'}.get(key, '')

        def getSetting(self, _):
            # '0' not '': the providers feed several settings straight to
            # int(), and an empty string is a ValueError before any scraping
            # happens. '0' reads as both "zero" and "not true".
            return '0'

        def getSettingString(self, _):
            return ''

        def getSettingBool(self, _):
            return False

        def getSettingInt(self, _):
            return 0

        def setSetting(self, *a):
            pass

        def openSettings(self):
            pass

        def getLocalizedString(self, _):
            return ''

    xbmcaddon = _module('xbmcaddon', Addon=Addon)
    xbmcgui = _module('xbmcgui', Dialog=_Any, DialogProgress=_Any, DialogProgressBG=_Any,
                      ListItem=_Any, Window=_Any, WindowDialog=_Any, WindowXML=_Any,
                      WindowXMLDialog=_Any, ControlLabel=_Any, ControlImage=_Any,
                      INPUT_ALPHANUM=0, ALPHANUM_HIDE_INPUT=0, getCurrentWindowId=lambda: 0)
    xbmcvfs = _module('xbmcvfs', translatePath=str, exists=os.path.exists,
                      mkdirs=lambda p: None, listdir=lambda p: ([], []),
                      File=_Any, delete=lambda p: None, copy=lambda a, b: None)
    xbmcplugin = _module('xbmcplugin', addDirectoryItem=lambda *a, **k: None,
                         addDirectoryItems=lambda *a, **k: None,
                         endOfDirectory=lambda *a, **k: None,
                         setContent=lambda *a, **k: None,
                         setPluginCategory=lambda *a, **k: None,
                         addSortMethod=lambda *a, **k: None,
                         setResolvedUrl=lambda *a, **k: None,
                         SORT_METHOD_NONE=0, SORT_METHOD_UNSORTED=0)

    for module in (xbmc, xbmcaddon, xbmcgui, xbmcvfs, xbmcplugin):
        sys.modules[module.__name__] = module


def prepare_path():
    for module_id in ('script.module.six', 'script.module.kodi-six',
                      'script.module.simplejson', 'script.module.requests',
                      'script.module.certifi', 'script.module.chardet',
                      'script.module.idna', 'script.module.urllib3',
                      'script.module.resolveurl'):
        for folder in ('lib', 'libs'):
            candidate = ADDONS / module_id / folder
            if candidate.is_dir():
                sys.path.insert(0, str(candidate))
                break
    # the providers import as `resources.lib.modules.x`, so the add-on root
    # itself has to be the package root
    sys.path.insert(0, str(SCRUBS))


def host_dict():
    """The flat list of resolvable domains, exactly as Scrubs builds it."""
    from functools import reduce
    import resolveurl
    # include_disabled, because with settings stubbed out every resolver reads
    # as switched off and the list comes back empty
    resolvers = resolveurl.relevant_resolvers(order_matters=True, include_disabled=True,
                                              include_universal=True)
    domains = [i.domains for i in resolvers if '*' not in i.domains]
    domains = [i.lower() for i in reduce(lambda x, y: x + y, domains, [])]
    return [x for y, x in enumerate(domains) if x not in domains[:y]]


def probe(name, title, year, imdb, hosts):
    import importlib
    module = importlib.import_module('resources.lib.sources.working.%s' % name)
    provider = module.source()
    url = provider.movie(imdb, '', title, title, [], str(year))
    if not url:
        return name, 'no url', 0
    sources = provider.sources(url, hosts) or []
    return name, 'ok' if sources else 'empty', len(sources)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--title', default='The Matrix')
    parser.add_argument('--year', default='1999')
    parser.add_argument('--imdb', default='tt0133093')
    parser.add_argument('--timeout', type=int, default=45)
    parser.add_argument('--workers', type=int, default=12)
    args = parser.parse_args()

    stub_kodi()
    prepare_path()

    folder = SCRUBS / 'resources' / 'lib' / 'sources' / 'working'
    names = sorted(p.stem for p in folder.glob('*.py')
                   if p.stem not in ('__init__', 'library'))
    hosts = host_dict()
    print('probing %d providers with "%s (%s)"; %d resolvable domains\n'
          % (len(names), args.title, args.year, len(hosts)))

    working, empty, broken = [], [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(probe, n, args.title, args.year, args.imdb, hosts): n
                   for n in names}
        for future in as_completed(futures, timeout=args.timeout * 4):
            name = futures[future]
            try:
                name, status, count = future.result()
            except Exception as exc:
                broken.append((name, type(exc).__name__ + ': ' + str(exc)[:60]))
                continue
            (working if status == 'ok' else empty).append((name, count))

    print('WORKING  %d' % len(working))
    for name, count in sorted(working, key=lambda x: -x[1]):
        print('   %-26s %d links' % (name, count))
    print('\nEMPTY    %d  (imported and ran, found nothing)' % len(empty))
    print('   ' + ', '.join(n for n, _ in sorted(empty)))
    print('\nBROKEN   %d' % len(broken))
    for name, reason in sorted(broken):
        print('   %-26s %s' % (name, reason))


if __name__ == '__main__':
    main()
