import html
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

username = os.environ["CREDLY_USERNAME"]
readme_path = Path(os.environ["CREDLY_README"])
badges_dir = Path(os.environ["CREDLY_OUTPUT_DIR"])
start = "<!--START_SECTION:credly-->"
end = "<!--END_SECTION:credly-->"
urls = [
    f"https://www.credly.com/users/{username}/badges.json",
    f"https://www.credly.com/users/{username}/badges?format=json",
]


def fetch(url):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; ptrvsrg-profile)",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


data = None
for url in urls:
    try:
        body = fetch(url).decode()
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"failed to fetch {url}: {error}")
        continue
    if body.strip().startswith("{"):
        data = json.loads(body)
        break

if data is None:
    print(
        f"failed to fetch badges for username {username}; keeping existing README section"
    )
    raise SystemExit(0)

badges_dir.mkdir(parents=True, exist_ok=True)
badges = []
for item in data.get("data", []):
    template = item.get("badge_template", {})
    image_url = template.get("image_url")
    badge_url = template.get("url")
    name = template.get("name")
    if image_url and badge_url and name:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        identifier = str(item.get("id") or template.get("id") or slug)
        extension = Path(urlparse(image_url).path).suffix or ".png"
        image_path = badges_dir / f"{slug}-{identifier}{extension}"
        image_path.write_bytes(fetch(image_url))
        name = html.escape(name)
        href = html.escape(badge_url, quote=True)
        src = html.escape(f"./{image_path.as_posix()}", quote=True)
        badges.append(
            f'<a href="{href}"><img src="{src}" title="{name}" alt="{name}" height="100" /></a>'
        )

if not badges:
    raise SystemExit(f"no badges found for username {username}")

readme = readme_path.read_text()
if start not in readme or end not in readme:
    raise SystemExit("badge markers not found in README.md")

start_idx = readme.index(start)
end_idx = readme.index(end) + len(end)
new_section = (
    start + '\n<div align="center">\n' + "\n".join(badges) + "\n</div>\n" + end
)
updated = readme[:start_idx] + new_section + readme[end_idx:]

if updated == readme:
    print("no changes detected")
else:
    readme_path.write_text(updated)
    print(f"updated {len(badges)} badge(s)")
