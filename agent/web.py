"""Reading public web pages and files the way a visitor's browser would, with size limits.
Sites whose robots.txt asks every robot to stay out of the whole site are left alone."""
import collections
import hashlib
import pathlib
import re
import urllib.robotparser
from urllib.parse import urljoin, urlparse

import requests
import urllib3

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
API_UA = "studio-agent/1.0 (small-business marketing; contact via the site owner's GitHub)"
# A security check page instead of the site (not just a contact form with a captcha on it).
BOT_WALL = re.compile(r"<title>\s*(?:just a moment|attention required|access denied|security check|ddos-guard)|"
                      r"cf-chl-|cf_chl_|checking your browser|verify you are (?:a )?human|incapsula incident|"
                      r"sucuri website firewall|are you a robot", re.I)
Page = collections.namedtuple("Page", "url status headers text")

_robots = {}
_session = None


def session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    return _session


def host_of(url):
    host = (urlparse(url if "//" in (url or "") else "https://" + (url or "")).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def normalize(url):
    url = (url or "").strip()
    if not url:
        return ""
    return url if re.match(r"^https?://", url, re.I) else "https://" + url.lstrip("/")


def allowed(url):
    """False only when the site's robots.txt shuts out every robot from this page."""
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = session().get(base + "/robots.txt", timeout=8)
            rp.parse(r.text.splitlines() if r.status_code == 200 and len(r.text) < 200_000 else [])
        except requests.RequestException:
            rp.parse([])
        _robots[base] = rp
    try:
        return _robots[base].can_fetch("*", url)
    except Exception:
        return True


def fetch(url, timeout=15, limit=2_000_000, respect_robots=True):
    """A page as Page(url, status, headers, text), or None if it can't be read."""
    url = normalize(url)
    if not url or (respect_robots and not allowed(url)):
        return None
    for verify in (True, False):
        try:
            if not verify:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            r = session().get(url, timeout=timeout, stream=True, verify=verify, allow_redirects=True)
            try:
                chunks, size = [], 0
                for chunk in r.iter_content(65536):
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= limit:
                        break
                body = b"".join(chunks)[:limit].decode(r.encoding or "utf-8", errors="replace")
                return Page(r.url, r.status_code, dict(r.headers), body)
            finally:
                r.close()
        except requests.exceptions.SSLError:
            continue                                   # read it anyway: we only look, we don't log in
        except requests.RequestException:
            return None
    return None


def is_html(page):
    """Whether a fetched page is a web page (not a PDF, an image or a download)."""
    if page is None:
        return False
    kind = str((page.headers or {}).get("Content-Type") or (page.headers or {}).get("content-type") or "").lower()
    if kind and "html" not in kind and "text/plain" not in kind:
        return False
    return not page.text[:1024].lstrip().startswith(("%PDF", "\x89PNG", "GIF8", "PK\x03\x04"))


def blocked(page):
    if page is None:
        return False
    if page.status in (403, 429, 503):
        return True
    return len(page.text) < 60_000 and bool(BOT_WALL.search(page.text[:20000]))


def download(url, folder, max_bytes=8_000_000, kinds=("image/",), timeout=20):
    """Save a file (like a logo or photo) into folder, named by its address. Returns the path or None."""
    url = normalize(url)
    if not url.lower().startswith(("http://", "https://")):
        return None
    folder = pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha1(url.encode()).hexdigest()[:16]
    for existing in folder.glob(name + ".*"):
        return existing
    try:
        r = session().get(url, timeout=timeout, stream=True)
        kind = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
        if r.status_code != 200 or not kind.startswith(kinds):
            r.close()
            return None
        data, size = [], 0
        for chunk in r.iter_content(65536):
            data.append(chunk)
            size += len(chunk)
            if size > max_bytes:
                r.close()
                return None
        r.close()
    except requests.RequestException:
        return None
    ext = {"image/svg+xml": ".svg", "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
           "image/gif": ".gif", "image/x-icon": ".ico", "image/vnd.microsoft.icon": ".ico",
           "image/avif": ".avif"}.get(kind, ".bin")
    path = folder / (name + ext)
    path.write_bytes(b"".join(data))
    return path


def absolute(base, href):
    return urljoin(base, (href or "").strip())
