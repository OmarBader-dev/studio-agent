"""Command line: python -m agent <command>

  daily          find businesses, make their free samples, publish, email (or draft), make clients' weekly
                 posts, post or remind, and report to Telegram
  inbox          your Telegram commands, then Gmail replies and client messages; posts that are due
  contacts       send you the businesses with no email, one Telegram message each, with a DM to copy
  sample URL     make a free sample for one website (same as sending the link to the Telegram bot)
  kit URL        save the brand kit picture for one website
  design CLIENT "REQUEST"   three versions of a design for a client
  week CLIENT    make a client's posts for next week now
  trends [CITY]  print what's worth posting about this week
  status         counts of businesses by status
  test-email     send yourself the first email exactly as a business would get it
  telegram-id    print your Telegram chat ID (message your bot first)
"""
import collections
import re
import shutil
import sys

from . import clients, commands, design, hq, inbox, mailer, meta, notify, packs, pipeline, publish, settings, trends
from .notify import esc, telegram
from .settings import SITE
from .store import Store, now


def _fresh(folder):
    shutil.rmtree(folder, ignore_errors=True)
    packs.site_root(folder)
    return folder


def publish_site(cfg, store, root, leads, weeks):
    """One deployment for everything this run made. Returns its address, or None."""
    if not (leads or weeks):
        return None
    removed = publish.write_removed(store, root)
    if not publish.configured(cfg):
        print("Cloudflare isn't set up yet, so pages were built in", root, "but not published.")
        return None
    dep = publish.deploy(cfg, root)
    if not dep:
        telegram(cfg, "Publishing to Cloudflare failed, so nothing was sent this run. Open the latest run in GitHub "
                      "Actions to see why.")
        for lead in leads:
            store.leads.pop(lead["id"], None)            # they'll be picked again another day
        return None
    publish.remember(store, dict(dep, removed=removed), "daily")
    latest = publish.latest_deployment(cfg)
    if latest and latest.get("url"):
        host = re.sub(r"^https?://[0-9a-f]+\.", "", latest["url"]).strip("/")
        store.flag("pages_host", {"project": cfg["pages"]["cloudflare_project"], "host": host})
    for lead in leads:
        lead["sample_url"] = f"{dep['url']}/s/{lead['token']}/"
    check = leads[0]["sample_url"] if leads else None
    if check and not publish.is_live(check):
        for lead in leads:                               # emailed only once their page is seen to open
            lead["unverified"] = True
        telegram(cfg, f"Pages were published but {esc(check)} doesn't open yet, so those businesses wait until "
                      "it does (checked again on every run).")
    return dep["url"]


def cmd_daily(cfg, store):
    today = now().strftime("%Y-%m-%d")
    pipeline.cleanup(cfg, store)
    clients.prune(cfg)
    root = _fresh(SITE / "daily")
    leads, weeks = [], []
    with design.Renderer() as r:
        if store.flag("prospect_date") != today:
            leads = pipeline.prospect_today(cfg, store, r, root)
            store.flag("prospect_date", today)
            store.save()
        for client in clients.due(cfg, store):
            try:
                start = clients.week_start()
                weeks.append((client, start.isoformat(), clients.make_week(cfg, store, r, client, root, start)))
            except Exception as e:
                telegram(cfg, f"Couldn't make {esc(client['name'])}'s posts: {esc(str(e)[:200])}")
        store.save()
        posters = clients.make_posters(cfg, store, r)       # the design agent's own posters for what's coming up
        store.save()
    base = publish_site(cfg, store, root, leads, weeks)
    for client, week, record in weeks:
        if base:
            clients.deliver(cfg, store, client, week, record, base)
    print("Outreach:", pipeline.outreach(cfg, store))     # follow-ups go out even on days with no new samples
    clients.settle(cfg, store)
    meta.autoconnect(cfg, store, cfg["clients"])        # clients who added you to their Facebook Page
    posted = meta.publish_due(cfg, store, clients.todays_posts(cfg, store))
    posted += meta.publish_extras(cfg, store, cfg["clients"])
    reminded = clients.remind(cfg, store)
    clients.billing_reminders(cfg, store)
    clients.monthly_reports(cfg, store)                 # first run of a month: last month's reports
    publish.publish_removals(cfg, store, SITE / "removals")
    if store.flag("digest_date") != today:
        todo = pipeline.pending_handover(store, cfg["limits"]["dm_handover_per_day"])
        line = ""
        if cfg["clients"]:
            plans = collections.Counter(settings.plan_of(c) for c in cfg["clients"])
            line = (f"Clients: {len(cfg['clients'])} (Social {plans['social']} · Design {plans['design']} · "
                    f"Both {plans['bundle']}) · Weekly packs made: {len(weeks)} · Posters: {len(posters)} · "
                    f"Posted: {posted} · Reminders: {reminded}")
            unset = [c["name"] for c in cfg["clients"] if str(c.get("plan") or "").lower() not in settings.PLANS]
            if unset:
                line += (f"\n⚠️ No plan set for {esc(', '.join(unset))} in clients.yaml (social, design or bundle). "
                         "Until then they get Social only.")
        pipeline.digest(cfg, store, contacts=len(todo), clients_line=line)
        store.flag("digest_date", today)
        store.save()
        pipeline.handover(cfg, store, todo)


def cmd_inbox(cfg, store):
    session = commands.Session(cfg, store)
    try:
        for text in notify.messages(cfg, store):
            session.run(text)
            store.save()
        if cfg.secret("GMAIL_APP_PASSWORD") and cfg["you"].get("email"):
            counts = inbox.check(cfg, store, on_design_request=session.design_from_email,
                                 hooks={"revision": session.revise_design, "week": session.redo_week})
            print("Inbox:", counts)
        else:
            print("Gmail isn't set up yet, so replies weren't checked.")
        hq.sync(cfg, store, on_onboard=session.onboard_from_hq)   # clients you marked as bought in HQ start now
        session.finish()
    finally:
        session.close()
    publish.publish_removals(cfg, store, SITE / "removals")   # someone asked for their page to come down
    clients.settle(cfg, store)
    meta.autoconnect(cfg, store, cfg["clients"])
    meta.publish_due(cfg, store, clients.todays_posts(cfg, store))
    meta.publish_extras(cfg, store, cfg["clients"])
    clients.remind(cfg, store)
    clients.billing_reminders(cfg, store)


def cmd_contacts(cfg, store):
    todo = pipeline.pending_handover(store, cfg["limits"]["dm_handover_per_day"])
    if not todo:
        telegram(cfg, "No new businesses to message yourself right now. New ones come with the daily run.")
        print("Nothing to send.")
        return
    print("Contact messages sent:", pipeline.handover(cfg, store, todo, header=True))


def cmd_sample(cfg, store, url="", *rest):
    if not url:
        raise SystemExit("Give a website, like: python -m agent sample https://example.com cafe")
    session = commands.Session(cfg, store)
    try:
        session.sample(" ".join([url, *rest]))
        session.finish()
        for lead in session.samples:
            where = lead.get("sample_url") or (session.root / "s" / lead["token"] / "index.html")
            print(lead["name"], "->", "(the link is on Telegram)" if settings.public_repo() else where)
    finally:
        session.close()


def cmd_kit(cfg, store, url=""):
    if not url:
        raise SystemExit("Give a website, like: python -m agent kit https://example.com")
    session = commands.Session(cfg, store)
    try:
        session.kit(url)
    finally:
        session.close()


def cmd_design(cfg, store, who="", *request):
    client = clients.find(cfg, who) or ({"name": who, "website": who, "niche": "restaurant"} if "." in who else None)
    if not client or not request:
        raise SystemExit('Like: python -m agent design florin "flyer for open mic night, Friday 7pm"')
    with design.Renderer() as r:
        job = clients.design_job(cfg, store, r, client, " ".join(request))
    print("Design job:", job, store.data["jobs"][job]["paths"])


def cmd_week(cfg, store, who=""):
    session = commands.Session(cfg, store)
    try:
        session.week(who)
        session.finish()
    finally:
        session.close()


def cmd_trends(cfg, store, *city):
    c = " ".join(city) or cfg["targets"]["cities"][0]
    r = trends.radar(cfg, store, city=c)
    print(f"Worth posting about in {c}:")
    for item in r["calendar"][:12]:
        print(f"  {item['date']}  {item['title']}  ({', '.join(item['niches'][:4])})")
    print("Trending today (safe topics only):")
    for item in r["live"][:12]:
        print(f"  [{item['source']}] {item['title']}")
    for w in r["weather"]:
        print(f"  Weather: {w['title']} - {w['angle']}")


def cmd_status(cfg, store):
    counts = collections.Counter(l.get("status") for l in store.leads.values())
    for status, n in counts.most_common():
        print(f"{status:>10}  {n}")
    print(f"Clients: {len(cfg['clients'])} · Design jobs: {len(store.data['jobs'])}")


def cmd_test_email(cfg, store):
    ready = [l for l in store.leads.values() if l.get("sample_url", "").startswith("http")]
    lead = ready[-1] if ready else {"name": "Example Cafe", "domain": "example-cafe.com", "has_logo": True,
                                    "sample_url": "https://example.pages.dev/s/sample/", "moments": ["Halloween"],
                                    "post_count": 3}
    email = mailer.first_email(lead, cfg)
    m = mailer.Mailer(cfg)
    m.send(cfg["you"]["email"], email._replace(subject=f"[TEST {now():%H:%M} UTC] " + email.subject))
    m.close()
    telegram(cfg, f"Test from your studio agent: Telegram works. The email for {esc(lead['name'])} is on its way.")
    print("Sent a test email to your own inbox.")


def cmd_telegram_id(cfg, store):
    found = notify.chat_ids(cfg)
    if not found:
        print("No messages yet. Open your bot in Telegram, send it any message, then run this again.")
    for chat_id, name in found.items():
        print(f"TELEGRAM_CHAT_ID={chat_id}   ({name})")


COMMANDS = {"daily": cmd_daily, "inbox": cmd_inbox, "contacts": cmd_contacts, "sample": cmd_sample, "kit": cmd_kit,
            "design": cmd_design, "week": cmd_week, "trends": cmd_trends, "status": cmd_status,
            "test-email": cmd_test_email, "telegram-id": cmd_telegram_id}


def main(argv):
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        return 1
    cfg = settings.load()
    store = Store()
    settings.with_saved_clients(cfg, store.data.get("clients_db"))   # clients added with /client
    clients.apply_overrides(cfg, store)                              # /pause, /resume, /plan
    try:
        COMMANDS[argv[0]](cfg, store, *[a for a in argv[1:] if a])
    finally:
        store.save()
        if argv[0] in ("daily", "inbox", "contacts", "sample", "week", "design"):
            hq.sync(cfg, store)                     # your dashboard sees what this run changed
            store.save()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
