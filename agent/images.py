"""Free pictures for designs, in order of preference:

1. The business's own photos (from its website, or what a client sends).
2. Theme photos for a moment (pumpkins for Halloween, snow for a cold snap) from Pixabay or Pexels (free keys) or
   Openverse (no key; openly licensed, attribution kept). Never used to stand in for the business's own
   food, products or place.
3. Abstract AI backgrounds from Cloudflare Workers AI (free daily allowance), or Pollinations (no key) when
   allowed. Prompts always ask for illustration or abstract art, never a fake photo of real products.
"""
import base64
import hashlib
import json
import re
import time
import zlib

import requests

from . import web
from .settings import CACHE

FOLDER = CACHE / "images"
FLUX = "@cf/black-forest-labs/flux-1-schnell"
STYLE_HINT = ("abstract editorial illustration, flat shapes, soft grain, no text, no letters, no logos, "
              "no people, no faces, no real products")


def _name(*parts):
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def _searched(source, query, orientation, fetch):
    """A stock search's results, kept for a day (Pixabay asks for that, and it spares everyone's free limits)."""
    path = CACHE / "stock-searches.json"
    key = f"{source}|{query}|{orientation}"
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        saved = {}
    now = time.time()
    hit = saved.get(key)
    if hit and now - hit.get("at", 0) < 86400:
        return hit["items"]
    items = fetch()
    if items is not None:
        saved = {k: v for k, v in saved.items() if now - v.get("at", 0) < 86400}
        saved[key] = {"at": now, "items": items}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(saved))
        except OSError:
            pass
    return items or []


def _turn(items, vary):
    """The same search gives different businesses different photos: start at a place picked by vary."""
    if not items or not vary:
        return items
    i = zlib.crc32(vary.encode()) % len(items)
    return items[i:] + items[:i]


def stock(cfg, query, orientation="portrait", vary=""):
    """A free theme photo: {'path', 'credit', 'url'} or None. vary (a business's name, say) picks among the best
    results, so two businesses with the same moment don't get the same picture."""
    if not cfg["images"].get("stock_photos"):
        return None
    FOLDER.mkdir(parents=True, exist_ok=True)
    key = cfg.secret("PEXELS_API_KEY")
    try:
        if key:
            def pexels():
                r = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": key}, timeout=20,
                                 params={"query": query, "orientation": orientation, "per_page": 6})
                return [{"src": p["src"].get("large2x") or p["src"]["large"], "by": p.get("photographer"), "url": p.get("url")}
                        for p in r.json().get("photos", [])] if r.status_code == 200 else None
            for p in _turn(_searched("pexels", query, orientation, pexels), vary):
                path = web.download(p["src"], FOLDER)
                if path:
                    return {"path": str(path), "credit": f"Photo by {p.get('by') or 'Pexels'} on Pexels", "url": p.get("url")}
        pixabay = cfg.secret("PIXABAY_API_KEY")
        if pixabay:                             # free key; its license allows commercial use, photos are downloaded
            def search():
                r = requests.get("https://pixabay.com/api/", timeout=20,
                                 params={"key": pixabay, "q": query[:100], "image_type": "photo", "safesearch": "true",
                                         "orientation": "vertical" if orientation == "portrait" else "horizontal",
                                         "min_width": 900, "per_page": 6})
                return [{"src": h.get("largeImageURL") or h.get("webformatURL"), "by": h.get("user"), "url": h.get("pageURL")}
                        for h in r.json().get("hits", [])] if r.status_code == 200 else None
            for h in _turn(_searched("pixabay", query, orientation, search), vary):
                path = web.download(h["src"], FOLDER)
                if path:
                    return {"path": str(path), "credit": f"Photo by {h.get('by') or 'Pixabay'} on Pixabay", "url": h.get("url")}
        def openverse():
            r = requests.get("https://api.openverse.org/v1/images/", timeout=20, headers={"User-Agent": web.API_UA},
                             params={"q": query, "license_type": "commercial,modification", "page_size": 8,
                                     "aspect_ratio": "tall" if orientation == "portrait" else "wide", "mature": "false"})
            return [{k: item.get(k) for k in ("url", "width", "title", "creator", "license", "foreign_landing_url")}
                    for item in r.json().get("results", [])] if r.status_code == 200 else None
        for item in _turn([i for i in _searched("openverse", query, orientation, openverse) if (i.get("width") or 0) >= 900],
                          vary):
            path = web.download(item.get("url"), FOLDER)
            if path:
                credit = f"\"{item.get('title') or 'Photo'}\" by {item.get('creator') or 'unknown'} ({(item.get('license') or '').upper()})"
                return {"path": str(path), "credit": credit[:160], "url": item.get("foreign_landing_url")}
    except (requests.RequestException, ValueError, KeyError):
        return None
    return None


def ai_background(cfg, store, theme, palette=(), w=1024, h=1280):
    """An abstract, on-palette background for a theme. {'path', 'credit'} or None."""
    if not cfg["images"].get("ai_backgrounds"):
        return None
    if store.usage("ai_images", period="day") >= cfg["limits"]["ai_images_per_day"]:
        return None
    colors_hint = ", ".join(palette[:3])
    prompt = f"{theme}, {STYLE_HINT}, color palette {colors_hint}" if colors_hint else f"{theme}, {STYLE_HINT}"
    FOLDER.mkdir(parents=True, exist_ok=True)
    path = FOLDER / (_name(prompt, str(w), str(h)) + ".jpg")
    if path.exists():
        return {"path": str(path), "credit": "AI illustration"}
    account, token = cfg.secret("CLOUDFLARE_ACCOUNT_ID"), cfg.secret("CLOUDFLARE_API_TOKEN")
    data = None
    if account and token:
        try:
            r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{FLUX}",
                              headers={"Authorization": f"Bearer {token}"}, timeout=90,
                              json={"prompt": prompt, "steps": 4, "width": w, "height": h})
            if r.status_code == 200:
                data = base64.b64decode(r.json()["result"]["image"])
                store.add_usage("cf_neurons_est", 60, period="day")
        except (requests.RequestException, KeyError, ValueError):
            data = None
    if data is None and cfg["ai"].get("keyless_fallback"):
        try:
            r = requests.get("https://image.pollinations.ai/prompt/" + requests.utils.quote(prompt), timeout=90,
                             params={"width": w, "height": h, "nologo": "true", "model": "flux"})
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                data = r.content
        except requests.RequestException:
            data = None
    if not data:
        return None
    path.write_bytes(data)
    store.add_usage("ai_images", period="day")
    return {"path": str(path), "credit": "AI illustration"}


def theme_query(post):
    """A stock search for the moment (not the product): 'halloween pumpkins', 'snowy street'."""
    moment = (post.get("moment") or "").lower()
    table = {"halloween": "halloween pumpkins", "thanksgiving": "autumn harvest table", "christmas": "christmas lights",
             "valentine": "red hearts", "new year": "confetti celebration", "snow": "snowy street",
             "cold": "winter scarf", "heat": "summer sun", "rain": "rainy window", "sunny": "sunny park",
             "fall": "autumn leaves", "spring": "spring flowers", "summer": "summer beach", "winter": "winter frost",
             "back to school": "school supplies", "football": "football field", "patio": "string lights patio",
             "gift": "gift wrapping", "independence": "fireworks"}
    for word, q in table.items():
        if word in moment:
            return q
    return re.sub(r"[^a-z ]", "", moment)[:40] or None


def credits_json(items):
    return json.dumps([i.get("credit") for i in items if i and i.get("credit")])
