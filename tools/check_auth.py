"""Open each premium-account authorisation flow and report what appeared.

Every one of these used to be a black box: the add-on either showed a device
code or silently notified "Please set a valid ... Client ID" and did nothing.
This drives all five from outside Kodi and prints which window each one
actually reached, so "the premium sources authenticate" is a measurement
rather than a claim.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kodi  # noqa: E402

FLOWS = (
    ('Real-Debrid', 'real_debrid.authenticate'),
    ('Premiumize', 'premiumize.authenticate'),
    ('AllDebrid', 'alldebrid.authenticate'),
    ('TorBox', 'torbox.authenticate'),
    ('Easynews', 'easynews.authenticate'),
)

# A device-code flow lands on the add-on's own progress window; an API-key flow
# lands on Kodi's keyboard. Anything else means it bailed out early.
EXPECTED = {'progress.xml': 'device code shown',
            '': 'keyboard or dialog (API key entry)'}


def window():
    result = kodi.call('XBMC.GetInfoLabels',
                       {'labels': ['Window.Property(xmlfile)', 'System.CurrentWindow']})
    info = result.get('result', {}) or {}
    path = info.get('Window.Property(xmlfile)') or ''
    return os.path.basename(path.replace('\\', os.sep)), info.get('System.CurrentWindow', '')


def main():
    kodi.call('Input.Back')
    time.sleep(1)
    for label, mode in FLOWS:
        kodi.call('Addons.ExecuteAddon',
                  {'addonid': 'plugin.video.grnshows',
                   'params': {'mode': mode, 'isFolder': 'false'}}, timeout=25)
        time.sleep(6)
        xml, current = window()
        verdict = EXPECTED.get(xml, 'unexpected window')
        print('%-12s -> %-16s %-28s %s' % (label, xml or '(none)', current, verdict))
        for _ in range(3):
            kodi.call('Input.Back')
            time.sleep(1)


if __name__ == '__main__':
    main()
