"""The design trend radar: what's showing up in brand and graphic design right now.

Reads the public feeds of design publications (Behance's newest projects, Abduzeedo, The Dieline, Creative
Bloq, Dezeen) and counts the style directions they mention (serif revival, grain, brutalism, retro...), and
samples the colors of recent work. The result weights the design agent's styles toward what's current.
It's inspiration only: no one's work is copied, and their images are only looked at for colors.
"""
import collections
import datetime as dt
import html
import json
import re

from . import colors, web
from .settings import CACHE

FEEDS = {
    "Behance": "https://www.behance.net/feeds/projects",
    "Abduzeedo": "https://abduzeedo.com/rss.xml",
    "The Dieline": "https://thedieline.com/feed/",
    "Creative Bloq": "https://www.creativebloq.com/feeds.xml",
    "Dezeen": "https://www.dezeen.com/design/feed/",
}
# Words in design writing -> the agent's styles they point to.
SIGNALS = {
    "bold": ["bold type", "bold typography", "big type", "oversized", "condensed", "poster", "kinetic", "statement",
             "loud", "punchy", "typographic"],
    "editorial": ["serif", "editorial", "elegant", "magazine", "classic", "custom serif", "refined", "luxury", "heritage"],
    "gradient": ["gradient", "grain", "noise", "texture", "glow", "blur", "aura", "glass", "fluted glass", "iridescent"],
    "brutal": ["brutalis", "brutalism", "raw", "anti-design", "sticker", "collage", "playful", "maximalis", "chaotic"],
    "duotone": ["duotone", "monochrome", "two-tone", "risograph", "halftone", "print", "screen print"],
    "minimal": ["minimal", "swiss", "grid", "modernist", "clean", "restraint", "simple", "reductive"],
    "retro": ["retro", "vintage", "nostalg", "70s", "1970s", "groovy", "y2k", "throwback", "mid-century", "art deco"],
    "photo": ["photograph", "lifestyle", "cinematic", "campaign", "art direction"],
}
TERMS = sorted({t for words in SIGNALS.values() for t in words} | {
    "hand-drawn", "illustration", "3d", "motion", "packaging", "rebrand", "identity", "mascot", "pastel", "neon",
    "earthy", "monogram", "wordmark", "pattern", "ai-generated", "sustainab"})


def _items(name, xml):
    out = []
    for raw in re.findall(r"<item\b.*?>(.*?)</item>", xml, re.S)[:50]:
        def tag(t):
            m = re.search(rf"<{t}\b[^>]*>(.*?)</{t}>", raw, re.S)
            return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip() if m else ""
        body = tag("description") + " " + tag("content:encoded")
        img = re.search(r"""<img[^>]+src=['"]([^'"]+)['"]""", body) or re.search(
            r"""<(?:media:content|media:thumbnail|enclosure)[^>]+url=['"]([^'"]+)['"]""", raw)
        out.append({"source": name, "title": tag("title")[:160],
                    "text": re.sub(r"<[^>]+>", " ", body)[:600], "image": img.group(1) if img else "",
                    "link": tag("link"), "date": tag("pubDate")})
    return out


def collect():
    items = []
    for name, url in FEEDS.items():
        page = web.fetch(url, limit=3_000_000, respect_robots=False, timeout=25)
        if page and page.status == 200:
            items += _items(name, page.text)
    return items


def analyze(items, sample_images=18):
    text = " ".join((i["title"] + " " + i["text"]).lower() for i in items)
    weights = {style: sum(text.count(w) for w in words) for style, words in SIGNALS.items()}
    total = sum(weights.values()) or 1
    weights = {k: round(v / total, 3) for k, v in weights.items()}
    terms = collections.Counter({t: text.count(t) for t in TERMS if text.count(t)})
    swatches = collections.Counter()
    folder = CACHE / "design-trends"
    for item in [i for i in items if i["image"]][:sample_images]:
        path = web.download(item["image"], folder, max_bytes=3_000_000)
        if not path:
            continue
        for c, share in colors.from_image(path, k=5):
            if share > 0.08 and not colors.is_neutral(c):
                swatches[c] += share
    palette = [c for c, _ in colors.merge_similar(swatches, closeness=60)[:8]]
    return {"weights": weights, "terms": [t for t, _ in terms.most_common(12)], "palette": palette,
            "examples": [{"source": i["source"], "title": i["title"], "link": i["link"]} for i in items[:12]],
            "count": len(items)}


def radar(force=False):
    """This week's design directions, cached for a week. Never fails: returns even weights offline."""
    week = dt.date.today().strftime("%G-W%V")
    path = CACHE / "design-trends" / f"{week}.json"
    if path.exists() and not force:
        try:
            return json.loads(path.read_text())
        except ValueError:
            pass
    items = collect()
    data = analyze(items) if items else {"weights": {s: round(1 / len(SIGNALS), 3) for s in SIGNALS}, "terms": [],
                                         "palette": [], "examples": [], "count": 0}
    data["week"] = week
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1))
    return data
