from datetime import datetime, timezone
import os
import requests

import textwrap
 
GRAPHQL_URL = "https://api.github.com/graphql"
 
YTD_START = f"{datetime.now().year}-01-01T00:00:00Z"
YTD_NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

 
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
 
 
def lang_line(name: str, percent: float, name_width: int = 8, bar_width: int = 20):
    bar = percent_bar(percent, bar_width)
    return f"{name:<{name_width}} {bar}  {percent:4.1f}%"
 
 
def render_languages(languages: dict) -> str:
    total_lang_size = sum(languages.values())

 
    code_block = ["```"]
 
    # -Languages
    for lang, size in languages.items():
        percent = (size / total_lang_size) * 100 if total_lang_size > 0 else 0
        code_block.append("\t" + lang_line(lang, percent))
 
    code_block.append("```")
    return "\n".join(code_block) + "\n"
 
 
def generate_readme(username: str, token: str, path: str = "README.md"):
    raw_languages = get_languages(username, token)
    languages = bucket_languages(raw_languages, threshold=1.0)
 
    card = render_languages(languages)

    CONFIG = {    
        "interests": "Machine Learning, Data Science, Python, C++",               
        "tech_stack": "C, C++, Python, SQL",
    }
 
    with open(path, "w", encoding="utf-8") as f:
        about = f"""### About
                   
                Interests: {CONFIG['interests']}
         
                Technologies: {CONFIG['tech_stack']}
                """
     
     
        f.write(textwrap.dedent(about))
     
        f.write(f"\n")
        
        f.write(card)
 
 
if __name__ == "__main__":
    username = "gabohs"
    token = os.getenv("GITHUB_TOKEN", "")
 
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is not set.")
 
    generate_readme(username, token)
