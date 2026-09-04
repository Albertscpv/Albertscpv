#!/usr/bin/env python3
"""
Renders the stats, language and activity cards directly from the GitHub API.

These three used to come from public card services. Both went down and stayed
down (github-readme-stats answered 503, the activity graph answered 402 after
its Vercel quota ran out), taking the profile's images with them. Generating
them here removes that dependency: the workflow already has a token, the API
is the same one those services called, and the palette is ours to match.

Output is written to assets/ as static SVG, so the profile page only ever
loads files from this repository.

  usage: generate-cards.py [--mock]

  --mock  render from canned data, for checking the SVG output without a
          token or network access.
"""

import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

# tokyonight, matching the streak card the README already uses.
BG = "#1a1b27"
TITLE = "#7aa2f7"
TEXT = "#a9b1d6"
ACCENT = "#bb9af7"
MUTED = "#565f89"

FONT = "'Segoe UI', Ubuntu, Sans-Serif"
OUT = "assets"

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date weekday contributionCount } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def fetch(login, token):
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{login}-profile-cards",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)

    # GraphQL reports failures in the body with an HTTP 200, so this has to be
    # checked explicitly rather than left to urlopen.
    if payload.get("errors"):
        raise SystemExit("GitHub API error: " + json.dumps(payload["errors"]))
    return payload["data"]["user"]


def mock():
    weeks = []
    for week in range(53):
        days = []
        for day in range(7):
            index = week * 7 + day
            days.append({"date": f"2026-01-{index % 28 + 1:02d}", "weekday": day,
                         "contributionCount": (index * 7) % 11})
        weeks.append({"contributionDays": days})
    return {
        "name": "Christopher Monge",
        "followers": {"totalCount": 12},
        "contributionsCollection": {
            "totalCommitContributions": 233,
            "totalPullRequestContributions": 9,
            "totalIssueContributions": 4,
            "contributionCalendar": {"totalContributions": 246, "weeks": weeks},
        },
        "repositories": {
            "totalCount": 14,
            "nodes": [
                {"stargazerCount": 3, "languages": {"edges": [
                    {"size": 90000, "node": {"name": "Java", "color": "#b07219"}},
                    {"size": 40000, "node": {"name": "HTML", "color": "#e34c26"}}]}},
                {"stargazerCount": 1, "languages": {"edges": [
                    {"size": 60000, "node": {"name": "JavaScript", "color": "#f1e05a"}},
                    {"size": 25000, "node": {"name": "CSS", "color": "#563d7c"}}]}},
            ],
        },
    }


def esc(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def frame(width, height, title, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" \
viewBox="0 0 {width} {height}" fill="none" role="img" aria-label="{esc(title)}">
  <rect width="{width}" height="{height}" rx="10" fill="{BG}"/>
  <text x="25" y="37" fill="{TITLE}" font-family="{FONT}" font-size="17" font-weight="600">{esc(title)}</text>
{body}
</svg>
"""


def stats_card(user):
    stars = sum(repo["stargazerCount"] for repo in user["repositories"]["nodes"])
    contributions = user["contributionsCollection"]
    # contributionsCollection defaults to the last twelve months, not the
    # calendar year, so those three rows say so rather than reading as totals.
    rows = [
        ("Public Repositories", user["repositories"]["totalCount"]),
        ("Total Stars Earned", stars),
        ("Followers", user["followers"]["totalCount"]),
        ("Commits (12 mo)", contributions["totalCommitContributions"]),
        ("Pull Requests (12 mo)", contributions["totalPullRequestContributions"]),
        ("Issues (12 mo)", contributions["totalIssueContributions"]),
    ]

    width, y = 420, 72
    body = []
    for label, value in rows:
        body.append(
            f'  <text x="25" y="{y}" fill="{TEXT}" font-family="{FONT}" font-size="14">{esc(label)}</text>\n'
            f'  <text x="{width - 25}" y="{y}" fill="{ACCENT}" font-family="{FONT}" font-size="14" '
            f'font-weight="700" text-anchor="end">{value:,}</text>'
        )
        y += 26

    # The README already carries the name above this card; repeating the
    # profile's `name` field here only invited the two to disagree.
    return frame(width, y - 12, "GitHub Stats", "\n".join(body))


def languages_card(user, count=6):
    totals = {}
    colors = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + edge["size"]
            colors[name] = edge["node"]["color"] or MUTED

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:count]
    total = sum(size for _, size in ranked)
    if not total:
        ranked, total = [("No data", 1)], 1
        colors["No data"] = MUTED

    width, bar_x, bar_w, bar_y = 320, 25, 270, 58
    body = [f'  <clipPath id="bar"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="10" rx="5"/></clipPath>']

    offset = bar_x
    for name, size in ranked:
        segment = bar_w * size / total
        body.append(f'  <rect x="{offset:.2f}" y="{bar_y}" width="{segment:.2f}" height="10" '
                    f'fill="{colors[name]}" clip-path="url(#bar)"/>')
        offset += segment

    y = bar_y + 38
    for index, (name, size) in enumerate(ranked):
        x = bar_x + (index % 2) * 145
        if index and index % 2 == 0:
            y += 24
        share = 100 * size / total
        body.append(
            f'  <circle cx="{x + 5}" cy="{y - 4}" r="5" fill="{colors[name]}"/>\n'
            f'  <text x="{x + 18}" y="{y}" fill="{TEXT}" font-family="{FONT}" font-size="12">'
            f'{esc(name)} <tspan fill="{MUTED}">{share:.1f}%</tspan></text>'
        )

    return frame(width, y + 20, "Most Used Languages", "\n".join(body))


def activity_card(user):
    """Contribution calendar, drawn as a heatmap.

    A line chart is a poor fit here: across a year of a few dozen sparse
    contributions it is a flat line with isolated spikes. The calendar grid
    stays readable at any volume, and it is the shape the data already has.
    """
    calendar = user["contributionsCollection"]["contributionCalendar"]
    weeks = calendar["weeks"]
    peak = max((day["contributionCount"] for week in weeks
                for day in week["contributionDays"]), default=0)

    # Empty, then four steps. Anything above zero gets a visible cell, so a
    # single contribution never disappears into the background.
    levels = ["#1f2335", "#283457", "#3d59a1", "#7aa2f7", "#bb9af7"]

    def shade(count):
        if count <= 0:
            return levels[0]
        return levels[min(4, 1 + int(3 * (count - 1) / max(peak - 1, 1)))]

    cell, gap = 11, 3
    pitch = cell + gap
    left, top = 42, 78
    width = left + len(weeks) * pitch + 20
    height = top + 7 * pitch + 20

    body = []
    for column, week in enumerate(weeks):
        x = left + column * pitch
        for day in week["contributionDays"]:
            y = top + day["weekday"] * pitch
            body.append(f'  <rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" '
                        f'fill="{shade(day["contributionCount"])}">'
                        f'<title>{day["date"]}: {day["contributionCount"]}</title></rect>')

    for row, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        y = top + row * pitch + cell - 1
        body.append(f'  <text x="{left - 8}" y="{y}" fill="{MUTED}" font-family="{FONT}" '
                    f'font-size="10" text-anchor="end">{label}</text>')

    seen = set()
    for column, week in enumerate(weeks):
        month = week["contributionDays"][0]["date"][:7]
        if month in seen:
            continue
        seen.add(month)
        x = left + column * pitch
        if x > width - 45:
            continue
        label = datetime.strptime(week["contributionDays"][0]["date"], "%Y-%m-%d").strftime("%b")
        body.append(f'  <text x="{x}" y="{top - 10}" fill="{MUTED}" font-family="{FONT}" '
                    f'font-size="10">{label}</text>')

    legend_x = width - 20 - 5 * pitch - 30
    body.append(f'  <text x="{legend_x - 6}" y="{height - 12}" fill="{MUTED}" '
                f'font-family="{FONT}" font-size="10" text-anchor="end">Less</text>')
    for index, colour in enumerate(levels):
        body.append(f'  <rect x="{legend_x + index * pitch}" y="{height - 21}" width="{cell}" '
                    f'height="{cell}" rx="2" fill="{colour}"/>')
    body.append(f'  <text x="{legend_x + 5 * pitch + 4}" y="{height - 12}" fill="{MUTED}" '
                f'font-family="{FONT}" font-size="10">More</text>')

    total = calendar["totalContributions"]
    body.append(f'  <text x="{width - 20}" y="37" fill="{MUTED}" font-family="{FONT}" '
                f'font-size="13" text-anchor="end">{total:,} contributions in the last year</text>')

    return frame(width, height, "Contribution Activity", "\n".join(body))


def main():
    if "--mock" in sys.argv:
        user = mock()
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("GITHUB_TOKEN is not set")
        user = fetch(os.environ.get("PROFILE_USER", "albertscpv"), token)

    os.makedirs(OUT, exist_ok=True)
    for name, svg in (("stats", stats_card(user)),
                      ("top-langs", languages_card(user)),
                      ("activity", activity_card(user))):
        # Never write a card that would render as a broken image.
        ET.fromstring(svg)
        path = os.path.join(OUT, f"{name}.svg")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(svg)
        print(f"  ok       {name} ({len(svg)}B)")


if __name__ == "__main__":
    main()
