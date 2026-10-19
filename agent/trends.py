"""The trend radar: what people are searching, talking about and doing right now, plus the calendar.

Free sources (no keys): Google Trends' daily trending searches (RSS), Bluesky's trending topics, the
calendar (observances.py and public holidays from Nager.Date), and the local weather forecast (Open-Meteo).
Optional free keys add YouTube's trending videos and Ticketmaster's local events.

News-driven trends are filtered for brand safety: no tragedies, crime, politics, illness or disasters,
and the social agent never uses a celebrity's or team's name in a way that suggests they endorse a business.
"""
import datetime as dt
import html
import json
import re

import requests

from . import observances, web
from .settings import CACHE

UNSAFE = re.compile(
    r"\b(dead|death|dies|died|killed|kill|shooting|shot|murder|stabb\w*|crash|accident|war|attack|bomb\w*|terror\w*|"
    r"hostage|election|vote|voting|ballot|trump|biden|harris|vance|obama|congress|senate|senator|democrat\w*|"
    r"republican\w*|president|governor|mayor|politic\w*|court|lawsuit|sued|indict\w*|arrest\w*|police|charged|"
    r"verdict|trial|prison|jail|hurricane|tornado|earthquake|flood\w*|wildfire|fire|storm|outbreak|virus|covid|"
    r"cancer|disease|hospital\w*|overdose|suicide|abuse|assault|scandal|racis\w*|protest\w*|riot|layoff\w*|"
    r"recession|tariff\w*|strike|shutdown|immigra\w*|deport\w*|ice raid|gun|weapon|missile|israel|gaza|ukraine|"
    r"russia|iran|china|nfl draft|lottery|powerball|mega millions|funeral|obituar\w*|missing|recall)(?:s|es)?\b", re.I)
WMO_SNOW = set(range(71, 78)) | {85, 86}
WMO_RAIN = set(range(51, 68)) | set(range(80, 83)) | {95, 96, 99}


def _get(url, **kw):
    try:
        r = requests.get(url, timeout=25, headers={"User-Agent": web.API_UA}, **kw)
        return r if r.status_code == 200 else None
    except requests.RequestException:
        return None


def safe(text, extra=()):
    t = text or ""
    return not UNSAFE.search(t) and not any(w.lower() in t.lower() for w in extra if w)


# Live sources ----------------------------------------------------------------------------------
def google_trends(geo="US"):
    """Today's trending searches: [{'title', 'traffic', 'context'}]."""
    r = _get("https://trends.google.com/trending/rss", params={"geo": geo})
    if not r:
        return []
    out = []
    for item in re.findall(r"<item>(.*?)</item>", r.text, re.S):
        title = html.unescape(re.search(r"<title>(.*?)</title>", item, re.S).group(1)).strip()
        traffic = re.search(r"<ht:approx_traffic>([\d,]+)\+?</ht:approx_traffic>", item)
        news = [html.unescape(n) for n in re.findall(r"<ht:news_item_title>(.*?)</ht:news_item_title>", item, re.S)]
        out.append({"title": title, "traffic": int(traffic.group(1).replace(",", "")) if traffic else 0,
                    "context": " / ".join(news[:2])[:240]})
    return out


def bluesky():
    """Topics trending on Bluesky right now: [{'title', 'context'}]."""
    r = _get("https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics")
    if not r:
        return []
    try:
        data = r.json()
    except ValueError:
        return []
    return [{"title": t.get("displayName") or t.get("topic"), "context": (t.get("description") or "")[:240]}
            for t in data.get("topics", []) if t.get("displayName") or t.get("topic")]


def holidays(year, country="US"):
    r = _get(f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country}")
    try:
        return [{"title": h["localName"] or h["name"], "date": h["date"]} for h in (r.json() if r else [])
                if h.get("global", True)]
    except (ValueError, KeyError, TypeError):
        return []


def weather(lat, lon):
    """Notable weather in the next week, as trend items (heat, cold snap, snow, rainy or sunny weekend)."""
    r = _get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": round(lat, 3), "longitude": round(lon, 3), "timezone": "auto", "forecast_days": 7,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum", "temperature_unit": "fahrenheit"})
    if not r:
        return []
    try:
        d = r.json()["daily"]
    except (ValueError, KeyError):
        return []
    out = []
    days = list(zip(d["time"], d["weather_code"], d["temperature_2m_max"], d["temperature_2m_min"], d["precipitation_sum"]))
    hot = [x for x in days if (x[2] or 0) >= 90]
    cold = [x for x in days if (x[2] if x[2] is not None else 99) <= 35]
    snow = [x for x in days if x[1] in WMO_SNOW]
    weekend = [x for x in days if dt.date.fromisoformat(x[0]).weekday() >= 5]
    if hot:
        out.append({"title": "Heat wave", "date": hot[0][0], "angle": f"highs near {round(max(x[2] for x in hot))}°F",
                    "icon": "☀️"})
    if snow:
        out.append({"title": "Snow day", "date": snow[0][0], "angle": "first snow of the week", "icon": "❄️"})
    elif cold:
        out.append({"title": "Cold snap", "date": cold[0][0], "angle": f"highs around {round(min(x[2] for x in cold))}°F",
                    "icon": "🧣"})
    if weekend and all((x[4] or 0) >= 4 or x[1] in WMO_RAIN for x in weekend):
        out.append({"title": "Rainy weekend", "date": weekend[0][0], "angle": "rain all weekend", "icon": "🌧️"})
    elif weekend and all(x[1] <= 3 and 60 <= (x[2] or 0) <= 88 for x in weekend):
        out.append({"title": "Sunny weekend", "date": weekend[0][0],
                    "angle": f"sunny, around {round(sum(x[2] for x in weekend) / len(weekend))}°F", "icon": "🌤️"})
    return out


def youtube(key, region="US"):
    if not key:
        return []
    r = _get("https://www.googleapis.com/youtube/v3/videos", params={
        "part": "snippet", "chart": "mostPopular", "regionCode": region, "maxResults": 25, "key": key})
    try:
        return [{"title": v["snippet"]["title"], "context": v["snippet"].get("channelTitle", "")}
                for v in (r.json().get("items", []) if r else [])]
    except (ValueError, KeyError):
        return []


def events(key, lat, lon, days=7):
    """Big local events (concerts, games, shows) in the next week, from Ticketmaster's free API."""
    if not key:
        return []
    start = dt.datetime.now(dt.timezone.utc)
    r = _get("https://app.ticketmaster.com/discovery/v2/events.json", params={
        "apikey": key, "latlong": f"{lat},{lon}", "radius": 15, "unit": "miles", "size": 20, "sort": "relevance,desc",
        "startDateTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endDateTime": (start + dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    try:
        items = r.json().get("_embedded", {}).get("events", []) if r else []
    except ValueError:
        return []
    out = []
    for ev in items:
        venue = ((ev.get("_embedded") or {}).get("venues") or [{}])[0].get("name", "")
        kind = ((ev.get("classifications") or [{}])[0].get("segment") or {}).get("name", "")
        out.append({"title": ev.get("name", ""), "date": (ev.get("dates", {}).get("start", {}) or {}).get("localDate", ""),
                    "context": f"{kind} at {venue}".strip()})
    return out


# The radar -------------------------------------------------------------------------------------
def city_center(store, city):
    """Latitude and longitude of a city, from the outline the prospecting step saved (or a lookup)."""
    box = (store.data.get("geo") or {}).get(city)
    if not box:
        from . import prospect
        try:
            box = prospect.city_bbox(city)
            store.data.setdefault("geo", {})[city] = box
        except Exception:
            return None
    return (box[1] + box[3]) / 2, (box[0] + box[2]) / 2


def radar(cfg, store, city=None, today=None, days=21):
    """Everything worth posting about for the next few weeks, for one city (weather, events) and the country.
    Cached per day and city. Returns {'calendar': [...], 'live': [...], 'weather': [...], 'events': [...]}."""
    today = today or dt.date.today()
    key = f"{today.isoformat()}:{city or 'all'}"
    cache_file = CACHE / "trends" / (re.sub(r"[^a-z0-9]+", "-", key.lower()) + ".json")
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except ValueError:
            pass
    country = cfg["trends"].get("country", "US")
    avoid = cfg["trends"].get("avoid") or []
    cal = observances.upcoming(today, days)
    known = {c["title"].lower() for c in cal}
    for h in holidays(today.year, country) + (holidays(today.year + 1, country) if today.month == 12 else []):
        d = dt.date.fromisoformat(h["date"])
        if 0 <= (d - today).days <= days and h["title"].lower() not in known:
            cal.append({"title": h["title"], "date": h["date"], "days_away": (d - today).days, "niches": observances.ALL,
                        "icon": "📅", "angle": "public holiday: hours and greetings", "kind": "holiday"})
    live = []
    for item in google_trends(country)[:25]:
        if safe(item["title"] + " " + item["context"], avoid):
            live.append(dict(item, source="Google Trends"))
    for item in bluesky()[:20]:
        if safe(item["title"] + " " + item["context"], avoid):
            live.append(dict(item, source="Bluesky"))
    for item in youtube(cfg.secret("YOUTUBE_API_KEY"), country)[:15]:
        if safe(item["title"], avoid):
            live.append(dict(item, source="YouTube"))
    out = {"date": today.isoformat(), "city": city, "calendar": sorted(cal, key=lambda c: c["days_away"]),
           "live": live, "weather": [], "events": []}
    if city:
        center = city_center(store, city)
        if center:
            out["weather"] = weather(*center)
            out["events"] = [e for e in events(cfg.secret("TICKETMASTER_API_KEY"), *center) if safe(e["title"], avoid)]
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(out, indent=1))
    return out


def for_niche(radar_data, niche, limit=8, site_text=None):
    """Calendar moments that suit a niche (and, given its website text, the business itself), soonest first."""
    from .observances import fits
    return [c for c in radar_data["calendar"] if niche in c.get("niches", [])
            and (site_text is None or fits(c["title"], site_text))][:limit]
