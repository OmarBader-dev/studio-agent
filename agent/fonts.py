"""Google Fonts (free, open licenses): which families exist, their weights and style, and the CSS link
for a design. The family list comes from Google's public metadata and is cached for a week."""
import json
import time
import urllib.parse

from . import web
from .settings import CACHE

META_URL = "https://fonts.google.com/metadata/fonts"
FILE = CACHE / "google-fonts.json"
# Used when the metadata can't be loaded: category and weights of the fonts the agents use most.
BUILTIN = {
    "Inter": ("Sans Serif", [400, 500, 600, 700, 800, 900]), "Anton": ("Sans Serif", [400]),
    "Bebas Neue": ("Sans Serif", [400]), "Oswald": ("Sans Serif", [400, 500, 600, 700]),
    "Fraunces": ("Serif", [400, 500, 600, 700, 800, 900]), "Playfair Display": ("Serif", [400, 500, 600, 700, 800, 900]),
    "DM Serif Display": ("Serif", [400]), "DM Sans": ("Sans Serif", [400, 500, 600, 700, 800, 900]),
    "Bricolage Grotesque": ("Sans Serif", [400, 500, 600, 700, 800]), "Lato": ("Sans Serif", [400, 700, 900]),
    "Nunito": ("Sans Serif", [400, 600, 700, 800, 900]), "Montserrat": ("Sans Serif", [400, 500, 600, 700, 800, 900]),
    "Open Sans": ("Sans Serif", [400, 600, 700, 800]), "Poppins": ("Sans Serif", [400, 500, 600, 700, 800, 900]),
    "Archivo Black": ("Sans Serif", [400]), "Space Grotesk": ("Sans Serif", [400, 500, 600, 700]),
    "Baloo 2": ("Display", [400, 500, 600, 700, 800]), "Shrikhand": ("Display", [400]),
    "Instrument Serif": ("Serif", [400]), "Syne": ("Sans Serif", [400, 500, 600, 700, 800]),
}
CONDENSED = {"Anton", "Bebas Neue", "Oswald", "League Gothic", "Archivo Narrow", "Barlow Condensed", "Big Shoulders Display",
             "Six Caps", "Teko", "Fjalla One", "Pathway Gothic One", "Antonio", "Saira Condensed", "Sofia Sans Condensed",
             "Roboto Condensed", "Alumni Sans", "Smooch Sans", "Staatliches"}

_meta = None


def _load():
    global _meta
    if _meta is not None:
        return _meta
    try:
        if FILE.exists() and time.time() - FILE.stat().st_mtime < 7 * 86400:
            _meta = json.loads(FILE.read_text())
            return _meta
    except (OSError, ValueError):
        pass
    page = web.fetch(META_URL, limit=8_000_000, respect_robots=False, timeout=30)
    if page and page.status == 200 and "familyMetadataList" in page.text:
        raw = json.loads(page.text[page.text.index("{"):])
        _meta = {}
        for f in raw.get("familyMetadataList", []):
            weights = sorted({int(k.rstrip("i")) for k in f.get("fonts", {}) if k.rstrip("i").isdigit()})
            subsets = f.get("subsets") or []
            _meta[f["family"]] = [f.get("category", ""), weights, f.get("popularity", 9999), f.get("trending", 9999),
                                  "latin" in subsets or not subsets]
        FILE.parent.mkdir(parents=True, exist_ok=True)
        FILE.write_text(json.dumps(_meta))
    else:
        _meta = {k: [c, w, 100, 1000, True] for k, (c, w) in BUILTIN.items()}
    return _meta


def info(name):
    """(category, weights) for a Google Fonts family, or None if Google Fonts doesn't have it."""
    m = _load().get(name)
    if m:
        return m[0], m[1]
    b = BUILTIN.get(name)
    return b if b else None


def exists(name):
    return info(name) is not None


def find(name):
    """The exact Google Fonts family name for a loosely written one ('playfair display' -> 'Playfair Display')."""
    if not name:
        return None
    if exists(name):
        return name
    low = name.lower().strip()
    for family in _load():
        if family.lower() == low:
            return family
    return None


def category(name):
    i = info(name)
    return i[0] if i else "Sans Serif"


def is_serif(name):
    return category(name) == "Serif"


def is_condensed(name):
    return name in CONDENSED


def best_weight(name, want=800):
    weights = (info(name) or ("", [400]))[1] or [400]
    return min(weights, key=lambda w: (abs(w - want), -w))


def css_url(families, weights=(400, 600, 700, 800, 900), icons=False):
    """One Google Fonts CSS link for the families (each with only the weights it has)."""
    parts = []
    for fam in dict.fromkeys(f for f in families if f):
        have = (info(fam) or ("", [400]))[1] or [400]
        use = sorted({w for w in weights if w in have} or {min(have, key=lambda w: abs(w - 400))})
        parts.append("family=" + urllib.parse.quote_plus(fam) + (":wght@" + ";".join(map(str, use))
                                                                if use != [400] else ""))
    if icons:
        parts.append("family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,400..700,0..1,0")
    return "https://fonts.googleapis.com/css2?" + "&".join(parts) + "&display=block"


def trending(category_name=None, n=12):
    """Display and serif families climbing on Google Fonts right now (popular enough to be safe choices)."""
    out = []
    for fam, (cat, weights, pop, trend, latin) in _load().items():
        if not latin or pop > 900 or (category_name and cat != category_name):
            continue
        if cat in ("Display", "Serif", "Sans Serif") and not fam.startswith(("Noto", "IBM Plex")):
            out.append((trend, fam))
    return [f for _, f in sorted(out)[:n]]
