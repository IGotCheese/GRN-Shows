"""Run our Stremio scraper against the real hosts, outside Kodi.

Inside the add-on every failure in the source chain is swallowed by a bare
`except`, so a broken scraper and a scraper that legitimately found nothing are
indistinguishable. This runs the real module with only Kodi stubbed, so a
traceback is a traceback.

    py -3 tools/probe_stremio.py --title "The Matrix" --year 1999
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / 'plugin.video.grnshows'
MODULE = ADDON / 'resources' / 'lib' / 'scrapers' / 'stremio.py'


def stub(title_filter: bool):
    """Only Kodi is faked. requests, the hosts and the parsing are all real."""
    def module(name, **members):
        stubbed = types.ModuleType(name)
        for key, value in members.items():
            setattr(stubbed, key, value)
        return stubbed

    sys.path.insert(0, str(ADDON / 'resources' / 'lib'))
    sys.modules['caches'] = module('caches')
    sys.modules['caches.main_cache'] = module(
        'caches.main_cache',
        cache_object=lambda fn, key, args, json=True, expiration=24: fn(*args))
    sys.modules['modules'] = module('modules')
    sys.modules['modules.kodi_utils'] = module(
        'modules.kodi_utils',
        logger=lambda label, message='': print('  [%s] %s' % (label, message)))
    sys.modules['modules.settings'] = module(
        'modules.settings',
        filter_by_name=lambda _: title_filter,
        get_setting=lambda key, fallback='': fallback)
    sys.modules['modules.utils'] = module(
        'modules.utils',
        clean_file_name=lambda value: value,
        normalize=lambda value: value)
    # the real source_utils needs Kodi; these are the only four calls used
    sys.modules['modules.source_utils'] = module(
        'modules.source_utils',
        internal_results=lambda provider, sources: None,
        get_aliases_titles=lambda aliases: [],
        check_title=lambda title, release, aliases, year, season, episode:
            all(word.lower() in release.lower() for word in title.split()),
        release_info_format=lambda value: value,
        get_file_info=lambda name_info=None, url=None, default_quality='SD':
            (quality_of(name_info or ''), ''))


def quality_of(name):
    lower = name.lower()
    for needle, label in (('2160', '4K'), ('4k', '4K'), ('1080', '1080p'), ('720', '720p')):
        if needle in lower:
            return label
    return 'SD'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--title', default='The Matrix')
    parser.add_argument('--year', default='1999')
    parser.add_argument('--imdb', default='tt0133093')
    parser.add_argument('--filter-titles', action='store_true',
                        help='apply the release-name filter, as the add-on does by default')
    args = parser.parse_args()

    stub(args.filter_titles)
    spec = importlib.util.spec_from_file_location('grn_stremio_live', MODULE)
    stremio = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stremio)

    print('hosts: %s\n' % ', '.join(h.split('//')[-1] for h in stremio.hosts()))
    scraper = stremio.source()
    sources = scraper.results({'media_type': 'movie', 'title': args.title,
                               'year': args.year, 'imdb_id': args.imdb, 'aliases': []})
    print('raw streams collected: %d' % len(scraper.scrape_results))
    print('playable sources kept: %d\n' % len(sources))
    for item in sources[:12]:
        print('  %-7s %-26s %-9s %s' % (item['quality'], item['source'][:26],
                                        item['size_label'], item['url_dl'][:52]))


if __name__ == '__main__':
    main()
