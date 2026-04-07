from datetime import datetime
import os
import requests

GRAPHQL_URL = "https://api.github.com/graphql"

STATS_QUERY = f"""
query userInfo($login: String!) {{
  user(login: $login) {{
    name
    login
    commits: contributionsCollection(from: "{datetime.now().year}-01-01T00:00:00Z") {{
      totalCommitContributions
    }}
    repositoriesContributedTo(
      first: 10
      contributionTypes: [COMMIT, PULL_REQUEST]
      orderBy: {{ direction: DESC, field: CREATED_AT }}
    ) {{
      totalCount
      nodes {{
        nameWithOwner
        description
        stargazers {{
          totalCount
        }}
      }}
    }}
    pullRequests(first: 1) {{
      totalCount
    }}
    mergedPullRequests: pullRequests(states: MERGED) {{
      totalCount
    }}
    openIssues: issues(states: OPEN) {{
      totalCount
    }}
    closedIssues: issues(states: CLOSED) {{
      totalCount
    }}
    followers {{
      totalCount
    }}
    repositories(first: 100, ownerAffiliations: OWNER) {{
      totalCount
      nodes {{
        name
        stargazers {{
          totalCount
        }}
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
        name
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node {
              color
              name
            }
          }
        }
      }
    }
  }
}
"""


def graphql_request(query: str, username: str, token: str):
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "variables": {"login": username}}
    response = requests.post(GRAPHQL_URL, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def get_stats(username: str, token: str):
    data = graphql_request(STATS_QUERY, username, token)["data"]["user"]

    stars = sum(r["stargazers"]["totalCount"] for r in data["repositories"]["nodes"])

    contributed = []
    for repo in data["repositoriesContributedTo"]["nodes"]:
        name = repo["nameWithOwner"]
        # skip own repos
        if name.lower().startswith(username.lower() + "/"):
            continue
        contributed.append({
            "name": name,
            "description": repo.get("description") or "",
            "stars": repo["stargazers"]["totalCount"],
        })

    return {
        "name": data["name"] or data["login"],
        "stars": stars,
        "commits": data["commits"]["totalCommitContributions"],
        "prs": data["pullRequests"]["totalCount"],
        "merged_prs": data["mergedPullRequests"]["totalCount"],
        "issues": data["openIssues"]["totalCount"] + data["closedIssues"]["totalCount"],
        "followers": data["followers"]["totalCount"],
        "repos": data["repositories"]["totalCount"],
        "contributed": contributed,
    }


def get_languages(username: str, token: str):
    data = graphql_request(LANGUAGES_QUERY, username, token)
    nodes = data["data"]["user"]["repositories"]["nodes"]

    languages = {}
    for repo in nodes:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            size = edge["size"]
            languages[name] = languages.get(name, 0) + size

    return dict(sorted(languages.items(), key=lambda x: x[1], reverse=True))


def percent_bar(percent: float, width: int = 22):
    percent = max(0, min(100, percent))
    filled = round((percent / 100) * width)
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}]"


def truncate(s: str, n: int):
    return s if len(s) <= n else s[: n - 1] + "…"


def generate_readme(username: str, token: str, path: str = "README.md"):
    stats = get_stats(username, token)
    languages = get_languages(username, token)

    now = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    total_lang_size = sum(languages.values())

    lines = []

    # header
    lines += [
        "```",
        f"  ┌─────────────────────────────────────────────────────────┐",
        f"  │  ~ {stats['name']:<53}│",
        f"  │  $ github.com/{username:<43}│",
        f"  └─────────────────────────────────────────────────────────┘",
        "```",
        "",
    ]

    # stats
    lines += [
        "```",
        "  ── stats ──────────────────────────────────────────────────",
        "",
        f"  {'Stars':<18}  {stats['stars']}",
        f"  {'Commits (YTD)':<18}  {stats['commits']}",
        f"  {'Pull Requests':<18}  {stats['prs']}  ({stats['merged_prs']} merged)",
        f"  {'Issues':<18}  {stats['issues']}",
        f"  {'Followers':<18}  {stats['followers']}",
        f"  {'Public Repos':<18}  {stats['repos']}",
        "",
        "```",
        "",
    ]

    # languages
    lines += [
        "```",
        "  ── top languages ───────────────────────────────────────────",
        "",
    ]
    for lang, size in list(languages.items())[:8]:
        percent = (size / total_lang_size) * 100 if total_lang_size > 0 else 0
        bar = percent_bar(percent)
        lines.append(f"  {lang:<14}  {bar}  {percent:5.1f}%")
    lines += ["", "```", ""]

    # ── contributed to ───────────────────────────────────────────────────────
    if stats["contributed"]:
        lines += [
            "```",
            "  ── contributed to ──────────────────────────────────────────",
            "",
        ]
        for repo in stats["contributed"][:8]:
            star_str = f"★ {repo['stars']}" if repo["stars"] else ""
            desc = truncate(repo["description"], 38)
            lines.append(f"  {repo['name']:<32}  {star_str}")
            if desc:
                lines.append(f"  {'':32}  {desc}")
        lines += ["", "```", ""]

    # ── footer ───────────────────────────────────────────────────────────────
    lines += [
        "```",
        f"  updated: {now:<49}",
        "```",
    ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"README.md generated for @{username}")


if __name__ == "__main__":
    username = "gabohs"
    token = os.getenv("GITHUB_TOKEN", "")

    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is not set.")

    generate_readme(username, token)
