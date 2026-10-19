"""Free pictures for designs, in order of preference:

1. The business's own photos (from its website, or what a client sends).
2. Theme photos for a moment (pumpkins for Halloween, snow for a cold snap) from Pexels (free key) or
   Openverse (no key; openly licensed, attribution kept). Never used to stand in for the business's own
   food, products or place.
3. Abstract AI backgrounds from Cloudflare Workers AI (free daily allowance), or Pollinations (no key) when
   allowed. Prompts always ask for illustration or abstract art, never a fake photo of real products.
"""
import base64
import hashlib
import json
import re

import requests

from . import web
from .settings import CACHE

FOLDER = CACHE / "images"
FLUX = "@cf/black-forest-labs/flux-1-schnell"
STYLE_HINT = ("abstract editorial illustration, flat shapes, soft grain, no text, no letters, no logos, "
              "no people, no faces, no real products")


def _name(*parts):
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def stock(cfg, query, orientation="portrait"):
    """A free theme photo: {'path', 'credit', 'url'} or None."""
    if not cfg["images"].get("stock_photos"):
        return None
    FOLDER.mkdir(parents=True, exist_ok=True)
    key = cfg.secret("PEXELS_API_KEY")
    try:
        if key:
            r = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": key}, timeout=20,
                             params={"query": query, "orientation": orientation, "per_page": 5})
            photos = r.json().get("photos", []) if r.status_code == 200 else []
            if photos:
                p = photos[0]
                path = web.download(p["src"].get("large2x") or p["src"]["large"], FOLDER)
                if path:
                    return {"path": str(path), "credit": f"Photo by {p.get('photographer', 'Pexels')} on Pexels",
                            "url": p.get("url")}
        r = requests.get("https://api.openverse.org/v1/images/", timeout=20, headers={"User-Agent": web.API_UA},
                         params={"q": query, "license_type": "commercial,modification", "page_size": 8,
                                 "aspect_ratio": "tall" if orientation == "portrait" else "wide", "mature": "false"})
        for item in (r.json().get("results", []) if r.status_code == 200 else []):
            if (item.get("width") or 0) < 900:
                continue
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
