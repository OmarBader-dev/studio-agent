"""Finding businesses: Overture Maps places (free open map data; no account, key or card).

Overture publishes its places as Parquet files on a public bucket, refreshed about monthly. DuckDB reads
only the parts that cover a city, so one city takes seconds. City outlines come from a built-in table of
~200 large US cities, or OpenStreetMap's free geocoders. Data license: https://docs.overturemaps.org/attribution/

Each candidate gets a website check later (brand.py). An email only counts when it belongs to the business:
at the website's own domain, or a free mailbox (Gmail...) whose name matches the business. Addresses are
never guessed.
"""
import collections
import json
import pathlib
import re
import time
import urllib.parse

import requests

from .settings import CATEGORY_NICHE, NICHES

STAC = "https://stac.overturemaps.org/catalog.json"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
PHOTON = "https://photon.komoot.io/api/"
UA = {"User-Agent": "studio-agent/1.0 (marketing for local businesses)"}
CITIES_FILE = pathlib.Path(__file__).with_name("cities.json")
LEGAL = re.compile(r"[\s,]+(?:l\.?\s?l\.?\s?c\.?|p\.?l\.?l\.?c\.?|inc\.?|incorporated|corp\.?|corporation|ltd\.?)$", re.I)
KEEP_UPPER = {"BBQ", "USA", "II", "III", "LLC", "NY", "NYC", "LA"}
# "Websites" that are someone else's platform, not the business's own site.
NOT_OWN_SITE = ("facebook.com", "instagram.com", "booksy.com", "etsy.com", "yelp.com", "linktr.ee", "vagaro.com",
                "fresha.com", "styleseat.com", "square.site", "toasttab.com", "doordash.com", "ubereats.com",
                "grubhub.com", "business.site", "g.page", "google.com", "tiktok.com", "x.com", "twitter.com",
                "mindbodyonline.com", "glossgenius.com", "schedulicity.com", "hub.biz", "locations.", "order.online",
                "clover.com", "menufy.com", "beyondmenu.com", "allmenus.com", "menupix.com", "opentable.com",
                "classpass.com", "groupon.com", "nextdoor.com", "linkedin.com", "youtube.com", "pinterest.com")
FREE_MAIL = {"gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "hotmail.com", "outlook.com", "live.com",
             "msn.com", "aol.com", "icloud.com", "me.com", "mac.com", "comcast.net", "att.net", "sbcglobal.net",
             "bellsouth.net", "verizon.net", "charter.net", "cox.net", "earthlink.net", "protonmail.com", "proton.me"}
GENERIC = {"the", "and", "cafe", "coffee", "pizza", "restaurant", "grill", "kitchen", "bar", "salon", "studio", "spa",
           "fitness", "gym", "shop", "store", "bakery", "boutique", "hair", "nails", "nail", "beauty", "barber",
           "company", "house", "llc", "inc", "bistro", "taqueria", "deli", "yoga", "market", "co", "of", "by"}


class ProspectError(RuntimeError):
    pass


# Release catalog -------------------------------------------------------------------------------
def latest_release():
    links = requests.get(STAC, timeout=30, headers=UA).json().get("links", [])
    children = [l for l in links if l.get("rel") == "child"]
    if not children:
        raise ProspectError("Couldn't read Overture's list of releases.")
    latest = [l for l in children if l.get("latest")]
    pick = latest[0] if latest else max(children, key=lambda l: l.get("href", ""))
    return pick["href"].rstrip("/").split("/")[-2]


def place_files(release):
    base = f"https://stac.overturemaps.org/{release}/places/place/"
    coll = requests.get(base + "collection.json", timeout=30, headers=UA).json()
    files = []
    for link in coll.get("links", []):
        if link.get("rel") != "item":
            continue
        item = requests.get(urllib.parse.urljoin(base, link["href"]), timeout=30, headers=UA).json()
        asset = (item.get("assets") or {}).get("aws") or {}
        if asset.get("href") and item.get("bbox"):
            files.append([item["bbox"], asset["href"]])
    if not files:
        raise ProspectError(f"No place files are listed for Overture release {release}.")
    return files


def release_files(store, refresh=False):
    cache = store.data.setdefault("overture", {})
    if refresh or not cache.get("files") or time.time() - cache.get("checked", 0) > 7 * 86400:
        release = latest_release()
        if refresh or release != cache.get("release") or not cache.get("files"):
            cache["files"] = place_files(release)
        cache.update(release=release, checked=time.time())
    return cache


# Geocoding -------------------------------------------------------------------------------------
STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky",
    "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota",
    "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}


def _city_key(city):
    name, _, state = city.partition(",")
    name = re.sub(r"\bst\.?\s+", "saint ", " ".join(name.lower().split()))
    return f"{name}, {state.strip().lower()}"


def _known(city):
    try:
        table = json.loads(CITIES_FILE.read_text())
    except (OSError, ValueError):
        return None
    return {_city_key(k): v for k, v in table.items()}.get(_city_key(city))


def _nominatim(city):
    name, _, state = (x.strip() for x in city.partition(","))
    r = requests.get(NOMINATIM, params={"city": name, "state": state, "country": "US", "format": "json", "limit": 1},
                     timeout=30, headers=UA)
    time.sleep(1.1)
    results = r.json() if r.status_code == 200 else []
    if not results:
        return None
    south, north, west, east = (float(x) for x in results[0]["boundingbox"])
    return [west, south, east, north]


def _photon(city):
    name, _, state = (x.strip() for x in city.partition(","))
    state_name = STATE_NAMES.get(state.upper(), state)
    r = requests.get(PHOTON, params={"q": f"{name}, {state_name}", "limit": 5, "layer": "city"}, timeout=30, headers=UA)
    places = [f.get("properties") or {} for f in (r.json().get("features", []) if r.status_code == 200 else [])]
    places = [p for p in places if p.get("countrycode") == "US" and p.get("extent")
              and (not state or (p.get("state") or "").lower() == state_name.lower())]
    places.sort(key=lambda p: (p.get("name") or "").lower() != name.lower())
    if not places:
        return None
    west, north, east, south = places[0]["extent"]
    return [west, south, east, north]


def city_bbox(city):
    box = _known(city)
    for lookup in (_nominatim, _photon):
        if box:
            break
        try:
            box = lookup(city)
        except (requests.RequestException, ValueError, KeyError):
            box = None
    if not box:
        raise ProspectError(f"Couldn't find the city '{city}'. Write it like \"Columbus, OH\" in config.yaml.")
    return box


def _overlaps(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


# Cleaning --------------------------------------------------------------------------------------
def digits(phone):
    d = re.sub(r"\D", "", phone or "")
    return d[1:] if len(d) == 11 and d.startswith("1") else d


def format_phone(raw):
    d = digits(raw)
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else (raw or "").strip()


def nice_case(text):
    text = " ".join((text or "").split())
    if not (text.isupper() or text.islower()):
        return text

    def word(w):
        core = w.strip(",.;:()")
        keep = core.upper() in KEEP_UPPER or (core and not core.isalpha())
        return w if keep else w.capitalize()
    return " ".join(word(w) for w in text.split())


def clean_name(name):
    name = nice_case(name)
    for _ in range(2):
        name = LEGAL.sub("", name).strip(" ,-")
    return name


def host(url):
    h = (urllib.parse.urlparse(url if "//" in (url or "") else "https://" + (url or "")).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def own_site(url):
    """The business's own website, or '' when the listing points at a platform page."""
    u = (url or "").strip()
    if not u:
        return ""
    u = u if "://" in u else "https://" + u
    h = host(u)
    if not h or any(h == d or h.endswith("." + d) or (d.endswith(".") and h.startswith(d)) for d in NOT_OWN_SITE):
        return ""
    return u


def _name_words(name):
    return [w for w in re.findall(r"[a-z0-9]{3,}", (name or "").lower()) if w not in GENERIC]


def email_belongs(email, website, name):
    """Whether a listed email is plausibly the business's own (not an agency's, a reporter's, or a typo)."""
    email = (email or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,24}", email):
        return False
    local, _, domain = email.partition("@")
    if re.match(r"^(noreply|no-reply|donotreply|privacy|abuse|webmaster|postmaster)$", local):
        return False
    site = host(website)
    if site and (domain == site or site.endswith("." + domain) or domain.endswith("." + site)):
        return True
    words = _name_words(name)
    squashed = re.sub(r"[^a-z0-9]", "", local)
    if domain in FREE_MAIL:
        return not words or any(w in squashed for w in words)
    # another domain: fine when the domain itself carries the business name (a second domain they own)
    return bool(words) and any(w in domain.replace("-", "") for w in words) and not site


# Search ----------------------------------------------------------------------------------------
def _query(urls, box, categories):
    import duckdb

    con = duckdb.connect()
    try:
        con.execute("INSTALL httpfs; LOAD httpfs; SET enable_progress_bar = false;")
        sql = f"""
            SELECT id, names.primary, taxonomy.primary, confidence, phones, websites, emails, socials,
                   addresses, brand.names.primary, operating_status
            FROM read_parquet({json.dumps(urls)})
            WHERE bbox.xmin BETWEEN ? AND ? AND bbox.ymin BETWEEN ? AND ?
              AND taxonomy.primary IN ({", ".join("?" for _ in categories)})
              AND coalesce(operating_status, 'open') NOT IN ('permanently_closed', 'temporarily_closed')
        """
        return con.execute(sql, [box[0], box[2], box[1], box[3], *categories]).fetchall()
    finally:
        con.close()


def candidates(rows, city):
    home_name, _, home_state = (x.strip() for x in city.partition(","))
    home_state = home_state.upper()
    out = []
    for (pid, name, category, conf, phones, websites, emails, socials, addresses, brand, status) in rows:
        if not name:
            continue
        addr = (addresses or [None])[0] or {}
        state = (addr.get("region") or "").upper().replace("US-", "")
        state = state if len(state) == 2 else home_state
        town = nice_case(addr.get("locality")) or home_name
        site = next((own_site(w) for w in (websites or []) if own_site(w)), "")
        nice = clean_name(name)
        out.append({
            "id": "ov:" + pid, "source": "overture", "name": nice, "category": category,
            "niche": CATEGORY_NICHE.get(category, "shop"), "street": " ".join((addr.get("freeform") or "").split()),
            "city": town, "state": state, "zip": (addr.get("postcode") or "")[:5],
            "phone": format_phone((phones or [""])[0]), "website": site,
            "listed_site": (websites or [""])[0] or "",
            "emails": [e.lower() for e in (emails or []) if e and email_belongs(e, site, nice)],
            "socials": [s for s in (socials or []) if s][:4], "confidence": round(conf or 0, 2), "brand": brand or "",
            "maps_url": "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote_plus(f"{nice} {town} {state}"),
        })
    states = collections.Counter(c["state"] for c in out)
    local = {s for s, n in states.items() if s == home_state or n >= max(3, 0.03 * len(out))}
    out = [c for c in out if c["state"] in local]
    best = {}
    for c in out:
        k = digits(c["phone"]) or c["name"].lower()
        if k not in best or c["confidence"] > best[k]["confidence"]:
            best[k] = c
    out = list(best.values())
    numbers = collections.defaultdict(set)
    sites = collections.Counter(host(c["website"]) for c in out if c["website"])
    for c in out:
        numbers[c["name"].lower()].add(digits(c["phone"]))
    for c in out:
        c["chain"] = bool(c["brand"]) or len(numbers[c["name"].lower()]) >= 3 or (
            bool(c["website"]) and sites[host(c["website"])] >= 3)
    out.sort(key=lambda c: -c["confidence"])
    return out


def search(store, city, niches):
    """Every business of these kinds in and around a city, as prospects (not yet checked)."""
    geo = store.data.setdefault("geo", {})
    if city not in geo:
        geo[city] = city_bbox(city)
    box = geo[city]
    categories = [c for n in niches for c in NICHES.get(n, [])]
    if not categories:
        return []
    for attempt in (0, 1):
        cache = release_files(store, refresh=bool(attempt))
        urls = [u for b, u in cache["files"] if _overlaps(b, box)]
        if not urls:
            return []
        try:
            rows = _query(urls, box, categories)
            break
        except Exception as e:
            if attempt:
                raise ProspectError(f"Reading Overture's data failed: {str(e)[:300]}")
    return candidates(rows, city)
