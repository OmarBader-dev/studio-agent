"""Optional: posting approved content to a client's Facebook Page and Instagram, through Meta's free Graph API.

Set posting.meta: true in config.yaml, put the client's meta_page_id (and meta_ig_id for Instagram) in
clients.yaml, and give the agent a token (see the README, "Posting for clients"): META_ACCESS_TOKEN is your
long-lived token from your own Meta app; the agent gets each Page's own token from it. In development mode a
Meta app can post to Pages and Instagram accounts of people who have a role on the app, so each client
adds you to their Page (or accepts a tester invite) once. Instagram allows 25 posts a day per account.
"""
import datetime as dt
import re
import time
from zoneinfo import ZoneInfo

import requests

from . import geo
from .notify import esc, telegram
from .store import iso

GRAPH = "https://graph.facebook.com/{v}"


def enabled(cfg):
    """Posting through Meta is on when the META_ACCESS_TOKEN secret is set (posting.meta: "auto", the default),
    or forced on/off with posting.meta: true/false."""
    setting = cfg["posting"].get("meta", "auto")
    return bool(cfg.secret("META_ACCESS_TOKEN")) and setting not in (False, "false", "off", "no")


def _graph(cfg):
    return GRAPH.format(v=cfg["posting"].get("graph_version", "v23.0"))


def page_token(cfg, client):
    user = cfg.secret("META_ACCESS_TOKEN")
    if not user or not client.get("meta_page_id"):
        return None
    try:
        r = requests.get(f"{_graph(cfg)}/{client['meta_page_id']}", params={"fields": "access_token", "access_token": user},
                         timeout=30)
        return r.json().get("access_token")
    except (requests.RequestException, ValueError):
        return None


def post_facebook(cfg, client, token, image_url, caption):
    r = requests.post(f"{_graph(cfg)}/{client['meta_page_id']}/photos", timeout=60,
                      data={"url": image_url, "caption": caption, "access_token": token})
    data = r.json()
    if r.status_code != 200:
        raise RuntimeError(data.get("error", {}).get("message", r.text[:200]))
    return data.get("post_id") or data.get("id")


def post_instagram(cfg, client, token, url, caption=None, kind="IMAGE"):
    """Publish to the client's Instagram: a feed picture (IMAGE), a Reel (REELS, url is the video) or a story
    (STORIES). Two steps, as Meta's content publishing API works: make a container, wait until it's processed,
    publish it. Returns the Instagram media id."""
    base = _graph(cfg)
    data = {"access_token": token}
    if kind == "REELS":
        data.update(media_type="REELS", video_url=url, share_to_feed="true")
    elif kind == "STORIES":
        data.update(media_type="STORIES", image_url=url)
    else:
        data.update(image_url=url)
    if caption and kind != "STORIES":
        data["caption"] = caption
    r = requests.post(f"{base}/{client['meta_ig_id']}/media", timeout=60, data=data)
    data = r.json()
    if r.status_code != 200:
        raise RuntimeError(data.get("error", {}).get("message", r.text[:200]))
    creation = data["id"]
    tries, wait = (30, 10) if kind == "REELS" else (10, 3)   # videos take a minute or more to process
    for _ in range(tries):
        s = requests.get(f"{base}/{creation}", params={"fields": "status_code", "access_token": token}, timeout=30).json()
        if s.get("status_code") in (None, "FINISHED"):
            break
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram couldn't process the {kind.lower()}")
        time.sleep(wait)
    r = requests.post(f"{base}/{client['meta_ig_id']}/media_publish", timeout=60,
                      data={"creation_id": creation, "access_token": token})
    data = r.json()
    if r.status_code != 200:
        raise RuntimeError(data.get("error", {}).get("message", r.text[:200]))
    return data.get("id")


def due_now(post, state):
    try:
        h, m = (int(x) for x in str(post.get("time", "12:00")).split(":"))
        when = dt.datetime.fromisoformat(post["day"]).replace(hour=h, minute=m, tzinfo=ZoneInfo(geo.tz_for(state)))
    except (ValueError, KeyError):
        return False
    return dt.datetime.now(ZoneInfo(geo.tz_for(state))) >= when


def publish_due(cfg, store, todays):
    """Post today's approved posts whose time has come. todays: [(client, week record, post)]. Returns count."""
    if not enabled(cfg):
        return 0
    done = 0
    for client, record, post in todays:
        if not client.get("meta_page_id") or post.get("posted"):
            continue
        state = (client.get("city") or "").partition(",")[2].strip()
        if not due_now(post, state):
            continue
        token = page_token(cfg, client)
        if not token:
            telegram(cfg, f"Couldn't get a posting token for {esc(client['name'])}'s Page. Check META_ACCESS_TOKEN and "
                          "that the client gave you access.")
            continue
        n = record["posts"].index(post) + 1
        image_url = f"{record['url']}post-{n}.jpg"
        caption = (post.get("caption") or "") + "\n\n" + " ".join("#" + t for t in post.get("hashtags") or [])
        try:
            if client.get("meta_ig_id"):
                post["ig_id"] = post_instagram(cfg, client, token, image_url, caption)
            if client.get("post_to_facebook", True):
                post["fb_id"] = post_facebook(cfg, client, token, image_url, caption)
            post["posted"] = iso()
            done += 1
        except (RuntimeError, requests.RequestException, KeyError, ValueError) as e:
            telegram(cfg, f"Posting for {esc(client['name'])} failed: {esc(str(e)[:200])}. Post it yourself today.")
            post["posted_error"] = str(e)[:200]
    return done


def extras_due(record, today=None):
    """The week's Reel and stories with their posting day and time: the Reel the day after the first post at 18:00,
    each story on its post's day. [(kind, n, day, time)]"""
    out = []
    posts = record.get("posts") or []
    if record.get("reel") and posts:
        try:
            day = (dt.date.fromisoformat(posts[0]["day"]) + dt.timedelta(days=1)).isoformat()
            out.append(("REELS", 1, day, "18:00"))
        except (KeyError, ValueError):
            pass
    for i, st in enumerate(record.get("stories") or [], 1):
        day = st.get("day") or (posts[i - 1]["day"] if i - 1 < len(posts) else None)
        if day:
            out.append(("STORIES", i, day, posts[i - 1].get("time", "12:00") if i - 1 < len(posts) else "12:00"))
    return out


def publish_extras(cfg, store, clients_list):
    """Post approved weeks' Reels and stories to Instagram when their time comes (clients with meta_ig_id).
    Returns how many were posted."""
    if not enabled(cfg):
        return 0
    from . import clients as cl
    done = 0
    for client in clients_list:
        if not client.get("meta_ig_id") or not client.get("meta_page_id") or client.get("paused"):
            continue
        state = (client.get("city") or "").partition(",")[2].strip()
        for week, record in store.client(cl.key_of(client))["weeks"].items():
            if record.get("status") != "approved" or not record.get("url"):
                continue
            posted = record.setdefault("extras_posted", {})
            for kind, n, day, at in extras_due(record):
                tag = f"{kind}-{n}"
                if tag in posted or not due_now({"day": day, "time": at}, state):
                    continue
                token = page_token(cfg, client)
                if not token:
                    continue
                url = f"{record['url']}reel.mp4" if kind == "REELS" else f"{record['url']}story-{n}.jpg"
                caption = None
                if kind == "REELS":
                    first = record["posts"][0]
                    caption = (first.get("caption") or "") + "\n\n" + " ".join("#" + t for t in first.get("hashtags") or [])
                try:
                    posted[tag] = post_instagram(cfg, client, token, url, caption, kind)
                    done += 1
                except (RuntimeError, requests.RequestException, KeyError, ValueError) as e:
                    posted[tag] = f"error: {str(e)[:120]}"
                    telegram(cfg, f"Posting {esc(client['name'])}'s {'Reel' if kind == 'REELS' else 'story'} failed: "
                                  f"{esc(str(e)[:200])}. It's in their pack if you want to post it yourself.")
    return done


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def autoconnect(cfg, store, clients_list):
    """Clients who added you to their Facebook Page get connected on their own: their Page and Instagram account
    are found among the Pages your token can manage (by name or website) and saved. Returns how many."""
    user = cfg.secret("META_ACCESS_TOKEN")
    from . import clients as cl
    from .settings import plan_has
    waiting = [c for c in clients_list if not c.get("meta_page_id") and plan_has(c, "social") and not c.get("paused")]
    if not enabled(cfg) or not waiting:
        return 0
    try:
        pages = requests.get(f"{_graph(cfg)}/me/accounts", timeout=30, params={
            "fields": "id,name,website,link,instagram_business_account{id,username}", "limit": 100,
            "access_token": user}).json().get("data") or []
    except (requests.RequestException, ValueError):
        return 0
    n = 0
    for c in waiting:
        domain = _norm(re.sub(r"^https?://(www\.)?", "", c.get("website") or "").split("/")[0])
        for page in pages:
            same_name = _norm(page.get("name")) == _norm(c["name"])
            same_site = domain and domain in _norm(page.get("website") or "")
            if not (same_name or same_site):
                continue
            ig = (page.get("instagram_business_account") or {}).get("id")
            book = store.client(cl.key_of(c))
            book["meta"] = {"page_id": page["id"], "ig_id": ig, "connected_at": iso()}
            c["meta_page_id"], c["meta_ig_id"] = page["id"], ig
            telegram(cfg, f"🔗 Connected {esc(c['name'])}'s Facebook Page" + (" and Instagram" if ig else
                          " (no Instagram linked to it yet)") + ". Their approved posts now go out automatically.")
            n += 1
            break
    return n


def engagement(cfg, store, clients_list):
    """Likes and comments on posted Instagram posts (for the monthly report)."""
    user = cfg.secret("META_ACCESS_TOKEN")
    if not user:
        return
    from . import clients as cl
    for client in clients_list:
        token = page_token(cfg, client)
        if not token:
            continue
        for record in store.client(cl.key_of(client))["weeks"].values():
            for post in record["posts"]:
                if post.get("ig_id"):
                    try:
                        d = requests.get(f"{_graph(cfg)}/{post['ig_id']}", timeout=30,
                                         params={"fields": "like_count,comments_count", "access_token": token}).json()
                        post["likes"], post["comments"] = d.get("like_count", 0), d.get("comments_count", 0)
                    except (requests.RequestException, ValueError):
                        continue
