#!/usr/bin/env bash
#
# Downloads the profile cards once, at build time, and stores them under
# assets/ so the README can serve them from this repository instead of
# fetching them from third-party services on every page view.
#
# GitHub proxies README images through Camo, which has a short upstream
# timeout and caches failures. The cards that query the GitHub API are slow
# enough to trip it, which is why they rendered as broken images.
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

  for attempt in 1 2 3 4 5; do
    status=$(curl -sSL --max-time 45 --compressed \
                  -H 'Accept: image/svg+xml' \
                  -w '%{http_code}' -o "$tmp" "$url" 2>/dev/null)

    if [ "$status" = "200" ] && looks_like_a_card "$tmp"; then
      mv "$tmp" "$OUT/$name.svg"
      echo "  ok       $name ($(wc -c <"$OUT/$name.svg")B, attempt $attempt)"
      return 0
    fi

    echo "  attempt $attempt/5 failed for $name (HTTP ${status:-000})"
    [ "$attempt" -lt 5 ] && sleep $((attempt * 5))
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
  "stats|https://github-readme-stats.vercel.app/api?username=${USER}&show_icons=true&theme=tokyonight&hide_border=true&bg_color=1a1b27&title_color=7aa2f7&icon_color=bb9af7&text_color=a9b1d6&card_width=420"
  "top-langs|https://github-readme-stats.vercel.app/api/top-langs?username=${USER}&layout=compact&langs_count=6&theme=tokyonight&hide_border=true&bg_color=1a1b27&title_color=7aa2f7&text_color=a9b1d6&card_width=320"
  "streak|https://streak-stats.demolab.com?user=${USER}&theme=tokyonight&hide_border=true&background=1a1b27&ring=7aa2f7&fire=bb9af7&currStreakLabel=7aa2f7"
  "activity|https://github-readme-activity-graph.vercel.app/graph?username=${USER}&theme=tokyo-night&bg_color=1a1b27&color=a9b1d6&line=7aa2f7&point=bb9af7&hide_border=true&radius=8&area=true"
  "followers|https://img.shields.io/github/followers/${USER}?label=Followers&style=flat-square&color=bb9af7&labelColor=1a1b27"
)

echo "Refreshing ${#cards[@]} cards for @${USER}"
for card in "${cards[@]}"; do
  fetch_card "${card%%|*}" "${card#*|}"
done
echo "Done."
