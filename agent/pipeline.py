"""The daily routine for finding clients: pick businesses, make each one a free sample (a week of posts in its
own brand), publish the samples, email them or hand them to you, and report to Telegram."""
import datetime as dt
import json
import pathlib
import random
import re
import shutil
import time
import urllib.parse

from . import brand, design, designer, geo, mailer, menus, packs, prospect, publish, social, trends
from .notify import esc, link, telegram
from .settings import CACHE, OUTBOX, SITE, public_repo
from .store import iso, now, parse

ACTIVE = ("ready", "manual", "emailed", "finished", "replied")


# Choosing who to make samples for ------------------------------------------------------------------
def _city_order(cfg, store):
    cities = list(cfg["targets"]["cities"])
    if not cities:
        return []
    start = int(store.flag("city_index") or 0) % len(cities)
    return cities[start:] + cities[:start]


def pick(cfg, store, candidates, limit, manual_limit):
    """Today's businesses: niches taken in turn, those with a usable email first, then a few to DM."""
    niches = cfg["targets"]["niches"]
    fresh = [c for c in candidates if c["id"] not in store.leads and not c["chain"] and c["website"]
             and c["niche"] in niches and not any(store.is_suppressed(e) for e in c["emails"])]
    with_email = {n: [c for c in fresh if c["niche"] == n and c["emails"]] for n in niches}
    social_only = {n: [c for c in fresh if c["niche"] == n and not c["emails"] and c["socials"]] for n in niches}
    out = []
    for pool, cap in ((with_email, limit), (social_only, manual_limit)):
        taken = 0
        while taken < cap and any(pool.values()):
            for n in niches:
                if pool[n] and taken < cap:
                    out.append(pool[n].pop(0))
                    taken += 1
    return out


def best_email(cand, kit):
    """An email that belongs to the business: from the listing (already checked) or shown on its own site."""
    site = kit.get("website") or cand["website"]
    found = list(cand["emails"]) + [e for e in kit.get("emails_found") or []
                                    if prospect.email_belongs(e, site, cand["name"]) and e not in cand["emails"]]
    if not found:
        return ""
    own = prospect.host(site)
    found.sort(key=lambda e: (e.split("@")[1] != own, not e.startswith(("info", "hello", "contact", "hi", "team"))))
    return found[0]


# Making one sample -------------------------------------------------------------------------------
def inside_bigger_site(website, name):
    """True when the listing's website is a page inside someone else's site (a museum's cafe page, a hotel's
    restaurant page): the address has a path and the domain doesn't carry the business's name. Those are
    departments of bigger organizations, not small businesses that hire a studio."""
    url = website if "://" in (website or "") else "https://" + (website or "")
    path = [s for s in urllib.parse.urlparse(url).path.lower().split("/")
            if s and s not in ("index.html", "index.php", "home", "en", "en-us", "#")]
    if not path:
        return False
    domain = re.sub(r"[^a-z0-9]", "", prospect.host(url))
    words = [w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(w) > 2 and w not in brand.NAME_FILLER]
    return bool(words) and not any(w in domain for w in words)


def slim_kit(kit):
    keep = ("name", "website", "domain", "niche", "category", "city", "state", "colors", "fonts", "socials", "booking",
            "ordering", "phone", "profile")
    out = {k: kit.get(k) for k in keep}
    out["logo"] = {k: kit["logo"].get(k) for k in ("url", "kind", "tone")} if kit.get("logo") else None
    out["photos"] = [p["url"] for p in kit.get("photos") or []][:6]
    return out


def make_sample(cfg, store, renderer, cand, radar_for, site_root, posts_n=3, force=False):
    """Read the business's brand, plan and design its posts, write its sample page. Returns the lead record.
    force: make the sample even when there's no way to contact them (you asked for it on Telegram)."""
    lead = {k: cand.get(k) for k in ("id", "name", "niche", "category", "city", "state", "phone", "website",
                                     "socials", "maps_url", "source")}
    if not force and inside_bigger_site(cand["website"], cand["name"]):
        return dict(lead, status="skipped", skip_reason="its page is part of a bigger organization's website")
    kit = brand.read(cand["website"], niche=cand["niche"], name=cand["name"], budget=45)
    if not kit["ok"]:
        return dict(lead, status="skipped", skip_reason=kit.get("problem", "website didn't load"))
    if kit.get("chain_hint"):
        return dict(lead, status="skipped", skip_reason="chain or franchise")
    kit.update(city=cand["city"], state=cand["state"], category=cand["category"], niche=cand["niche"])
    email = best_email(cand, kit)
    if email and (store.is_suppressed(email) or store.find_by_email(email)):
        return dict(lead, status="skipped", skip_reason="opted out before" if store.is_suppressed(email)
                    else "same email as another business")
    socials = dict(kit.get("socials") or {})
    for s in cand.get("socials") or []:
        kind = "instagram" if "instagram.com" in s else "facebook" if "facebook.com" in s else None
        if kind and kind not in socials:
            socials[kind] = s
    if not email and not socials and not force:     # nobody to send it to: don't spend AI or design time
        return dict(lead, status="skipped", skip_reason="no email and no social pages to message")
    radar = radar_for(f"{cand['city']}, {cand['state']}" if cand.get("state") else cand["city"])
    posts = social.plan(cfg, store, kit, radar, n=posts_n, start=dt.date.today(), span=14)
    token = packs.new_token()
    work = CACHE / "samples" / token
    designer.design_posts(cfg, store, renderer, kit, posts, work, fmt="post", seed=random.randint(0, 999))
    board = designer.brand_board(renderer, kit, work / "brand-board.png")
    reel = None
    if posts and store.usage("sample_reels", period="day") < cfg["limits"]["sample_reels_per_day"]:
        reel = designer.reel(renderer, kit, posts[0], work / "reel.mp4", seed=random.randint(0, 999))
        if reel:
            store.add_usage("sample_reels", period="day")
    listing = None                     # the design agent's part: their own menu / price list / schedule, redesigned
    if cfg["limits"].get("sample_designs", True):
        try:
            found = menus.from_website(cfg, store, kit, cand["niche"])
            if found:
                path, issues = menus.render(renderer, kit, found, work / "design.png", "flyer", "paper")
                if not issues:
                    listing = {"kind": menus.LISTING[cand["niche"]], "image": str(path),
                               "pdf": str(path.with_suffix(".pdf"))}
        except Exception as e:                              # a bonus: never lose the sample over it
            print("Design sample skipped:", str(e)[:200])
    upcoming = [{"title": c["title"], "icon": c.get("icon"), "when": c["date"]}
                for c in trends.for_niche(radar, cand["niche"], site_text=kit.get("text") or "")]
    expires = (dt.date.today() + dt.timedelta(days=cfg["limits"]["sample_days"])).strftime("%B %-d, %Y")
    packs.write_sample(cfg, kit, posts, board, upcoming, token, expires, root=site_root, status_url=status_url(cfg, store),
                       reel=reel, listing=listing)
    lead.update(status="ready" if email else ("manual" if socials else "skipped"), email=email, token=token,
                domain=kit.get("domain"), has_logo=bool(kit.get("logo")), post_count=len(posts), has_reel=bool(reel),
                redesigned=listing["kind"] if listing else None,
                moments=[p.get("moment") for p in posts if p.get("moment")], expires=expires, socials=socials,
                kit=slim_kit(kit), posts=[{k: p.get(k) for k in ("day", "time", "moment", "idea", "style", "caption")}
                                         | {"headline": p["content"].get("headline")} for p in posts],
                ai=posts[0].get("source") if posts else None)
    if lead["status"] == "skipped":
        lead["skip_reason"] = "no email and no social pages to message"
    return lead


def status_url(cfg, store):
    host = (store.flag("pages_host") or {}).get("host") or f"{cfg['pages']['cloudflare_project']}.pages.dev"
    base = (cfg["pages"].get("base_url") or f"https://{host}").rstrip("/")
    return base + "/removed.json"


def prospect_today(cfg, store, renderer, site_root):
    """Find today's businesses and make their samples. Returns the new leads (not yet published)."""
    lim = cfg["limits"]
    deadline = time.time() + lim["prospect_minutes"] * 60
    want = max(0, lim["new_prospects_per_day"] - store.usage("prospects", period="day"))
    manual = max(0, lim["dm_handover_per_day"] - store.usage("manual_samples", period="day"))
    radars = {}

    def radar_for(city):
        if city not in radars:
            radars[city] = trends.radar(cfg, store, city=city)
        return radars[city]

    made = []
    for city in _city_order(cfg, store):
        if (want <= 0 and manual <= 0) or time.time() > deadline:
            break
        try:
            cands = prospect.search(store, city, cfg["targets"]["niches"])
        except prospect.ProspectError as e:
            telegram(cfg, f"Couldn't search {esc(city)}: {esc(str(e)[:200])}")
            continue
        while (want > 0 or manual > 0) and time.time() < deadline:
            todo = pick(cfg, store, cands, want, manual)     # skipped ones are now in the store, so this refills
            if not todo:
                store.data["searches"][city] = {"done": True, "at": iso()}
                break
            for cand in todo:
                if time.time() > deadline:
                    break
                try:
                    lead = make_sample(cfg, store, renderer, cand, radar_for, site_root)
                except Exception as e:                  # one bad website never stops the run
                    lead = {k: cand.get(k) for k in ("id", "name", "niche", "city", "state", "website")}
                    lead.update(status="skipped", skip_reason=f"error: {str(e)[:120]}")
                store.add(lead)
                store.add_usage("prospects_checked", period="day")
                if lead["status"] == "ready":
                    want -= 1
                    store.add_usage("prospects", period="day")
                    made.append(lead)
                elif lead["status"] == "manual":
                    manual -= 1
                    store.add_usage("manual_samples", period="day")
                    made.append(lead)
                store.log(lead["id"], "added", f"{lead['status']} {lead.get('skip_reason', '')}".strip())
                store.save()
    cities = cfg["targets"]["cities"]
    if cities:                                          # a different city leads each day, so all get a turn
        store.flag("city_index", (int(store.flag("city_index") or 0) + 1) % len(cities))
    return made


# Emails -------------------------------------------------------------------------------------------
def recheck(store):
    """Samples whose page didn't open right after publishing: check them again (one try each)."""
    for lead in store.leads.values():
        if lead.get("unverified") and lead.get("sample_url", "").startswith("http") \
                and lead.get("status") in ("ready", "manual") and publish.is_live(lead["sample_url"], tries=1):
            lead.pop("unverified", None)


def write_drafts(cfg, store, leads):
    OUTBOX.mkdir(parents=True, exist_ok=True)
    n = 0
    for lead in leads:
        if not lead.get("sample_url") or lead.get("drafted"):
            continue
        email = mailer.first_email(lead, cfg)
        safe = re.sub(r"[^a-z0-9]+", "-", lead["name"].lower()).strip("-")[:50]
        (OUTBOX / f"{dt.date.today()}-{safe}.txt").write_text(f"To: {lead['email']}\nSubject: {email.subject}\n\n{email.text}\n")
        if email.html:
            (OUTBOX / f"{dt.date.today()}-{safe}.html").write_text(email.html)
        lead["drafted"] = iso()
        n += 1
    return n


def _due_followups(cfg, store):
    days = cfg["limits"]["followup_days"]
    due = []
    for lead in store.with_status("emailed"):
        touches = lead.get("touches", 1)
        if touches > len(days):
            lead["status"] = "finished"
            continue
        first = parse(lead.get("first_sent_at"))
        if first and (now() - first).days >= days[touches - 1]:
            due.append(lead)
    return due


def outreach(cfg, store):
    """Send due follow-ups, then first emails, within daily caps and each business's own working hours."""
    lim = cfg["limits"]
    recheck(store)
    first_due = [l for l in store.with_status("ready") if l.get("email") and l.get("sample_url", "").startswith("http")
                 and not l.get("unverified") and not store.is_suppressed(l["email"])]
    first_due.sort(key=lambda l: l.get("created_at", ""))
    if not cfg.live:
        return {"drafted": write_drafts(cfg, store, first_due[: lim["new_emails_per_day"]]), "first": 0, "followups": 0}
    counts = {"drafted": 0, "first": 0, "followups": 0}
    fu_left = lim["followups_per_day"] - store.usage("emails_fu", period="day")
    new_left = lim["new_emails_per_day"] - store.usage("emails_new", period="day")
    hours = lim["send_hours"]
    batch = ([("fu", l) for l in _due_followups(cfg, store) if geo.in_send_window(l.get("state"), hours)][:max(fu_left, 0)]
             + [("first", l) for l in first_due if geo.in_send_window(l.get("state"), hours)][:max(new_left, 0)])
    if not batch:
        return counts
    m = mailer.Mailer(cfg)
    try:
        for kind, lead in batch:
            if kind == "fu":
                email = mailer.followup_email(lead, cfg, lead.get("touches", 1))
                msgid = m.send(lead["email"], email, reply_to_id=lead.get("thread_id"))
                store.update(lead["id"], touches=lead.get("touches", 1) + 1, last_sent_at=iso())
                store.add_usage("emails_fu", period="day")
                counts["followups"] += 1
                store.log(lead["id"], "sent:fu", email.subject)
            else:
                email = mailer.first_email(lead, cfg)
                msgid = m.send(lead["email"], email)
                store.update(lead["id"], status="emailed", touches=1, subject=email.subject, thread_id=msgid,
                             first_sent_at=iso(), last_sent_at=iso())
                store.add_usage("emails_new", period="day")
                counts["first"] += 1
                store.log(lead["id"], "sent:first", email.subject)
            store.record_sent(msgid, lead["id"])
            store.save()
            time.sleep(random.uniform(6, 18))
    finally:
        m.close()
    return counts


# Businesses to message yourself -----------------------------------------------------------------------
def dial(phone):
    d = re.sub(r"\D", "", phone or "")
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return f"+1 {d[:3]} {d[3:6]} {d[6:]}" if len(d) == 10 else (phone or "")


def _shown(url):
    return re.sub(r"^https?://(www\.)?", "", url or "").rstrip("/")


def dm_draft(cfg, lead):
    o, me = cfg["offer"], (cfg["you"].get("name") or "").split()[:1]
    hello = f"Hi! I'm {me[0]}, I do social media and design for local businesses." if me else "Hi!"
    extras = (["a short Reel"] if lead.get("has_reel") else []) + \
        ([f"your {lead['redesigned']} redesigned"] if lead.get("redesigned") else [])
    reel = f" (plus {' and '.join(extras)})" if extras else ""
    return (f"{hello} I made {lead['name']} a week of Instagram posts{reel} in your own brand, free to keep and post: "
            f"{lead['sample_url']}\n\nPosts every week are ${o['social_monthly']} a month, design on its own (menus, "
            f"flyers, promos) is ${o['design_monthly']}, or both for ${o['bundle_monthly']}"
            + (f", with {o['trial']}" if o.get("trial") else "") + ". No pressure either way!")


def handover(cfg, store, leads, header=False, pause=1.1):
    """One Telegram message per business without an email: where to message them, and a draft to copy."""
    leads = [l for l in leads if l.get("sample_url", "").startswith("http")]
    if not leads:
        return 0
    if header:
        telegram(cfg, f"<b>{len(leads)} business{'' if len(leads) == 1 else 'es'} to message yourself</b> "
                      "(no public email). One message each, with a message you can copy:")
    sent = 0
    for i, lead in enumerate(leads, 1):
        s = lead.get("socials") or {}
        ways = [f"{k.title()}: {link(v, _shown(v))}" for k, v in s.items() if k in ("instagram", "facebook", "tiktok")]
        if lead.get("phone"):
            ways.append(f"Phone: {esc(dial(lead['phone']))}")
        text = "\n".join([f"<b>{i}/{len(leads)} · {esc(lead['name'])}</b>",
                          esc(f"{lead.get('niche', '').title()} · {lead.get('city')}, {lead.get('state')}"), ""]
                         + ways + [f"Their sample: {link(lead['sample_url'], 'open it')}", "",
                                   "Send it as an Instagram or Facebook message. Tap the message to copy it:",
                                   f"<pre>{esc(dm_draft(cfg, lead))}</pre>"])
        if telegram(cfg, text):
            lead["handed_over"] = iso()
            sent += 1
        if i < len(leads):
            time.sleep(pause)
    return sent


def pending_handover(store, limit=8):
    recheck(store)
    leads = [l for l in store.with_status("manual") if not l.get("handed_over") and not l.get("unverified")
             and l.get("sample_url", "").startswith("http")]
    return sorted(leads, key=lambda l: l.get("created_at", ""), reverse=True)[:limit]


# Housekeeping and the daily report ---------------------------------------------------------------------
def cleanup(cfg, store):
    """Samples older than limits.sample_days expire: their deployments are deleted."""
    keep = cfg["limits"]["sample_days"]
    n = 0
    for lead in store.leads.values():
        created = parse(lead.get("created_at"))
        if lead.get("status") in ("ready", "manual", "emailed", "finished") and created and (now() - created).days >= keep:
            lead["status"] = "expired"
            lead.pop("kit", None)
            n += 1
    publish.cleanup(cfg, store, keep + 1)
    shutil.rmtree(CACHE / "samples", ignore_errors=True)
    return n


def digest(cfg, store, contacts=0, clients_line=""):
    since = store.flag("digest_at") or "1970-01-01T00:00:00+00:00"
    events = [e for e in store.data["events"] if e["at"] > since]
    count = lambda kind: sum(1 for e in events if e["kind"] == kind)
    made = sum(1 for e in events if e["kind"] == "added" and e["detail"].startswith(("ready", "manual")))
    lines = [f"<b>Studio agent · {dt.date.today():%b %d}</b>",
             f"Businesses checked: {store.usage('prospects_checked', period='day')} · Samples made: {made}",
             f"Emails sent: {count('sent:first')} · Follow-ups: {count('sent:fu')}",
             f"Replies: {count('reply:reply') + count('reply:later')} · Opt-outs: {count('reply:optout') + count('reply:remove')} · "
             f"Bounces: {count('bounced')}",
             f"Free AI used today: {store.usage('ai_calls', period='day')} requests · "
             f"{store.usage('ai_images', period='day')} images"]
    if clients_line:
        lines.append(clients_line)
    if not cfg.live:
        drafts = len(list(OUTBOX.glob("*.txt"))) if OUTBOX.exists() else 0
        where = "One is below." if public_repo() else "They're all in data/outbox, and one is below."
        lines.append(f"\nMode is <b>draft</b>, so nothing was sent. {drafts} draft email{'' if drafts == 1 else 's'} "
                     f"written. {where}" if drafts else "\nMode is <b>draft</b>, so nothing was sent.")
    sample = next((l for l in reversed(list(store.leads.values())) if l.get("sample_url", "").startswith("http")), None)
    if sample:
        lines.append(f"\nNewest sample: {link(sample['sample_url'], sample['name'])}")
    if contacts:
        lines.append(f"\n<b>{contacts} business{'' if contacts == 1 else 'es'} to message yourself</b> (no public "
                     "email). Each one comes next as its own message, with a message you can copy.")
    telegram(cfg, "\n".join(lines))
    store.flag("digest_at", iso())
    if not cfg.live:                                   # show one draft, so you can judge it from your phone
        draft = next((l for l in sorted(store.with_status("ready"), key=lambda l: l.get("drafted") or "", reverse=True)
                      if l.get("drafted") and l.get("sample_url", "").startswith("http")), None)
        if draft:
            email = mailer.first_email(draft, cfg)
            telegram(cfg, f"<b>A draft email, as {esc(draft['name'])} would get it</b>\n"
                          f"Subject: {esc(email.subject)}\n\n<pre>{esc(email.text[:3000])}</pre>")
