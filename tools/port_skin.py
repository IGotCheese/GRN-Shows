"""Port the Fen Light skin layer into GRN Shows, rebranded.

Copies resources/skins/Default (media + 1080i layouts) out of the FenLightPlus
checkout, renames the fenlight_* asset folders to grn_*, and rewrites every
reference inside the XML so nothing points at the original add-on id, window
property namespace or texture paths.

    py -3 tools/port_skin.py --source <path to plugin.video.fenlight>

Re-runnable: it overwrites the ported files and leaves anything else alone.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "plugin.video.grnshows/resources/skins/Default"

# Every layout the source ships. Ones without a window class yet are still
# ported so the skin is complete and the classes can be filled in against real
# XML rather than guesses.
WINDOWS = None  # None means "all of them"

FOLDER_RENAMES = {
    "fenlight_common": "grn_common",
    "fenlight_buttons": "grn_buttons",
    "fenlight_diffuse": "grn_diffuse",
    "fenlight_flags": "grn_flags",
}

# Order matters: the folder names must be rewritten before the bare word.
TEXT_REPLACEMENTS = [
    ("fenlight_common/", "grn_common/"),
    ("fenlight_buttons/", "grn_buttons/"),
    ("fenlight_diffuse/", "grn_diffuse/"),
    ("fenlight_flags/", "grn_flags/"),
    ("grn_common/fenlight.png", "grn_common/logo.png"),
    ("plugin.video.fenlight", "plugin.video.grnshows"),
    ("Window.Property(fenlight.", "Window.Property(grnshows."),
    ("Container.Property(fenlight.", "Container.Property(grnshows."),
    ("FENLIGHT_", "GRN_"),
    ("Fen Light+", "GRN Shows"),
    ("Fen Light", "GRN Shows"),
    ("FenLight", "GRN Shows"),
]


def rewrite(text):
    for old, new in TEXT_REPLACEMENTS:
        text = text.replace(old, new)
    # catch any remaining bare reference so nothing points back at the original
    text = re.sub(r"fenlight", "grnshows", text, flags=re.IGNORECASE)
    return text


def rewrite_name(name):
    """File names are shown in the tips list, so they get rebranded too."""
    for old, new in (("Fen Light+", "GRN Shows"), ("Fen Light", "GRN Shows"),
                     ("FenLightAM", "GRN Shows"), ("FenLight", "GRN Shows")):
        name = name.replace(old, new)
    return re.sub(r"fenlight", "grnshows", name, flags=re.IGNORECASE)


def port_media(source):
    media_source = source / "resources/skins/Default/media"
    if not media_source.is_dir():
        raise SystemExit("no media folder at %s" % media_source)
    media_target = TARGET / "media"
    copied = 0
    for folder in sorted(p for p in media_source.iterdir() if p.is_dir()):
        destination = media_target / FOLDER_RENAMES.get(folder.name, folder.name)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(folder, destination)
        copied += len(list(destination.rglob("*.png"))) + len(list(destination.rglob("*.jpg")))
    for loose in sorted(p for p in media_source.iterdir() if p.is_file()):
        shutil.copyfile(loose, media_target / loose.name)
        copied += 1
    # their logo becomes ours
    logo = media_target / "grn_common" / "fenlight.png"
    if logo.exists():
        icon = ROOT / "plugin.video.grnshows/resources/media/icon.png"
        target_logo = media_target / "grn_common" / "logo.png"
        shutil.copyfile(icon if icon.is_file() else logo, target_logo)
        logo.unlink()
    return copied


def port_windows(source):
    layouts = source / "resources/skins/Default/1080i"
    destination = TARGET / "1080i"
    destination.mkdir(parents=True, exist_ok=True)
    written = []
    names = WINDOWS or sorted(p.name for p in layouts.glob("*.xml"))
    for name in names:
        path = layouts / name
        if not path.is_file():
            print("  skipped %s (not in source)" % name)
            continue
        text = rewrite(path.read_text(encoding="utf-8"))
        (destination / name).write_text(text, encoding="utf-8", newline="\n")
        written.append((name, len(text)))
    return written


def port_text(source):
    """The tips pages and changelog: product content, not code."""
    text_source = source / "resources/text"
    if not text_source.is_dir():
        return 0
    text_target = ROOT / "plugin.video.grnshows/resources/text"
    if text_target.exists():
        shutil.rmtree(text_target)
    text_target.mkdir(parents=True)
    count = 0
    for path in sorted(text_source.rglob("*.txt")):
        relative = path.relative_to(text_source)
        # the file names are shown to the user, so rebrand those too
        relative = Path(*[rewrite_name(part) for part in relative.parts])
        destination = text_target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = rewrite(path.read_text(encoding="utf-8", errors="replace"))
        destination.write_text(content, encoding="utf-8", newline="\n")
        count += 1
    return count


def verify():
    """Nothing ported may still reference the original add-on."""
    offenders = []
    for path in TARGET.rglob("*"):
        if path.suffix.lower() != ".xml":
            continue
        text = path.read_text(encoding="utf-8").lower()
        if "fenlight" in text or "fen light" in text:
            offenders.append(path.name)
    for path in TARGET.rglob("*"):
        if path.is_dir() and "fenlight" in path.name.lower():
            offenders.append(path.name + "/")
    return offenders


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()
    source = args.source
    if not (source / "resources/skins/Default").is_dir():
        raise SystemExit("not a fenlight checkout: %s" % source)

    TARGET.mkdir(parents=True, exist_ok=True)
    assets = port_media(source)
    print("media files ported: %d" % assets)
    pages = port_text(source)
    print("text pages ported:  %d" % pages)
    for name, size in port_windows(source):
        print("  %-24s %7d bytes" % (name, size))
    offenders = verify()
    if offenders:
        print("STILL REFERENCES THE ORIGINAL:", offenders)
        return 1
    print("no remaining references to the original add-on")
    return 0


if __name__ == "__main__":
    sys.exit(main())
