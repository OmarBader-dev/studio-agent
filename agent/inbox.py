"""Reads Gmail (IMAP): replies from businesses you emailed, and messages from your clients.

Businesses: replies stop the follow-ups and ping you on Telegram; "no thanks" and "unsubscribe" opt them
out for good; "remove" also takes their sample page down; bounces mark the address as bad.
Clients: "approved" approves the week's posts; anything that asks for a design (a flyer, a menu, a promo
post...) becomes a design job: three versions are made and sent to you on Telegram to check; photos they
attach are saved to their folder for future designs; anything else is forwarded to you on Telegram.
"""
import datetime as dt
import email
import imaplib
import re
from email import policy
from email.utils import parseaddr
from urllib.parse import quote

from .notify import esc, telegram
from .store import iso

IMAP_HOST = "imap.gmail.com"
OPT_OUT = re.compile(
    r"\b(unsubscribe|remove me|take me off|stop (?:emailing|contacting|sending)|do not (?:contact|email)|"
    r"don'?t (?:contact|email)|not interested|no thanks|no thank you|no thx|leave me alone|wrong (?:person|email))\b",
    re.I)
REMOVE_PAGE = re.compile(r"\b(remove|delete|take down)\b.{0,30}\b(page|posts?|sample|it)\b|^\W*remove\W*$", re.I | re.S)
LATER = re.compile(r"^\W*(later|not now|maybe later|check back)\b", re.I)
INTEREST = re.compile(
    r"\b(yes|yeah|interested|how much|pricing|price|cost|call me|sounds good|let'?s do|go ahead|i'?m in|invoice|"
    r"more info|when can|like (?:it|them)|love (?:it|them)|looks? (?:great|good|nice|amazing)|sign (?:me|us) up|"
    r"send (?:me )?details|trial)\b", re.I)
APPROVE = re.compile(r"^\W*(approved?|looks? (?:good|great)|all good|go ahead|perfect|yes|ok(?:ay)?|post (?:them|it))\b", re.I)
DESIGN_ASK = re.compile(r"\b(flyer|poster|menu|banner|sign|story|stories|post (?:for|about)|promo|design|graphic|"
                        r"price list|schedule|coupon|gift card|invite|invitation|announcement)\b", re.I)
QUOTE_START = re.compile(r"^(On .{5,200}wrote:|-{2,} ?Original Message ?-{2,}|From: .+|Sent from my \w+)", re.I | re.M)


def _text_of(msg):
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    text = part.get_content()
    if part.get_content_type() == "text/html":
        text = re.sub(r"<(br|/p|/div)[^>]*>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
    return text


def new_text(full):
    """Only what they wrote, without the quoted email below it."""
    m = QUOTE_START.search(full)
    text = full[:m.start()] if m else full
    lines = [l for l in text.splitlines() if not l.lstrip().startswith(">")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def is_auto(msg):
    subject = (msg.get("Subject") or "").lower()
    if (msg.get("Auto-Submitted") or "no").lower() != "no":
        return True
    if msg.get("X-Autoreply") or msg.get("X-Autorespond") or (msg.get("Precedence") or "").lower() in ("auto_reply", "bulk", "junk"):
        return True
    return subject.startswith(("automatic reply", "auto-reply", "autoreply", "out of office", "out of the office"))


def is_bounce(msg):
    sender = (msg.get("From") or "").lower()
    return "mailer-daemon" in sender or "postmaster" in sender or msg.get_content_type() == "multipart/report"


def classify(text, msg=None):
    """'auto', 'remove', 'optout', 'later' or 'reply', plus whether they sound interested."""
    if msg is not None and is_auto(msg):
        return "auto", False
    if msg is not None and re.search(r"\bunsubscribe\b", msg.get("Subject") or "", re.I):
        return "optout", False
    t = text.strip()
    head = t[:400]
    if REMOVE_PAGE.search(head) and len(t.split()) <= 25:
        return "remove", False
    if OPT_OUT.search(head) or (len(t.split()) <= 3 and re.search(r"\bstop\b", t, re.I)):
        return "optout", False
    if LATER.search(t) and len(t.split()) <= 12:
        return "later", False
    return "reply", bool(INTEREST.search(t))


def gmail_link(msgid):
    return "https://mail.google.com/mail/u/0/#search/" + quote("rfc822msgid:" + msgid.strip("<>"))


def ping_reply(cfg, lead, text, msgid, kind, interested, answered=None):
    o = cfg["offer"]
    tag = "Likely interested" if interested else ("Asked you to check back later" if kind == "later" else "New reply")
    excerpt = text if len(text) < 900 else text[:900] + "…"
    lines = [f"<b>{esc(tag)}: {esc(lead['name'])}</b> ({esc(lead.get('city'))})", "",
             f"<i>{esc(excerpt) or '(no text)'}</i>", "",
             f"Their sample: {esc(lead.get('sample_url'))}",
             f'<a href="{esc(gmail_link(msgid))}">Open the thread in Gmail</a>', ""]
    if answered and answered[0] == "plans":
        lines.append("🤖 " + ("Answered them automatically with the plans and prices; their choice comes next."
                              if answered[2] else "Draft mode: the plans reply above wasn't sent."))
    elif answered and answered[0] == "plan":
        plan = answered[1]
        price = {"social": o["social_monthly"], "design": o["design_monthly"], "bundle": o["bundle_monthly"]}[plan]
        lines += [f"💰 <b>They chose {esc(plan.title())} (${price}/month)</b>"
                  + (" and got a thank-you with the next steps." if answered[2] else " (draft mode: reply not sent)."),
                  f"Start them now: <code>/client {esc(lead['name'])} {plan}</code> (first week free), and send the "
                  f"Payoneer request for ${price} to {esc(lead.get('email') or 'them')}."]
    else:
        lines.append(f"If they're in: start them with <code>/client {esc(lead['name'])} social</code> (or design, or "
                     f"bundle), then send the Payoneer request (Social ${o['social_monthly']}, Design "
                     f"${o['design_monthly']}, both ${o['bundle_monthly']}).")
    telegram(cfg, "\n".join(lines))


PLAN_BOTH = re.compile(r"\b(both|bundle|everything|all of it|the combo|full package|129)\b", re.I)
PLAN_SOCIAL = re.compile(r"\b(social|social media|the posts|posts|instagram|99)\b", re.I)
PLAN_DESIGN = re.compile(r"\b(design|designs|graphic|flyers?|menus?|49)\b", re.I)


def chosen_plan(text):
    """The plan a business picked in its reply ("Social please", "let's do both"), or None."""
    t = (text or "")[:300]
    if len(t.split()) > 40 or re.search(r"\b(not|no|don'?t|maybe|later|which|what|how|\?)", t[:60], re.I):
        return None
    social, design = PLAN_SOCIAL.search(t), PLAN_DESIGN.search(t)
    if PLAN_BOTH.search(t) or (social and design):
        return "bundle"
    return "social" if social else "design" if design else None


def auto_answer(cfg, store, lead, sender, text, msgid, kind, interested):
    """On autopilot: answer an interested business with the plans and prices, and its plan choice with the next
    steps. Returns (what, plan, sent) or None when it's left to you."""
    if not cfg["autopilot"].get("replies") or kind != "reply" or not sender:
        return None
    from . import mailer
    plan = chosen_plan(text) if lead.get("offered_at") and not lead.get("plan_chosen") else None
    if plan:
        price = {"social": cfg["offer"]["social_monthly"], "design": cfg["offer"]["design_monthly"],
                 "bundle": cfg["offer"]["bundle_monthly"]}[plan]
        email, what = mailer.plan_chosen_reply(lead, cfg, plan, price), "plan"
        store.update(lead["id"], plan_chosen=plan, plan_chosen_at=iso())
    elif interested and not lead.get("offered_at"):
        email, what = mailer.plans_reply(lead, cfg, lead.get("sample_url")), "plans"
        store.update(lead["id"], offered_at=iso())
    else:
        return None
    sent = False
    if cfg.live:
        m = mailer.Mailer(cfg)
        try:
            m.send(sender, email, reply_to_id=msgid, sales=True)
            sent = True
        finally:
            m.close()
    else:
        telegram(cfg, f"<i>Draft mode, this reply to {esc(lead['name'])} wasn't sent:</i>\n<pre>{esc(email.text[:1800])}</pre>")
    store.log(lead["id"], "auto:" + what, plan or "")
    return what, plan, sent


def check(cfg, store, days=4, on_design_request=None, hooks=None):
    """Process new mail. Returns counts of what happened."""
    cfg.require("GMAIL_APP_PASSWORD")
    counts = {"replies": 0, "optouts": 0, "bounces": 0, "auto": 0, "client": 0, "removed": 0}
    imap = imaplib.IMAP4_SSL(IMAP_HOST, 993)
    imap.login(cfg["you"]["email"], cfg.secret("GMAIL_APP_PASSWORD"))
    imap.select("INBOX", readonly=True)
    since = (dt.date.today() - dt.timedelta(days=days)).strftime("%d-%b-%Y")
    _, data = imap.search(None, f'(SINCE "{since}")')
    for num in data[0].split()[-400:]:
        _, parts = imap.fetch(num, "(BODY.PEEK[])")
        raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
        if not raw:
            continue
        msg = email.message_from_bytes(raw, policy=policy.default)
        msgid = (msg.get("Message-ID") or "").strip()
        if not msgid or store.is_seen(msgid):
            continue
        store.mark_seen(msgid)
        handle(cfg, store, msg, msgid, counts, on_design_request, hooks)
    imap.logout()
    return counts


def client_for(cfg, sender):
    sender = (sender or "").lower()
    for c in cfg.get("clients") or []:
        emails = [x.strip().lower() for x in str(c.get("email") or "").split(",") if x.strip()]
        if sender in emails:
            return c
    return None


def handle(cfg, store, msg, msgid, counts, on_design_request=None, hooks=None):
    full = _text_of(msg)
    if is_bounce(msg):
        for addr in set(re.findall(r"[\w.%+-]+@[\w.-]+\.[a-z]{2,}", full, re.I)):
            lead = store.find_by_email(addr)
            if lead and lead.get("status") in ("emailed", "ready"):
                store.update(lead["id"], status="bounced")
                store.suppress(addr, "bounced")
                store.log(lead["id"], "bounced", addr)
                counts["bounces"] += 1
        return
    sender = parseaddr(msg.get("From") or "")[1].lower()
    text = new_text(full)
    client = client_for(cfg, sender)
    if client:
        counts["client"] += 1
        handle_client(cfg, store, client, msg, msgid, text, on_design_request, hooks)
        return
    refs = re.findall(r"<[^>]+>", (msg.get("In-Reply-To") or "") + " " + (msg.get("References") or ""))
    lead = store.lead_for_msgids(refs) or store.find_by_email(sender)
    if not lead:
        return
    kind, interested = classify(text, msg)
    store.log(lead["id"], "reply:" + kind, text[:300])
    if kind == "auto":
        counts["auto"] += 1
        return
    if kind in ("optout", "remove"):
        store.update(lead["id"], status="opted_out", replied_at=iso(), removed=kind == "remove" or None)
        store.suppress(sender or lead.get("email"), "asked to stop")
        counts["optouts"] += 1
        if kind == "remove":
            store.data.setdefault("removed", []).append(lead.get("token"))
            counts["removed"] += 1
        return
    if lead.get("status") != "client":
        store.update(lead["id"], status="replied", replied_at=iso(), reply_text=text[:2000])
    counts["replies"] += 1
    answered = auto_answer(cfg, store, lead, sender, text, msgid, kind, interested)
    ping_reply(cfg, lead, text, msgid, kind, interested, answered)


def save_photos(client_key, msg, folder):
    """Photos a client attached: saved (resized) to their folder for future designs. Returns the paths."""
    from PIL import Image
    import io
    saved = []
    for part in msg.iter_attachments():
        if not (part.get_content_type() or "").startswith("image/"):
            continue
        try:
            folder.mkdir(parents=True, exist_ok=True)
            im = Image.open(io.BytesIO(part.get_content()))
            im = im.convert("RGB")
            im.thumbnail((2000, 2000))
            name = re.sub(r"[^a-z0-9]+", "-", (part.get_filename() or "photo").lower()).strip("-")[:40] or "photo"
            path = folder / f"{dt.date.today():%Y%m%d}-{name}.jpg"
            im.save(path, "JPEG", quality=86)
            saved.append(path)
        except Exception:
            continue
    return saved


def handle_client(cfg, store, client, msg, msgid, text, on_design_request=None, hooks=None):
    """A client's email: a reply to a design email (pick a version, or changes), to their weekly pack ("approved", or
    changes), a new design request, or anything else (forwarded to you)."""
    from . import clients
    from .settings import client_inbox_folder, plan_has, plan_of
    hooks = hooks or {}
    key = clients.key_of(client)
    book = store.client(key)
    photos = save_photos(key, msg, client_inbox_folder(key) / "photos")
    if photos:
        telegram(cfg, f"📸 {esc(client['name'])} sent {len(photos)} photo(s). They're saved and will be used in "
                      "their next designs.")
    refs = re.findall(r"<[^>]+>", (msg.get("In-Reply-To") or "") + " " + (msg.get("References") or ""))
    job_id = clients.job_for_reply(store, refs)
    if job_id:                                           # about a design we sent them
        result = clients.reply_to_job(cfg, store, job_id, text, on_revision=hooks.get("revision"))
        if result:
            telegram(cfg, f"<b>{esc(client['name'])}</b> on {esc(store.data['jobs'][job_id]['request'][:80])}:\n"
                          f"<i>{esc(text[:400])}</i>\n→ {esc(result)}")
        return
    week = clients.week_for_reply(store, client, refs)
    pending = [w for w, info in book["weeks"].items() if info.get("status") == "sent"]
    if (week or pending) and APPROVE.search(text) and len(text.split()) <= 25:
        week = week if week in pending else sorted(pending)[-1] if pending else week
        book["weeks"][week].update(status="approved", approved_at=iso())
        telegram(cfg, f"✅ {esc(client['name'])} approved the posts for {esc(week)}.")
        return
    if week and hooks.get("week") and not clients.THANKS.match(text.strip()[:120] or "thanks"):
        result = hooks["week"](client, week, text)       # changes to their week: redone and sent again
        telegram(cfg, f"<b>{esc(client['name'])}</b> asked for changes to {esc(week)}:\n<i>{esc(text[:400])}</i>\n→ {esc(result)}")
        return
    if DESIGN_ASK.search(text) and on_design_request:
        if not plan_has(client, "design"):             # design is its own plan: offer it, don't just do it
            o = cfg["offer"]
            telegram(cfg, "\n".join([
                f"<b>{esc(client['name'])} asked for a design</b>, but they're on the {esc(plan_of(client).title())} "
                "plan, which doesn't include design.", "", f"<i>{esc(text[:600])}</i>", "",
                f"Offer Design (${o['design_monthly']}/month) or Social + Design (${o['bundle_monthly']}/month). "
                f"To make this one anyway: <code>/design {esc(key)}: …</code>",
                f'<a href="{esc(gmail_link(msgid))}">Open in Gmail</a>']))
            return
        job = on_design_request(client, text, msgid)
        if job:
            return
    telegram(cfg, "\n".join([f"<b>Message from {esc(client['name'])}</b>", "", f"<i>{esc(text[:900])}</i>", "",
                             f'<a href="{esc(gmail_link(msgid))}">Open in Gmail</a>']))
