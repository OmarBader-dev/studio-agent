"""Paying clients: their weekly posts, design requests, approvals, posting and monthly reports.

Each client's plan decides which agent works for them (settings.PLANS): "social" gets the social media agent
(weekly posts, stories, Reel, Google post, posting, report), "design" gets the design agent (designs on request,
menus, price lists, schedules, print PDFs, a monthly allowance), and "bundle" gets both.

clients.yaml lists them. Each week, on the client's content day, the agent plans and designs next week's
posts (with their own photos from clients/<name>/photos first), publishes a pack page, and either sends
it to you on Telegram to check first (review_first: true, the default) or emails it to the client with the
images attached. "approved" in their reply approves it. Approved posts are posted for them when Meta is
connected, otherwise you get a Telegram reminder with the image and caption on each posting day.
"""
import datetime as dt
import json
import pathlib
import re

from . import ai, brand, design, designer, mailer, menus, notify, packs, social, trends
from .notify import esc, link, telegram
from .settings import CACHE, ROOT, client_folders, plan_has, plan_of
from .store import iso, now

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def key_of(client):
    return re.sub(r"[^a-z0-9]+", "-", client["name"].lower()).strip("-")


def find(cfg, name):
    """A client by (part of) their name, or by website."""
    want = (name or "").lower().strip()
    for c in cfg.get("clients") or []:
        if want and (want in c["name"].lower() or want in (c.get("website") or "").lower()):
            return c
    return None


def kit_for(cfg, store, client):
    """The client's brand kit: their website, refreshed monthly, plus their own photos and any overrides."""
    key = key_of(client)
    path = CACHE / "clients" / key / "kit.json"
    kit = None
    if path.exists() and (now().timestamp() - path.stat().st_mtime) < 30 * 86400:
        try:
            kit = json.loads(path.read_text())
        except ValueError:
            kit = None
    if kit is None:
        kit = brand.read(client["website"], niche=client.get("niche", "restaurant"), name=client["name"],
                         folder=CACHE / "clients" / key / "site") if client.get("website") else {"ok": False}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(kit, default=str))
    kit = dict(kit, name=client["name"], niche=client.get("niche", kit.get("niche") or "restaurant"))
    city, _, state = (client.get("city") or "").partition(",")
    kit.update(city=city.strip() or kit.get("city"), state=state.strip() or kit.get("state"))
    override = client.get("brand") or {}
    if override.get("colors"):
        kit["colors"] = dict(kit.get("colors") or {}, **override["colors"])
    if override.get("fonts"):
        kit["fonts"] = dict(kit.get("fonts") or {}, **override["fonts"], from_site=True)
    if override.get("logo") and (ROOT / override["logo"]).exists():
        kit["logo"] = {"path": str(ROOT / override["logo"]), "kind": "raster", "tone": override.get("logo_tone", "mid")}
    own = sorted((p for folder in client_folders(key) for p in (folder / "photos").glob("*")
                  if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")), key=lambda p: p.name)
    if own:
        kit["photos"] = [{"path": str(p), "url": "", "w": 0, "h": 0} for p in own[-12:]] + (kit.get("photos") or [])
    kit["rules"] = " ".join(x for x in (client.get("notes"), client.get("feedback")) if x)   # followed, not quoted
    if client.get("offerings"):                       # facts they gave you: up front, so the writer sees them
        kit["text"] = "[WHAT WE SELL] " + ", ".join(client["offerings"]) + "\n\n" + (kit.get("text") or "")
    return kit


def apply_overrides(cfg, store):
    """Changes you made from Telegram (/pause, /resume, /plan) on top of clients.yaml and saved clients."""
    for c in cfg.get("clients") or []:
        book = store.client(key_of(c))
        if "paused" in book:
            c["paused"] = book["paused"]
        if book.get("plan"):
            c["plan"] = book["plan"]
        if (book.get("meta") or {}).get("page_id") and not c.get("meta_page_id"):
            c["meta_page_id"], c["meta_ig_id"] = book["meta"]["page_id"], book["meta"].get("ig_id")
    return cfg


def meta_on(cfg):
    from . import meta
    return meta.enabled(cfg)


def week_start(today=None, ahead=True):
    """The Monday of next week (ahead) or this week."""
    today = today or dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    return monday + dt.timedelta(days=7) if ahead else monday


def due(cfg, store, today=None):
    """Clients whose content day is today and who don't have next week's pack yet."""
    today = today or dt.date.today()
    out = []
    for c in cfg.get("clients") or []:
        if not plan_has(c, "social") or c.get("paused"):
            continue
        day = str(c.get("content_day") or "thursday").lower()
        week = week_start(today).isoformat()
        if DAYS[today.weekday()] == day and week not in store.client(key_of(c))["weeks"]:
            out.append(c)
    return out


def make_week(cfg, store, renderer, client, site_root, start=None):
    """Plan and design a client's posts for a week, and write their pack page. Returns the week record."""
    start = start or week_start()
    key = key_of(client)
    kit = kit_for(cfg, store, client)
    city = client.get("city") or f"{kit.get('city')}, {kit.get('state')}"
    radar = trends.radar(cfg, store, city=city)
    n = int(client.get("posts_per_week") or cfg["offer"]["posts_per_week"])
    posts = social.plan(cfg, store, kit, radar, n=n, start=start)
    work = CACHE / "clients" / key / start.isoformat()
    designer.design_posts(cfg, store, renderer, kit, posts, work, extra_images=True, seed=start.toordinal(),
                          photo_first=True)
    stories = []
    if client.get("stories", True):
        stories = [dict(p, content=dict(p["content"]), format="story") for p in posts[:2]]
        designer.design_posts(cfg, store, renderer, kit, stories, work / "stories", fmt="story", extra_images=True,
                              seed=start.toordinal() + 50, photo_first=True)
    reel = None
    if client.get("reels", True) and posts:                # the week's first post as a short video
        reel = designer.reel(renderer, kit, stories[0] if stories else posts[0], work / "reel.mp4", seed=start.toordinal())
    gbp = None
    if client.get("google_posts", True) and posts:          # the same news for their Google Business Profile
        gbp = social.gbp_post(kit, posts[0])
        g = dict(posts[0], content=dict(posts[0]["content"]))
        designer.design_posts(cfg, store, renderer, kit, [g], work / "google", fmt="gbp", extra_images=True,
                              seed=start.toordinal() + 90)
        gbp["image"] = g.get("image")
    token = packs.new_token(12)
    label = f"Week of {start:%b %-d}"
    sunday = (start - dt.timedelta(days=1)).strftime("%A")
    extras = [f"{len(stories)} story versions" if stories else "", "a Reel" if reel else "",
              "a Google post" if gbp and gbp.get("image") else ""]
    extras = [x for x in extras if x]
    note = (f"Here are {len(posts)} posts for the {label[0].lower() + label[1:]}"
            + (" plus " + (", ".join(extras[:-1]) + " and " + extras[-1] if len(extras) > 1 else extras[0]) if extras else "")
            + ", designed in your brand and timed for what's happening. Captions and hashtags are ready to go."
            + ("" if client.get("auto_approve") is False else
               f" If I don't hear back by {sunday}, they'll go out as planned."))
    packs.write_week(cfg, kit, posts, key, label, note, token, root=site_root, stories=stories, reel=reel, gbp=gbp)
    record = {"status": "made", "token": token, "label": label, "made_at": iso(), "note": note, "posts": [
        {k: p.get(k) for k in ("day", "time", "moment", "idea", "caption", "hashtags", "alt_text", "image", "style",
                               "issues")}
        | {"headline": p["content"].get("headline")} for p in posts],
        "stories": [{"image": s.get("image"), "headline": s["content"].get("headline"), "day": s.get("day"),
                     "issues": s.get("issues")} for s in stories],
        "reel": str(reel) if reel else None, "google": gbp}
    store.client(key)["weeks"][start.isoformat()] = record
    return record


def week_problems(record):
    """Why a made week shouldn't go to the client without your check. Empty when it's fine."""
    out = []
    for i, p in enumerate(record["posts"], 1):
        if not p.get("image") or not pathlib.Path(p["image"]).exists():
            out.append(f"post {i} has no picture")
        elif p.get("issues"):
            out.append(f"post {i}'s design didn't pass its check ({', '.join(p['issues'])[:80]})")
        if len((p.get("caption") or "").split()) < 12:
            out.append(f"post {i}'s caption is too short")
    return out


def deliver(cfg, store, client, week, record, base_url):
    """Send a made week to the client. On autopilot it goes straight to them when every check passes (you get a
    copy); otherwise, or with review_first: true, it comes to you first."""
    key = key_of(client)
    record["url"] = f"{base_url}/c/{key}/{record['token']}/"
    if record["status"] != "made":
        return record["status"]
    problems = week_problems(record)
    imgs = [p["image"] for p in record["posts"] if p.get("image")]
    if client.get("review_first", not cfg["autopilot"]["clients"]) or problems or not client.get("email"):
        record["status"] = "review"
        notify.album(cfg, imgs, f"<b>{esc(client['name'])}</b> · {esc(record['label'])}")
        if record.get("reel") and pathlib.Path(record["reel"]).exists():
            notify.video(cfg, record["reel"], f"<b>{esc(client['name'])}</b> · this week's Reel",
                         cover=pathlib.Path(record["reel"]).with_suffix(".jpg"))
        why = (["", "It needs your check because " + "; ".join(problems) + "."] if problems else
               ["", "It needs your check because they have no email in their client details."] if not client.get("email")
               else [])
        telegram(cfg, "\n".join([f"<b>Check {esc(client['name'])}'s posts for {esc(record['label'].lower())}</b>",
                                 link(record["url"], "Open the pack")] + [esc(x) for x in why] + ["",
                                 f"Send them to the client: <code>/approve {esc(key)}</code>",
                                 f"Make new ones: <code>/week {esc(key)}</code>"]))
        return "review"
    send_to_client(cfg, store, client, week, record)
    notify.album(cfg, imgs, f"<b>{esc(client['name'])}</b> · {esc(record['label'])} · sent to them automatically · "
                            + link(record["url"], "pack"))
    return "sent"


def send_to_client(cfg, store, client, week, record):
    if not client.get("email"):
        telegram(cfg, f"{esc(client['name'])} has no email in clients.yaml, so send them the pack yourself: "
                      f"{link(record.get('url'), 'pack')}")
        record["status"] = "sent"
        return
    posts = [dict(p, content={"headline": p.get("headline")}) for p in record["posts"]]
    email = mailer.week_email(client, cfg, record["url"], posts, record.get("note") or
                              f"Here are your posts for {record['label'].lower()}, designed in your brand.",
                              extra_files=[record.get("reel")])
    msgid = send_email(cfg, client, email)
    record.update(status="sent", sent_at=iso(), msgid=msgid)


def settle(cfg, store, today=None):
    """Weeks the client didn't answer about are approved the day before they start (unless auto_approve: false)."""
    today = today or dt.date.today()
    n = 0
    for c in cfg.get("clients") or []:
        if c.get("auto_approve") is False:
            continue
        for week, record in store.client(key_of(c))["weeks"].items():
            if record.get("status") == "sent" and today >= dt.date.fromisoformat(week) - dt.timedelta(days=1):
                record.update(status="approved", approved_at=iso(), approved_by="no reply")
                n += 1
    return n


def todays_posts(cfg, store, today=None):
    """(client, week record, post) for approved posts scheduled today."""
    today = (today or dt.date.today()).isoformat()
    out = []
    for c in cfg.get("clients") or []:
        for week, record in store.client(key_of(c))["weeks"].items():
            if record.get("status") != "approved":
                continue
            for p in record["posts"]:
                if p.get("day") == today and not p.get("posted"):
                    out.append((c, record, p))
    return out


def remind(cfg, store, today=None):
    """Your Telegram reminders: weeks still waiting for your check two days before they start, and today's posts
    (when they aren't posted automatically)."""
    today = today or dt.date.today()
    n = 0
    for c in cfg.get("clients") or []:
        key = key_of(c)
        for week, record in store.client(key)["weeks"].items():
            if record.get("status") == "review" and not record.get("nudged") and \
                    today >= dt.date.fromisoformat(week) - dt.timedelta(days=2):
                telegram(cfg, f"⏰ {esc(c['name'])}'s posts for {esc(record['label'].lower())} are still waiting for "
                              f"your check. {link(record.get('url'), 'Open the pack')}\n"
                              f"Send them: <code>/approve {esc(key)}</code> · Make new ones: <code>/week {esc(key)}</code>")
                record["nudged"] = iso()
                n += 1
    for client, record, post in todays_posts(cfg, store, today):
        if meta_on(cfg) and client.get("meta_page_id"):
            continue
        if post.get("reminded"):
            continue
        if cfg["autopilot"]["clients"] and client.get("email"):
            # not connected to Meta yet: the client gets today's post by email, ready to share
            post["reminded"] = iso()
            send_email(cfg, client, mailer.post_today_email(client, cfg, post, record.get("url")))
            n += 1
            continue
        tags = " ".join("#" + t for t in post.get("hashtags") or [])
        caption = f"<b>Post today for {esc(client['name'])}</b> at {esc(post.get('time'))}\n<pre>{esc(post.get('caption'))}\n\n{esc(tags)}</pre>"
        if post.get("image") and pathlib.Path(post["image"]).exists():
            notify.photo(cfg, post["image"], caption)
        else:
            telegram(cfg, caption + "\n" + link(record.get("url"), "Images in the pack"))
        post["reminded"] = iso()
        n += 1
    return n


def send_email(cfg, client, email, reply_to=None):
    """Email a client (not a sales email). In draft mode it's shown to you on Telegram instead.
    Returns the email's Message-ID (None in draft mode), so their replies can be matched to it."""
    to = (client.get("email") or "").split(",")[0].strip()
    if not cfg.live or not to:
        telegram(cfg, f"<i>{'Draft mode' if to else 'No email for them'}, so this wasn't sent to "
                      f"{esc(client['name'])}:</i> {esc(email.subject)}\n<pre>{esc(email.text[:1500])}</pre>")
        return None
    m = mailer.Mailer(cfg)
    try:
        return m.send(to, email, reply_to_id=reply_to, sales=False)
    finally:
        m.close()


def design_job(cfg, store, renderer, client, request, out_root=None, source="you", revision_of=None):
    """Versions of a requested design. A request the client emailed goes straight back to them on autopilot (they
    reply with the number they like, or with changes); one you asked for comes to you on Telegram. Returns the job id."""
    kit = kit_for(cfg, store, client)
    job = new_job_id(store, client)
    folder = (out_root or CACHE / "jobs") / job
    listing = menus.extract(cfg, store, kit, request) if menus.wanted(request) else None
    if listing:                                            # a menu, price list or schedule: print-ready pages
        fmt = "flyer"
        results, extras = menus.variants(renderer, kit, listing, folder)
    else:
        extras = []
        fmt, content = designer.request_to_content(cfg, store, kit, request)
        results = designer.variants(cfg, store, renderer, kit, content, fmt, folder, n=3, seed=len(store.data["jobs"]))
    good = [i for i, (_, _, issues) in enumerate(results) if not issues]
    paths = [str(results[i][0]) for i in good] or [str(p) for p, _, _ in results]
    extras = [extras[i] for i in good if i < len(extras)] if good else extras
    rounds = 0
    if revision_of and revision_of in store.data["jobs"]:
        rounds = int(store.data["jobs"][revision_of].get("round", 0)) + 1
    used = designs_this_month(store, client) + (0 if revision_of else 1)
    store.data["jobs"][job] = {"client": client["name"], "request": request[:800], "paths": paths, "format": fmt,
                               "at": iso(), "status": "review", "posts": extras, "kind": "list" if listing else "design",
                               "source": source, "revision_of": revision_of, "round": rounds}
    allowance = int(client.get("designs_per_month") or cfg["offer"]["designs_per_month"])
    is_client = bool(find(cfg, client["name"]))
    auto = (source == "client" and cfg["autopilot"]["clients"] and is_client and plan_has(client, "design")
            and client.get("email") and good and (revision_of or used <= allowance))
    if auto:
        offer_versions(cfg, store, job)
        notify.album(cfg, paths, f"<b>{esc(client['name'])}</b>: {esc(request[:160])}\nSent to them to pick from"
                                 + (f" (changes, round {rounds})" if revision_of else f" · design {used} of {allowance} this month"))
        return job
    notify.album(cfg, paths, f"<b>{esc(client['name'])}</b>: {esc(request[:200])}")
    if not is_client:
        count = ""                                         # a website, not a client: a one-off
    elif not plan_has(client, "design"):
        count = (f"\nNote: {esc(client['name'])} is on the {esc(plan_of(client).title())} plan, which doesn't include "
                 f"design. This one is your call (or offer them Design).")
    elif used > allowance:
        count = f"\nThis is design {used} this month; their plan includes {allowance}, so it waits for you."
    elif not good:
        count = "\nThe designs didn't pass their checks, so they wait for you."
    else:
        count = f"\nDesign {used} of {allowance} this month."
    telegram(cfg, f"Send these to {esc(client['name'])}: <code>/send {job}</code> (they pick one) or "
                  f"<code>/send {job} 2</code> (just version 2). Ask for changes: <code>/design {esc(key_of(client))}: …</code>"
                  + count)
    return job


def new_job_id(store, client, kind=""):
    """A short, unique id for a design job, like bean-co-10261412 (the one you type in /send)."""
    base = f"{key_of(client)[:12]}{'-' + kind if kind else ''}-{now():%m%d%H%M}"
    job, n = base, 1
    while job in store.data["jobs"]:
        n += 1
        job = f"{base}-{n}"
    return job


def designs_this_month(store, client, month=None):
    """How many designs a client has had this month (requests and posters; changes to one don't count)."""
    month = month or now().strftime("%Y-%m")
    return sum(1 for j in store.data["jobs"].values()
               if j.get("client") == client["name"] and str(j.get("at", "")).startswith(month) and not j.get("revision_of"))


def _job_files(job, chosen):
    paths = [job["paths"][i] for i in chosen if i < len(job["paths"])]
    if job["format"] == "flyer":                          # print-ready PDFs, and post versions when there are some
        paths += [str(pathlib.Path(p).with_suffix(".pdf")) for p in list(paths) if pathlib.Path(p).with_suffix(".pdf").exists()]
    paths += [job["posts"][i] for i in chosen if i < len(job.get("posts") or []) and pathlib.Path(job["posts"][i]).exists()]
    return [p for p in paths if pathlib.Path(p).exists()]


def offer_versions(cfg, store, job_id):
    """Email the client the versions to pick from. Returns a line for you."""
    job = store.data["jobs"][job_id]
    client = find(cfg, job["client"])
    paths = [p for p in job["paths"] if pathlib.Path(p).exists()]
    if not paths:
        return "That design job's files are gone (old jobs are cleaned up). Make it again with /design."
    if not client or not client.get("email"):
        return "That client has no email in their details. Download the designs from Telegram and send them yourself."
    msgid = send_email(cfg, client, mailer.design_email(client, cfg, job["request"], paths))
    job.update(status="offered", offered_at=iso(), msgid=msgid)
    return (f"Sent {client['name']} {len(paths)} version(s) to pick from." if cfg.live else
            f"Draft mode: the {len(paths)} version(s) for {client['name']} weren't sent.")


def deliver_pick(cfg, store, job_id, n):
    """Email the client the final files of version n (picture, print PDF, post version). Returns a line for you."""
    job = store.data["jobs"][job_id]
    client = find(cfg, job["client"])
    if not (0 < n <= len(job["paths"])):
        return f"That job has {len(job['paths'])} versions."
    paths = _job_files(job, [n - 1])
    if not paths:
        return "That design job's files are gone (old jobs are cleaned up). Make it again with /design."
    if not client or not client.get("email"):
        return "That client has no email in their details. Download the designs from Telegram and send them yourself."
    send_email(cfg, client, mailer.design_email(client, cfg, job["request"], paths, final=True), reply_to=job.get("msgid"))
    job.update(status="done", picked=n, sent_at=iso())
    return (f"Sent {client['name']} the final files of version {n}." if cfg.live else
            f"Draft mode: the final files of version {n} weren't sent.")


def send_job(cfg, store, job_id, pick=None):
    """Your /send: the versions for the client to pick from, or (with a number) the final files of that version."""
    if job_id not in store.data["jobs"]:
        return f"No design job {job_id}."
    if pick and str(pick).isdigit():
        return deliver_pick(cfg, store, job_id, int(pick))
    return offer_versions(cfg, store, job_id)


PICK = re.compile(r"^\W*(?:(?:i(?:'?d| would)?\s+)?(?:like|love|want|choose|pick|prefer|take|go with|let'?s go with)\s+)?"
                  r"(?:(?:option|version|design|number|no\.?|#)\s*)?(?:the\s+)?"
                  r"(1|2|3|one|two|three|first|second|third|1st|2nd|3rd)\b(?:\s+one)?", re.I)
NUMBERS = {"1": 1, "one": 1, "first": 1, "1st": 1, "2": 2, "two": 2, "second": 2, "2nd": 2, "3": 3, "three": 3,
           "third": 3, "3rd": 3}
CHANGE = re.compile(r"\b(but|change|can you|could you|make|instead|except|add|remove|swap|replace|bigger|smaller|"
                    r"different|without|with the|move|fix|wrong|typo)\b", re.I)
THANKS = re.compile(r"^\W*(thanks?|thank you|thx|ty|great|awesome|perfect|love (?:it|them)|looks? (?:good|great)|"
                    r"got it|received)\W*(?:(?:so|very) much)?\W*$", re.I)


def reply_to_job(cfg, store, job_id, text, on_revision=None):
    """A client answered a design email: a number picks that version, thanks needs nothing, anything else is a change
    request, redone (up to autopilot.revisions times; after that it comes to you). Returns a line for you."""
    job = store.data["jobs"][job_id]
    client = find(cfg, job["client"])
    first = (text or "").strip().splitlines()[0][:120] if (text or "").strip() else ""
    m = PICK.match(first)
    rest = (text or "").strip()[m.end():] if m else ""
    if m and job.get("status") == "offered" and not CHANGE.search(rest):
        return deliver_pick(cfg, store, job_id, NUMBERS[m.group(1).lower()])
    if m:                                                 # "2, but with Saturday instead": redo from version 2
        text = f"Start from version {NUMBERS[m.group(1).lower()]}. {rest.lstrip(' ,.;:-')}"
    if THANKS.match(first) or not first:
        if job.get("status") == "offered" and len(job["paths"]) == 1:
            return deliver_pick(cfg, store, job_id, 1)
        return ""
    root = job.get("revision_of") or job_id
    if job.get("round", 0) >= cfg["autopilot"]["revisions"] or not on_revision or not client:
        telegram(cfg, f"<b>{esc(job['client'])} wants more changes</b> to {esc(job['request'][:80])}:\n<i>{esc(text[:600])}</i>\n"
                      f"Make them with <code>/design {esc(key_of(client) if client else job['client'])}: …</code>")
        return "sent to you"
    request = store.data["jobs"][root]["request"].split("\nChanges they asked for:")[0]
    on_revision(client, f"{request}\nChanges they asked for: {text.strip()[:500]}", job_id)
    return "redone with their changes"


def job_for_reply(store, msgids):
    """The design job a client's email answers (by the email it replies to)."""
    for job_id, job in store.data["jobs"].items():
        if job.get("msgid") and job["msgid"] in msgids:
            return job_id
    return None


def week_for_reply(store, client, msgids):
    book = store.client(key_of(client))
    for week, record in book["weeks"].items():
        if record.get("msgid") and record["msgid"] in msgids:
            return week
    return None


# Posters: the design agent's own initiative ---------------------------------------------------------------
def poster_moments(cfg, store, client, today=None, kit=None):
    """Days coming up in 7 to 31 days that suit this business and haven't had a poster yet."""
    from . import observances
    today = today or dt.date.today()
    site = (kit or {}).get("text") or ""
    niche = client.get("niche", "restaurant")
    done = store.client(key_of(client)).setdefault("posters", {})
    out = []
    for x in observances.upcoming(today + dt.timedelta(days=7), 24):
        if x["kind"] != "day" or niche not in x["niches"] or not observances.fits(x["title"], site):
            continue
        if f"{x['title']}|{x['date'][:4]}" not in done:
            out.append(x)
    return out


def posters_this_month(store, client, month=None):
    month = month or now().strftime("%Y-%m")
    return sum(1 for j in store.data["jobs"].values() if j.get("client") == client["name"] and j.get("kind") == "poster"
               and str(j.get("at", "")).startswith(month))


def poster_job(cfg, store, renderer, client, moment, out_root=None):
    """Two versions of a poster for a moment (print PDF, Letter) plus a post version, sent to the client on autopilot.
    The words follow the same rules as posts: only what their website backs up. Returns the job id or None."""
    kit = kit_for(cfg, store, client)
    title, day = moment["title"], dt.date.fromisoformat(moment["date"])
    data = ai.ask(cfg, store, f"""Write a window poster for {kit.get('name')} ({client.get('niche')}) in
{kit.get('city') or ''} for {title} on {day:%A, %B %-d}. Angle: {moment.get('angle')}.
WEBSITE TEXT (facts only): {(kit.get('text') or '')[:2500]}
{('RULES FROM THE CLIENT (always follow them): ' + kit['rules'][:400]) if kit.get('rules') else ''}
Only mention products from the website text; no prices, discounts, opening hours or events unless the text shows them.
Return JSON: {{"eyebrow": "2-4 words", "headline": "2-6 words", "subhead": "under 90 characters", "cta": "2-4 words",
"icon": "one emoji", "caption": "40-80 words for posting it on Instagram"}}""",
                  system=social.SYSTEM, max_tokens=900, temperature=0.7)
    p = dict(data) if isinstance(data, dict) else {}
    p.setdefault("headline", social.SEASON_LINES.get(title) or f"Happy {title}")
    p.update(moment=title, day=day.isoformat(), eyebrow=p.get("eyebrow") or title)
    if not p.get("caption"):
        p["caption"] = (f"{title} is almost here! From all of us at {kit.get('name')}, thank you for being part of our "
                        f"story. See you soon{', ' + kit['city'] if kit.get('city') else ''}!")
    post = social.clean_post(p, kit, social.profile(cfg, store, kit), day, "12:00", "poster")
    content = dict(post["content"], icon=p.get("icon") or moment.get("icon") or "")
    job = new_job_id(store, client, "poster")
    folder = (out_root or CACHE / "jobs") / job
    results = designer.variants(cfg, store, renderer, kit, content, "flyer", folder, n=2, seed=day.toordinal())
    good = [(p_, st) for p_, st, issues in results if not issues]
    if not good:
        telegram(cfg, f"A {esc(title)} poster for {esc(client['name'])} didn't pass its design check, so it was skipped.")
        return None
    photos = [p_["path"] for p_ in kit.get("photos") or [] if p_.get("path")]
    first_style = good[0][1]
    social_version, _, _ = design.render_best(renderer, {"format": "post", "style": first_style, "brand": kit,
                                                        "content": content, "seed": day.toordinal(),
                                                        "photo": photos[0] if photos and first_style in
                                                        designer.styles.NEEDS_PHOTO else None},
                                              folder / "post-version.png", designer.fallback_styles(kit, "post", first_style))
    paths = [str(p_) for p_, _ in good]
    files = paths + [str(pathlib.Path(x).with_suffix(".pdf")) for x in paths if pathlib.Path(x).with_suffix(".pdf").exists()] \
        + [str(social_version)]
    store.data["jobs"][job] = {"client": client["name"], "request": f"A poster for {title} ({day:%B %-d})", "paths": paths,
                               "format": "flyer", "at": iso(), "status": "review", "posts": [str(social_version)] * len(paths),
                               "kind": "poster", "moment": title, "caption": post["caption"], "source": "agent", "round": 0}
    store.client(key_of(client)).setdefault("posters", {})[f"{title}|{day.year}"] = job
    notify.album(cfg, paths + [str(social_version)], f"<b>{esc(client['name'])}</b>: a poster for {esc(title)}")
    if cfg["autopilot"]["clients"] and client.get("email"):
        msgid = send_email(cfg, client, mailer.poster_email(client, cfg, title, f"{day:%A, %B %-d}", files))
        store.data["jobs"][job].update(status="offered", offered_at=iso(), msgid=msgid)
        telegram(cfg, f"Sent {esc(client['name'])} a {esc(title)} poster on its own (design "
                      f"{designs_this_month(store, client)} of their month).")
    else:
        telegram(cfg, f"Send it to {esc(client['name'])}: <code>/send {job}</code>")
    return job


def make_posters(cfg, store, renderer, today=None):
    """Each design client gets up to autopilot.posters posters a month, for what's coming up, within their allowance.
    One per client per run. Returns the job ids."""
    made = []
    per_month = int(cfg["autopilot"].get("posters") or 0)
    for c in cfg.get("clients") or []:
        if not per_month or not plan_has(c, "design") or c.get("paused") or c.get("posters") is False:
            continue
        allowance = int(c.get("designs_per_month") or cfg["offer"]["designs_per_month"])
        if posters_this_month(store, c) >= per_month or designs_this_month(store, c) >= allowance:
            continue
        kit = kit_for(cfg, store, c)
        upcoming = poster_moments(cfg, store, c, today, kit)
        if upcoming:
            try:
                job = poster_job(cfg, store, renderer, c, upcoming[0])
            except Exception as e:                      # one client's poster never stops the run
                telegram(cfg, f"Couldn't make {esc(c['name'])}'s poster: {esc(str(e)[:200])}")
                job = None
            if job:
                made.append(job)
    return made


# Clients you add from Telegram, and their billing ---------------------------------------------------------
def add_client(cfg, store, lead, plan, email=""):
    """Make a business a client (from its lead record). Returns the client."""
    key = re.sub(r"[^a-z0-9]+", "-", lead["name"].lower()).strip("-")
    client = {"name": lead["name"], "website": lead.get("website") or "", "email": email or lead.get("email") or "",
              "niche": lead.get("niche") or "restaurant",
              "city": ", ".join(x for x in (lead.get("city"), lead.get("state")) if x), "plan": plan,
              "content_day": "thursday", "started": dt.date.today().isoformat(), "from_lead": lead.get("id")}
    store.data["clients_db"][key] = client
    cfg["clients"] = [c for c in cfg.get("clients") or [] if c["name"].lower() != client["name"].lower()] + [client]
    if lead.get("id") in store.leads:
        store.update(lead["id"], status="client", plan_chosen=plan)
    send_email(cfg, client, mailer.welcome_email(client, cfg))
    return client


def first_bill(client):
    """The first payment date: after the free first week when there's a trial."""
    try:
        start = dt.date.fromisoformat(str(client.get("started")))
    except ValueError:
        return None
    return start + dt.timedelta(days=7 if client.get("trial", True) else 0)


def billing_reminders(cfg, store, today=None):
    """Telegram reminders to send each client's monthly payment request (clients added with /client). Once a month,
    from their billing day until you send /paid. Returns how many were sent."""
    today = today or dt.date.today()
    prices = {"social": cfg["offer"]["social_monthly"], "design": cfg["offer"]["design_monthly"],
              "bundle": cfg["offer"]["bundle_monthly"]}
    n = 0
    for c in cfg.get("clients") or []:
        first = first_bill(c)
        if not first or today < first or c.get("paused"):
            continue
        day = min(first.day, 28)
        due = dt.date(today.year, today.month, day)
        if today < due:                                    # this month's isn't due yet: last month's may be open
            prev = today.replace(day=1) - dt.timedelta(days=1)
            due = dt.date(prev.year, prev.month, day)
            if due < first.replace(day=day):
                continue
        period = due.strftime("%Y-%m")
        book = store.client(key_of(c))
        if period in book.setdefault("paid", []) or book.setdefault("billed", {}).get(period):
            continue
        price = c.get("price") or prices[plan_of(c)]
        telegram(cfg, f"💳 <b>{esc(c['name'])}</b>: send this month's Payoneer request, ${price} ({esc(plan_of(c))}), to "
                      f"{esc(c.get('email') or 'their email')}. When it's paid: <code>/paid {esc(key_of(c))}</code>")
        book["billed"][period] = iso()
        n += 1
    return n


def mark_paid(cfg, store, client, today=None):
    today = today or dt.date.today()
    book = store.client(key_of(client))
    month = today.strftime("%Y-%m")
    if month not in book.setdefault("paid", []):
        book["paid"].append(month)
    return month


def month_stats(store, client, month):
    """What was made for a client in a month ("YYYY-MM"): posts, Reels, Google posts, designs, and engagement."""
    weeks = [r for w, r in store.client(key_of(client))["weeks"].items() if w.startswith(month)]
    posts = [p for r in weeks for p in r["posts"]]
    delivered = [p for r in weeks if r.get("status") in ("approved", "sent") for p in r["posts"]]
    posted = [p for p in posts if p.get("posted")]
    designs = [j for j in store.data["jobs"].values() if j.get("client") == client["name"] and str(j.get("at", "")).startswith(month)]
    return {"planned": len(posts), "delivered": len(delivered), "posted": len(posted),
            "reels": sum(1 for r in weeks if r.get("reel")), "google": sum(1 for r in weeks if r.get("google")),
            "designs": len(designs), "likes": sum(p.get("likes", 0) for p in posted),
            "comments": sum(p.get("comments", 0) for p in posted),
            "top": [p.get("headline") for p in sorted(posted, key=lambda p: -(p.get("likes", 0) + 3 * p.get("comments", 0)))[:3]
                    if p.get("likes") or p.get("comments")]}


def monthly_report(cfg, store, client, month):
    """A short report of a month's work for a client, as Telegram text (only what their plan includes)."""
    s = month_stats(store, client, month)
    parts = []
    if plan_has(client, "social"):
        parts.append(f"Posts: {s['planned']} made · {s['posted'] or s['delivered']} "
                     f"{'posted' if s['posted'] else 'delivered'} · Reels: {s['reels']} · Google posts: {s['google']}")
    if plan_has(client, "design") or s["designs"]:
        parts.append(f"Designs: {s['designs']}")
    lines = [f"<b>{esc(client['name'])} · {esc(month)}</b> ({esc(plan_of(client))})", " · ".join(parts)]
    if s["likes"] or s["comments"]:
        lines.append(f"Likes: {s['likes']} · Comments: {s['comments']}")
    lines += [f"• {esc(h)}" for h in s["top"]]
    return "\n".join(lines)


def monthly_reports(cfg, store, today=None):
    """On the first daily run of a month, each client's report for last month, with what's coming up next month.
    You get them on Telegram; in live mode each client also gets theirs by email (reports: false turns that off).
    Returns how many were made."""
    from . import meta, observances
    today = today or dt.date.today()
    if store.flag("report_month") == today.strftime("%Y-%m"):
        return 0
    store.flag("report_month", today.strftime("%Y-%m"))
    last = today.replace(day=1) - dt.timedelta(days=1)
    month = last.strftime("%Y-%m")
    if meta.enabled(cfg):
        meta.engagement(cfg, store, cfg.get("clients") or [])
    n = 0
    for c in cfg.get("clients") or []:
        stats = month_stats(store, c, month)
        if c.get("paused") or not (stats["planned"] or stats["designs"]):
            continue
        coming = []
        if plan_has(c, "social"):                          # next month's moments are for the social plan
            site = (kit_for(cfg, store, c).get("text") or "") if c.get("website") else ""
            niche = c.get("niche", "restaurant")
            coming = [x for x in observances.upcoming(today, 35)
                      if niche in x["niches"] and observances.fits(x["title"], site)][:6]
        telegram(cfg, monthly_report(cfg, store, c, month) + ("\n\nComing up: " + ", ".join(esc(x["title"]) for x in coming)
                                                              if coming else ""))
        if cfg.live and c.get("email") and c.get("reports", True):
            email = mailer.report_email(c, cfg, f"{last:%B}", stats, coming)
            m = mailer.Mailer(cfg)
            try:
                m.send(c["email"].split(",")[0].strip(), email, sales=False)
            finally:
                m.close()
        n += 1
    return n


def prune(cfg, days=45):
    """Delete old weekly work and design jobs from the run cache (the published packs stay online), so the cache
    stays small and fast to restore. Returns how many folders were removed."""
    import shutil
    cutoff = dt.date.today() - dt.timedelta(days=days)
    removed = 0
    for folder in (CACHE / "clients").glob("*/*"):
        try:
            old = folder.is_dir() and dt.date.fromisoformat(folder.name) < cutoff
        except ValueError:
            continue                                       # kit.json, site/, photos: kept
        if old:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    for folder in (CACHE / "jobs").glob("*"):
        if folder.is_dir() and (now().timestamp() - folder.stat().st_mtime) > days * 86400:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    return removed
