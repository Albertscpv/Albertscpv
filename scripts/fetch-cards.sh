#!/usr/bin/env bash
#
# Downloads the cards that come from third-party services once, at build
# time, and stores them under assets/ so the README serves them from this
# repository instead of fetching them on every page view.
#
# Only the two services that still answer are listed here. The stats,
# language and activity cards are rendered by generate-cards.py instead,
# after github-readme-stats began answering 503 and the activity graph
# began answering 402.
#
# A card is only written when the download both succeeds and looks like a
# real card, so a bad response never overwrites a good committed copy.

set -uo pipefail

USER=albertscpv
OUT=assets
MIN_BYTES=300

mkdir -p "$OUT"

# Error strings these services return as a rendered SVG instead of failing
# the request, so an HTTP 200 is not on its own proof of a usable card.
ERROR_PATTERNS='Maximum retries exceeded|Something went wrong|rate limit|Not Found|Internal Server Error|invalid username|Bad credentials'

looks_like_a_card() {
  local file=$1 size

  [ -s "$file" ] || { echo "    empty response"; return 1; }

  size=$(wc -c <"$file")
  if [ "$size" -lt "$MIN_BYTES" ]; then
    echo "    too small (${size}B, expected at least ${MIN_BYTES}B)"
    return 1
  fi

  if ! head -c 2000 "$file" | grep -qi '<svg'; then
    echo "    not an SVG"
    return 1
  fi

  if grep -qiE "$ERROR_PATTERNS" "$file"; then
    echo "    service returned an error card: $(grep -oiE "$ERROR_PATTERNS" "$file" | head -1)"
    return 1
  fi

  return 0
}

fetch_card() {
  local name=$1 url=$2 tmp status
  tmp=$(mktemp)

  for attempt in 1 2 3; do
    status=$(curl -sSL --max-time 20 --compressed \
                  -H 'Accept: image/svg+xml' \
                  -w '%{http_code}' -o "$tmp" "$url" 2>/dev/null)

    if [ "$status" = "200" ] && looks_like_a_card "$tmp"; then
      mv "$tmp" "$OUT/$name.svg"
      echo "  ok       $name ($(wc -c <"$OUT/$name.svg")B, attempt $attempt)"
      return 0
    fi

    echo "  attempt $attempt/3 failed for $name (HTTP ${status:-000})"
    [ "$attempt" -lt 3 ] && sleep $((attempt * 3))
  done

  rm -f "$tmp"
  if [ -f "$OUT/$name.svg" ]; then
    echo "  KEPT     $name — refresh failed, previous copy left in place"
  else
    echo "  MISSING  $name — refresh failed and there is no previous copy"
  fi
  # Never fail the run: a stale card is better than no card.
  return 0
}

cards=(
  "streak|https://streak-stats.demolab.com?user=${USER}&theme=tokyonight&hide_border=true&background=1a1b27&ring=7aa2f7&fire=bb9af7&currStreakLabel=7aa2f7"
  "followers|https://img.shields.io/github/followers/${USER}?label=Followers&style=flat-square&color=bb9af7&labelColor=1a1b27"
)

echo "Refreshing ${#cards[@]} cards for @${USER}"
for card in "${cards[@]}"; do
  fetch_card "${card%%|*}" "${card#*|}"
done
echo "Done."
