"""Point Kodi's screenshot action at a folder and capture the current screen.

    py -3 tools/shot.py                 # capture whatever is on screen
    py -3 tools/shot.py <route> <name>  # open an add-on route, then capture

Kodi ships with debug.screenshotpath unset, in which case the screenshot
action logs "screenshots folder:" and writes nothing at all, which is why
earlier capture attempts produced no file.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kodi  # noqa: E402

FOLDER = Path(os.environ['LOCALAPPDATA']) / 'Temp' / 'grnshots'


def capture(name=None):
    FOLDER.mkdir(parents=True, exist_ok=True)
    # Setting a path setting makes Kodi open its "Browse for folder" dialog,
    # which then sits on top of whatever we meant to photograph. Only set it
    # when it is not already pointing where we want.
    current = kodi.call('Settings.GetSettingValue', {'setting': 'debug.screenshotpath'})
    if (current.get('result') or {}).get('value', '').rstrip('\\/') != str(FOLDER).rstrip('\\/'):
        kodi.call('Settings.SetSettingValue',
                  {'setting': 'debug.screenshotpath', 'value': str(FOLDER) + os.sep})
        kodi.call('Input.Select')
    before = set(FOLDER.glob('*.png'))
    kodi.call('Input.ExecuteAction', {'action': 'screenshot'})
    for _ in range(40):
        new = set(FOLDER.glob('*.png')) - before
        if new:
            shot = new.pop()
            # Kodi creates the file, then writes it. Renaming the moment it
            # appears produces a zero-byte image, so wait for the size to settle.
            size = -1
            while size != shot.stat().st_size:
                size = shot.stat().st_size
                time.sleep(0.4)
            if name:
                target = FOLDER / ('%s.png' % name)
                if target.exists():
                    target.unlink()
                shot = shot.rename(target)
            return shot
        time.sleep(0.25)
    return None


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1].startswith('plugin://'):
        kodi.call('GUI.ActivateWindow', {'window': 'videos', 'parameters': [sys.argv[1]]})
        time.sleep(3)
    shot = capture(sys.argv[2] if len(sys.argv) > 2 else None)
    print(shot or 'no screenshot was written')
