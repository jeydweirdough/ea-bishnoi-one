#!/usr/bin/env bash
# Make a release: squash everything new on `dev` into one commit on `main`, named after the version.
#
#   scripts/release.sh 1.1.0          # prepares main, the v1.1.0 tag and the changelog (no push)
#   git push origin main v1.1.0       # then publish
#
# Day to day, every feature is its own commit on `dev` (local only). `main` holds one commit per
# release, so GitHub stays clean. The detailed commits are kept locally on `archive/v<version>`.
set -euo pipefail

v="${1:-}"
[[ "$v" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Usage: scripts/release.sh <major.minor.patch>, e.g. 1.1.0" >&2; exit 1; }
cd "$(git rev-parse --show-toplevel)"
[ "$(git branch --show-current)" = "dev" ] || { echo "Switch to the dev branch first" >&2; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "Commit or stash your changes on dev first" >&2; exit 1; }
! git rev-parse -q --verify "refs/tags/v$v" >/dev/null || { echo "v$v already exists" >&2; exit 1; }

notes="$(git log --reverse --no-merges --format='- %s' main..dev)"
[ -n "$notes" ] || { echo "Nothing new on dev since the last release" >&2; exit 1; }

git switch -q main
git merge -q --squash dev

# The version shown by the web app and the API.
node -e '
  const fs = require("fs"), v = process.argv[1];
  for (const f of ["web/package.json", "web/package-lock.json"]) {
    const j = JSON.parse(fs.readFileSync(f, "utf8"));
    j.version = v;
    if (j.packages && j.packages[""]) j.packages[""].version = v;
    fs.writeFileSync(f, JSON.stringify(j, null, 2) + "\n");
  }
' "$v"
sed -i -E "s/^    version=\"[^\"]*\",/    version=\"$v\",/" api/app/main.py

# CHANGELOG.md: newest release first.
entry="## v$v · $(date +%Y-%m-%d)"$'\n\n'"$notes"$'\n'
if [ -f CHANGELOG.md ]; then
  { head -n 2 CHANGELOG.md; printf '%s\n' "$entry"; tail -n +3 CHANGELOG.md; } > CHANGELOG.md.tmp && mv CHANGELOG.md.tmp CHANGELOG.md
else
  printf '# Changelog\n\n%s' "$entry" > CHANGELOG.md
fi

git add -A
git commit -q -m "v$v" -m "$notes"
git tag -a "v$v" -m "v$v"$'\n\n'"$notes"

# Keep the detailed commits locally, then start dev again from the release.
git branch -f "archive/v$v" dev
git switch -q dev
git reset -q --hard main

echo "Release v$v is ready on main:"
echo "$notes"
echo
echo "Publish with: git push origin main v$v"
