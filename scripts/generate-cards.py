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
        weeks { contributionDays { date contributionCount } }
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
            days.append({"date": f"2026-01-{index % 28 + 1:02d}",
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
    rows = [
        ("Total Stars Earned", stars),
        (f"Total Commits ({datetime.utcnow().year})", contributions["totalCommitContributions"]),
        ("Total PRs", contributions["totalPullRequestContributions"]),
        ("Total Issues", contributions["totalIssueContributions"]),
        ("Public Repositories", user["repositories"]["totalCount"]),
        ("Followers", user["followers"]["totalCount"]),
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

    name = user.get("name") or "GitHub"
    return frame(width, y - 12, f"{name}'s GitHub Stats", "\n".join(body))


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
    days = [day
            for week in user["contributionsCollection"]["contributionCalendar"]["weeks"]
            for day in week["contributionDays"]]
    counts = [day["contributionCount"] for day in days] or [0]
    peak = max(counts) or 1

    width, height = 840, 240
    left, right, top, bottom = 45, 25, 60, 45
    plot_w, plot_h = width - left - right, height - top - bottom

    step = plot_w / max(len(counts) - 1, 1)
    points = [(left + index * step, top + plot_h - (count / peak) * plot_h)
              for index, count in enumerate(counts)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    area = f"{left},{top + plot_h} {line} {left + plot_w:.1f},{top + plot_h}"

    body = [
        f'  <defs><linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{TITLE}" stop-opacity="0.45"/>'
        f'<stop offset="100%" stop-color="{TITLE}" stop-opacity="0"/></linearGradient></defs>',
        f'  <polygon points="{area}" fill="url(#fade)"/>',
        f'  <polyline points="{line}" fill="none" stroke="{TITLE}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>',
    ]

    # Horizontal guides, labelled with the contribution count they sit at.
    for fraction in (0, 0.5, 1):
        y = top + plot_h - fraction * plot_h
        body.append(
            f'  <line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" '
            f'stroke="{MUTED}" stroke-width="1" stroke-opacity="0.35"/>\n'
            f'  <text x="{left - 10}" y="{y + 4:.1f}" fill="{MUTED}" font-family="{FONT}" '
            f'font-size="11" text-anchor="end">{round(peak * fraction)}</text>'
        )

    # One label per month, placed at the first day of each month we hold.
    seen = set()
    for index, day in enumerate(days):
        month = day["date"][:7]
        if month in seen:
            continue
        seen.add(month)
        x = left + index * step
        if x > left + plot_w - 20:
            continue
        label = datetime.strptime(day["date"], "%Y-%m-%d").strftime("%b")
        body.append(f'  <text x="{x:.1f}" y="{height - 18}" fill="{MUTED}" font-family="{FONT}" '
                    f'font-size="11" text-anchor="middle">{label}</text>')

    total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    body.append(f'  <text x="{width - 25}" y="37" fill="{MUTED}" font-family="{FONT}" '
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
