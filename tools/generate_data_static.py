"""
generate_data.py
================

This script reads project data from the Eclipse SDV API or from a local
JSON file and generates a `data.yml` file in the Landscape2 configuration
format. The generated YAML can then be used as input for the
`PLeVasseur/eclipse‑sdv‑projects‑landscape2` repository.

Usage::

    python generate_data.py --input projects.json --output data.yml

If no input JSON is provided, the script attempts to fetch the data
directly from the API (`https://projects.eclipse.org/api/projects?working_group=sdv&pagesize=90000`).

The script groups projects according to the `category` field in the
JSON data. If the category follows the pattern ``A / B`` then ``A`` is
used as the category and ``B`` as the subcategory. Fields that are not
present in the input are omitted.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests
import yaml


API_URL = (
    "https://projects.eclipse.org/api/projects?working_group=sdv&pagesize=90000"
)
GITHUB_API_URL = "https://api.github.com"
_WARNED_KEYS: set[str] = set()


def warn_once(key: str, message: str) -> None:
    """Print warning message only once per key."""
    if key in _WARNED_KEYS:
        return
    _WARNED_KEYS.add(key)
    print(message, file=sys.stderr)


def fetch_projects_from_api() -> List[Dict[str, Any]]:
    """Fetch projects from the Eclipse SDV API.

    Returns a list of project dictionaries.
    """
    resp = requests.get(API_URL)
    resp.raise_for_status()
    return resp.json()


def load_projects_from_file(path: Path) -> List[Dict[str, Any]]:
    """Load projects from a local JSON file."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_static_categories(path: Path) -> List[Dict[str, Any]]:
    """Load static category definitions from a YAML file.

    The file must contain a mapping with a top‑level `categories` key. Each
    category entry should define `name`, `subcategories` and `items` as
    illustrated in `static_categories.yml`.

    Returns the list of categories.
    """
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("categories", [])


def download_logo(url: str, dest: Path) -> str:
    """Download a logo from a URL and save it into dest.

    Returns the file name of the saved logo. On failure, returns the
    placeholder file name. The file is saved in ``dest``.
    """
    try:
        file_name = url.split("/")[-1].split("?")[0]
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        file_path = dest / file_name
        with file_path.open("wb") as f:
            f.write(response.content)
        return file_name
    except Exception:
        return "placeholder.svg"


def extract_github_slug(repo_url: str) -> str | None:
    """Extract owner/repo slug from a GitHub repository URL."""
    if not repo_url:
        return None
    repo_url = repo_url.strip()
    if repo_url.startswith("git@github.com:"):
        path = repo_url.split(":", maxsplit=1)[1]
    else:
        parsed = urlparse(repo_url)
        if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            return None
        path = parsed.path.lstrip("/")

    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        return None
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return f"{parts[0]}/{repo}"


def get_github_headers() -> Dict[str, str]:
    """Build headers for GitHub API requests."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "eclipse-sdv-landscape-generator",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_org_repositories(
    owner: str,
    ignored_repos: set[str],
    org_repo_cache: Dict[str, List[str]],
) -> List[str]:
    """Fetch all public repository URLs for a GitHub org/user."""
    if not owner:
        return []
    if owner in org_repo_cache:
        return org_repo_cache[owner]

    headers = get_github_headers()
    repos: List[str] = []

    def fetch_pages(base_url: str) -> List[str] | None:
        page = 1
        urls: List[str] = []
        while True:
            response = requests.get(
                f"{base_url}?per_page=100&type=public&sort=pushed&direction=desc&page={page}",
                headers=headers,
                timeout=15,
            )
            if response.status_code == 404:
                return None
            if response.status_code == 403 and "rate limit" in response.text.lower():
                warn_once(
                    "github_rate_limit",
                    "GitHub API rate limit reached. Set GITHUB_TOKEN (or use --github-token) to fetch all repositories and releases.",
                )
                return []
            response.raise_for_status()
            data = response.json()
            if not data:
                break
            for repo in data:
                name = repo.get("name")
                full_name = repo.get("full_name")
                html_url = repo.get("html_url")
                if not html_url:
                    continue
                if name in ignored_repos or full_name in ignored_repos:
                    continue
                urls.append(html_url)
            if len(data) < 100:
                break
            page += 1
        return urls

    try:
        repos = fetch_pages(f"{GITHUB_API_URL}/orgs/{owner}/repos") or []
        if not repos:
            repos = fetch_pages(f"{GITHUB_API_URL}/users/{owner}/repos") or []
    except requests.RequestException:
        repos = []

    org_repo_cache[owner] = repos
    return repos


def parse_latest_release_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize GitHub release payload to output structure."""
    return {
        "tag_name": payload.get("tag_name"),
        "name": payload.get("name"),
        "url": payload.get("html_url"),
        "published_at": payload.get("published_at"),
    }


def fetch_latest_release(
    repo_url: str,
    release_cache: Dict[str, Dict[str, Any] | None],
) -> Dict[str, Any] | None:
    """Fetch latest release metadata for a GitHub repository URL."""
    slug = extract_github_slug(repo_url)
    if not slug:
        return None
    if slug in release_cache:
        return release_cache[slug]

    headers = get_github_headers()

    try:
        response = requests.get(
            f"{GITHUB_API_URL}/repos/{slug}/releases?per_page=1",
            headers=headers,
            timeout=10,
        )
        if response.status_code == 404:
            release_cache[slug] = None
            return None
        if response.status_code == 403 and "rate limit" in response.text.lower():
            warn_once(
                "github_rate_limit",
                "GitHub API rate limit reached. Set GITHUB_TOKEN (or use --github-token) to fetch all repositories and releases.",
            )
            release_cache[slug] = None
            return None
        response.raise_for_status()
        releases = response.json()
        if releases:
            release_data = parse_latest_release_payload(releases[0])
            release_cache[slug] = release_data
            return release_data

        # Fallback for repositories without formal releases: use latest tag.
        response = requests.get(
            f"{GITHUB_API_URL}/repos/{slug}/tags?per_page=1",
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        tags = response.json()
        if not tags:
            release_cache[slug] = None
            return None
        tag_name = tags[0].get("name")
        release_data = {
            "tag_name": tag_name,
            "name": tag_name,
            "url": f"https://github.com/{slug}/releases/tag/{tag_name}" if tag_name else None,
            "published_at": None,
        }
        release_cache[slug] = release_data
        return release_data
    except requests.RequestException:
        release_cache[slug] = None
        return None


def collect_repositories(
    project: Dict[str, Any],
    release_cache: Dict[str, Dict[str, Any] | None],
    org_repo_cache: Dict[str, List[str]],
) -> tuple[List[str], List[Dict[str, Any]]]:
    """Collect all repository URLs and their latest release metadata."""
    explicit_repo_urls: List[str] = []
    repo_urls_set: set[str] = set()
    for repo in project.get("github_repos") or []:
        repo_url = (repo or {}).get("url")
        if not repo_url:
            continue
        normalized_url = repo_url.rstrip("/")
        if normalized_url not in repo_urls_set:
            explicit_repo_urls.append(normalized_url)
            repo_urls_set.add(normalized_url)

    github = project.get("github") if isinstance(project.get("github"), dict) else {}
    owner = (github or {}).get("org")
    ignored_repos = set((github or {}).get("ignored_repos") or [])
    discovered_repo_urls: List[str] = []

    if owner:
        discovered_repo_urls = fetch_org_repositories(owner, ignored_repos, org_repo_cache)

    for repo_url in discovered_repo_urls:
        repo_urls_set.add(repo_url.rstrip("/"))

    # Preserve explicitly mapped project repositories first.
    repo_urls: List[str] = list(explicit_repo_urls)
    for repo_url in discovered_repo_urls:
        normalized_url = repo_url.rstrip("/")
        if normalized_url not in repo_urls:
            repo_urls.append(normalized_url)
    for repo_url in sorted(repo_urls_set):
        if repo_url not in repo_urls:
            repo_urls.append(repo_url)
    repositories: List[Dict[str, Any]] = []
    for repo_url in repo_urls:
        repositories.append(
            {
                "url": repo_url,
                "latest_release": fetch_latest_release(repo_url, release_cache),
            }
        )
    return repo_urls, repositories


def build_landscape_from_static(
    projects: List[Dict[str, Any]],
    static_categories: List[Dict[str, Any]],
    logo_dir: Path | None = None,
) -> Dict[str, Any]:
    """Build landscape data using a static category mapping.

    Projects are looked up by name according to the items lists in the
    supplied `static_categories`. Any project not found in the mapping
    will be placed into a fallback "Misc" subcategory under an
    automatically created "Unmapped" category.

    If ``logo_dir`` is provided, logos are downloaded into this directory
    and only the file name is referenced in the YAML. Otherwise, full
    URLs or the placeholder value are used.
    """
    # Prepare lookup of projects by name
    projects_by_name: Dict[str, Dict[str, Any]] = {p.get("name"): p for p in projects}
    assigned: set[str] = set()

    # Ensure logo directory exists if specified
    if logo_dir is not None:
        logo_dir.mkdir(parents=True, exist_ok=True)

    output_categories: List[Dict[str, Any]] = []
    release_cache: Dict[str, Dict[str, Any] | None] = {}
    org_repo_cache: Dict[str, List[str]] = {}

    def build_item(project: Dict[str, Any]) -> Dict[str, Any]:
        """Construct a landscape item record from project data."""
        item: Dict[str, Any] = {
            "name": project.get("name"),
            "description": project.get("summary"),
            "homepage_url": project.get("url"),
        }
        state = project.get("state")
        if state:
            item["project"] = state
        repo_urls, repositories = collect_repositories(
            project, release_cache, org_repo_cache
        )
        if repo_urls:
            item["repo_url"] = repo_urls[0]
            item["repo_urls"] = repo_urls
            item["repositories"] = repositories
        logo_url = project.get("logo")
        if logo_dir is not None and logo_url:
            file_name = download_logo(logo_url, logo_dir)
            item["logo"] = file_name
        else:
            if logo_url:
                item["logo"] = logo_url
            else:
                item["logo"] = "placeholder.svg"
        return item

    # Build categories and subcategories according to static mapping
    for cat in static_categories:
        cat_name: str = cat.get("name", "")
        new_cat: Dict[str, Any] = {"name": cat_name, "subcategories": []}
        for sub in cat.get("subcategories", []):
            sub_name: str = sub.get("name", "")
            new_sub: Dict[str, Any] = {"name": sub_name, "items": []}
            for proj_name in sub.get("items", []):
                proj_data = projects_by_name.get(proj_name)
                if proj_data:
                    new_sub["items"].append(build_item(proj_data))
                    assigned.add(proj_name)
            new_cat["subcategories"].append(new_sub)
        output_categories.append(new_cat)

    # Handle projects that were not assigned to any static category
    unassigned_items: List[Dict[str, Any]] = []
    for proj_name, proj_data in projects_by_name.items():
        if proj_name not in assigned:
            unassigned_items.append(build_item(proj_data))

    if unassigned_items:
        misc_category = {
            "name": "Unmapped",
            "subcategories": [
                {
                    "name": "Misc",
                    "items": unassigned_items,
                }
            ],
        }
        output_categories.append(misc_category)

    return {"categories": output_categories}


def build_landscape_from_dynamic(
    projects: List[Dict[str, Any]],
    logo_dir: Path | None = None,
) -> Dict[str, Any]:
    """Fallback dynamic grouping using the project's 'category' field.

    This function replicates the original behaviour of grouping projects by
    their `category` field. Each project may define its category as
    "Parent / Subcategory"; if no slash is present, the project is
    placed under a subcategory named "Misc". Projects lacking a
    category are placed under "Unknown/Misc".

    If ``logo_dir`` is provided, logo URLs are downloaded into this
    directory and the ``logo`` field references only the file name.
    Otherwise, the full URL or placeholder is used.
    """
    categories: Dict[str, Dict[str, Any]] = {}
    release_cache: Dict[str, Dict[str, Any] | None] = {}
    org_repo_cache: Dict[str, List[str]] = {}

    # Ensure logo directory exists if specified
    if logo_dir is not None:
        logo_dir.mkdir(parents=True, exist_ok=True)

    for proj in projects:
        # Determine category and subcategory names
        cat_str: str = proj.get("category", "Unknown")
        parts = [part.strip() for part in cat_str.split("/", maxsplit=1)]
        if len(parts) == 2:
            cat_name, subcat_name = parts
        else:
            cat_name = parts[0]
            subcat_name = "Misc"

        # Ensure category entry exists
        category = categories.setdefault(
            cat_name, {"name": cat_name, "subcategories": {}}
        )
        subcats = category["subcategories"]
        # Ensure subcategory entry exists
        subcat = subcats.setdefault(
            subcat_name, {"name": subcat_name, "items": []}
        )

        # Build item record
        item: Dict[str, Any] = {
            "name": proj.get("name"),
            "description": proj.get("summary"),
            "homepage_url": proj.get("url"),
        }

        # Map project state to the ``project`` field
        state = proj.get("state")
        if state:
            item["project"] = state

        # Add all GitHub repo URLs and their latest releases
        repo_urls, repositories = collect_repositories(
            proj, release_cache, org_repo_cache
        )
        if repo_urls:
            item["repo_url"] = repo_urls[0]
            item["repo_urls"] = repo_urls
            item["repositories"] = repositories

        # Handle logo
        logo_url = proj.get("logo")
        if logo_dir is not None and logo_url:
            # Download logo and use only the file name in YAML
            file_name = download_logo(logo_url, logo_dir)
            item["logo"] = file_name
        else:
            # Without download, keep full URL or fallback
            if logo_url:
                item["logo"] = logo_url
            else:
                item["logo"] = "placeholder.svg"

        # Append item to subcategory
        subcat["items"].append(item)

    # Convert nested dict of subcategories to list structure required by YAML
    category_list = []
    for cat in categories.values():
        subcat_list = []
        for subcat in cat["subcategories"].values():
            subcat_list.append(subcat)
        cat["subcategories"] = subcat_list
        category_list.append(cat)

    return {"categories": category_list}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate data.yml for landscape2")
    parser.add_argument(
        "--input",
        help="Path to a local JSON file containing project data (optional)",
    )
    parser.add_argument(
        "--output",
        default="data.yml",
        help="Name of the YAML file to generate (default: data.yml)",
    )
    parser.add_argument(
        "--categories",
        default="static_categories.yml",
        help=(
            "Path to a YAML file defining static categories. If provided, the script"
            " will organise projects according to this file. If not present,"
            " projects are grouped using their 'category' field."
        ),
    )
    parser.add_argument(
        "--github-token",
        help=(
            "Optional GitHub token used for repository/release lookups."
            " Equivalent to setting GITHUB_TOKEN."
        ),
    )
    args = parser.parse_args()

    if args.github_token:
        os.environ["GITHUB_TOKEN"] = args.github_token

    # Load projects
    if args.input:
        projects = load_projects_from_file(Path(args.input))
    else:
        projects = fetch_projects_from_api()

    # Download logos into a local 'logos' directory and reference them in YAML
    logo_dir = Path("logos")
    # If a categories file exists, load it; otherwise use dynamic grouping
    categories_path = Path(args.categories)
    if categories_path.exists():
        static_categories = load_static_categories(categories_path)
        landscape_data = build_landscape_from_static(
            projects, static_categories, logo_dir=logo_dir
        )
    else:
        # Fall back to dynamic grouping if no categories file is provided
        landscape_data = build_landscape_from_dynamic(
            projects, logo_dir=logo_dir
        )

    # Write YAML file
    out_path = Path(args.output)
    with out_path.open("w", encoding="utf-8") as f:
        yaml.dump(
            landscape_data,
            f,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    print(f"Generated {out_path}")


if __name__ == "__main__":
    main()
