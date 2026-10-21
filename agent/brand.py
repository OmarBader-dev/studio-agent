"""The brand kit: what a business looks and sounds like, read from its own website.

Logo, brand colors, fonts, photos, social links, contact details, opening hours and the words on the site
(for the brand's voice and what it actually sells). Everything comes from public pages a visitor sees.
"""
import collections
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import parse_qs, unquote, urlparse

from . import colors, fonts, web
from .settings import CACHE

SOCIAL_HOSTS = {"instagram.com": "instagram", "facebook.com": "facebook", "fb.com": "facebook",
                "tiktok.com": "tiktok", "x.com": "x", "twitter.com": "x", "youtube.com": "youtube",
                "pinterest.com": "pinterest", "linkedin.com": "linkedin", "yelp.com": "yelp",
                "threads.net": "threads", "threads.com": "threads"}
ORDERING = ("doordash.com", "ubereats.com", "grubhub.com", "toasttab.com", "order.online", "chownow.com",
            "slicelife.com", "postmates.com", "seamless.com", "clover.com", "square.site", "olo.com",
            "menufy.com", "beyondmenu.com", "ezcater.com")
BOOKING = ("vagaro.com", "booksy.com", "fresha.com", "mindbodyonline.com", "mindbody.io", "glossgenius.com",
           "schedulicity.com", "styleseat.com", "squareup.com/appointments", "acuityscheduling.com",
           "calendly.com", "zenoti.com", "wellnessliving.com", "glofox.com", "pushpress.com", "zen-planner",
           "opentable.com", "resy.com", "exploretock.com", "sevenrooms.com", "yelp.com/reservations",
           "clubready.com", "trainerize.com", "classpass.com")
# Paid fonts sites often use, and the free Google Font that looks closest.
FONT_LOOKALIKES = {
    "proxima nova": "Montserrat", "gotham": "Montserrat", "futura": "Jost", "futura pt": "Jost",
    "avenir": "Nunito Sans", "avenir next": "Nunito Sans", "helvetica": "Inter", "helvetica neue": "Inter",
    "arial": "Arimo", "brandon grotesque": "Josefin Sans", "gill sans": "Lato", "gilroy": "Plus Jakarta Sans",
    "circular": "DM Sans", "sofia pro": "Nunito Sans", "museo sans": "Mulish", "din": "Barlow",
    "din next": "Barlow", "trade gothic": "Archivo Narrow", "georgia": "Gelasio", "times new roman": "Tinos",
    "times": "Tinos", "garamond": "EB Garamond", "baskerville": "Libre Baskerville", "didot": "Playfair Display",
    "bodoni": "Bodoni Moda", "freight": "Playfair Display", "canela": "Fraunces", "recoleta": "Fraunces",
    "brown": "DM Sans", "graphik": "Inter", "sf pro": "Inter", "segoe ui": "Open Sans", "verdana": "PT Sans",
    "tahoma": "PT Sans", "trebuchet ms": "Fira Sans", "century gothic": "Questrial", "copperplate": "Cinzel",
    "bebas": "Bebas Neue", "impact": "Anton", "league gothic": "League Gothic", "knockout": "Anton",
    "brush script": "Pacifico", "museo": "Mulish", "aktiv grotesk": "Inter", "neue haas": "Inter",
    "europa": "Nunito Sans", "objektiv": "Outfit", "cooper": "Cooper Hewitt",
}
FONT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{1,40}$")
ICON_FONT = re.compile(r"icon|awesome|themify|linearicons|fontello|et-?line|etmodules|glyph|material symbols|"
                       r"ionicons|feather|simple-line|flaticon|socicon|elegant", re.I)
SYSTEM_FONTS = {"sans-serif", "serif", "monospace", "cursive", "fantasy", "system-ui", "inherit", "initial",
                "-apple-system", "blinkmacsystemfont", "ui-sans-serif", "ui-serif", "apple color emoji",
                "segoe ui emoji", "noto color emoji", "emoji", "var", "unset", "fontawesome", "font awesome",
                "dashicons", "icomoon", "eicons", "material icons", "glyphicons halflings", "revicons"}
DEFAULT_FONTS = {   # by niche, when a site gives nothing usable: (heading, body)
    "restaurant": ("Bricolage Grotesque", "Inter"), "cafe": ("Fraunces", "DM Sans"), "bakery": ("Fraunces", "Nunito"),
    "gym": ("Anton", "Inter"), "beauty": ("Playfair Display", "Lato"), "shop": ("DM Serif Display", "DM Sans"),
    "bar": ("Bebas Neue", "Inter"), "pets": ("Baloo 2", "Nunito"),
}
# Colors of social network icons and buttons, which sites carry but which aren't their brand.
NETWORK_COLORS = ("#1877f2", "#3b5998", "#4267b2", "#1da1f2", "#55acee", "#e4405f", "#c13584", "#833ab4", "#fd1d1d",
                  "#fcaf45", "#f77737", "#ff0000", "#cd201f", "#0077b5", "#0a66c2", "#bd081c", "#e60023", "#cb2027",
                  "#ea4c89", "#0063dc", "#ff0084", "#1ab7ea", "#35465c", "#d32323", "#ff0050", "#00f2ea", "#25d366",
                  "#fffc00", "#1db954", "#1769ff", "#ff4500", "#00af87", "#34e0a1", "#f56400", "#4285f4", "#ea4335",
                  "#fbbc05", "#34a853", "#ff9900", "#720e9e", "#00ab6c", "#ff5500", "#9146ff", "#6441a5", "#5865f2",
                  "#7289da", "#0088cc", "#f94877", "#f26522", "#4dbc15", "#7dbb00", "#00b488", "#21759b", "#ff6600",
                  "#00aced", "#3d5b99", "#dd4b39", "#0084ff", "#7d7d7d")
SPAM = re.compile(r"\b(slot (?:online|gacor)|casino|judi|togel|poker online|sbobet|rtp (?:live|slot)|bandar|"
                  r"situs (?:resmi|slot)|viagra|cialis|replica watches|payday loans?|escort)\b", re.I)
BOILERPLATE = re.compile(r"^(skip to (?:main )?content|your cart(?: is empty)?|continue shopping|have an account\?|"
                         r"estimated total|\$0\.00.*|taxes, discounts.*|check ?out|top of page|bottom of page|-->|"
                         r"log in.*|sign in.*|loading\.\.\.|cart|menu|open menu|close menu|toggle navigation|"
                         r"special instructions.*|search|close|view cart|checkout|0 items?|accept( all)?( cookies)?|"
                         r"this website uses cookies.*|powered by .*|©.*|copyright.*|all rights reserved.*)$", re.I)
# An accent for black-and-white brands, by niche.
NICHE_ACCENT = {"restaurant": "#c8102e", "cafe": "#a0673f", "bakery": "#e07a5f", "gym": "#ff5a1f",
                "beauty": "#c9a227", "shop": "#b5835a", "bar": "#d4a017", "pets": "#2f9bd6"}
OFFER_PAGES = re.compile(r"\b(menu|menus|food|drinks|classes|class schedule|schedule|services|pricing|prices|"
                         r"treatments|memberships?|shop|products|collections?|specials)\b", re.I)
NAV_SKIP = re.compile(r"cart|login|log in|sign in|account|privacy|terms|cookie|careers|jobs", re.I)


def _attrs(tag):
    return {k.lower(): html.unescape(v1 or v2 or v3 or "") for k, v1, v2, v3 in
            re.findall(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""", tag)}


def _meta(page_html, *names):
    for tag in re.findall(r"<meta\b[^>]*>", page_html, re.I):
        a = _attrs(tag)
        key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
        if key in names and a.get("content"):
            return a["content"].strip()
    return ""


def visible_text(page_html, limit=6000):
    t = re.sub(r"(?is)<(script|style|noscript|svg|template)\b.*?</\1>", " ", page_html or "")
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h\d|section|tr)>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    lines, seen = [], set()
    for l in t.splitlines():
        l = " ".join(l.split())
        if len(l) > 1 and not BOILERPLATE.match(l) and l.lower() not in seen:
            seen.add(l.lower())
            lines.append(l)
    return "\n".join(lines)[:limit]


def json_ld(page_html):
    """Schema.org data the site publishes about itself (name, logo, address, hours...)."""
    found = []
    for block in re.findall(r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page_html or ""):
        try:
            data = json.loads(html.unescape(block.strip()))
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if "@graph" in item:
                    stack.extend(item["@graph"] if isinstance(item["@graph"], list) else [item["@graph"]])
                found.append(item)
            elif isinstance(item, list):
                stack.extend(item)
    business = [d for d in found if any(t in str(d.get("@type", "")) for t in (
        "LocalBusiness", "Restaurant", "Organization", "Store", "Bakery", "CafeOrCoffeeShop", "HealthClub",
        "BeautySalon", "HairSalon", "DaySpa", "NailSalon", "SportsActivityLocation", "FoodEstablishment",
        "ExerciseGym", "BarOrPub", "ClothingStore", "Florist"))]
    return business[0] if business else {}


def _img(value):
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl") or ""
    return value if isinstance(value, str) else ""


def links(page_html, base):
    out = []
    for tag, inner in re.findall(r"(?is)(<a\b[^>]{0,3000}>)(.{0,3000}?)</a>", page_html or ""):
        href = _attrs(tag).get("href", "")
        if href and not href.lower().startswith(("javascript:", "data:", "#")):
            text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", inner)).split())
            out.append((web.absolute(base, href), text))
    return out


def socials(all_links):
    out = {}
    for url, _ in all_links:
        host = web.host_of(url)
        for domain, kind in SOCIAL_HOSTS.items():
            if host == domain or host.endswith("." + domain):
                path = urlparse(url).path.strip("/")
                if path and not re.match(r"^(sharer|share|intent|dialog|plugins|tr|hashtag|p/|reel|watch)", path, re.I):
                    out.setdefault(kind, url.split("?")[0])
    return out


def services(all_links):
    ordering, booking = [], []
    for url, _ in all_links:
        low = url.lower()
        if any(d in low for d in ORDERING) and url not in ordering:
            ordering.append(url)
        if any(d in low for d in BOOKING) and url not in booking:
            booking.append(url)
    return ordering[:3], booking[:3]


EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")
JUNK_EMAIL = re.compile(r"\.(?:png|jpe?g|gif|webp|svg)$|@(?:sentry|wixpress|example|domain|email|yourdomain|godaddy|"
                        r"sentry-next|mysite|company|squarespace|shopify)\.|^(?:noreply|no-reply|donotreply)@", re.I)


def _cf_decode(hexstr):
    try:
        key = int(hexstr[:2], 16)
        return "".join(chr(int(hexstr[i:i + 2], 16) ^ key) for i in range(2, len(hexstr), 2))
    except ValueError:
        return ""


def emails_in(page_html):
    """Email addresses a page shows (mailto links, protected addresses and plain text). Never guessed."""
    found = re.findall(r'mailto:([^"\'?\s>]+)', page_html or "", re.I)
    found += [_cf_decode(h) for h in re.findall(r'data-cfemail=["\']([0-9a-fA-F]+)["\']', page_html or "")]
    found += EMAIL.findall(re.sub(r"<[^>]+>", " ", page_html or ""))
    clean = []
    for e in found:
        e = unquote(e).strip().strip(".,;:").lower()
        if EMAIL.fullmatch(e) and not JUNK_EMAIL.search(e) and e not in clean:
            clean.append(e)
    return clean


# Logo -----------------------------------------------------------------------------------------
def logo_candidates(page_html, base, ld):
    cands = []
    if _img(ld.get("logo")):
        cands.append((100, web.absolute(base, _img(ld["logo"]))))
    header = re.search(r"(?is)<header\b.*?</header>", page_html or "")
    for scope, bonus in ((header.group(0) if header else "", 30), (page_html or "", 0)):
        for tag in re.findall(r"<img\b[^>]*>", scope, re.I):
            a = _attrs(tag)
            src = a.get("src") or a.get("data-src") or a.get("data-lazy-src") or ""
            if not src or src.startswith("data:image/gif"):
                continue
            hint = " ".join([a.get("class", ""), a.get("id", ""), a.get("alt", ""), src]).lower()
            if "logo" in hint:
                score = 80 + bonus - (10 if "footer" in hint else 0)
                cands.append((score, web.absolute(base, src)))
    for tag in re.findall(r"<link\b[^>]*>", page_html or "", re.I):
        a = _attrs(tag)
        rel = a.get("rel", "").lower()
        if "apple-touch-icon" in rel and a.get("href"):
            cands.append((45, web.absolute(base, a["href"])))
        elif "icon" in rel and a.get("href"):
            size = max([int(x) for x in re.findall(r"(\d+)x\d+", a.get("sizes", ""))] or [16])
            cands.append((20 + min(size, 256) // 16, web.absolute(base, a["href"])))
    seen, out = set(), []
    for score, url in sorted(cands, key=lambda x: -x[0]):
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _raster_size(path):
    from PIL import Image
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def ico_to_png(path):
    from PIL import Image
    try:
        with Image.open(path) as im:
            sizes = im.info.get("sizes") or [im.size]
            im.size = max(sizes)
            out = path.with_suffix(".png")
            im.convert("RGBA").save(out)
            return out
    except Exception:
        return None


def pick_logo(cands, folder):
    for url in cands[:6]:
        path = web.download(url, folder, max_bytes=3_000_000)
        if not path:
            continue
        if path.suffix == ".ico":
            path = ico_to_png(path)
            if not path:
                continue
        if path.suffix == ".svg":
            text = path.read_text(errors="ignore")
            if "<svg" in text.lower() and len(text) > 100:
                return {"url": url, "path": str(path), "kind": "svg", "w": 0, "h": 0}
            continue
        size = _raster_size(path)
        if size and min(size) >= 48:
            return {"url": url, "path": str(path), "kind": "raster", "w": size[0], "h": size[1]}
    return None


def logo_tone(logo):
    """Main colors of the logo and whether it needs a light or dark backing to stay visible."""
    if not logo or logo["kind"] != "raster":
        return {"colors": [], "tone": "unknown"}
    from PIL import Image
    try:
        im = Image.open(logo["path"]).convert("RGBA")
    except Exception:
        return {"colors": [], "tone": "unknown"}
    im.thumbnail((128, 128))
    px = list(im.getdata())
    solid = [p for p in px if p[3] > 200]
    transparent = len(solid) < 0.92 * len(px)
    if not solid:
        return {"colors": [], "tone": "unknown"}
    lum = sum(colors.luminance(p[:3]) for p in solid) / len(solid)
    tone = ("dark" if lum < 0.25 else "light" if lum > 0.7 else "mid") if transparent else "boxed"
    return {"colors": [c for c, share in colors.from_image(logo["path"]) if share > 0.04], "tone": tone,
            "transparent": transparent}


# Colors and fonts -----------------------------------------------------------------------------
VAR_HINT = re.compile(r"primary|brand|accent|secondary|main|theme|highlight|button|link", re.I)
KEY_SELECTOR = re.compile(r"button|\.btn|\bnav\b|header|(?:^|[\s,>])a(?:[\s,:.\[]|$)|\bh[12]\b|\.menu|\.cta|banner", re.I)
FRAMEWORK_CSS = re.compile(r"fonts\.googleapis|typekit|bootstrap|font-?awesome|fontawesome|animate(\.min)?\.css|"
                           r"slick|swiper|owl\.carousel|jquery|wp-includes|block-library|dashicons|elementor/assets|"
                           r"woocommerce|magnific|fancybox|lightbox|aos\.css|normalize|reset\.css|tailwind", re.I)


def stylesheets(page_html, base, site, limit=4):
    css = "\n".join(re.findall(r"(?is)<style\b[^>]*>(.*?)</style>", page_html or ""))
    css += "\n" + " ".join(re.findall(r'style\s*=\s*"([^"]*)"', page_html or "", re.I))
    own, other = [], []
    for tag in re.findall(r"<link\b[^>]*>", page_html or "", re.I):
        a = _attrs(tag)
        if "stylesheet" in a.get("rel", "").lower() and a.get("href"):
            url = web.absolute(base, a["href"])
            if FRAMEWORK_CSS.search(url):
                continue                        # Bootstrap's blue isn't the business's brand color
            (own if web.host_of(url).endswith(site) else other).append(url)
    for url in (own + other)[:limit]:
        page = web.fetch(url, limit=600_000, respect_robots=False, timeout=10)
        if page and page.status == 200:
            css += "\n" + page.text
    return clean_css(css)


def clean_css(css, limit=600_000):
    """CSS without embedded files (base64 fonts and images) and capped in size, so reading it stays fast."""
    out, i = [], 0
    low = (css or "").lower()
    while True:
        j = low.find("data:", i)
        if j < 0:
            out.append(css[i:])
            break
        out.append(css[i:j])
        k = j
        while k < len(css) and css[k] not in ")'\";":
            k += 1
        i = k
    css = "".join(out)
    return css[:limit]


def rules(css):
    """(selector, declarations) for each CSS rule, in one linear pass."""
    for chunk in css.split("}"):
        selector, _, body = chunk.rpartition("{")
        if body:
            yield selector[-300:], body


def brand_colors(page_html, css, logo_info, niche="restaurant"):
    score = collections.Counter()
    theme = _meta(page_html, "theme-color", "msapplication-tilecolor")
    if colors.rgb(theme):
        score[colors.hexify(theme)] += 40
    for selector, body in rules(css):
        for decl in body.split(";"):
            name, _, value = decl.partition(":")
            name = name.strip()
            if name.startswith("--") and VAR_HINT.search(name):
                for c in colors.in_css(value):
                    score[c] += 12 if re.search(r"primary|brand", name, re.I) else 6
        if KEY_SELECTOR.search(selector) and re.search(r"background|color|border", body, re.I):
            for c, n in colors.in_css(body).items():
                score[c] += 2 * n
    for c, n in colors.in_css(css).items():
        score[c] += min(n, 30) * 0.3
    strong = {colors.hexify(theme)} if colors.rgb(theme) else set()
    for c in logo_info.get("colors", []):
        score[c] += 25
        strong.add(c)
    for c in list(score):
        if c not in strong and any(colors.distance(c, n) < 30 for n in NETWORK_COLORS):
            del score[c]                       # a social icon's color, not the brand's
    merged = colors.merge_similar(score)
    # A color has to show up in more than passing to count as the brand's (or come from the logo).
    ranked = [c for c, n in merged if n >= 3 or c in strong or colors.is_neutral(c)]
    return colors.palette(ranked, NICHE_ACCENT.get(niche, "#c8102e")), ranked[:12]


def google_fonts_in(page_html):
    fams = []
    for url in re.findall(r"""fonts\.googleapis\.com/css2?\?([^"'>\s]+)""", page_html or ""):
        query = parse_qs(html.unescape(url))
        for fam in query.get("family", []):
            for part in fam.split("|"):
                name = unquote(part.split(":")[0]).replace("+", " ").strip()
                if name and name not in fams:
                    fams.append(name)
    return fams


def _font_name(value):
    first = value.split(",")[0].strip().strip("'\"").replace("!important", "").strip()
    if (not FONT_NAME.match(first) or first.lower() in SYSTEM_FONTS or ICON_FONT.search(first)
            or first.lower() in ("normal", "bold", "italic", "regular", "light", "medium", "auto", "none")
            or re.search(r"mono|consolas|courier|menlo|monaco|code", first, re.I)):
        return None
    return first


def declared_fonts(css):
    """Font families the site sets on headings and body text, most used first."""
    heads, body = collections.Counter(), collections.Counter()
    for selector, decl in rules(css or ""):
        if "font-family" not in decl.lower():
            continue
        m = re.search(r"font-family\s*:\s*([^;}]+)", decl, re.I)
        if not m:
            continue
        first = _font_name(m.group(1))
        if not first:
            continue
        target = heads if re.search(r"\bh[1-3]\b|title|heading|hero|display|logo", selector, re.I) else body
        target[first] += 1
    for _, decls in rules(css or ""):
        for decl in decls.split(";"):
            name, _, value = decl.partition(":")
            name = name.strip()
            if not name.startswith("--") or "font" not in name.lower() or re.search(r"size|weight|style|height|spacing",
                                                                                   name, re.I):
                continue
            first = _font_name(value)
            if first:
                (heads if re.search(r"head|display|title", name, re.I) else body)[first] += 2
    return [f for f, _ in heads.most_common(3)], [f for f, _ in body.most_common(3)]


def google_font(name):
    """The Google Fonts family for a font name (the same one, or a free lookalike), or None."""
    if not name:
        return None
    clean = re.sub(r"[-_]+", " ", name).strip()
    clean = re.sub(r"\b(regular|bold|light|medium|semibold|black|webfont|web|pro|std|w01|roman)\b", "", clean,
                   flags=re.I)
    clean = " ".join(clean.split())
    if clean.lower() in FONT_LOOKALIKES:
        return FONT_LOOKALIKES[clean.lower()]
    return fonts.find(clean)


def brand_fonts(page_html, css, niche):
    found = [f for f in google_fonts_in(page_html) if not ICON_FONT.search(f)]
    heads, bodies = declared_fonts(css)
    heading = next((g for g in map(google_font, heads + found) if g), None)
    body = next((g for g in map(google_font, bodies + found) if g and g != heading), None)
    d_head, d_body = DEFAULT_FONTS.get(niche, ("Bricolage Grotesque", "Inter"))
    return {"heading": heading or d_head, "body": body or (d_body if heading != d_body else "Inter"),
            "found": (heads + bodies + found)[:8], "from_site": bool(heading or body)}


# Photos ---------------------------------------------------------------------------------------
def _largest(srcset):
    """The biggest picture in a srcset. Entries are split at a comma followed by a space: addresses on some
    image servers (Wix) have commas inside them."""
    parts = [p.strip().split() for p in re.split(r",\s+", (srcset or "").strip()) if p.strip()]
    parts = [(p[0], int(re.sub(r"\D", "", p[1]) or 0) if len(p) > 1 else 0) for p in parts]
    return max(parts, key=lambda x: x[1])[0] if parts else None


def upsize(url):
    """The big version of a photo on the common site builders' image servers: their pages often hold small
    previews and swap in big ones with JavaScript."""
    m = re.match(r"(https?://static\.wixstatic\.com/media/[^/?#]+)", url or "")
    if m:
        return m.group(1)                                   # Wix: the original, not a blurred thumbnail
    if "squarespace-cdn.com" in url or "static1.squarespace.com" in url:
        return re.sub(r"\?.*$", "", url) + "?format=1500w"
    if "cdn.shopify.com" in url:
        url = re.sub(r"_(?:\d+x\d*|\d*x\d+|pico|icon|thumb|small|compact|medium)(?=\.(?:jpe?g|png|webp)\b)", "", url, flags=re.I)
        return re.sub(r"([?&])width=\d+&?", r"\1", url).rstrip("?&")
    if "/wp-content/uploads/" in url:
        return re.sub(r"-\d{2,4}x\d{2,4}(?=\.(?:jpe?g|png|webp)(?:\?|$))", "", url, flags=re.I)
    return url


def photo_candidates(page_html, base, ld=None):
    urls = []
    for key in ("og:image", "twitter:image", "og:image:url"):
        v = _meta(page_html, key)
        if v:
            urls.append(web.absolute(base, v))
    images = (ld or {}).get("image")
    for v in (images if isinstance(images, list) else [images]):
        v = _img(v)
        if v:
            urls.append(web.absolute(base, v))
    for tag in re.findall(r"<(?:img|source)\b[^>]*>", page_html or "", re.I):
        a = _attrs(tag)
        hint = " ".join([a.get("class", ""), a.get("alt", ""), a.get("id", "")]).lower()
        if "logo" in hint or "icon" in hint:
            continue
        best = _largest(a.get("srcset") or a.get("data-srcset") or a.get("data-bgset"))
        src = (best or a.get("data-image") or a.get("data-src") or a.get("data-lazy-src") or a.get("data-original")
               or a.get("data-bg") or a.get("src") or "")
        if src and not src.startswith("data:") and not re.search(r"\.(svg|gif)(\?|$)|sprite|pixel|spacer", src, re.I):
            urls.append(web.absolute(base, src))
    for bg in re.findall(r"(?:background(?:-image)?\s*:\s*url\(|data-bg(?:-image|-src)?=)['\"]?([^'\")\s>]+)", page_html or "", re.I):
        if not re.search(r"\.(svg|gif)(\?|$)", bg, re.I):
            urls.append(web.absolute(base, bg))
    seen, out = set(), []
    for u in urls:
        key = re.sub(r"[?#].*$", "", upsize(u))
        if key not in seen:
            seen.add(key)
            out.append(u)
    return out


def words_in(path):
    """The words clear enough to read in a picture and the share of it they cover, using Tesseract (the free
    text reader, installed on the agent's machine). None when it isn't installed."""
    exe = shutil.which("tesseract")
    if not exe:
        return None
    from PIL import Image
    try:
        with Image.open(path) as im:
            g = im.convert("L")
            g.thumbnail((1000, 1000))
            w, h = g.size
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                g.save(f.name)
                tmp = f.name
        run = subprocess.run([exe, tmp, "stdout", "--psm", "11", "tsv"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    finally:
        try:
            os.unlink(tmp)
        except (OSError, NameError):
            pass
    words, area = [], 0
    for line in run.stdout.splitlines()[1:]:
        f = line.split("\t")
        if len(f) >= 12 and f[0] == "5" and float(f[10] or 0) >= 70 and sum(ch.isalpha() for ch in f[11]) >= 2:
            words.append(f[11].strip())
            area += int(f[8]) * int(f[9])
    return words, area / max(1, w * h)


def has_lettering(path):
    """True for posters, promo graphics, awards and screenshots: our headline would fight their words. A sign
    in a photo of the place (two words) is fine."""
    found = words_in(path)
    if found is None:
        return text_heavy(path)                    # without Tesseract: the rough check below
    words, area = found
    return sum(1 for x in words if sum(ch.isalpha() for ch in x) >= 3) >= 4 or area >= .05


def text_heavy(path):
    """Rough check for pictures with big lettering (promo banners, flyers): many sharp light/dark edges in rows."""
    from PIL import Image, ImageFilter
    try:
        with Image.open(path) as im:
            g = im.convert("L").resize((240, 240))
    except Exception:
        return False
    edges = g.filter(ImageFilter.FIND_EDGES)
    px = edges.load()
    strong_rows = 0
    for y in range(240):
        hits = sum(1 for x in range(240) if px[x, y] > 110)
        if hits > 40:
            strong_rows += 1
    return strong_rows > 55


def photo_score(path):
    """How good a photo looks leading a post (higher is better): well lit, colorful, sharp, big, not wide."""
    from PIL import Image, ImageFilter, ImageStat
    try:
        with Image.open(path) as im:
            w, h = im.size
            rgb = im.convert("RGB").resize((96, 96))
    except Exception:
        return 0.0
    gray = rgb.convert("L")
    light = ImageStat.Stat(gray).mean[0] / 255
    sharp = min(1.0, ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).stddev[0] / 40)
    rg, yb = [], []
    for r, g, b in rgb.getdata():
        rg.append(r - g)
        yb.append((r + g) / 2 - b)
    mean = lambda xs: sum(xs) / len(xs)
    sd = lambda xs: (sum((x - mean(xs)) ** 2 for x in xs) / len(xs)) ** .5
    colorful = min(1.0, ((sd(rg) ** 2 + sd(yb) ** 2) ** .5 + .3 * (mean(rg) ** 2 + mean(yb) ** 2) ** .5) / 90)
    exposure = max(0.0, 1 - abs(light - .52) * 2.2)          # too dark or washed out reads badly in a feed
    size = min(1.0, min(w, h) / 1000)
    shape = 1.0 if h >= w * .75 else .6                      # very wide pictures lose most of themselves in 4:5
    return round(.34 * exposure + .3 * colorful + .14 * sharp + .12 * size + .1 * shape, 3)


def _fingerprint(path):
    """A tiny picture of the picture, to spot the same photo saved twice at different addresses."""
    from PIL import Image
    try:
        with Image.open(path) as im:
            g = im.convert("L").resize((9, 8))
    except Exception:
        return None
    px = list(g.getdata())
    return tuple(px[r * 9 + c] > px[r * 9 + c + 1] for r in range(8) for c in range(8))


def pick_photos(cands, folder, want=8, skip=(), deadline=None):
    from PIL import Image
    out, prints = [], []
    for url in cands[:40]:
        if len(out) >= want or (deadline and time.time() > deadline):
            break
        if url in skip or re.search(r"logo|favicon|icon|placeholder|badge|seal|award|promo|sale|shipping|"
                                    r"coupon|discount|offer|flyer|poster|graphic|gift-?card|menu", urlparse(url).path, re.I):
            continue
        if re.search(r"instagram|fbcdn|facebook|tiktok", web.host_of(url) or ""):
            continue                                  # a social feed shown on their site: not taken from there
        big = upsize(url)
        path = web.download(big, folder, max_bytes=8_000_000) if big != url else None
        path = path or web.download(url, folder, max_bytes=6_000_000)
        if not path or path.suffix in (".svg", ".ico", ".gif", ".bin"):
            continue
        try:
            with Image.open(path) as im:
                w, h = im.size
                small = im.convert("RGB").resize((24, 24))
                px = list(small.getdata())
        except Exception:
            continue
        if min(w, h) < 360 or max(w, h) < 600 or max(w, h) / min(w, h) > 2.4:
            continue                                  # too small, or a banner strip a post would crop to nothing
        flat = sum(1 for p in px if max(p) - min(p) < 12) / len(px)
        tones = len({(r >> 4, g >> 4, b >> 4) for r, g, b in px})
        if flat > 0.8 or tones < 40:                  # flat colors or few tones: a graphic, not a photo
            continue
        if has_lettering(path):                       # a promo banner: its own words would clash with ours
            continue
        mark = _fingerprint(path)
        if any(o["path"] == str(path) for o in out) or (mark and any(
                sum(a != b for a, b in zip(mark, m)) <= 6 for m in prints)):
            continue                                  # the same photo at another address or size
        prints.append(mark)
        out.append({"url": url, "path": str(path), "w": w, "h": h, "score": photo_score(path)})
    return sorted(out, key=lambda o: -o["score"])            # the best photo leads the first post


# Putting it together --------------------------------------------------------------------------
def offer_page(all_links, site):
    best = None
    for url, text in all_links:
        if re.search(r"\.(pdf|jpe?g|png|gif|webp|docx?|zip)(\?|$)", urlparse(url).path, re.I):
            continue                                       # a PDF menu or a picture isn't a page to read
        if web.host_of(url).endswith(site) and OFFER_PAGES.search(text or "") and not NAV_SKIP.search(text):
            if urlparse(url).path.strip("/"):
                best = best or url
    return best


def _unique(photos):
    """Photos found on several pages, once each."""
    out, prints = [], []
    for p in photos:
        mark = _fingerprint(p["path"])
        if mark and any(sum(a != b for a, b in zip(mark, m)) <= 6 for m in prints):
            continue
        prints.append(mark)
        out.append(p)
    return out


PHOTO_PAGES = re.compile(r"\b(gallery|photos?|pictures|our (food|space|story|work)|about( us)?|portfolio|lookbook)\b", re.I)


def photo_page(all_links, site, skip=()):
    """A page of the site likely to show more photos: its gallery, or its about page."""
    for url, text in all_links:
        if url in skip or re.search(r"\.(pdf|jpe?g|png|gif|webp)(\?|$)", urlparse(url).path, re.I):
            continue
        if web.host_of(url).endswith(site) and urlparse(url).path.strip("/") and \
                (PHOTO_PAGES.search(text or "") or PHOTO_PAGES.search(urlparse(url).path.replace("-", " "))):
            return url
    return None


def read(url, niche="restaurant", name="", folder=None, fetch_extra=True, budget=60, renderer=None):
    """The brand kit for a website. Never raises for a bad site: returns what it could learn,
    with 'ok' False when the site couldn't be read. budget: seconds before optional steps are skipped.
    renderer (a design.Renderer): also look at the page as a browser shows it, for photos its scripts load."""
    deadline = time.time() + budget
    url = web.normalize(url)
    kit = {"website": url, "domain": web.host_of(url), "niche": niche, "name": name, "ok": False,
           "colors": colors.palette([]), "fonts": {"heading": DEFAULT_FONTS.get(niche, ("Inter", "Inter"))[0],
                                                   "body": DEFAULT_FONTS.get(niche, ("Inter", "Inter"))[1],
                                                   "found": [], "from_site": False},
           "logo": None, "photos": [], "socials": {}, "ordering": [], "booking": [], "text": ""}
    page = web.fetch(url)
    if not page or page.status >= 400 or web.blocked(page):
        kit["problem"] = ("blocked automatic visits" if web.blocked(page) else
                          f"returned {page.status}" if page else "didn't load")
        return kit
    if not web.is_html(page):
        kit["problem"] = "the website link isn't a web page"
        return kit
    folder = folder or CACHE / "brands" / kit["domain"]
    base, site = page.url, web.host_of(page.url)
    if SPAM.search(page.text[:20000]):
        kit["problem"] = "the site shows spam (it may have been hacked or the domain lapsed)"
        return kit
    if _registrable(site) != _registrable(kit["domain"]) and not _platform_host(site):
        page_text = visible_text(page.text, 20000).lower()
        if name and not any(w in page_text for w in re.findall(r"[a-z]{4,}", name.lower())):
            kit["problem"] = f"the address now goes to a different site ({site})"
            return kit
    kit["website"], kit["domain"] = page.url, site
    ld = json_ld(page.text)
    all_links = links(page.text, base)
    title = re.sub(r"\s+", " ", html.unescape(re.search(r"(?is)<title[^>]*>(.*?)</title>", page.text).group(1))).strip() \
        if re.search(r"(?is)<title[^>]*>(.*?)</title>", page.text) else ""
    kit["name"] = name or ld.get("name") or _meta(page.text, "og:site_name") or re.split(r"\s[|\-–—:]\s", title)[0]
    kit["description"] = (_meta(page.text, "description", "og:description") or ld.get("description") or "")[:400]
    kit["title"] = title[:160]
    kit["socials"] = socials(all_links)
    kit["ordering"], kit["booking"] = services(all_links)
    kit["phone"] = ld.get("telephone") or ""
    addr = ld.get("address") if isinstance(ld.get("address"), dict) else {}
    kit["address"] = ", ".join(x for x in (addr.get("streetAddress"), addr.get("addressLocality"),
                                           addr.get("addressRegion")) if x)
    hours = ld.get("openingHours") or ld.get("openingHoursSpecification") or ""
    kit["hours"] = hours if isinstance(hours, (str, list)) else ""
    kit["logo"] = pick_logo(logo_candidates(page.text, base, ld), folder)
    tone = logo_tone(kit["logo"])
    if kit["logo"]:
        kit["logo"].update(tone=tone["tone"], colors=tone["colors"])
    css = stylesheets(page.text, base, site, limit=4 if time.time() < deadline - 30 else 1)
    kit["colors"], kit["color_candidates"] = brand_colors(page.text, css, tone, niche)
    kit["fonts"] = brand_fonts(page.text, css, niche)
    logo_url = [kit["logo"]["url"]] if kit["logo"] else []
    kit["photos"] = pick_photos(photo_candidates(page.text, base, ld), folder, skip=logo_url, deadline=deadline - 12) \
        if time.time() < deadline - 10 else []
    text = visible_text(page.text)
    kit["emails_found"] = emails_in(page.text)
    extra = offer_page(all_links, site) if fetch_extra and time.time() < deadline - 10 else None
    if extra:
        p2 = web.fetch(extra, limit=1_500_000)
        if p2 and p2.status == 200 and web.is_html(p2) and not web.blocked(p2):
            text += "\n\n[" + (urlparse(extra).path.strip("/") or "page") + "]\n" + visible_text(p2.text, 5000)
            kit["emails_found"] += [x for x in emails_in(p2.text) if x not in kit["emails_found"]]
            if len(kit["photos"]) < 5:
                kit["photos"] += pick_photos(photo_candidates(p2.text, p2.url), folder, want=5 - len(kit["photos"]),
                                             skip=logo_url + [p["url"] for p in kit["photos"]], deadline=deadline - 8)
    gallery = photo_page(all_links, site, skip=[extra]) if fetch_extra and len(kit["photos"]) < 5 else None
    if gallery and time.time() < deadline - 10:
        p3 = web.fetch(gallery, limit=1_500_000)
        if p3 and p3.status == 200 and web.is_html(p3) and not web.blocked(p3):
            kit["photos"] += pick_photos(photo_candidates(p3.text, p3.url), folder, want=6 - len(kit["photos"]),
                                         skip=logo_url + [p["url"] for p in kit["photos"]], deadline=deadline - 6)
    if renderer is not None and len(kit["photos"]) < 3 and time.time() < deadline - 12:
        shown = [u for u in renderer.images_on(page.url) if web.host_of(u)]      # what its scripts loaded
        kit["photos"] += pick_photos(shown, folder, want=6 - len(kit["photos"]),
                                     skip=logo_url + [p["url"] for p in kit["photos"]], deadline=deadline - 2)
    kit["photos"] = _unique(sorted(kit["photos"], key=lambda o: -o.get("score", 0)))[:8]
    kit["text"] = text[:9000]
    owned = belongs(name, title, text)
    if owned is not True:
        kit["problem"] = owned
        return kit
    kit["chain_hint"] = bool(re.search(r"\bfranchis(e|ing)\b|\b\d{2,} locations\b|find a location|"
                                       r"store locator|all locations", text, re.I))
    kit["ok"] = True
    return kit


NAME_FILLER = {"the", "and", "cafe", "coffee", "pizza", "restaurant", "grill", "kitchen", "salon", "studio", "fitness",
               "shop", "store", "bakery", "boutique", "nails", "beauty", "barber", "company", "house", "bistro", "market",
               "llc", "inc", "co", "of", "gym", "spa", "bar", "pub", "deli", "yoga", "hair", "baked", "goods", "finest"}


def belongs(name, title, text):
    """True when the page looks like the business's own site; otherwise why not (a sold or hijacked domain)."""
    sample = (title or "") + " " + (text or "")[:6000]
    letters = [ch for ch in sample if ch.isalpha()]
    foreign = sum(1 for ch in letters if ord(ch) > 0x2E7F or 0x0400 <= ord(ch) <= 0x04FF) / max(1, len(letters))
    if foreign > 0.3:
        return "the website now shows another business in another language (the domain probably changed hands)"
    words = [w for w in re.findall(r"[a-z0-9]{4,}", (name or "").lower()) if w not in NAME_FILLER]
    low = re.sub(r"[^a-z0-9 ]", "", sample.lower().replace("'", "").replace("’", ""))
    squashed = low.replace(" ", "")
    if words and not any(w in low or w in squashed for w in words):
        return "the website doesn't mention the business (it may have changed hands)"
    return True


def _registrable(host):
    parts = (host or "").split(".")
    two = {"co.uk", "com.au", "co.nz", "com.br", "co.za", "com.mx", "com.lb", "org.uk"}
    return ".".join(parts[-3:]) if len(parts) >= 3 and ".".join(parts[-2:]) in two else ".".join(parts[-2:])


def _platform_host(host):
    """Website builders that host a business's own site on their domain."""
    return any(host == d or host.endswith("." + d) for d in (
        "square.site", "squarespace.com", "wixsite.com", "weebly.com", "godaddysites.com", "myshopify.com",
        "webflow.io", "carrd.co", "business.site", "wordpress.com", "blogspot.com", "jimdosite.com",
        "mystrikingly.com", "site123.me", "webs.com", "ueniweb.com", "framer.website"))
