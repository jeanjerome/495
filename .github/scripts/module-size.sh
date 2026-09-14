#!/usr/bin/env bash
# Print, as Markdown on stdout, the largest module of harness495/ and every module whose line
# count differs from a base commit.
#
# The number is reported and gates nothing. A ceiling at N lines is met by moving code into a
# second file without giving it a seam: the cheapest answer to the check is the one that leaves
# the coupling where it was while looking like progress. A count in front of a reader on every
# change carries no such incentive, and the reader decides.
#
# Usage: module-size.sh [<base-commit>]
# With no argument, or one naming no commit, the largest module is printed without a delta.

# The backticks in the printf formats below are Markdown code spans, not command substitutions.
# shellcheck disable=SC2016

set -euo pipefail

# sort and join must agree on how they order paths, and both are locale-sensitive.
export LC_ALL=C

if [ "$#" -gt 1 ]; then
    echo "usage: ${0##*/} [<base-commit>]" >&2
    exit 2
fi

# The rows the table keeps; the rest are counted in a trailing line.
readonly ROW_LIMIT=15

sizes() {
    # sizes <commit> — "<lines> <path>" for every Python module of harness495/ at <commit>.
    # awk counts the last line whether or not the file ends with a newline; wc -l does not.
    local commit=$1 path
    git ls-tree -r --name-only "$commit" -- harness495 | while IFS= read -r path; do
        case $path in
        *.py) printf '%s %s\n' "$(git show "$commit:$path" | awk 'END { print NR }')" "$path" ;;
        esac
    done
}

base_sha=""
if [ "$#" -eq 1 ] && [ -n "$1" ] && git rev-parse --verify --quiet "$1^{commit}" >/dev/null; then
    base_sha=$(git rev-parse --short "$1")
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

sizes HEAD | sort -k2,2 >"$work/head"

largest=$(sort -k1,1nr -k2,2 "$work/head" | awk 'NR == 1')
largest_lines=${largest%% *}
largest_path=${largest#* }

printf '## Module size\n\n'

if [ -z "$base_sha" ]; then
    printf '`%s` is the largest module of `harness495/`, at %s lines. No base commit to compare against.\n' \
        "$largest_path" "$largest_lines"
    exit 0
fi

sizes "$base_sha" | sort -k2,2 >"$work/base"

largest_was=$(awk -v path="$largest_path" '$2 == path { print $1 }' "$work/base")
largest_delta=$((largest_lines - ${largest_was:-0}))

if [ "$largest_delta" -eq 0 ]; then
    printf '`%s` is the largest module of `harness495/`, at %s lines, unchanged against `%s`.\n' \
        "$largest_path" "$largest_lines" "$base_sha"
else
    printf '`%s` is the largest module of `harness495/`, at %s lines, %+d against `%s`.\n' \
        "$largest_path" "$largest_lines" "$largest_delta" "$base_sha"
fi

# "<path> <base lines> <head lines>" over the union of the two trees, 0 where a module is
# absent from one of them, then "<delta> <path> <base> <head>" for those that differ.
changed=$(
    join -j 2 -a 1 -a 2 -e 0 -o '0,1.1,2.1' "$work/base" "$work/head" |
        awk '$2 != $3 { print $3 - $2, $1, $2, $3 }' |
        sort -k1,1nr -k2,2
)

if [ -z "$changed" ]; then
    printf '\nNo module of `harness495/` changed size.\n'
    exit 0
fi

printf '\n| Module | Base | Head | Delta |\n| --- | ---: | ---: | ---: |\n'
printf '%s\n' "$changed" |
    awk -v limit="$ROW_LIMIT" 'NR <= limit { printf "| `%s` | %d | %d | %+d |\n", $2, $3, $4, $1 }'

rows=$(printf '%s\n' "$changed" | awk 'END { print NR }')
if [ "$rows" -gt "$ROW_LIMIT" ]; then
    printf '\n%d further modules changed size.\n' "$((rows - ROW_LIMIT))"
fi
