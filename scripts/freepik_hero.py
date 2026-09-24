"""Swap the hero video for a Freepik stock clip (fiber-optic light streaks look).

Usage:
    python scripts/freepik_hero.py search [--per 8] ["custom query"]
    python scripts/freepik_hero.py pick <freepik_video_id>
    python scripts/freepik_hero.py get <id> [<id> ...]     # licensed download only, to the temp dir

Key: env FREEPIK_API_KEY, or %USERPROFILE%/.claude/footage-keys.json -> {"freepik": "..."}

`search` prints candidate clips with preview URLs. `pick` downloads the clip via the
licensed Freepik download endpoint, trims/encodes it to img/hero-fiber.mp4 (1920w) and
img/hero-fiber-sm.mp4 (1280w), writes img/hero-poster-fiber.jpg, and patches index.html.
"""
import json, os, re, subprocess, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOSTS = ["https://api.freepik.com", "https://api.magnific.com"]
KEYFILE = os.path.join(os.path.expanduser("~"), ".claude", "footage-keys.json")
UA = "Mozilla/5.0 montanadata-hero/1.0"

QUERIES = [
    "fiber optic light streaks dark blue network abstract",
    "data flow light lines dark background technology loop",
    "glowing light trails digital network futuristic dark",
]


def key():
    k = os.environ.get("FREEPIK_API_KEY")
    if not k and os.path.exists(KEYFILE):
        k = json.load(open(KEYFILE)).get("freepik")
    if not k or k.startswith("PASTE"):
        sys.exit("No Freepik key. Set FREEPIK_API_KEY or fill %s" % KEYFILE)
    return k


def get(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "x-freepik-api-key": key(), "User-Agent": UA, "Accept-Language": "en-US"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:300]}


def search(term, per):
    params = {
        "term": term, "page": 1, "order": "relevance", "limit": per,
        "filters[category]": "footage",
        "filters[orientation][]": "horizontal",
        "filters[resolution][1080]": 1,
        "filters[duration][from]": 8,
    }
    for host in HOSTS:
        st, body = get(host + "/v1/videos", params)
        if st == 200:
            return body.get("data", [])[:per]
    print("  Freepik %s: %s" % (st, body))
    return []


def cmd_search(argv):
    per = 8
    if "--per" in argv:
        i = argv.index("--per"); per = int(argv[i + 1]); del argv[i:i + 2]
    queries = argv or QUERIES
    for q in queries:
        print("\n== %s ==" % q)
        for v in search(q, per):
            prev = (v.get("previews") or [{}])[-1].get("url")
            print("  id=%-10s %3ss %-6s %s%s\n      preview: %s\n      page: %s" % (
                v.get("id"), v.get("duration"), v.get("aspect_ratio") or "",
                v.get("name"), "  [AI]" if v.get("is_ai_generated") else "",
                prev, v.get("url")))


def run(*args):
    print("  $", " ".join(args))
    subprocess.check_call(args)


def fetch(vid):
    """Licensed download of one clip into the temp dir; returns the local path."""
    for host in HOSTS:
        st, body = get("%s/v1/videos/%s/download" % (host, vid))
        if st == 200:
            break
    if st != 200:
        sys.exit("Download failed %s: %s" % (st, body))
    src = os.path.join(tempfile.gettempdir(), "freepik-%s.mp4" % vid)
    if not os.path.exists(src):
        print("  downloading", vid, "...")
        urllib.request.urlretrieve(body["data"]["url"], src)
    print("  ", src)
    return src


def cmd_pick(vid):
    for host in HOSTS:
        st, body = get("%s/v1/videos/%s/download" % (host, vid))
        if st == 200:
            break
    if st != 200:
        sys.exit("Download failed %s: %s" % (st, body))
    url = body["data"]["url"]
    src = os.path.join(tempfile.gettempdir(), "freepik-%s.mp4" % vid)
    print("  downloading", url[:80], "...")
    urllib.request.urlretrieve(url, src)

    img = os.path.join(ROOT, "img")
    big, sm, poster = [os.path.join(img, n) for n in
                       ("hero-fiber.mp4", "hero-fiber-sm.mp4", "hero-poster-fiber.jpg")]
    common = ["-an", "-t", "10", "-c:v", "libx264", "-preset", "slow", "-pix_fmt", "yuv420p",
              "-movflags", "+faststart"]
    run("ffmpeg", "-v", "error", "-y", "-i", src, "-vf", "scale=1920:-2", "-crf", "24", *common, big)
    run("ffmpeg", "-v", "error", "-y", "-i", src, "-vf", "scale=1280:-2", "-crf", "27", *common, sm)
    run("ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", big, "-frames:v", "1", "-q:v", "3", poster)

    html = os.path.join(ROOT, "index.html")
    s = open(html, encoding="utf-8").read()
    s = s.replace('data-src="img/hero-warehouse.mp4"', 'data-src="img/hero-fiber.mp4"')
    s = s.replace('data-src-sm="img/hero-warehouse-sm.mp4"', 'data-src-sm="img/hero-fiber-sm.mp4"')
    s = re.sub(r'img/hero-poster\.jpg', 'img/hero-poster-fiber.jpg', s)
    open(html, "w", encoding="utf-8").write(s)
    print("done: hero now uses img/hero-fiber.mp4 (+ -sm, poster). Reload http://127.0.0.1:8080/")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] not in ("search", "pick", "get"):
        sys.exit(__doc__)
    if a[0] == "search":
        cmd_search(a[1:])
    elif a[0] == "get":
        for vid in a[1:]:
            fetch(vid)
    else:
        cmd_pick(a[1])
