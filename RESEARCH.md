# Fen Light AM behavior audit

Research date: 2026-09-17.

## References inspected

- Tikipeter's current public repository: <https://github.com/Tikipeter/Tikipeter.github.io>
- Fen Light+ source tree, a maintained Fen Light derivative: <https://github.com/thejason40/FenLightPlus>
- Fen Light FL repository/source layout: <https://github.com/maccb/FL>
- Kodi plug-in source documentation: <https://kodi.wiki/view/Plugin_sources>
- Kodi add-on manifest documentation: <https://kodi.wiki/view/Addon.xml>
- Real-Debrid REST and OAuth documentation: <https://api.real-debrid.com/>
- Trakt device authentication documentation: <https://docs.trakt.tv/reference/auth>

## Findings

The audited Fen Light+ 2.5.x source contained 185 files, including 99 Python modules and 24 XML files. Its manifest registers three extension roles: video plug-in, background service, and Python module. It depends on Kodi Python 3 and `script.module.requests`.

The application is organized around a large query-string router. Separate indexers build movie, show, season, episode, next-episode, calendar, and people lists. Navigators expose TMDb discovery, search histories, favorites, downloads, Trakt collections/watchlists/recommendations, and service tools.

Playback is a pipeline rather than a direct catalog link:

1. Build normalized metadata for a movie or episode.
2. Start internal/cloud/folder and external scraper workers concurrently.
3. Normalize provider results.
4. Check debrid cache/cloud availability.
5. Filter by resolution, size, codec, HDR/Dolby Vision, audio, language, and provider.
6. Sort sources for autoplay or source selection.
7. Resolve the selected item through the appropriate debrid API.
8. Hand the final URL to Kodi and monitor playback for resume/watched synchronization.

The inspected derivative supports Real-Debrid, Premiumize, AllDebrid, Offcloud, EasyDebrid, TorBox, Easynews, local folders, and an external scraper-module contract. Trakt supplies lists, watch history, progress, calendars, recommendations, comments, and list management; a background service periodically refreshes state.

## GRN Shows scope mapping

GRN Shows implements the same core product shape with original code: Kodi routing and service extensions, TMDb lists and episodic hierarchy, pluggable source aggregation, quality ordering, Real-Debrid device OAuth/cloud/unrestrict/magnet resolution, Trakt device OAuth/watchlists/collections/history/watched updates, and repository packaging.

The first release deliberately omits unlicensed scraper packages and additional premium services. It includes personal sources, the user's own Real-Debrid cloud, a narrowly scoped Internet Archive public-domain provider, and a documented external-provider interface.

## Licensing decision

The Fen Light+ tree inspected during the audit contains no `LICENSE`, `COPYING`, or `NOTICE` file and its `addon.xml` does not declare a license. Therefore it was treated as behavioral reference only; none of its source files are redistributed in GRN Shows.
