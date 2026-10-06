#!/bin/bash
# Releases are built and uploaded to PyPI by .github/workflows/manylinux_wheel_builder.yml,
#  which runs when a GitHub release is published. This checks the release is ready, and then
#  gives the link to create the GitHub release with the tag, branch, title, and notes filled in.
#
# Usage: ./release.sh [branch]    (default branch: v3; use v3-dev for a pre-release)

set -euo pipefail
cd "$(dirname "$0")"

branch=${1:-v3}
version=$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml)
tag="v${version}"
problems=0

problem() {
    echo "  ✗ $1"
    problems=1
}

echo "Checking release ${tag} from branch ${branch}..."
git fetch -q origin

if [[ $(git show "origin/${branch}:pyproject.toml" | sed -n 's/^version = "\(.*\)"$/\1/p') != "${version}" ]]; then
    problem "origin/${branch} is not at version ${version} - push it first (for v3, merge v3-dev into it with a PR)."
fi
if git ls-remote --exit-code --tags origin "refs/tags/${tag}" > /dev/null; then
    problem "The tag ${tag} already exists on GitHub - bump the version in pyproject.toml."
fi
if ! grep -qx "${version}" docs/release-notes.rst; then
    problem "docs/release-notes.rst has no section for ${version}."
fi
if [[ ${problems} -ne 0 ]]; then
    exit 1
fi

# The notes for this version, from its heading up to the next version's heading
notes=$(awk -v version="${version}" '
    $0 == version { found = 1; getline; next }
    found && /^~+$/ { exit }
    found { lines[n++] = $0 }
    END { if (n) n--; for (i = 0; i < n; i++) print lines[i] }' docs/release-notes.rst)

prerelease=0
if [[ ${version} =~ (a|b|rc)[0-9]+$ ]]; then
    prerelease=1
fi

url=$(python3 -c '
import re
import sys
from urllib.parse import urlencode
tag, branch, prerelease, notes = sys.argv[1:]
# RST to Markdown: :py:meth:`pynmrstar.Entry.get_json` and ``str()`` become `Entry.get_json` and `str()`
notes = re.sub(r":py:\w+:`(?:pynmrstar\.)?([^`]+)`", r"`\1`", notes)
notes = re.sub(r"``([^`]+)``", r"`\1`", notes)
query = {"tag": tag, "target": branch, "title": f"{tag} - ", "body": notes.strip()}
if prerelease == "1":
    query["prerelease"] = "1"
print("https://github.com/bmrb-io/PyNMRSTAR/releases/new?" + urlencode(query))
' "${tag}" "${branch}" "${prerelease}" "${notes}")

echo "  ✓ Ready to release."
echo
echo "Create and publish the GitHub release here, adding a summary to the title:"
echo
echo "  ${url}"
echo
echo "Publishing it runs the 'Build and upload to PyPI' workflow, which builds the wheels and sdist"
echo "and uploads them to PyPI. Watch it at https://github.com/bmrb-io/PyNMRSTAR/actions"
