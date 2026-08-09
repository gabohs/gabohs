import os
import colorsys
import textwrap
from datetime import datetime
import requests

INTERESTS = ""
TECHNOLOGIES = "C, C++, Python, SQL, x86 AVX"

USER_NAME = os.getenv("USER_NAME", "gabohs")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

GRAPHQL_URL = "https://api.github.com/graphql"
YTD_START = f"{datetime.now().year}-01-01T00:00:00Z"
YTD_NOW = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

STATS_QUERY = f"""
query userInfo($login: String!) {{
  user(login: $login) {{
    commits: contributionsCollection(from: "{YTD_START}", to: "{YTD_NOW}") {{
      totalCommitContributions
    }}
    pullRequests(first: 1) {{
      totalCount
    }}
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {{
      nodes {{
        stargazers {{ totalCount }}
      }}
    }}
  }}
}}
"""

LANGUAGES_QUERY = """
query userInfo($login: String!) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
      nodes {
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node { name }
          }
        }
      }
    }
  }
}
"""


def graphql_request(query: str, username: str, token: str):
    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}
    resp = requests.post(GRAPHQL_URL, json={"query": query, "variables": {"login": username}}, headers=headers)
    resp.raise_for_status()
    return resp.json()


def get_stats(username: str, token: str):
    data = graphql_request(STATS_QUERY, username, token)["data"]["user"]
    stars = sum(r["stargazers"]["totalCount"] for r in data["repositories"]["nodes"])
    return {
        "stars": stars,
        "commits": data["commits"]["totalCommitContributions"],
        "prs": data["pullRequests"]["totalCount"],
    }


def get_languages(username: str, token: str):
    data = graphql_request(LANGUAGES_QUERY, username, token)
    nodes = data["data"]["user"]["repositories"]["nodes"]
    languages = {}
    for repo in nodes:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            languages[name] = languages.get(name, 0) + edge["size"]
    return dict(sorted(languages.items(), key=lambda x: x[1], reverse=True))


def bucket_languages(languages: dict, threshold: float = 1.0):
    """Keep languages above threshold%, group the rest as 'other'."""
    total = sum(languages.values())
    if total == 0:
        return {}
    result, other = {}, 0
    for lang, size in languages.items():
        if (size / total) * 100 >= threshold:
            result[lang] = size
        else:
            other += size
    if other > 0:
        result["other"] = other
    return result


# Card styling 
COLOR_BG = "#0D1117"
COLOR_BORDER = "#30363D"
COLOR_CHROME = "#161B22"
COLOR_BLUE = "#79C0FF"      # headers
COLOR_ORANGE = "#FFA657"    # labels
COLOR_TEXT = "#C9D1D9"      # values
COLOR_MUTED = "#8B949E"     # percentages 
COLOR_TRACK = "#21262D"     # empty part of the language bar

FONT_STACK = "ui-monospace, 'Cascadia Code', 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace"
FONT_SIZE = 14
LINE_HEIGHT = 21
PAD_X = 24
TOP_BAR_H = 36
PAD_TOP = 28
PAD_BOTTOM = 20
WIDTH = 620
MAX_CHARS = 68        # ~ how many monospace chars fit in WIDTH at FONT_SIZE

LABEL_COL = 16         # width reserved for "Label:" column
LANG_NAME_COL = 18     # width reserved for language name
BAR_WIDTH = 20         # width (chars) of the bar itself

LANGUAGE_COLORS = {
    "Python": "#3572A5", "C": "#555555", "C++": "#f34b7d",
    "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "Java": "#b07219",
    "Go": "#00ADD8", "Rust": "#dea584",
    "Shell": "#89e051", "PHP": "#4F5D95", "Ruby": "#701516", "Swift": "#F05138",
    "Kotlin": "#A97BFF", "Dart": "#00B4AB", "Jupyter Notebook": "#DA5B0B",
    "Dockerfile": "#384d54", "Makefile": "#427819", "Lua": "#000080",
    "R": "#198CE7", "SQL": "#e38c00", "Assembly": "#6E4C13",
    "TeX": "#3D6117", "CMake": "#DA3434",
}
_FALLBACK = ["#79C0FF", "#FFA657", "#7EE787", "#D2A8FF", "#FF7B72", "#A5D6FF"]


def _readable(hex_color: str, min_lightness: float = 0.45) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    if light < min_lightness:
        r, g, b = colorsys.hls_to_rgb(hue, min_lightness, sat)
        return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))
    return hex_color


def lang_color(name: str) -> str:
    if name == "other":
        return COLOR_MUTED
    if name in LANGUAGE_COLORS:
        return _readable(LANGUAGE_COLORS[name])
    return _readable(_FALLBACK[sum(map(ord, name)) % len(_FALLBACK)])


def esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def kv_row(label: str, value: str):
    label_txt = f"{label}:".ljust(LABEL_COL)
    wrapped = textwrap.wrap(str(value), width=MAX_CHARS - LABEL_COL) or [""]
    rows = [[(label_txt, COLOR_ORANGE), (wrapped[0], COLOR_TEXT)]]
    for cont in wrapped[1:]:
        rows.append([(" " * LABEL_COL, COLOR_TEXT), (cont, COLOR_TEXT)])
    return rows


def lang_row(name: str, size: float, total: float):
    percent = (size / total * 100) if total else 0
    filled = round(percent / 100 * BAR_WIDTH)
    color = lang_color(name)
    return [
        (name.ljust(LANG_NAME_COL), color),
        ("█" * filled, color),
        ("░" * (BAR_WIDTH - filled), COLOR_TRACK),
        (f"{percent:4.1f}%".rjust(7), COLOR_MUTED),
    ]


def build_svg(interests: str, technologies: str, stats: dict, languages: dict) -> str:
    rows = []  # list[list[(text, color)]]

    def header(title):
        rows.append([(f"-{title}", COLOR_BLUE)])

    def blank():
        rows.append([("", COLOR_TEXT)])

    header("About")
    rows += kv_row("Interests", interests)
    rows += kv_row("Technologies", technologies)
    blank()
    header("Stats")
    rows += kv_row("Stars", f"{stats['stars']:,}")
    rows += kv_row("commits (ytd)", f"{stats['commits']:,}")
    rows += kv_row("pull requests", f"{stats['prs']:,}")
    blank()
    header("Languages")
    total = sum(languages.values())
    for name, size in languages.items():
        rows.append(lang_row(name, size, total))

    height = TOP_BAR_H + PAD_TOP + len(rows) * LINE_HEIGHT + PAD_BOTTOM

    svg = [
        f'<svg width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">',
        f'<style>text,tspan{{font-family:{FONT_STACK};font-size:{FONT_SIZE}px;}}</style>',
        # card background
        f'<rect x="0.5" y="0.5" width="{WIDTH-1}" height="{height-1}" rx="10" '
        f'fill="{COLOR_BG}" stroke="{COLOR_BORDER}"/>',
        # terminal chrome bar
        f'<path d="M0.5,10.5 a10,10 0 0 1 10,-10 h{WIDTH-21} a10,10 0 0 1 10,10 '
        f'v{TOP_BAR_H-10} h-{WIDTH-1} z" fill="{COLOR_CHROME}"/>',
        f'<line x1="0.5" y1="{TOP_BAR_H}" x2="{WIDTH-0.5}" y2="{TOP_BAR_H}" stroke="{COLOR_BORDER}"/>',
    ]
    for i, dot_color in enumerate(["#FF5F56", "#FFBD2E", "#27C93F"]):
        cx = PAD_X - 6 + i * 18
        svg.append(f'<circle cx="{cx}" cy="{TOP_BAR_H/2}" r="5.5" fill="{dot_color}" fill-opacity="0.9"/>')
    svg.append(
        f'<text x="{WIDTH/2}" y="{TOP_BAR_H/2 + 4}" text-anchor="middle" '
        f'fill="{COLOR_MUTED}" font-size="12">{esc(USER_NAME)}@github ~ profile.stats</text>'
    )

    y = TOP_BAR_H + PAD_TOP
    for row in rows:
        parts = [f'<text x="{PAD_X}" y="{y}" xml:space="preserve">']
        for text, color in row:
            parts.append(f'<tspan fill="{color}">{esc(text)}</tspan>')
        parts.append('</text>')
        svg.append("".join(parts))
        y += LINE_HEIGHT

    svg.append('</svg>')
    return "\n".join(svg)


def main():
    if not GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN environment variable is not set.")

    stats = get_stats(USER_NAME, GITHUB_TOKEN)
    raw_languages = get_languages(USER_NAME, GITHUB_TOKEN)
    languages = bucket_languages(raw_languages, threshold=1.0)

    svg = build_svg(INTERESTS, TECHNOLOGIES, stats, languages)
    with open("stats-card.svg", "w", encoding="utf-8") as f:
        f.write(svg)
    print("Wrote stats-card.svg")


if __name__ == "__main__":
    main()
