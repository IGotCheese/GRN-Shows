"""Decide which version a push publishes, bumping it when the add-on changed.

WHY THIS EXISTS
Kodi only updates an add-on when the repository advertises a HIGHER version.
Push new code under the same version and Kodi sees nothing: the site rebuilds,
the workflow goes green, and not one user receives the change. That is the
usual way self-hosted Kodi repositories quietly stop updating, and it is easy to
hit, because nothing fails.

So a push that changes the add-on always ships a new version:

  - add-on unchanged since the last release (docs, tests, tooling):
        no new version, nothing released. Correct: users have nothing to get.
  - add-on changed and the version was already raised by hand:
        that version is released as it stands.
  - add-on changed but the version was not raised:
        the patch number is bumped (3.2.0 -> 3.2.1), <news> is filled from the
        commit subjects since the last release so Kodi's update dialog says
        what changed, and the workflow commits that back.
  - version LOWER than the last release:
        refuse. Kodi would never install it, so shipping it would only look
        like a release.

Prints key=value lines for $GITHUB_OUTPUT.

    python3 tools/release_version.py            # decide and apply
    python3 tools/release_version.py --dry-run  # decide only, change nothing
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ADDON_XML = Path("plugin.video.grnshows/addon.xml")
# Everything whose change means users must receive a new build.
SHIPPED = ["plugin.video.grnshows", "addon_extras", "vendor", "repository.grnshows"]
NEWS_LIMIT = 1400    # Kodi truncates long <news>; keep it readable in the dialog


def git(*arguments):
    return subprocess.run(["git", *arguments], capture_output=True, text=True).stdout.strip()


def parse(version):
    return tuple(int(part) for part in version.split("."))


def current_version():
    match = re.search(r'id="plugin\.video\.grnshows"[^>]*?version="([0-9.]+)"',
                      ADDON_XML.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("could not read the add-on version from %s" % ADDON_XML)
    return match.group(1)


def last_release():
    for tag in git("tag", "--list", "v*", "--sort=-v:refname").splitlines():
        if re.fullmatch(r"v\d+(\.\d+)*", tag):
            return tag
    return None


def changed_since(tag):
    """True if anything users receive differs from the last release."""
    return subprocess.run(["git", "diff", "--quiet", tag, "HEAD", "--", *SHIPPED]).returncode != 0


def news_since(tag):
    """Commit subjects since the last release, for Kodi's update dialog."""
    subjects = git("log", "--no-merges", "--format=%s", "%s..HEAD" % tag).splitlines()
    lines, total = [], 0
    for subject in subjects:
        subject = subject.strip()
        # Housekeeping commits say nothing a user would want to read.
        if not subject or "[skip ci]" in subject or subject.lower().startswith(("merge", "release ")):
            continue
        entry = "- " + subject
        if total + len(entry) > NEWS_LIMIT:
            break
        lines.append(entry)
        total += len(entry) + 1
    return "\n".join(lines) or "- Maintenance update"


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def apply_bump(new_version, news):
    text = ADDON_XML.read_text(encoding="utf-8")
    text = re.sub(r'(id="plugin\.video\.grnshows"[^>]*?version=")[0-9.]+(")',
                  r"\g<1>%s\g<2>" % new_version, text, count=1)
    body = "v%s\n%s" % (new_version, escape(news))
    if re.search(r"<news>.*?</news>", text, flags=re.S):
        text = re.sub(r"<news>.*?</news>", lambda _: "<news>%s</news>" % body,
                      text, count=1, flags=re.S)
    else:
        text = text.replace("</extension>\n</addon>",
                            "    <news>%s</news>\n    </extension>\n</addon>" % body, 1)
    ADDON_XML.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    version = current_version()
    tag = last_release()

    def emit(**values):
        for key, value in values.items():
            print("%s=%s" % (key, value))

    if tag is None:
        emit(version=version, release="true", bumped="false",
             reason="no previous release; publishing %s" % version)
        return 0

    released = tag[1:]
    if parse(version) < parse(released):
        print("version %s is lower than the last release %s; Kodi would never "
              "install it" % (version, released), file=sys.stderr)
        return 1

    if not changed_since(tag):
        emit(version=version, release="false", bumped="false",
             reason="add-on unchanged since %s; nothing new for Kodi" % tag)
        return 0

    if parse(version) > parse(released):
        emit(version=version, release="true", bumped="false",
             reason="version raised by hand to %s" % version)
        return 0

    major, minor, patch = (parse(version) + (0, 0, 0))[:3]
    new_version = "%d.%d.%d" % (major, minor, patch + 1)
    news = news_since(tag)
    if not arguments.dry_run:
        apply_bump(new_version, news)
    emit(version=new_version, release="true", bumped="true",
         reason="add-on changed since %s; bumped %s -> %s" % (tag, version, new_version))
    return 0


if __name__ == "__main__":
    sys.exit(main())
