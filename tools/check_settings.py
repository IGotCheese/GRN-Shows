"""Prove a settings change survives the round trip.

Settings do not live in Kodi's settings.xml here: they are rows in a SQLite
database, mirrored into window properties as a memory cache. That gives three
places a write can go missing, and get_setting() reads the property FIRST, so a
stale property masks a correct database row and the setting looks like it did
nothing.

This toggles real settings through the add-on's own route, then reads both the
database and the in-memory property back.

    py -3 tools/check_settings.py
"""
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kodi  # noqa: E402

DB = (Path(os.environ['LOCALAPPDATA']) /
      'Packages/XBMCFoundation.Kodi_4n2hpmxwrvr6p/LocalCache/Roaming/Kodi/userdata'
      '/addon_data/plugin.video.grnshows/databases/settings.db')

# Safe to flip twice: each is a display or filter preference, and the test puts
# every one back the way it found it.
BOOLEANS = ('extras.enable_item_ratings', 'ignore_articles',
            'extras.enable_extra_ratings', 'auto_start_grnshows')


def from_database(setting_id):
    connection = sqlite3.connect('file:%s?mode=ro' % DB.as_posix(), uri=True)
    try:
        row = connection.execute('SELECT setting_value FROM settings WHERE setting_id = ?',
                                 (setting_id,)).fetchone()
        return row[0] if row else None
    finally:
        connection.close()


def from_memory(setting_id):
    result = kodi.call('XBMC.GetInfoLabels',
                       {'labels': ['Window(10000).Property(grnshows.%s)' % setting_id]})
    return (result.get('result', {}) or {}).get(
        'Window(10000).Property(grnshows.%s)' % setting_id)


def toggle(setting_id):
    """Invoke the route the settings window invokes.

    Addons.ExecuteAddon with a params object does NOT reliably deliver them:
    set_boolean reads params['setting_id'] and gets nothing, so the toggle dies
    silently and the setting looks broken. The window itself uses RunPlugin
    with a query string, so drive the plugin URL directly. The JSON-RPC error
    that comes back is expected: this route is not a directory listing.
    """
    kodi.listing('plugin://plugin.video.grnshows/'
                 '?mode=settings_manager.set_boolean&setting_id=%s&isFolder=false' % setting_id)
    time.sleep(3)


def main():
    if not DB.is_file():
        print('no settings database at %s' % DB)
        return
    print('%-32s %-10s %-10s %-10s %s' % ('setting', 'before', 'after', 'memory', 'verdict'))
    failures = 0
    for setting_id in BOOLEANS:
        before = from_database(setting_id)
        if before is None:
            print('%-32s %s' % (setting_id, 'not in the registry, skipped'))
            continue
        toggle(setting_id)
        after, memory = from_database(setting_id), from_memory(setting_id)
        ok = after != before and memory == after
        failures += 0 if ok else 1
        print('%-32s %-10s %-10s %-10s %s'
              % (setting_id, before, after, memory or '(unset)', 'ok' if ok else 'FAILED'))
        toggle(setting_id)   # leave it exactly as found
        restored = from_database(setting_id)
        if restored != before:
            print('   WARNING: left as %s, was %s' % (restored, before))
    print('\n%s' % ('all settings round-tripped' if not failures
                    else '%d setting(s) did not round-trip' % failures))


if __name__ == '__main__':
    main()
