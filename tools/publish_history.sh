#!/usr/bin/env bash
# Upload every previously built ZIP as a GitHub Release, once.
#
# WHY THIS EXISTS
# Kodi offers whichever versions it finds under zips/<addon id>/, so the
# published site has to carry the history. Those ZIPs total roughly 200 MB, and
# putting them in git would bake that into the history for ever, with another
# 15 MB added on every future release. Release assets live outside git, so this
# uploads them once and the Pages workflow pulls them back in on every build.
#
# Safe to re-run: a version already released is skipped, nothing is overwritten.
#
#   ./publish_history.sh [directory-of-zips]
set -euo pipefail

ZIPS="${1:-dist/zips}"

command -v gh >/dev/null || { echo "gh is not installed: https://cli.github.com"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "run 'gh auth login' first"; exit 1; }
[ -d "$ZIPS" ] || { echo "no such directory: $ZIPS"; exit 1; }

repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
echo "Publishing history to $repo"
echo

# Group by version: one release per version, carrying every add-on built at it.
versions=$(find "$ZIPS" -name '*.zip' -printf '%f\n' \
  | sed -E 's/^.*-([0-9]+(\.[0-9]+)*)\.zip$/\1/' | sort -uV)

created=0
skipped=0
for version in $versions; do
  tag="v$version"
  if gh release view "$tag" --repo "$repo" >/dev/null 2>&1; then
    printf '  %-10s already released, skipping\n' "$version"
    skipped=$((skipped + 1))
    continue
  fi

  assets=$(find "$ZIPS" -name "*-$version.zip")
  count=$(echo "$assets" | wc -l)
  printf '  %-10s uploading %s file(s)...' "$version" "$count"
  gh release create "$tag" $assets \
    --repo "$repo" \
    --title "GRN Shows $version" \
    --notes "Archived build, published so Kodi can still offer this version." \
    >/dev/null
  echo ' done'
  created=$((created + 1))
done

echo
echo "created $created release(s), skipped $skipped already present"
echo "Now re-run the Publish workflow so the site picks them all up:"
echo "  gh workflow run 'Publish Kodi repository'"
