# -*- coding: utf-8 -*-
"""Free sources from Stremio-protocol addons.

Every other scraper in this add-on needs something paid: Easynews needs a
subscription, the cloud scrapers need a debrid account, and CocoScrapers ships
nothing but torrent providers, which need a debrid account to become playable.
This one needs nothing.

The Stremio addon protocol is a single unauthenticated GET:

    GET <host>/stream/movie/tt0133093.json
    GET <host>/stream/series/tt0944947:1:1.json

and a response of {"streams": [...]}. Two shapes come back. A stream carrying
"infoHash" is a torrent, which is Torrentio's whole output and is useless
without debrid, so those are dropped here. A stream carrying "url" is a plain
HTTP or HLS link that Kodi can play directly, which is the point of this
scraper.

Behaviour worth knowing:
  * Some hosts refuse a default urllib/curl agent but answer a Stremio one, so
    a failed request here does not mean the host is down.
  * Hosts are queried in parallel and one slow or dead host must not hold up
    the rest, hence the per-host timeout and the blanket except.
  * BestCine bans an IP after roughly fifty requests in a burst, so results are
    cached and hosts are never retried within one scrape.
"""
import json
from threading import Thread

from caches.main_cache import cache_object
from modules import source_utils
from modules.kodi_utils import logger
from modules.settings import filter_by_name, get_setting
from modules.utils import clean_file_name, normalize

TIMEOUT = 12
USER_AGENT = 'Stremio/5.0'

# Verified to return streams with a playable "url" rather than an infoHash.
# Kept as a setting so a dead host can be dropped without shipping a new build.
DEFAULT_HOSTS = (
    'https://froststream.cloutteam.com',
    'https://stremio.alirostami.com/streams',
    'https://bestcine.dpdns.org',
    'https://fenixflix.fenixhub.online',
    'https://rajstreamaddon.onrender.com',
)

# These hosts answer with a landing page or a captcha instead of media, so a
# link pointing at one is a dead end no matter what the addon claimed.
BAD_HOSTS = ('pixel.hubcloud.ist', 'pixeldrain.dev')


def hosts():
    configured = get_setting('grnshows.stremio.hosts', '')
    if configured in ('', 'empty_setting'):
        return list(DEFAULT_HOSTS)
    return [i.strip().rstrip('/') for i in configured.split(',') if i.strip()]


class source:
    def __init__(self):
        self.scrape_provider = 'stremio'
        self.sources = []

    def results(self, info):
        try:
            self.scrape_results = []
            filter_title = filter_by_name(self.scrape_provider)
            title = info.get('title')
            self.media_type = info.get('media_type')
            self.year = int(info.get('year') or 0)
            self.season, self.episode = info.get('season'), info.get('episode')
            imdb_id = info.get('imdb_id') or info.get('imdb')
            if not imdb_id:
                # the protocol is keyed on IMDb ids; without one there is
                # nothing to ask for
                return source_utils.internal_results(self.scrape_provider, self.sources)
            path = self._path(imdb_id)
            threads = [Thread(target=self._scrape_host, args=(host, path)) for host in hosts()]
            [i.start() for i in threads]
            [i.join() for i in threads]
            if not self.scrape_results:
                return source_utils.internal_results(self.scrape_provider, self.sources)
            aliases = source_utils.get_aliases_titles(info.get('aliases', []))

            def _process():
                seen = set()
                for host_name, stream in self.scrape_results:
                    try:
                        url = stream.get('url')
                        if not url or url in seen:
                            continue
                        if any(bad in url for bad in BAD_HOSTS):
                            continue
                        seen.add(url)
                        file_name = self._release_name(stream)
                        if filter_title and not source_utils.check_title(
                                title, file_name, aliases, self.year, self.season, self.episode):
                            continue
                        display_name = clean_file_name(file_name).replace('+', ' ')
                        video_quality, details = source_utils.get_file_info(
                            name_info=source_utils.release_info_format(file_name))
                        size = self._size(stream)
                        yield {
                            'name': file_name, 'display_name': display_name,
                            'quality': video_quality, 'size': size,
                            'size_label': '%.2f GB' % size if size else 'NA',
                            'extraInfo': details, 'url_dl': url, 'id': url,
                            'direct': True, 'source': host_name,
                            'debrid': self.scrape_provider,
                            'scrape_provider': self.scrape_provider,
                            # tells resolve_internal to play url_dl as-is
                            # instead of sending it to a debrid unrestrict
                            'direct_debrid_link': True,
                        }
                    except Exception:
                        pass
            self.sources = list(_process())
        except Exception as exc:
            logger('stremio scraper Exception', str(exc))
        source_utils.internal_results(self.scrape_provider, self.sources)
        return self.sources

    def _path(self, imdb_id):
        if self.media_type == 'episode':
            return '/stream/series/%s:%s:%s.json' % (imdb_id, self.season, self.episode)
        return '/stream/movie/%s.json' % imdb_id

    def _scrape_host(self, host, path):
        try:
            # json=False because _fetch already decodes; 4 hour expiry keeps a
            # rate-limiting host like BestCine from being hammered on every
            # re-open of the same title
            streams = cache_object(self._fetch, 'stremio_%s%s' % (host, path),
                                   [host, path], False, 4)
        except Exception:
            streams = None
        if not streams:
            return
        name = host.split('//')[-1].split('/')[0]
        self.scrape_results.extend((name, stream) for stream in streams)

    @staticmethod
    def _fetch(host, path):
        import requests
        try:
            response = requests.get(host + path, timeout=TIMEOUT,
                                    headers={'User-Agent': USER_AGENT})
            if response.status_code != 200:
                return []
            # only the playable half is worth caching
            return [i for i in response.json().get('streams', []) if i.get('url')]
        except Exception:
            return []

    @staticmethod
    def _release_name(stream):
        """The best release string the addon gave us.

        Addons are inconsistent: some put the release name in title, some in
        name, some only in behaviorHints.filename. Quality detection reads this,
        so picking the longest sensible one beats picking a fixed field.
        """
        hints = stream.get('behaviorHints') or {}
        candidates = [hints.get('filename'), stream.get('title'), stream.get('name')]
        candidates = [str(i).replace('\n', ' ').strip() for i in candidates if i]
        if not candidates:
            return 'Stremio source'
        return normalize(max(candidates, key=len))

    @staticmethod
    def _size(stream):
        """Size in GB, or 0 when the addon did not say."""
        hints = stream.get('behaviorHints') or {}
        try:
            value = hints.get('videoSize')
            if value:
                return round(float(value) / 1073741824, 2)
        except (TypeError, ValueError):
            pass
        return 0
