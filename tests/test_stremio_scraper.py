"""The Stremio scraper, exercised without Kodi.

This is the only source in the add-on that works with no account of any kind,
so the parts that decide what is playable are worth pinning down: dropping
torrent-only streams, dropping hosts that serve a landing page instead of
media, and marking results so playback uses the URL directly rather than
handing it to a debrid unrestrict.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'plugin.video.grnshows' / 'resources' / 'lib' / 'scrapers' / 'stremio.py'


def load():
    """Import the scraper with its Kodi-side dependencies stubbed."""
    def module(name, **members):
        stub = types.ModuleType(name)
        for key, value in members.items():
            setattr(stub, key, value)
        return stub

    recorded = {}
    sys.modules['caches'] = module('caches')
    sys.modules['caches.main_cache'] = module(
        'caches.main_cache',
        cache_object=lambda fn, key, args, json=True, expiration=24: fn(*args))
    sys.modules['modules'] = module('modules')
    sys.modules['modules.kodi_utils'] = module(
        'modules.kodi_utils', logger=lambda *a, **k: None)
    sys.modules['modules.settings'] = module(
        'modules.settings',
        filter_by_name=lambda _: False,
        get_setting=lambda key, fallback='': recorded.get(key, fallback))
    sys.modules['modules.utils'] = module(
        'modules.utils',
        clean_file_name=lambda value: value,
        normalize=lambda value: value)
    sys.modules['modules.source_utils'] = module(
        'modules.source_utils',
        internal_results=lambda provider, sources: None,
        get_aliases_titles=lambda aliases: [],
        check_title=lambda *a: True,
        release_info_format=lambda value: value,
        get_file_info=lambda name_info=None, url=None, default_quality='SD': ('1080p', 'HEVC'))

    spec = importlib.util.spec_from_file_location('grn_stremio', MODULE)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded, recorded


stremio, SETTINGS = load()


class PathTests(unittest.TestCase):
    def test_movie_path(self):
        scraper = stremio.source()
        scraper.media_type = 'movie'
        self.assertEqual(scraper._path('tt0133093'), '/stream/movie/tt0133093.json')

    def test_episode_path(self):
        """Series use imdb:season:episode, not separate query parameters."""
        scraper = stremio.source()
        scraper.media_type, scraper.season, scraper.episode = 'episode', 1, 1
        self.assertEqual(scraper._path('tt0944947'), '/stream/series/tt0944947:1:1.json')


class FilteringTests(unittest.TestCase):
    def build(self, streams):
        """Run results() with the network replaced, not the filtering.

        results() clears scrape_results itself, so the streams have to arrive
        the way real ones do: appended by _scrape_host. Everything downstream
        of that, which is the part worth testing, runs untouched.
        """
        info = {'title': 'The Matrix', 'year': '1999', 'media_type': 'movie',
                'imdb_id': 'tt0133093', 'aliases': []}
        original = stremio.source._scrape_host

        def fake_scrape(self, host, path):
            self.scrape_results.extend(('testhost', stream) for stream in streams)

        stremio.source._scrape_host = fake_scrape
        try:
            scraper = stremio.source()
            scraper.results(info)
        finally:
            stremio.source._scrape_host = original
        return scraper.sources

    def test_torrent_only_streams_are_dropped(self):
        """A stream with infoHash and no url is a magnet. Torrentio returns
        nothing but these, and they cannot play without a debrid account."""
        sources = self.build([{'name': 'Torrentio 4K', 'infoHash': 'a' * 40}])
        self.assertEqual(sources, [])

    def test_direct_url_streams_are_kept(self):
        sources = self.build([{'name': 'FrostStream 1080p',
                               'url': 'http://example.test/film.mp4'}])
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]['url_dl'], 'http://example.test/film.mp4')

    def test_playback_bypasses_debrid(self):
        """resolve_internal() plays url_dl as-is only when this flag is set;
        without it the URL is sent to a debrid unrestrict and fails."""
        sources = self.build([{'name': 'x', 'url': 'http://example.test/a.mp4'}])
        self.assertTrue(sources[0]['direct_debrid_link'])
        self.assertTrue(sources[0]['direct'])
        self.assertEqual(sources[0]['scrape_provider'], 'stremio')

    def test_known_dead_hosts_are_dropped(self):
        """pixel.hubcloud.ist serves an HTML landing page and pixeldrain.dev
        answers hotlinks with a captcha, so both are dead ends."""
        sources = self.build([
            {'name': 'a', 'url': 'https://pixel.hubcloud.ist/?id=1'},
            {'name': 'b', 'url': 'https://pixeldrain.dev/api/file/xyz'},
            {'name': 'c', 'url': 'https://good.test/film.mkv'}])
        self.assertEqual([i['url_dl'] for i in sources], ['https://good.test/film.mkv'])

    def test_duplicate_urls_collapse(self):
        """Several addons front the same CDN, so the same file arrives twice."""
        sources = self.build([{'name': 'a', 'url': 'http://same.test/f.mp4'},
                              {'name': 'b', 'url': 'http://same.test/f.mp4'}])
        self.assertEqual(len(sources), 1)


class ReleaseNameTests(unittest.TestCase):
    def test_prefers_the_most_descriptive_field(self):
        """Quality detection parses this string, and addons scatter the release
        name across three different fields."""
        name = stremio.source._release_name({
            'name': 'HD', 'title': 'The Matrix 1999 2160p BluRay REMUX HEVC',
            'behaviorHints': {'filename': 'matrix.mkv'}})
        self.assertEqual(name, 'The Matrix 1999 2160p BluRay REMUX HEVC')

    def test_newlines_are_flattened(self):
        """Titles routinely carry emoji and line breaks for display."""
        name = stremio.source._release_name({'title': 'Matrix\n1080p\nPortuguese'})
        self.assertNotIn('\n', name)

    def test_falls_back_when_nothing_is_named(self):
        self.assertEqual(stremio.source._release_name({}), 'Stremio source')


class SizeTests(unittest.TestCase):
    def test_bytes_become_gigabytes(self):
        self.assertEqual(stremio.source._size({'behaviorHints': {'videoSize': 3291291606}}), 3.07)

    def test_missing_size_is_zero_not_a_crash(self):
        self.assertEqual(stremio.source._size({}), 0)
        self.assertEqual(stremio.source._size({'behaviorHints': {'videoSize': 'unknown'}}), 0)


class HostTests(unittest.TestCase):
    def tearDown(self):
        SETTINGS.clear()

    def test_defaults_are_used_when_unset(self):
        self.assertEqual(stremio.hosts(), list(stremio.DEFAULT_HOSTS))
        SETTINGS['grnshows.stremio.hosts'] = 'empty_setting'
        self.assertEqual(stremio.hosts(), list(stremio.DEFAULT_HOSTS))

    def test_user_hosts_override_and_are_tidied(self):
        SETTINGS['grnshows.stremio.hosts'] = ' https://a.test/ , https://b.test '
        self.assertEqual(stremio.hosts(), ['https://a.test', 'https://b.test'])

    def test_every_default_host_is_https(self):
        for host in stremio.DEFAULT_HOSTS:
            self.assertTrue(host.startswith('https://'), host)


if __name__ == '__main__':
    unittest.main()
