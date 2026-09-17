# GRN Shows for Kodi

GRN Shows is an original Kodi 19+ movie and TV add-on modeled on the fast workflow of Fen Light AM: compact menus, TMDb catalogs, full season/episode navigation, source aggregation, Real-Debrid resolution/cloud access, Trakt lists and watched-state updates, and a background token-refresh service.

GRN Shows is our own Kodi add-on. Fen Light AM provides design and feature inspiration. Linux hosts the installation and update repository; Kodi runs the add-on on each client. See [Linux hosting instructions](LINUX.md).

## Features

- Movies and TV from TMDb: trending, popular, top-rated, in cinemas, upcoming, and airing
- Search, show seasons, and episodes with Kodi metadata and artwork
- Five debrid services: Real-Debrid, Premiumize, AllDebrid, TorBox, and Offcloud. Each one
  contributes its cloud to source results and can resolve magnets and restricted links
- Device authorization for Real-Debrid and Premiumize, PIN authorization for AllDebrid, and
  API keys for TorBox and Offcloud, all from the My Services menu
- Trakt device OAuth, automatic token refresh, watchlists, collections, history, and watched updates
- Source aggregation and quality sorting from:
  - personal JSON mappings
  - the clouds of every debrid account you connect
  - exact-title public-domain films in Internet Archive's Feature Films collection
  - an optional external scraper module you install yourself, using the same interface
    CocoScrapers and Magneto expose
  - optional user-installed folder providers using a small documented interface
- Maximum-resolution and maximum-file-size source filters
- TMDb and Trakt credentials baked in at package time, so users are not asked for API keys
- Installable add-on ZIP, repository ZIP, `addons.xml`, checksum, and browser index

## Build and install

On Linux, use Python 3.8+ from the project directory:

```sh
cp keys.example.json keys.json   # fill in TMDb and Trakt values, or skip for a keyless build
python3 build.py --base-url http://YOUR_LINUX_SERVER:8080
python3 serve.py --bind 0.0.0.0 --port 8080
```

Replace `YOUR_LINUX_SERVER` with the address reachable from Kodi. For persistent
hosting, serve `dist/` with your Linux web server; an Nginx template is included.
Windows can use the same scripts with `py -3` instead of `python3`.

```powershell
./build.ps1 -BaseUrl http://127.0.0.1:8080
```

Install `dist/zips/plugin.video.grnshows/plugin.video.grnshows-1.0.0.zip` directly, or run `./serve.ps1` and add `http://127.0.0.1:8080` in Kodi File Manager. Then install `repository.grnshows-1.0.0.zip` from that source.

For Kodi on another device, build with this computer's LAN IP instead of `127.0.0.1`, keep the server running, and allow the selected port through the firewall. For a permanent HTTPS source, upload the contents of `dist/` to static hosting and rebuild with that public base URL.

The included GitHub Pages workflow does this automatically after the project is pushed to a repository whose default branch is `main`. Enable **Settings → Pages → Source: GitHub Actions**; the Kodi source will be `https://<owner>.github.io/<repository-name>`.

## Accounts

### TMDb and Trakt

Both are supplied by the build. `build.py` reads `keys.json` (copy `keys.example.json`) or the
`GRNSHOWS_TMDB_API_KEY`, `GRNSHOWS_TRAKT_CLIENT_ID` and `GRNSHOWS_TRAKT_CLIENT_SECRET`
environment variables, and writes them into `resources/lib/grnshows/keys.py` **inside the ZIP
only**. The copy in the source tree stays blank and `keys.json` is git-ignored.

The build prints a warning naming any credential it could not find. A build without them still
works, it just falls back to whatever the user types under Settings. Those settings fields remain
either way, so a user can point the add-on at their own TMDb key or Trakt application if ours is
ever rate limited. A Trakt application needs its redirect URI set to `urn:ietf:wg:oauth:2.0:oob`.

### Debrid services

Choose **My Services** and pick a service. Real-Debrid and Premiumize show a code to enter on
their website, AllDebrid shows a PIN, and TorBox and Offcloud ask for the API key from your
account page. Each authorized service gets a toggle controlling whether it contributes sources,
and **Settings, Sources, Preferred debrid service** decides which account receives magnets.

Real-Debrid's published open-source client ID only starts the device flow; the credentials the
add-on stores and refreshes are the device-bound pair Real-Debrid issues back.

## Sources

`examples/streams.example.json` demonstrates personal mappings. Keys are `movie:<TMDb ID>` or
`episode:<TMDb episode ID>`, and values can be one URL or a list. HTTP(S), SMB, NFS, and
authorized magnet URLs are supported; magnets require a debrid account.

### External scraper modules

Set **Settings, Sources, Scraper module add-on ID** to the ID of a scraper module you have
installed yourself, for example `script.module.cocoscrapers`. GRN Shows adds that add-on's `lib`
directory to `sys.path` and supports both layouts in use:

- package layout: `<name>.sources_<name>.total_providers['torrents']` lists providers, each
  `<name>.sources_<name>.torrents.<provider>` exposes a `source` class with
  `sources(data, host_dict)`
- flat layout: a top-level `sources(specified_folders=['torrents'], ret_all=...)` returning
  `(name, module)` pairs

Providers run in parallel under a configurable timeout, one crashing provider cannot stop the
others, and by default only the module's own default providers run. GRN Shows ships no scraper
module and does not install one for you.

### Folder providers

For custom integrations, copy `examples/external_provider.py` to a dedicated folder and select
that folder under **Settings, Sources**. Each `.py` file must expose `search(media)` and return
dictionaries containing at least `name` and `url`; optional keys include `quality`, `size`,
`provider`, and `needs_unrestrict`. Provider code executes inside Kodi, so only install code you
trust.

## Tests

```powershell
py -3 -m unittest discover -s tests -v
py -3 -m compileall -q plugin.video.grnshows
```

The offline suite covers routing, atomic settings storage, stream-map validation, media
normalization, source quality and size filtering, title and episode matching, the authorization
flow of every debrid service, the external scraper bridge, key baking, and the repository
contract. `tests/test_addon.py` imports the Kodi-facing modules against stub `xbmc` bindings, so
menu building and action dispatch are exercised without Kodi. Live OAuth and playback require
Kodi plus user-owned accounts and are not exercised by offline tests.

## Research basis

The architecture was derived from behavioral inspection of public Fen Light/Fen Light AM successor repositories and their manifests, plus official Kodi add-on documentation, the official Real-Debrid REST/OAuth documentation, and the official Trakt device-authentication documentation. No upstream Fen source files are included.
