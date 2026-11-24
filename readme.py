from datetime import datetime, timezone
import os
import textwrap

import requests

GRAPHQL_URL = "https://api.github.com/graphql"

YTD_START = f"{datetime.now().year}-01-01T00:00:00Z"
YTD_NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

USERNAME = "gabohs"
EXTRA_ORGS = ["IDENTIFICA_ERECHIM"]  # login da org, como aparece na URL do GitHub

IGNORED_LANGUAGES = {
    "Jupyter Notebook",
    "HTML",
    "CSS",
    "Makefile",
    "CMake",
    "Batchfile",
    "Dockerfile",
}

REPO_FIELDS = """
fragment RepoLangs on Repository {
  nameWithOwner
  languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
    edges { size node { name } }
  }
}
"""

USER_REPOS_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes { ...RepoLangs }
    }
  }
}
""" + REPO_FIELDS

ORG_REPOS_QUERY = """
query($login: String!, $after: String) {
  organization(login: $login) {
    repositories(isFork: false, first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes { ...RepoLangs }
    }
  }
}
""" + REPO_FIELDS


def graphql_request(query: str, variables: dict, token: str) -> dict:
    headers = {
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "variables": variables}
    response = requests.post(GRAPHQL_URL, json=payload, headers=headers, timeout=30)
    response.raise_for_status()

    # GraphQL devolve HTTP 200 mesmo com erro, então é preciso checar "errors".
    body = response.json()
    if body.get("errors"):
        msgs = "; ".join(e.get("message", "?") for e in body["errors"])
        raise RuntimeError(f"GraphQL error: {msgs}")
    return body["data"]


def fetch_repos(query: str, owner_key: str, login: str, token: str) -> list:
    """Busca todas as páginas de repositórios de um user ou org."""
    repos = []
    cursor = None
    while True:
        data = graphql_request(query, {"login": login, "after": cursor}, token)
        owner = data.get(owner_key)
        if owner is None:
            raise RuntimeError(f"'{login}' não encontrado (ou token sem acesso).")

        conn = owner["repositories"]
        repos.extend(node for node in conn["nodes"] if node)

        if not conn["pageInfo"]["hasNextPage"]:
            return repos
        cursor = conn["pageInfo"]["endCursor"]


def get_languages(username: str, orgs: list, token: str) -> dict:
    repos = fetch_repos(USER_REPOS_QUERY, "user", username, token)
    for org in orgs:
        repos += fetch_repos(ORG_REPOS_QUERY, "organization", org, token)

    ignored = {lang.lower() for lang in IGNORED_LANGUAGES}

    seen = set()
    languages = {}
    for repo in repos:
        key = repo["nameWithOwner"]
        if key in seen:
            continue
        seen.add(key)

        for edge in (repo.get("languages") or {}).get("edges") or []:
            if not edge or not edge.get("node"):
                continue
            name = edge["node"].get("name")
            if not name or name.lower() in ignored:
                continue
            languages[name] = languages.get(name, 0) + edge.get("size", 0)

    return dict(sorted(languages.items(), key=lambda x: x[1], reverse=True))


def bucket_languages(languages: dict, threshold: float = 1.0) -> dict:
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


def percent_bar(percent: float, width: int = 20) -> str:
    percent = max(0, min(100, percent))
    filled = round((percent / 100) * width)
    empty = width - filled
    return f"{'█' * filled}{'░' * empty}"


def lang_line(name: str, percent: float, name_width: int = 8, bar_width: int = 20) -> str:
    bar = percent_bar(percent, bar_width)
    return f"{name:<{name_width}} {bar}  {percent:4.1f}%"


def render_languages(languages: dict) -> str:
    total_lang_size = sum(languages.values())

    code_block = ["```"]
    for lang, size in languages.items():
        percent = (size / total_lang_size) * 100 if total_lang_size > 0 else 0
        code_block.append("\t" + lang_line(lang, percent))
    code_block.append("```")

    return "\n".join(code_block) + "\n"


def generate_readme(username: str, orgs: list, token: str, path: str = "README.md"):
    raw_languages = get_languages(username, orgs, token)
    languages = bucket_languages(raw_languages, threshold=1.0)

    card = render_languages(languages)

    CONFIG = {
        "interests": "Machine Learning, Data Science, Python, C++",
        "tech_stack": "C, C++, Python, SQL",
    }

    about = textwrap.dedent(
        f"""\
        ### About me/Sobre mim

        **Interests/Interesses**: {CONFIG['interests']}

        **Technologies/Tecnologias**: {CONFIG['tech_stack']}
        """
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(about)
        f.write("\n")
        f.write(card)


if __name__ == "__main__":
    token = os.getenv("GITHUB_TOKEN", "")

    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is not set.")

    generate_readme(USERNAME, EXTRA_ORGS, token)
