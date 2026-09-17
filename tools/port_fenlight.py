"""Port the whole FenLightAM add-on into plugin.video.grnshows.

Not a skin port and not a reimplementation. FenLightAM is 91 Python modules
arranged as apis / caches / indexers / modules / scrapers / windows, and every
attempt to approximate that from screenshots produced something that behaved
differently. This copies the tree and renames it.

What the rename has to cover, because a miss is a runtime failure, not a
cosmetic one:

  * the add-on id appears in ListItem property names and in the
    plugin://plugin.video.fenlight/ URLs that custom_keys.py parses back out of
    those properties, so a half-rename silently breaks every context action
  * settings live in a SQLite database keyed by ids with a 'fenlight.' prefix
    that SettingsCache.get() strips, so the prefix has to move together with
    the id strings
  * skin media lives in directories named fenlight_common, fenlight_buttons,
    fenlight_diffuse and fenlight_flags, referenced by path from the window XML
  * resources/lib is on sys.path as the add-on's python module root, so the
    package names (modules, caches, ...) stay as they are and only the entry
    point file is renamed

Run it again whenever the upstream copy changes; it is idempotent and rebuilds
the destination tree from scratch.
"""
from __future__ import annotations

import argparse
import compileall
import io
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / 'plugin.video.grnshows'

TEXT_SUFFIXES = {'.py', '.xml', '.txt', '.md', '.json'}

# Longest first, and the special cases before the general ones.
#
# 'FenlightAnonyMouse' contains both 'Fenlight' and 'AnonyMouse', so without an
# explicit entry it comes out as a mangled 'GRNShowsGRN'.
#
# The two class names matter more: the display name becomes 'GRN Shows' with a
# space, and blindly applying that to FenLightPlayer produces
# 'class GRN ShowsPlayer', a syntax error in seven modules. Identifiers get the
# closed-up form.
SUBSTITUTIONS = (
    ('FenlightAnonyMouse.github.io', '{repo_location}'),
    ('FenlightAnonyMouse', '{repo_username}'),
    ('FenLightPlayer', 'GRNShowsPlayer'),
    ('FenLightMonitor', 'GRNShowsMonitor'),
    ('FenLightAM', 'GRN Shows'),
    ('Fen Light', 'GRN Shows'),
    ('FenLight', 'GRN Shows'),
    ('Fenlight', 'GRN Shows'),
    ('FENLIGHT', 'GRNSHOWS'),
    ('fenlight', 'grnshows'),
    ('AnonyMouse', 'GRN'),
)

# Anything still matching this after the pass is a missed rename.
RESIDUE = re.compile(r'fen[ _-]?light|anonymouse', re.IGNORECASE)

# Where our own TMDb and Trakt credentials go.
#
# Upstream 2.2.03 shipped the author's own keys as these defaults. 2.2.04
# replaced them with the sentinel 'empty_setting', which the add-on reads as
# "not configured" and the settings window compares against to decide whether
# to offer a clear/reset row. Swapping the sentinel for a token in both places
# keeps that behaviour intact while letting build.py fill in our keys, so the
# working tree still never holds one.
CREDENTIAL_SETTINGS = {
    'tmdb_api': '@@TMDB_API_KEY@@',
    'trakt.client': '@@TRAKT_CLIENT_ID@@',
    'trakt.secret': '@@TRAKT_CLIENT_SECRET@@',
}
SENTINEL = 'empty_setting'

# Upstream bugs worth not reproducing. Each is (file suffix, before, after) and
# every one has to apply, so a rewritten upstream is a loud failure rather than
# a silent regression.
#   flag_sd: the unknown-quality fallback omits the 'flags' folder that all the
#   other flag lookups pass, so it resolves to icons/flag_sd.png, which does
#   not exist and renders blank.
UPSTREAM_FIXES = (
    ('windows/sources.py', "except: return 'sd', get_icon('flag_sd')",
     "except: return 'sd', get_icon('flag_sd', 'flags')"),
    # Real-Debrid and Premiumize authorisation refuses to even start unless the
    # user first pastes an OAuth client id, so out of the box both report
    # "Please set a valid ... Client ID" and no source ever plays. These are the
    # public client identifiers both services publish for open-source device
    # -code clients: they name the application, they are not secrets, and every
    # user still authorises their own account against them. Both verified live
    # to return a device code.
    ('caches/settings_cache.py',
     "{'setting_id': 'rd.client_id', 'setting_type': 'string', 'setting_default': 'empty_setting'}",
     "{'setting_id': 'rd.client_id', 'setting_type': 'string', 'setting_default': 'X245A4XAIBGVM'}"),
    ('caches/settings_cache.py',
     "{'setting_id': 'pm.client_id', 'setting_type': 'string', 'setting_default': 'empty_setting'}",
     "{'setting_id': 'pm.client_id', 'setting_type': 'string', 'setting_default': '888228107'}"),
    # Upstream ships every source switched off and no scraper module chosen, so
    # a fresh install finds nothing at all until you go and configure it. For a
    # public build the sane out-of-box state is "works as soon as you connect an
    # account". The four cloud providers are safe to switch on because
    # active_internal_scrapers() only reaches them when that debrid is both
    # authorised and enabled. Easynews and folders stay off: they need
    # credentials and a path that only the user has.
    ('caches/settings_cache.py',
     "{'setting_id': 'provider.external', 'setting_type': 'boolean', 'setting_default': 'false'}",
     "{'setting_id': 'provider.external', 'setting_type': 'boolean', 'setting_default': 'true'}"),
    ('caches/settings_cache.py',
     "{'setting_id': 'provider.rd_cloud', 'setting_type': 'boolean', 'setting_default': 'false'}",
     "{'setting_id': 'provider.rd_cloud', 'setting_type': 'boolean', 'setting_default': 'true'}"),
    ('caches/settings_cache.py',
     "{'setting_id': 'provider.pm_cloud', 'setting_type': 'boolean', 'setting_default': 'false'}",
     "{'setting_id': 'provider.pm_cloud', 'setting_type': 'boolean', 'setting_default': 'true'}"),
    ('caches/settings_cache.py',
     "{'setting_id': 'provider.ad_cloud', 'setting_type': 'boolean', 'setting_default': 'false'}",
     "{'setting_id': 'provider.ad_cloud', 'setting_type': 'boolean', 'setting_default': 'true'}"),
    ('caches/settings_cache.py',
     "{'setting_id': 'provider.tb_cloud', 'setting_type': 'boolean', 'setting_default': 'false'}",
     "{'setting_id': 'provider.tb_cloud', 'setting_type': 'boolean', 'setting_default': 'true'}"),
    ('caches/settings_cache.py',
     "{'setting_id': 'external_scraper.module', 'setting_type': 'string', 'setting_default': 'empty_setting'}",
     "{'setting_id': 'external_scraper.module', 'setting_type': 'string', 'setting_default': 'script.module.cocoscrapers'}"),
    # Refreshing a Trakt token is guarded on the client id and secret being
    # present, but not on there actually being a token to refresh. Upstream
    # shipped no keys, so the client-id guard caught this; now that we bake
    # our own application in, every user who has not connected Trakt POSTs
    # grant_type=refresh_token with refresh_token='0' and logs a 400 on
    # startup and on every authorised call.
    # Real-Debrid removed /torrents/instantAvailability in November 2024, so the
    # only way left to know whether a torrent plays instantly is to ask
    # Torrentio (with the user's debrid token) and DebridMediaManager (hashes
    # only). Upstream ships that check off, which is why every result reads
    # HOSTER: UNCHECKED and picking one is a coin flip between instant playback
    # and waiting for a download. Users who would rather not hand their token to
    # a third party can switch it back off in Settings -> Results.
    ('caches/settings_cache.py',
     "{'setting_id': 'external.cache_check', 'setting_type': 'boolean', 'setting_default': 'false'}",
     "{'setting_id': 'external.cache_check', 'setting_type': 'boolean', 'setting_default': 'true'}"),
    # The Stremio scraper is ours, not upstream's: it is the only source in
    # the add-on that needs no debrid account, no subscription and no key.
    # Shipped OFF: every free host that actually returns a playable URL serves
    # a re-encoded, watermarked copy, which is worse than no result when a
    # debrid account is present. The code stays so it can be switched back on.
    # The module itself is copied in from addon_extras/; these three edits
    # are what make the add-on actually run it.
    ('modules/sources.py',
     "active_sources = [i for i in self.active_internal_scrapers if i in ['easynews', 'rd_cloud', 'pm_cloud', 'ad_cloud', 'tb_cloud']]",
     "active_sources = [i for i in self.active_internal_scrapers if i in ['stremio', 'easynews', 'rd_cloud', 'pm_cloud', 'ad_cloud', 'tb_cloud']]"),
    ('modules/settings.py',
     "settings = ['provider.external', 'provider.easynews', 'provider.folders']",
     "settings = ['provider.external', 'provider.easynews', 'provider.folders', 'provider.stremio']"),
    ('caches/settings_cache.py',
     "{'setting_id': 'provider.easynews', 'setting_type': 'boolean', 'setting_default': 'false'},",
     "{'setting_id': 'provider.easynews', 'setting_type': 'boolean', 'setting_default': 'false'},\n{'setting_id': 'provider.stremio', 'setting_type': 'boolean', 'setting_default': 'false'},\n{'setting_id': 'stremio.hosts', 'setting_type': 'string', 'setting_default': 'empty_setting'},\n{'setting_id': 'stremio.title_filter', 'setting_type': 'boolean', 'setting_default': 'true'},"),
    ('modules/settings.py',
     "\ttb_priority = int(get_setting('grnshows.tb.priority', '10'))\n",
     "\ttb_priority = int(get_setting('grnshows.tb.priority', '10'))\n\tst_priority = int(get_setting('grnshows.stremio.priority', '9'))\n"),
    ('modules/settings.py',
     "'tb_cloud': tb_priority, 'folders': fo_priority}",
     "'tb_cloud': tb_priority, 'folders': fo_priority, 'stremio': st_priority}"),
    ('modules/sources.py',
     '\t\treturn self.provider_sort_ranks[account_type] or 11\n',
     '\t\treturn self.provider_sort_ranks.get(account_type, 11) or 11\n'),
    ('caches/settings_cache.py',
     "{'setting_id': 'stremio.hosts', 'setting_type': 'string', 'setting_default': 'empty_setting'},",
     "{'setting_id': 'stremio.hosts', 'setting_type': 'string', 'setting_default': 'empty_setting'},\n{'setting_id': 'stremio.priority', 'setting_type': 'action', 'setting_default': '9', 'min_value': '1', 'max_value': '10'},"),
    ('modules/sources.py',
     "\t\tself.default_internal_scrapers = ('easynews', 'rd_cloud', 'pm_cloud', 'ad_cloud', 'tb_cloud', 'folders')\n",
     "\t\tself.default_internal_scrapers = ('stremio', 'easynews', 'rd_cloud', 'pm_cloud', 'ad_cloud', 'tb_cloud', 'folders')\n"),
    ('caches/settings_cache.py',
     "{'setting_id': 'stremio.title_filter', 'setting_type': 'boolean', 'setting_default': 'true'},",
     "{'setting_id': 'stremio.title_filter', 'setting_type': 'boolean', 'setting_default': 'false'},"),
    # get_provider_and_path() falls back to the 'folders' label for any
    # provider missing from this table, so free Stremio sources were being
    # labelled FOLDERS, which reads like they came off local disk.
    ('windows/sources.py',
     "'pm_cloud': get_icon('premiumize'), 'tb_cloud': get_icon('torbox')}",
     "'pm_cloud': get_icon('premiumize'), 'tb_cloud': get_icon('torbox'), 'stremio': get_icon('grnshows')}"),
    ('apis/trakt_api.py',
     "\t\tif CLIENT_SECRET in (None, 'empty_setting', ''): return no_secret_key()\n\t\tkodi_utils.set_property('grnshows.trakt_refreshing_token', 'true')\n",
     "\t\tif CLIENT_SECRET in (None, 'empty_setting', ''): return no_secret_key()\n\t\tif get_setting('grnshows.trakt.refresh') in (None, 'empty_setting', '', '0'): return\n\t\tkodi_utils.set_property('grnshows.trakt_refreshing_token', 'true')\n"),
)

ADDON_XML = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="plugin.video.grnshows" name="GRN Shows" provider-name="GRN" version="{version}">
    <requires>
        <import addon="xbmc.python" version="3.0.0"/>
        <import addon="script.module.requests" version="2.19.1"/>
        <import addon="script.module.pil" version="1.1.7" optional="true"/>
        <!-- Required, not optional: the add-on points its scraper module at this
             and finds no sources without it. The GRN repository carries it so a
             fresh Kodi can resolve it without adding another repository. -->
        <import addon="script.module.cocoscrapers"/>
    </requires>
    <extension point="xbmc.python.pluginsource" library="resources/lib/grnshows.py">
        <provides>video</provides>
    </extension>
    <extension point="xbmc.service" library="resources/lib/service.py"/>
    <extension point="xbmc.python.module" library="resources/lib/"/>
    <extension point="xbmc.addon.metadata">
        <reuselanguageinvoker>true</reuselanguageinvoker>
        <summary lang="en">Browse your own media and debrid clouds on the Gamers Revolution Network.</summary>
        <description lang="en">GRN Shows indexes metadata from TMDb and Trakt and plays back content you already own or have a subscription to. It hosts no media of its own.</description>
        <platform>all</platform>
        <disclaimer lang="en">GRN Shows hosts no media and has no affiliation with any content provider. Use only sources and content you are authorized to access.</disclaimer>
        <license/>
        <assets>
            <icon>resources/media/addon_icons/grnshows_icon_01.png</icon>
            <fanart>resources/media/grnshows_fanart_01.jpg</fanart>
        </assets>
        <news>See the Changelog under Tools for the latest changes.</news>
    </extension>
</addon>
'''

# script.module.pil is not carried by every repository, and FenLightAM needs it
# for exactly one feature: compositing the four-poster artwork used by custom
# lists. A hard <requires> would make the whole add-on uninstallable for that,
# so the import is made optional and the one call site degrades with a message.
PIL_GUARD_BEFORE = '\tfrom PIL import Image\n'
PIL_GUARD_AFTER = (
    '\ttry: from PIL import Image\n'
    '\texcept ImportError:\n'
    '\t\tfrom modules.kodi_utils import notification\n'
    '\t\tnotification("List artwork needs script.module.pil", 4000)\n'
    '\t\treturn None\n'
)

# get_icon() builds a raw.githubusercontent.com URL for every menu row, button
# and notification. The upstream account it pointed at 404s on every path now,
# so stock FenLightAM renders with no icons at all, and our own repo does not
# exist yet. Bundled icons win; the remote URL stays as the fallback for names
# tools/recover_icons.py could not pull out of Kodi's texture cache.
ICON_BEFORE = r"""def get_icon(image_name, image_folder='icons', image_type='png'):
	return 'https://raw.githubusercontent.com/%s/%s/main/packages/media/%s/%s.%s' \
			% (get_property('grnshows.update.username'), get_property('grnshows.update.location'), image_folder, image_name, image_type)
"""
ICON_AFTER = r"""def get_icon(image_name, image_folder='icons', image_type='png'):
	bundled = os.path.join(addon_path(), 'resources', 'media', image_folder, '%s.%s' % (image_name, image_type))
	if os.path.exists(bundled): return bundled
	return 'https://raw.githubusercontent.com/%s/%s/main/packages/media/%s/%s.%s' \
			% (get_property('grnshows.update.username'), get_property('grnshows.update.location'), image_folder, image_name, image_type)
"""



def is_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


def tokenise_credentials(text: str, relative: str) -> tuple:
    """Put a build-time token where the credential default lives.

    Returns the text and the setting ids it changed, so the caller can fail
    loudly if upstream moved something rather than shipping a build with no
    keys in it.
    """
    changed = set()
    for setting_id, token in CREDENTIAL_SETTINGS.items():
        if relative.endswith('caches/settings_cache.py'):
            needle = "{'setting_id': '%s', 'setting_type': 'string', 'setting_default': '%s'}" % (setting_id, SENTINEL)
            replacement = needle.replace("'%s'}" % SENTINEL, "'%s'}" % token)
        elif relative.endswith('1080i/settings_manager.xml'):
            needle = 'Property(grnshows.%s),%s)' % (setting_id, SENTINEL)
            replacement = 'Property(grnshows.%s),%s)' % (setting_id, token)
        else:
            continue
        if needle in text:
            text = text.replace(needle, replacement)
            changed.add(setting_id)
    return text, changed


def rebrand(text: str, repo_username: str, repo_location: str) -> str:
    for needle, replacement in SUBSTITUTIONS:
        text = text.replace(needle, replacement.format(repo_username=repo_username,
                                                       repo_location=repo_location))
    return text


def check_anchors(source: Path, repo_username: str, repo_location: str):
    """Confirm both source patches will apply, before anything is deleted.

    Finding out mid-copy that an upstream function moved leaves the
    destination half-written and any bundled art gone, which is how the GRN
    icon got replaced by the upstream one once already.
    """
    for relative, anchor, label in (('resources/lib/modules/utils.py', PIL_GUARD_BEFORE, 'the PIL import'),
                                    ('resources/lib/modules/kodi_utils.py', ICON_BEFORE, 'get_icon')):
        body = rebrand((source / relative).read_text(encoding='utf-8-sig'), repo_username, repo_location)
        if anchor not in body:
            raise SystemExit('%s changed upstream; the patch in port_fenlight.py no longer applies' % label)


def collect_media(media: Path, existing: Path, repo_username: str, repo_location: str) -> dict:
    """The icon set to bundle: from packages/media, else whatever is already in the tree.

    File names go through the same rename as everything else: the set includes
    a fenlight.png that the code asks for by the add-on's own name, so leaving
    it alone gives a blank icon wherever the add-on refers to itself.
    """
    folders = ('icons', 'flags', 'results', 'network_icons', 'themes', 'rpdb_posters')
    root = media if media and media.is_dir() else existing
    collected = {}
    for folder in folders:
        for path in sorted((root / folder).glob('*')):
            if path.is_file():
                name = rebrand(path.name, repo_username, repo_location)
                collected['%s/%s' % (folder, name)] = path.read_bytes()
    # get_icon('audio') asks for icons/audio.png, but upstream saved that file
    # as audiopng.png, so the audio icon 404s in FenLightAM itself. Ship both
    # names rather than reproducing the typo.
    if 'icons/audiopng.png' in collected:
        collected.setdefault('icons/audio.png', collected['icons/audiopng.png'])
    return collected


def port(source: Path, version: str, repo_username: str, repo_location: str, media: Path = None) -> dict:
    if not (source / 'resources' / 'lib' / 'fenlight.py').is_file():
        raise SystemExit('%s does not look like a FenLightAM checkout' % source)
    check_anchors(source, repo_username, repo_location)

    # Branding art survives the rebuild; it is ours, not upstream's.
    icon = (DEST / 'resources/media/addon_icons/grnshows_icon_01.png')
    fanart = (DEST / 'resources/media/grnshows_fanart_01.jpg')
    keep = {}
    for path in (icon, fanart, DEST / 'resources/media/icon.png', DEST / 'resources/media/fanart.jpg'):
        if path.is_file():
            keep[path.name] = path.read_bytes()
    # The menu art is not in the add-on tree at all: get_icon fetched it over
    # HTTP from a GitHub account that has since been deleted. It lives in the
    # sibling packages/media folder of the source repository, so it is read
    # from there and bundled, and kept across a re-port when it is not.
    bundled = collect_media(media, DEST / 'resources/media', repo_username, repo_location)

    if DEST.exists():
        shutil.rmtree(DEST)

    counts = {'text': 0, 'binary': 0, 'skipped': 0}
    tokenised = set()
    fixed = set()
    for path in sorted(source.rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(source)
        if '__pycache__' in relative.parts or path.suffix in ('.pyc', '.pyo'):
            counts['skipped'] += 1
            continue
        if relative.as_posix() == 'addon.xml':
            counts['skipped'] += 1
            continue  # replaced wholesale below
        target = DEST / rebrand(relative.as_posix(), repo_username, repo_location)
        target.parent.mkdir(parents=True, exist_ok=True)
        if is_text(path):
            body = path.read_text(encoding='utf-8-sig')
            body = rebrand(body, repo_username, repo_location)
            if relative.as_posix().endswith('modules/utils.py'):
                if PIL_GUARD_BEFORE not in body:
                    raise SystemExit('the PIL import moved; update PIL_GUARD_BEFORE')
                body = body.replace(PIL_GUARD_BEFORE, PIL_GUARD_AFTER)
            for suffix, before, after in UPSTREAM_FIXES:
                if relative.as_posix().endswith(suffix):
                    if before not in body:
                        raise SystemExit('upstream fix for %s no longer applies' % suffix)
                    body = body.replace(before, after)
                    fixed.add((suffix, before))
            if relative.as_posix().endswith('modules/kodi_utils.py'):
                if ICON_BEFORE not in body:
                    raise SystemExit('get_icon changed upstream; update ICON_BEFORE')
                body = body.replace(ICON_BEFORE, ICON_AFTER)
            body, changed = tokenise_credentials(body, relative.as_posix())
            tokenised |= changed
            target.write_text(body, encoding='utf-8', newline='')
            counts['text'] += 1
        else:
            shutil.copyfile(path, target)
            counts['binary'] += 1

    (DEST / 'addon.xml').write_text(ADDON_XML.format(version=version), encoding='utf-8')

    # GRN art over the upstream icon and fanart, at every path the add-on and
    # its own icon chooser look for them.
    art = {'grnshows_icon_01.png': keep.get('grnshows_icon_01.png') or keep.get('icon.png'),
           'grnshows_fanart_01.jpg': keep.get('grnshows_fanart_01.jpg') or keep.get('fanart.jpg')}
    if art['grnshows_icon_01.png']:
        # icon.png is the canonical copy the next re-port reads back, so it has
        # to survive too; without it a rebuild silently falls back to the
        # upstream FenLightAM icon.
        for name in ('resources/media/addon_icons/grnshows_icon_01.png',
                     'resources/media/addon_icons/minis/grnshows_icon_01.png',
                     'resources/media/icon.png'):
            (DEST / name).write_bytes(art['grnshows_icon_01.png'])
    if art['grnshows_fanart_01.jpg']:
        for name in ('resources/media/grnshows_fanart_01.jpg', 'resources/media/fanart.jpg'):
            (DEST / name).write_bytes(art['grnshows_fanart_01.jpg'])
    for relative, payload in bundled.items():
        target = DEST / 'resources/media' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    unapplied = {(suffix, before) for suffix, before, _ in UPSTREAM_FIXES} - fixed
    if unapplied:
        raise SystemExit('upstream fix never applied for: %s'
                         % ', '.join(sorted(s for s, _ in unapplied)))
    missing = set(CREDENTIAL_SETTINGS) - tokenised
    if missing:
        raise SystemExit('could not place a credential token for: %s. Upstream changed how '
                         'these defaults are stored; the build would ship with no keys.'
                         % ', '.join(sorted(missing)))
    counts['icons'] = len(bundled)
    counts['extras'] = copy_extras()
    return counts


EXTRAS = ROOT / 'addon_extras'


def copy_extras() -> int:
    """Overlay our own additions onto the ported tree.

    The port rebuilds the destination from scratch every run, so anything we
    write by hand would be destroyed. Keeping our files in addon_extras/ and
    copying them last means they survive, and it keeps the boundary between
    "theirs" and "ours" visible instead of buried in a diff.
    """
    if not EXTRAS.is_dir():
        return 0
    copied = 0
    for path in sorted(EXTRAS.rglob('*')):
        if not path.is_file():
            continue
        target = DEST / path.relative_to(EXTRAS)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        copied += 1
    return copied


def verify(version: str, upstream_icon: bytes) -> list:
    """Every check that would otherwise fail as a runtime error inside Kodi."""
    problems = []

    # 1. no upstream identifier survived anywhere
    for path in sorted(DEST.rglob('*')):
        if not path.is_file() or not is_text(path):
            continue
        for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
            if RESIDUE.search(line):
                problems.append('%s:%d still says %r' % (path.relative_to(DEST), number, line.strip()[:90]))
        if RESIDUE.search(path.as_posix()):
            problems.append('%s: path still carries the upstream name' % path.relative_to(DEST))

    # 2. the entry points addon.xml names actually exist
    for library in ('resources/lib/grnshows.py', 'resources/lib/service.py',
                    'resources/media/addon_icons/grnshows_icon_01.png',
                    'resources/media/grnshows_fanart_01.jpg'):
        if not (DEST / library).is_file():
            problems.append('addon.xml points at missing %s' % library)

    # 3. every window class names a skin XML that shipped
    skins = {p.name for p in (DEST / 'resources/skins/Default/1080i').glob('*.xml')}
    for path in sorted((DEST / 'resources/lib/windows').glob('*.py')):
        for name in re.findall(r"['\"]([a-z_]+\.xml)['\"]", path.read_text(encoding='utf-8')):
            if name not in skins:
                problems.append('%s opens %s, which is not in the skin' % (path.name, name))

    # 4. every media path the skin references resolves on disk
    media_root = DEST / 'resources/skins/Default'
    for path in sorted((media_root / '1080i').glob('*.xml')):
        body = path.read_text(encoding='utf-8')
        for ref in set(re.findall(r'(grnshows_[a-z]+/[A-Za-z0-9_\-]+\.png)', body)):
            if not (media_root / 'media' / ref).is_file():
                problems.append('%s references missing media %s' % (path.name, ref))

    # 5. it compiles
    stream = io.StringIO()
    stdout, sys.stdout = sys.stdout, stream
    try:
        ok = compileall.compile_dir(str(DEST), quiet=1, force=True)
    finally:
        sys.stdout = stdout
    if not ok:
        problems.append('compileall failed:\n' + stream.getvalue())
    for cache in DEST.rglob('__pycache__'):
        shutil.rmtree(cache, ignore_errors=True)

    # 6. every credential token landed in both the registry and the skin
    registry = (DEST / 'resources/lib/caches/settings_cache.py').read_text(encoding='utf-8-sig')
    skin = (DEST / 'resources/skins/Default/1080i/settings_manager.xml').read_text(encoding='utf-8-sig')
    for setting_id, token in CREDENTIAL_SETTINGS.items():
        if token not in registry:
            problems.append('%s has no %s default; the build would ship without that key' % (setting_id, token))
        if token not in skin:
            problems.append('%s still compares against the sentinel in the settings window' % setting_id)

    # 7. the icon is ours, not the one carried over from upstream
    shipped = (DEST / 'resources/media/addon_icons/grnshows_icon_01.png').read_bytes()
    if shipped == upstream_icon:
        problems.append('the add-on icon is still the upstream FenLightAM icon')

    # 8. the version in addon.xml is what was asked for
    if 'version="%s"' % version not in (DEST / 'addon.xml').read_text(encoding='utf-8'):
        problems.append('addon.xml version is not %s' % version)
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='FenLightAM add-on folder')
    parser.add_argument('--version', default='3.0.0')
    parser.add_argument('--media', type=Path,
                        help='packages/media from the source repository, holding the icon set '
                             'that get_icon used to fetch over HTTP')
    parser.add_argument('--repo-username', default='GRN-Shows',
                        help='GitHub account the built-in updater pulls from')
    parser.add_argument('--repo-location', default='grn-shows',
                        help='GitHub repository the built-in updater pulls from')
    args = parser.parse_args()

    source = args.source.resolve()
    upstream_icon = (source / 'resources/media/addon_icons/fenlight_icon_01.png').read_bytes()
    counts = port(source, args.version, args.repo_username, args.repo_location,
                  args.media.resolve() if args.media else None)
    print('ported %(text)d text files, %(binary)d binary files, skipped %(skipped)d, '
          'kept %(icons)d bundled menu icons, %(extras)d of our own files' % counts)
    problems = verify(args.version, upstream_icon)
    if problems:
        print('\n%d PROBLEM(S):' % len(problems))
        for problem in problems[:60]:
            print('  ' + problem)
        raise SystemExit(1)
    print('verified: no upstream identifiers, entry points present, skins and media resolve, compiles clean')


if __name__ == '__main__':
    main()
