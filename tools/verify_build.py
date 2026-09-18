"""Refuse to publish a build that users could not actually use.

Two failures here are silent - the build succeeds and the site deploys - so they
need a check of their own:

  - Keys missing. build.py warns and carries on when the TMDb and Trakt keys are
    absent, and the add-on it produces installs fine but has no working
    catalogue until each user finds and enters their own TMDb key. In CI the
    keys arrive as repository secrets, so a renamed or deleted secret produces
    exactly that build.
  - Not browsable. Kodi installs by browsing the source like a folder. GitHub
    Pages lists nothing, so without the generated listings every new install
    stops at "Add source" while existing users keep updating and nobody notices.

    python3 tools/verify_build.py [dist]
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

SETTINGS = {"tmdb_api": "TMDb key", "trakt.client": "Trakt client id",
            "trakt.secret": "Trakt client secret"}


# A key that was not supplied is written as 'empty_setting', the add-on's own
# "not configured" marker - never as an empty string. Matching only the empty
# string passed a build with no keys at all, so the value is read and judged.
UNCONFIGURED = {"", "empty_setting"}


def configured(registry, setting_id):
    match = re.search(r"\{'setting_id': '%s', 'setting_type': 'string', "
                      r"'setting_default': '([^']*)'\}" % re.escape(setting_id), registry)
    if not match:
        return False
    value = match.group(1)
    return value not in UNCONFIGURED and not value.startswith("@@")


def newest(folder, prefix):
    def version(path):
        return tuple(int(n) for n in re.findall(r"\d+", path.stem.split(prefix + "-", 1)[-1]))
    candidates = sorted(folder.glob(prefix + "-*.zip"), key=version)
    return candidates[-1] if candidates else None


def main():
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    problems = []

    addon = newest(dist / "zips" / "plugin.video.grnshows", "plugin.video.grnshows")
    if addon is None:
        problems.append("no plugin.video.grnshows ZIP was built")
    else:
        with zipfile.ZipFile(addon) as archive:
            registry = archive.read(
                "plugin.video.grnshows/resources/lib/caches/settings_cache.py").decode("utf-8")
        for setting_id, label in SETTINGS.items():
            if not configured(registry, setting_id):
                problems.append("%s ships without a %s - check the GRNSHOWS_* repository secrets"
                                % (addon.name, label))

        # The add-on's own updater installs whatever version this file names.
        marker = addon.parent / "grnshowsam_version"
        offered = marker.read_text(encoding="utf-8").strip() if marker.is_file() else None
        if offered != addon.stem.split("-", 1)[1]:
            problems.append("grnshowsam_version says %r but the newest ZIP is %s, so the in-add-on "
                            "updater would offer the wrong version" % (offered, addon.name))

    for folder in ("", "zips", "zips/plugin.video.grnshows", "zips/repository.grnshows"):
        if not (dist / folder / "index.html").is_file():
            problems.append("/%s has no listing, so Kodi cannot browse it" % folder)
    root = (dist / "index.html").read_text(encoding="utf-8") if (dist / "index.html").is_file() else ""
    if not re.search(r'href="repository\.grnshows-[0-9.]+\.zip"', root):
        problems.append("the source root does not offer the repository ZIP the install guide names")

    if problems:
        for problem in problems:
            print("::error::" + problem)
        return 1
    print("verified %s: keys present, every directory browsable" % (addon.name if addon else "build"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
