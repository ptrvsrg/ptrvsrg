import html
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

username = os.environ["GH_USERNAME"]
token = os.environ["GH_TOKEN"]
output_dir = Path(os.environ["ACHIEVEMENTS_OUTPUT_DIR"])
readme_path = Path(os.environ["ACHIEVEMENTS_README"])
threshold = os.environ["ACHIEVEMENTS_THRESHOLD"].upper()
display = os.environ["ACHIEVEMENTS_DISPLAY"].lower()
start = "<!--START_SECTION:achievements-->"
end = "<!--END_SECTION:achievements-->"

if not token:
    raise SystemExit("GH_TOKEN is required")
if display not in {"compact", "detailed"}:
    raise SystemExit("display must be either compact or detailed")


def request_json(url, *, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "ptrvsrg-achievements-action",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    if payload is not None:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode())


def request_text(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "ptrvsrg-achievements-action"}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode(errors="replace")


def load_achievement_icons():
    return json.loads((Path(__file__).with_name("icons.json")).read_text())


def graphql(query, variables=None):
    response = request_json(
        "https://api.github.com/graphql",
        method="POST",
        payload={"query": query, "variables": variables or {}},
    )
    if response.get("errors"):
        raise SystemExit(json.dumps(response["errors"], indent=2))
    return response["data"]


query = """
query Achievements($login: String!) {
  user(login: $login) {
    createdAt
    repositories(first: 100, privacy: PUBLIC, affiliations: OWNER, ownerAffiliations: OWNER, orderBy: {field: CREATED_AT, direction: ASC}) {
      totalCount
      nodes {
        createdAt
        forkCount
        stargazers { totalCount }
        languages(first: 20) { edges { node { name } } }
      }
    }
    forks: repositories(first: 1, privacy: PUBLIC, isFork: true, orderBy: {field: CREATED_AT, direction: ASC}) {
      totalCount
      nodes { createdAt }
    }
    popular: repositories(first: 1, privacy: PUBLIC, affiliations: OWNER, ownerAffiliations: OWNER, orderBy: {field: STARGAZERS, direction: DESC}) {
      nodes { stargazers { totalCount } }
    }
    pullRequests(first: 1, orderBy: {field: CREATED_AT, direction: ASC}) {
      totalCount
      nodes { createdAt }
    }
    contributionsCollection {
      pullRequestReviewContributions(first: 1, orderBy: {direction: ASC}) {
        totalCount
        nodes { occurredAt }
      }
    }
    projectsV2(first: 1, orderBy: {field: CREATED_AT, direction: ASC}) { totalCount }
    packages(first: 1, orderBy: {field: CREATED_AT, direction: ASC}) { totalCount }
    gists(first: 1, orderBy: {field: CREATED_AT, direction: ASC}) {
      totalCount
      nodes { createdAt }
    }
    organizations(first: 1) { totalCount }
    starredRepositories { totalCount }
    followers { totalCount }
    following { totalCount }
    sponsorshipsAsSponsor { totalCount }
    discussionsStarted: repositoryDiscussions { totalCount }
    discussionsComments: repositoryDiscussionComments { totalCount }
    discussionAnswers: repositoryDiscussionComments(onlyAnswers: true) { totalCount }
  }
  viewer { login }
  metrics: repository(owner: "lowlighter", name: "metrics") { viewerHasStarred }
  octocat: user(login: "octocat") { viewerIsFollowing }
}
"""

data = graphql(query, {"login": username})
user = data["user"]


def plural(value, singular="", plural_suffix="s"):
    return singular if int(value) == 1 else plural_suffix


def rank(value, levels):
    c, b, a, s, m = levels
    if value >= s:
        return "S", min(1, (value - s) / max(1, m - s))
    if value >= a:
        return "A", (value - a) / max(1, s - a)
    if value >= b:
        return "B", (value - b) / max(1, a - b)
    if value >= c:
        return "C", (value - c) / max(1, b - c)
    return "X", value / max(1, c)


def first_date(nodes, key="createdAt"):
    value = (nodes or [{}])[0].get(key)
    return value


def safe_rest_count(path):
    try:
        return len(request_json(f"https://api.github.com{path}"))
    except Exception:
        return 0


try:
    has_gpg = "BEGIN PGP PUBLIC KEY BLOCK" in request_text(
        f"https://github.com/{username}.gpg"
    )
except Exception:
    has_gpg = False
try:
    has_starred_topic = "doesn’t have any starred topics yet" not in request_text(
        f"https://github.com/stars/{username}/topics"
    )
except Exception:
    has_starred_topic = False

repos = user["repositories"]["nodes"]
languages = {
    edge["node"]["name"] for repo in repos for edge in repo["languages"]["edges"]
}
max_forks = max([repo["forkCount"] for repo in repos] or [0])
years_registered = (
    datetime.now(timezone.utc)
    - datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
).days / 365.2425
package_count = user["packages"]["totalCount"] + safe_rest_count(
    f"/users/{username}/packages?package_type=container"
)
viewer_login = data["viewer"]["login"]
icons = load_achievement_icons()

achievements = []


def add(title, text, value, levels=None, unlocked_at=None, forced_rank=None):
    if forced_rank:
        current_rank, progress = forced_rank, 1 if forced_rank == "$" else 0
    else:
        current_rank, progress = rank(float(value or 0), levels)

    achievements.append(
        {
            "title": title,
            "text": text,
            "value": value,
            "rank": current_rank,
            "progress": max(0, min(1, progress)),
            "unlocked_at": unlocked_at,
            "icon": icons.get(title, ""),
        }
    )


add(
    "Developer",
    f"Published {user['repositories']['totalCount']} public repositor{plural(user['repositories']['totalCount'], 'y', 'ies')}",
    user["repositories"]["totalCount"],
    [1, 20, 50, 100, 250],
    first_date(repos),
)
add(
    "Forker",
    f"Forked {user['forks']['totalCount']} public repositor{plural(user['forks']['totalCount'], 'y', 'ies')}",
    user["forks"]["totalCount"],
    [1, 5, 10, 20, 50],
    first_date(user["forks"]["nodes"]),
)
add(
    "Contributor",
    f"Opened {user['pullRequests']['totalCount']} pull request{plural(user['pullRequests']['totalCount'])}",
    user["pullRequests"]["totalCount"],
    [1, 200, 500, 1000, 2500],
    first_date(user["pullRequests"]["nodes"]),
)
add(
    "Manager",
    f"Created {user['projectsV2']['totalCount']} user project{plural(user['projectsV2']['totalCount'])}",
    user["projectsV2"]["totalCount"],
    [1, 2, 3, 4, 5],
)
reviews = user["contributionsCollection"]["pullRequestReviewContributions"]
add(
    "Reviewer",
    f"Reviewed {reviews['totalCount']} pull request{plural(reviews['totalCount'])}",
    reviews["totalCount"],
    [1, 200, 500, 1000, 2500],
    first_date(reviews["nodes"], "occurredAt"),
)
add(
    "Packager",
    f"Created {package_count} package{plural(package_count)}",
    package_count,
    [1, 5, 10, 20, 30],
)
add(
    "Gister",
    f"Published {user['gists']['totalCount']} gist{plural(user['gists']['totalCount'])}",
    user["gists"]["totalCount"],
    [1, 20, 50, 100, 250],
    first_date(user["gists"]["nodes"]),
)
add(
    "Worker",
    f"Joined {user['organizations']['totalCount']} organization{plural(user['organizations']['totalCount'])}",
    user["organizations"]["totalCount"],
    [1, 2, 4, 8, 10],
)
add(
    "Stargazer",
    f"Starred {user['starredRepositories']['totalCount']} repositor{plural(user['starredRepositories']['totalCount'], 'y', 'ies')}",
    user["starredRepositories"]["totalCount"],
    [1, 200, 500, 1000, 2500],
)
add(
    "Follower",
    f"Following {user['following']['totalCount']} user{plural(user['following']['totalCount'])}",
    user["following"]["totalCount"],
    [1, 200, 500, 1000, 2500],
)
add(
    "Influencer",
    f"Followed by {user['followers']['totalCount']} user{plural(user['followers']['totalCount'])}",
    user["followers"]["totalCount"],
    [1, 200, 500, 1000, 2500],
)
popular_stars = (user["popular"]["nodes"] or [{"stargazers": {"totalCount": 0}}])[0][
    "stargazers"
]["totalCount"]
add(
    "Maintainer",
    f"Maintaining a repository with {popular_stars} star{plural(popular_stars)}",
    popular_stars,
    [1, 1000, 5000, 10000, 25000],
)
add(
    "Inspirer",
    f"Maintaining or created a repository which has been forked {max_forks} time{plural(max_forks)}",
    max_forks,
    [1, 100, 500, 1000, 2500],
)
add(
    "Polyglot",
    f"Using {len(languages)} different programming language{plural(len(languages))}",
    len(languages),
    [1, 4, 8, 16, 32],
)
add(
    "Member",
    f"Registered {int(years_registered)} year{plural(int(years_registered))} ago",
    years_registered,
    [1, 3, 5, 10, 15],
)
add(
    "Sponsor",
    f"Sponsoring {user['sponsorshipsAsSponsor']['totalCount']} user{plural(user['sponsorshipsAsSponsor']['totalCount'])} or organization{plural(user['sponsorshipsAsSponsor']['totalCount'])}",
    user["sponsorshipsAsSponsor"]["totalCount"],
    [1, 3, 5, 10, 25],
)
discussions = (
    user["discussionsStarted"]["totalCount"] + user["discussionsComments"]["totalCount"]
)
add(
    "Chatter",
    f"Participated in discussions {discussions} time{plural(discussions)}",
    discussions,
    [1, 200, 500, 1000, 2500],
)
add(
    "Helper",
    f"Answered and solved {user['discussionAnswers']['totalCount']} discussion{plural(user['discussionAnswers']['totalCount'])}",
    user["discussionAnswers"]["totalCount"],
    [1, 20, 50, 100, 250],
)
add(
    "Verified",
    "Registered a GPG key to sign commits",
    has_gpg,
    forced_rank="$" if has_gpg else "X",
)
add(
    "Explorer",
    "Starred a topic on GitHub Explore",
    has_starred_topic,
    forced_rank="$" if has_starred_topic else "X",
)
add(
    "Automator",
    "Use GitHub Actions to automate profile updates",
    bool(os.environ.get("GITHUB_ACTIONS")),
    forced_rank="$" if os.environ.get("GITHUB_ACTIONS") else "X",
)
infographile = data["metrics"]["viewerHasStarred"] and username == viewer_login
add(
    "Infographile",
    "Fervent supporter of metrics",
    infographile,
    forced_rank="$" if infographile else "X",
)
octonaut = data["octocat"]["viewerIsFollowing"] and username == viewer_login
add("Octonaut", "Following octocat", octonaut, forced_rank="$" if octonaut else "X")

order = {"S": 5, "A": 4, "B": 3, "C": 2, "$": 1, "X": 0}
colors = {
    "S": ("#EB355E", "#731237"),
    "A": ("#B59151", "#FFD576"),
    "B": ("#7D6CFF", "#B2A8FF"),
    "C": ("#2088FF", "#79B8FF"),
    "$": ("#FF48BD", "#FF92D8"),
    "X": ("#7A7A7A", "#B0B0B0"),
}
threshold_score = order.get(threshold, 0)
selected = [item for item in achievements if order[item["rank"]] >= threshold_score]
selected.sort(key=lambda item: (order[item["rank"]], item["progress"]), reverse=True)

output_dir.mkdir(parents=True, exist_ok=True)
for stale in output_dir.glob("*.svg"):
    stale.unlink()


def slugify(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def render_svg(item):
    title = html.escape(item["title"])
    text = html.escape(item["text"])
    rank = item["rank"]
    primary, secondary = colors[rank]
    prefix = {"S": "Master", "A": "Super", "B": "Great"}.get(rank, "")
    display_title = (
        f'<span class="prefix">{prefix}</span> {title.lower() if prefix else title}'
    )
    rank_class = "secret" if rank == "$" else rank[0].lower()
    progress = item["progress"] if item["progress"] or rank != "X" else 0
    icon = item["icon"].replace("#primary", primary).replace("#secondary", secondary)
    value = item["value"]
    if isinstance(value, bool):
        value_label = "☆" if value else "?"
    elif isinstance(value, (int, float)):
        value_label = str(int(value))
    else:
        value_label = html.escape(str(value))
    css = '''svg{
        font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif;
        color:#777
    }
    .gauge{
        stroke-linecap:round;
        fill:none
    }
    .gauge-base,.gauge-arc{
        stroke:currentColor;
        stroke-width:6
    }
    .gauge-base{
        stroke-opacity:.2
    }
    .achievement{
        display:flex;
        margin:4px 0
    }
    .achievement .icon{
        margin:0 4px;
        width:44px;
        height:44px
    }
    .achievement .text{
        font-size:12px;
        color:#666
    }
    .achievement .title{
        font-size:14px;
        color:#58A6FF
    }
    .achievement .gauge.info{
        color:#58A6FF
    }
    .achievement .value{
        background-color:#58A6FF26
    }
    .achievement.x .title{
        color:#666
    }
    .achievement.x .gauge.info{
        color:#B0B0B0
    }
    .achievement.x .value{
        background-color:#B0B0B026
    }
    .achievement.b .title{
        color:#9D8FFF
    }
    .achievement.b .gauge.info{
        color:#9E91FF
    }
    .achievement.b .value{
        background-color:#9E91FF26
    }
    .achievement.a .title{
        color:#D79533
    }
    .achievement.a .gauge.info{
        color:#E7BD69
    }
    .achievement.a .value{
        background-color:#E7BD6926
    }
    .achievement.s .title{
        color:#EB355E
    }
    .achievement.s .gauge.info{
        color:#EB355E
    }
    .achievement.s .value{
        background-color:#EB355E26
    }
    .achievement.secret .title{
        color:#FF76CD
    }
    .achievement.secret .gauge.info{
        color:#FF79D1
    }
    .achievement.secret .value{
        background-color:#FF79D126
    }
    .achievement .gh,.achievement .value{
        border:1px solid currentColor;
        border-radius:16px;
        font-size:10px;
        padding:0 5px;
        white-space:nowrap
    }
    .achievement .value-wrapper{
        margin-bottom:-50px;
        margin-top:36px;
        display:none
    }
    .achievement .value{
        margin-left:46px
    }
    .achievements.compact{
        display:flex;
        flex-wrap:wrap
    }
    .achievements.compact .achievement{
        flex-direction:column-reverse;
        align-items:center;
        width:80px
    }
    .achievements.compact .info{
        width:100%
    }
    .achievements.compact .achievement .title{
        margin-bottom:2px;
        text-transform:capitalize;
        text-align:center
    }
    .achievements.compact .achievement .title .prefix{
        min-height:13px;
        font-size:10px;
        display:block;
        margin-bottom:-.25rem
    }
    .achievements.compact .achievement .value-wrapper{
        display:flex
    }
    .achievements.compact .achievement .text,.achievements.compact .achievement .gh{
        display:none
    }
'''
    width, height = (88, 96) if display == "compact" else (420, 64)
    achievement_html = f'''<section class="achievements {display}">
    <div class="achievement {rank_class}">
      <div class="icon">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 60" height="44" width="44">
          <defs>
            <mask id="mask">
              <circle class="gauge-base" r="25" cx="28" cy="28" fill="white"></circle>
            </mask>
          </defs>
          <svg xmlns="http://www.w3.org/2000/svg" class="gauge info">
            <circle class="gauge-base" r="25" cx="28" cy="28"></circle>
            <circle class="gauge-arc" transform="rotate(-90 28 28)" r="25" cx="28" cy="28" stroke-dasharray="{progress * 155} 155"></circle>
          </svg>
          <svg xmlns="http://www.w3.org/2000/svg" mask="url(#mask)">{icon}</svg>
        </svg>
      </div>
      <div class="info">
        <div class="title">
          {display_title}
          <div class="value-wrapper">
            <div class="value">{value_label}</div>
          </div>
        </div>
        <div class="text">{text}</div>
      </div>
    </div>
  </section>'''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">
  <style>{css}</style>
  <foreignObject width="100%" height="100%">
    <div xmlns="http://www.w3.org/1999/xhtml">
      {achievement_html}
    </div>
  </foreignObject>
</svg>
'''


links = []
for item in selected:
    filename = f"{order[item['rank']]}-{slugify(item['title'])}.svg"
    path = output_dir / filename
    path.write_text(render_svg(item))
    height = "96" if display == "compact" else "64"
    links.append(
        f'<img src="./{path.as_posix()}" title="{html.escape(item["title"], quote=True)}" alt="{html.escape(item["title"], quote=True)}" height="{height}" />'
    )

if not links:
    raise SystemExit("no achievements generated")

readme = readme_path.read_text()
if start not in readme or end not in readme:
    raise SystemExit("achievement markers not found in README")
before = readme[: readme.index(start)]
after = readme[readme.index(end) + len(end) :]
section = start + '\n<div align="center">\n' + "\n".join(links) + "\n</div>\n" + end
readme_path.write_text(before + section + after)
print(f"generated {len(links)} achievement svg(s)")
