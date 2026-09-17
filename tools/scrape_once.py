"""Scrape one title inside Kodi and report which window the add-on reached.

The whole source chain is wrapped in bare `except` blocks, so from the outside
"no providers", "import failed" and "everything filtered out" all look the same:
an empty list. This drives a real scrape and watches the window, so the failure
mode can at least be located.

    py -3 tools/scrape_once.py "the matrix"
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kodi  # noqa: E402

PLUGIN = 'plugin://plugin.video.grnshows/'


def window_xml():
    result = kodi.call('XBMC.GetInfoLabels', {'labels': ['Window.Property(xmlfile)']})
    path = (result.get('result', {}) or {}).get('Window.Property(xmlfile)') or ''
    return os.path.basename(path.replace('\\', os.sep))


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else 'the matrix'
    search = PLUGIN + '?mode=build_movie_list&action=tmdb_movies_search&query=' + query.replace(' ', '+')
    items, error = kodi.listing(search)
    if error or not items:
        print('search failed:', error or 'no results')
        return
    target = items[0]
    print('scraping: %s' % target.get('label'))
    print('route:    %s' % target.get('file', '')[:100])
    kodi.call('GUI.ActivateWindow', {'window': 'videos', 'parameters': [target['file']]})
    seen = None
    for tick in range(1, 21):
        time.sleep(3)
        xml = window_xml()
        if xml != seen:
            print('  t+%02ds  %s' % (tick * 3, xml or '(none)'))
            seen = xml
        if xml == 'sources_results.xml':
            print('  -> results window opened')
            return
    print('  -> never reached sources_results.xml')


if __name__ == '__main__':
    main()
