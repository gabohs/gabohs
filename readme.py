from datetime import datetime, timezone
import os
import requests

CONFIG = {
    "interests": "Machine Learning, Data Science, Python, C++",           
    "technologies": "C, C++, Python, SQL",
}
 
GRAPHQL_URL = "https://api.github.com/graphql"
 
YTD_START = f"{datetime.now().year}-01-01T00:00:00Z"
YTD_NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
 
STATS_QUERY = f"""
query userInfo($login: String!) {{
  user(login: $login) {{
    name
    login
    commits: contributionsCollection(from: "{YTD_START}", to: "{YTD_NOW}") {{
      totalCommitContributions
    }}
    pullRequests(first: 1) {{
      totalCount
    }}
    mergedPullRequests: pullRequests(states: MERGED) {{
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
    res = graphql_request(STATS_QUERY, username, token)
    data = res.get("data", {}).get("user")
    if not data:
        raise ValueError(f"Failed to retrieve user data from GitHub API: {res.get('errors')}")
 
    repo_nodes = data.get("repositories", {}).get("nodes") or []
    stars = sum(
        (repo.get("stargazers") or {}).get("totalCount", 0)
        for repo in repo_nodes
        if repo
    )
 
    return {
        "stars": stars,
        "commits": (data.get("commits") or {}).get("totalCommitContributions", 0),
        "prs": (data.get("pullRequests") or {}).get("totalCount", 0),
        "merged_prs": (data.get("mergedPullRequests") or {}).get("totalCount", 0),
    }
 
 
def get_languages(username: str, token: str):
    res = graphql_request(LANGUAGES_QUERY, username, token)
    user_data = res.get("data", {}).get("user")
    if not user_data:
        return {}
 
    nodes = user_data.get("repositories", {}).get("nodes") or []
 
    languages = {}
    for repo in nodes:
        if not repo or not repo.get("languages"):
            continue
        for edge in (repo["languages"].get("edges") or []):
            if not edge or not edge.get("node"):
                continue
            name = edge["node"].get("name")
            size = edge.get("size", 0)
            if name:
                languages[name] = languages.get(name, 0) + size
 
    return dict(sorted(languages.items(), key=lambda x: x[1], reverse=True))
 
 
def bucket_languages(languages: dict, threshold: float = 1.0):
    """Keep languages above threshold%, group the rest as 'other'."""
    total = sum(languages.values())
    if total == 0:
        return {}
 
    result = {}
    other = 0
    for lang, size in languages.items():
        if (size / total) * 100 >= threshold:
            result[lang] = size
        else:
            other += size
 
    if other > 0:
        result["other"] = other
 
    return result
 
 
def percent_bar(percent: float, width: int = 20):
    percent = max(0, min(100, percent))
    filled = round((percent / 100) * width)
    empty = width - filled
    return f"{'█' * filled}{'░' * empty}"
 
 
def kv_line(label: str, value, label_width: int = 15):
    """'label:' padded to label_width, then value."""
    return f"{label + ':':<{label_width}} {value}"
 
 
def lang_line(name: str, percent: float, name_width: int = 8, bar_width: int = 20):
    bar = percent_bar(percent, bar_width)
    return f"{name:<{name_width}} {bar}  {percent:4.1f}%"
 
 
def render_card(stats: dict, languages: dict) -> str:
    total_lang_size = sum(languages.values())
 
    lines = ["```"]
 
    # -About
    lines.append("-About")
    lines.append(kv_line("Interests", CONFIG["interests"]))
    lines.append(kv_line("Technologies", CONFIG["technologies"]))
    lines.append("")
 
    # -Stats
    lines.append("-Stats")
    lines.append(kv_line("Stars", stats["stars"]))
    lines.append(kv_line("commits (ytd)", stats["commits"]))
    lines.append(kv_line("pull requests", f"{stats['prs']} ({stats['merged_prs']} merged)"))
    lines.append("")
 
    # -Languages
    lines.append("-Languages")
    for lang, size in languages.items():
        percent = (size / total_lang_size) * 100 if total_lang_size > 0 else 0
        lines.append(lang_line(lang, percent))
 
    lines.append("```")
    return "\n".join(lines) + "\n"
 
 
def generate_readme(username: str, token: str, path: str = "README.md"):
    stats = get_stats(username, token)
    raw_languages = get_languages(username, token)
    languages = bucket_languages(raw_languages, threshold=1.0)
 
    card = render_card(stats, languages)
 
    with open(path, "w", encoding="utf-8") as f:
        f.write(card)
 
 
if __name__ == "__main__":
    username = "gabohs"
    token = os.getenv("GITHUB_TOKEN", "")
 
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is not set.")
 
    generate_readme(username, token)
