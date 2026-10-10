"""
Neofetch-style GitHub profile card for ynahmany.

Fetches live stats from the GitHub GraphQL API and renders dark_mode.svg and
light_mode.svg. Runs daily via .github/workflows/build.yaml.

Env vars:
  ACCESS_TOKEN  personal access token (see README_SETUP.md)
  USER_NAME     GitHub login (defaults to CONFIG["username"])

Edit CONFIG below to change what the card says.
"""
import datetime as dt
import json
import os
import sys
import time
from xml.sax.saxutils import escape

import requests
from dateutil import relativedelta

# ─────────────────────────────── EDIT ME ───────────────────────────────
CONFIG = {
    "username": "ynahmany",
    "header": "yohay@nahmany",
    # Set to "YYYY-MM-DD" to show your age as "Uptime".
    # Leave as None to show how long your GitHub account has existed instead.
    "birthday": None,
    # Each section: (title or None, [(key, value), ...])
    "sections": [
        (None, [
            ("OS", "macOS, Linux, iOS"),
            ("Uptime", "{uptime}"),
            ("Host", "Pruvo (PruvoAI)"),
            ("Kernel", "Director of Engineering"),
            ("IDE", "VS Code, Claude Code"),
            ("Location", "Barcelona, ES"),
        ]),
        ("", [
            ("Languages.Programming", "TypeScript, JavaScript, Python"),
            ("Languages.Computer", "SQL, GraphQL, YAML, Markdown"),
            ("Languages.Real", "Hebrew, English, Spanish"),
        ]),
        ("", [
            ("Stack.Cloud", "AWS, Node.js, LoopBack"),
            ("Stack.Tools", "GitHub, GitLab, Notion"),
            ("Interests.Eng", "Developer Experience, AI Dev Tools"),
            ("Interests.Org", "Engineering Process & Scale"),
        ]),
        ("Contact", [
            ("LinkedIn", "ynahmany"),
            ("Web", "pruvo.com"),
        ]),
    ],
    "line_width": 60,  # characters per info line (dots fill the gap)
}

THEMES = {
    "dark_mode.svg": {
        "bg": "#161b22", "text": "#c9d1d9", "key": "#ffa657", "value": "#a5d6ff",
        "cc": "#616e7f", "add": "#3fb950", "del": "#f85149",
    },
    "light_mode.svg": {
        "bg": "#f6f8fa", "text": "#24292f", "key": "#953800", "value": "#0a3069",
        "cc": "#c2cfde", "add": "#1a7f37", "del": "#cf222e",
    },
}
# ───────────────────────────────────────────────────────────────────────

TOKEN = os.environ.get("ACCESS_TOKEN")
USER = os.environ.get("USER_NAME") or CONFIG["username"]
HEADERS = {"Authorization": f"bearer {TOKEN}"} if TOKEN else {}
CACHE_FILE = os.path.join("cache", f"{USER}.json")
API_CALLS = 0


# ─────────────────────────── GitHub GraphQL ────────────────────────────
def gql(query, variables=None, retries=3):
    global API_CALLS
    for attempt in range(retries):
        API_CALLS += 1
        r = requests.post("https://api.github.com/graphql",
                          json={"query": query, "variables": variables or {}},
                          headers=HEADERS, timeout=60)
        if r.status_code == 200 and "errors" not in r.json():
            return r.json()["data"]
        if r.status_code in (502, 503, 504) or r.status_code == 403:
            time.sleep(5 * (attempt + 1))
            continue
        raise RuntimeError(f"GraphQL error {r.status_code}: {r.text[:500]}")
    raise RuntimeError(f"GraphQL failed after {retries} attempts: {r.status_code} {r.text[:300]}")


def get_user():
    d = gql("""query($login:String!){ user(login:$login){
        id createdAt followers{totalCount} } }""", {"login": USER})["user"]
    return d["id"], dt.datetime.fromisoformat(d["createdAt"].replace("Z", "+00:00")), d["followers"]["totalCount"]


def get_repos(affiliations):
    """All repos for the given affiliations: [{name, stars, commits}]"""
    repos, cursor = [], None
    while True:
        d = gql("""query($login:String!,$aff:[RepositoryAffiliation],$cursor:String){
          user(login:$login){ repositories(first:60, after:$cursor, ownerAffiliations:$aff){
            totalCount
            pageInfo{ hasNextPage endCursor }
            nodes{ nameWithOwner stargazerCount
              defaultBranchRef{ target{ ... on Commit{ history{ totalCount } } } } } } } }""",
                {"login": USER, "aff": affiliations, "cursor": cursor})["user"]["repositories"]
        for n in d["nodes"]:
            ref = n["defaultBranchRef"]
            repos.append({"name": n["nameWithOwner"], "stars": n["stargazerCount"],
                          "commits": ref["target"]["history"]["totalCount"] if ref else 0})
        if not d["pageInfo"]["hasNextPage"]:
            return d["totalCount"], repos
        cursor = d["pageInfo"]["endCursor"]


def contributions_total(created_at):
    """Sum of commit contributions (public + private if shown on profile) for every year."""
    total, start = 0, created_at
    now = dt.datetime.now(dt.timezone.utc)
    while start < now:
        end = min(start + dt.timedelta(days=365), now)
        d = gql("""query($login:String!,$from:DateTime!,$to:DateTime!){ user(login:$login){
            contributionsCollection(from:$from,to:$to){ totalCommitContributions restrictedContributionsCount } } }""",
                {"login": USER, "from": start.isoformat(), "to": end.isoformat()})
        c = d["user"]["contributionsCollection"]
        total += c["totalCommitContributions"] + c["restrictedContributionsCount"]
        start = end
    return total


def repo_loc(name, user_id):
    """Walk default-branch history; sum additions/deletions/commits authored by user_id."""
    owner, repo = name.split("/")
    add = dele = mine = 0
    cursor = None
    while True:
        d = gql("""query($owner:String!,$repo:String!,$cursor:String){ repository(owner:$owner,name:$repo){
            defaultBranchRef{ target{ ... on Commit{ history(first:100, after:$cursor){
              pageInfo{ hasNextPage endCursor }
              nodes{ additions deletions author{ user{ id } } } } } } } } }""",
                {"owner": owner, "repo": repo, "cursor": cursor})
        ref = d["repository"]["defaultBranchRef"]
        if not ref:
            return add, dele, mine
        h = ref["target"]["history"]
        for n in h["nodes"]:
            if n["author"] and n["author"]["user"] and n["author"]["user"]["id"] == user_id:
                add += n["additions"]
                dele += n["deletions"]
                mine += 1
        if not h["pageInfo"]["hasNextPage"]:
            return add, dele, mine
        cursor = h["pageInfo"]["endCursor"]


def loc_stats(repos, user_id):
    """LOC with a per-repo cache: a repo is only re-scanned when its commit count changes."""
    os.makedirs("cache", exist_ok=True)
    try:
        with open(CACHE_FILE) as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}
    new_cache = {}
    for r in repos:
        c = cache.get(r["name"])
        if not c or c["commits"] != r["commits"]:
            try:
                a, d, m = repo_loc(r["name"], user_id)
            except RuntimeError as e:
                print(f"  ! skipped {r['name']}: {e}", file=sys.stderr)
                if c:
                    new_cache[r["name"]] = c
                continue
            c = {"commits": r["commits"], "add": a, "del": d, "mine": m}
        new_cache[r["name"]] = c
    with open(CACHE_FILE, "w") as f:
        json.dump(new_cache, f, indent=1, sort_keys=True)
    add = sum(c["add"] for c in new_cache.values())
    dele = sum(c["del"] for c in new_cache.values())
    return add, dele


def uptime(since):
    now = dt.datetime.now(dt.timezone.utc)
    diff = relativedelta.relativedelta(now, since)
    p = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    cake = " 🎂" if CONFIG["birthday"] and diff.months == 0 and diff.days == 0 else ""
    return f"{p(diff.years, 'year')}, {p(diff.months, 'month')}, {p(diff.days, 'day')}{cake}"


# ───────────────────────────── SVG render ──────────────────────────────
CHAR_W, LINE_H, FONT = 9.65, 20, 16


def seg(text, cls=None):
    return (text, cls)


def kv(key, value, width):
    """'. Key: ........ value' padded to width"""
    fill = width - len(". ") - len(key) - len(": ") - len(value) - 1
    dots = " " + "." * max(1, fill) + " " if fill > 2 else " "
    return [seg(". ", "cc"), seg(key, "key"), seg(":"), seg(dots, "cc"), seg(value, "value")]


def kv_short(key, value, width):
    """Same as kv but for side-by-side stats (fixed width chunk)."""
    fill = width - len(key) - len(": ") - len(value)
    dots = " " + "." * max(1, fill - 1) + " " if fill > 2 else " "
    return [seg(key, "key"), seg(":"), seg(dots, "cc"), seg(value, "value")]


def rule(title, width):
    if title is None:
        return None
    if title == "":
        return [seg("—" * width, "cc")]
    head = f"- {title} "
    return [seg(head), seg("—" * (width - len(head)), "cc")]


def build_info(stats):
    W = CONFIG["line_width"]
    lines = [[seg(CONFIG["header"]), seg(" " + "—" * (W - len(CONFIG["header"]) - 1), "cc")]]
    for title, items in CONFIG["sections"]:
        r = rule(title, W)
        if r:
            lines.append(r)
        for k, v in items:
            lines.append(kv(k, v.format(**stats), W))
    lines.append(rule("GitHub Stats", W))
    f = lambda n: f"{n:,}"
    half = (W - len(". ") - len(" | ")) // 2
    lines.append([seg(". ", "cc")] + kv_short("Repos", f"{f(stats['repos'])} {{Contributed: {f(stats['contrib'])}}}", half)
                 + [seg(" | ")] + kv_short("Stars", f(stats["stars"]), W - 2 - 3 - half))
    lines.append([seg(". ", "cc")] + kv_short("Commits", f(stats["commits"]), half)
                 + [seg(" | ")] + kv_short("Followers", f(stats["followers"]), W - 2 - 3 - half))
    loc_val = f(stats["loc_add"] - stats["loc_del"])
    tail = [seg(" ( "), seg(f(stats["loc_add"]) + "++", "add"), seg(", "), seg(f(stats["loc_del"]) + "--", "del"), seg(" )")]
    tail_len = sum(len(t) for t, _ in tail)
    lines.append(kv("Lines of Code on GitHub", loc_val, W - tail_len) + tail)
    return lines


def render(filename, theme, ascii_lines, info_lines):
    ascii_cols = max((len(l) for l in ascii_lines), default=0)
    info_x = 15 + ascii_cols * CHAR_W + 30
    width = int(info_x + CONFIG["line_width"] * CHAR_W + 20)
    rows = max(len(ascii_lines), len(info_lines))
    height = rows * LINE_H + 40
    a_off = (rows - len(ascii_lines)) * LINE_H // 2
    i_off = (rows - len(info_lines)) * LINE_H // 2

    out = [f'<?xml version="1.0" encoding="utf-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,\'DejaVu Sans Mono\',monospace" '
           f'width="{width}px" height="{height}px" font-size="{FONT}px">',
           "<style>",
           "@font-face{font-family:ConsolasFallback;src:local('Consolas');size-adjust:109%}",
           f".key{{fill:{theme['key']}}} .value{{fill:{theme['value']}}} .cc{{fill:{theme['cc']}}}",
           f".add{{fill:{theme['add']}}} .del{{fill:{theme['del']}}}",
           "text,tspan{white-space:pre}",
           "</style>",
           f'<rect width="{width}px" height="{height}px" fill="{theme["bg"]}" rx="15"/>',
           f'<text x="15" y="30" fill="{theme["text"]}" class="ascii">']
    for i, l in enumerate(ascii_lines):
        out.append(f'<tspan x="15" y="{30 + a_off + i * LINE_H}">{escape(l)}</tspan>')
    out.append("</text>")
    out.append(f'<text x="{info_x:.0f}" y="30" fill="{theme["text"]}">')
    for i, line in enumerate(info_lines):
        y = 30 + i_off + i * LINE_H
        parts = [f'<tspan x="{info_x:.0f}" y="{y}">']
        for text, cls in line:
            parts.append(f'<tspan class="{cls}">{escape(text)}</tspan>' if cls else f"<tspan>{escape(text)}</tspan>")
        parts.append("</tspan>")
        out.append("".join(parts))
    out.append("</text></svg>")
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


# ─────────────────────────────── main ──────────────────────────────────
def main(demo=False):
    t0 = time.perf_counter()
    if demo or not TOKEN:
        print("No ACCESS_TOKEN (or --demo): rendering with sample numbers.")
        stats = dict(repos=12, contrib=48, stars=34, commits=2345, followers=27,
                     loc_add=412_389, loc_del=118_204,
                     uptime=uptime(dt.datetime(2014, 3, 1, tzinfo=dt.timezone.utc)))
    else:
        user_id, created_at, followers = get_user()
        repos_owned, owned = get_repos(["OWNER"])
        contrib_count, all_repos = get_repos(["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"])
        loc_add, loc_del = loc_stats(all_repos, user_id)
        since = (dt.datetime.fromisoformat(CONFIG["birthday"]).replace(tzinfo=dt.timezone.utc)
                 if CONFIG["birthday"] else created_at)
        stats = dict(repos=repos_owned, contrib=contrib_count,
                     stars=sum(r["stars"] for r in owned),
                     commits=contributions_total(created_at), followers=followers,
                     loc_add=loc_add, loc_del=loc_del, uptime=uptime(since))

    def load_art(name):
        for fn in (name, "ascii.txt"):
            if os.path.exists(fn):
                with open(fn, encoding="utf-8") as f:
                    return f.read().rstrip("\n").split("\n")
        return []

    info = build_info(stats)
    for fn, theme in THEMES.items():
        art = load_art("ascii_dark.txt" if fn.startswith("dark") else "ascii_light.txt")
        render(fn, theme, art, info)
    print(json.dumps({k: v for k, v in stats.items()}, ensure_ascii=False, indent=1))
    print(f"Done in {time.perf_counter() - t0:.2f}s, {API_CALLS} GraphQL calls.")


if __name__ == "__main__":
    main(demo="--demo" in sys.argv)
