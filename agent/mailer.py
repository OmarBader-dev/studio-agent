"""Emails: the first note with a business's free sample, two short follow-ups, and client emails.
Sent through Gmail (SMTP with an app password). Every sales email says it's one, has a way to opt out
and your mailing address (US CAN-SPAM rules)."""
import collections
import datetime as dt
import html
import mimetypes
import pathlib
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
TEXT, MUTED, LINE = "#1f2328", "#6b7280", "#e3e6ea"

Email = collections.namedtuple("Email", "subject text html attachments", defaults=(None, ()))


def _e(text):
    return html.escape(str(text or ""), quote=True)


def _p(inner, margin="0 0 16px"):
    return f'<p style="margin:{margin};font-family:{FONT};font-size:15px;line-height:1.6;color:{TEXT};">{inner}</p>'


def signature(cfg):
    you = cfg["you"]
    return [x for x in (you.get("name"), you.get("business"), you.get("website"), you.get("instagram")) if x]


def _page(subject, body, cfg, footer):
    sig = "<br>".join(_e(x) for x in signature(cfg))
    foot = "<br>".join(_e(x) for x in footer)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>{_e(subject)}</title></head>
<body style="margin:0;padding:0;background:#ffffff;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td style="padding:20px 16px 28px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;"><tr><td>
{body}
{_p(sig, "24px 0 0")}
<p style="margin:28px 0 0;padding-top:14px;border-top:1px solid {LINE};font-family:{FONT};font-size:12px;line-height:1.55;color:{MUTED};">{foot}</p>
</td></tr></table></td></tr></table></body></html>"""


def _thumbs(lead):
    """Three small pictures of their posts, linking to the sample page."""
    url = lead["sample_url"]
    cells = "".join(
        f'<td width="33%" style="padding:0 4px;"><a href="{_e(url)}" target="_blank" style="text-decoration:none;">'
        f'<img src="{_e(url)}post-{i}.jpg" width="176" alt="Post {i} for {_e(lead["name"])}" '
        f'style="display:block;width:100%;max-width:176px;height:auto;border-radius:10px;border:1px solid {LINE};"></a></td>'
        for i in range(1, min(3, lead.get("post_count", 3)) + 1))
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="margin:4px 0 18px;"><tr>{cells}</tr></table>')


def sales_footer(cfg, lead):
    return [f"You're getting this because {lead['name']} is listed publicly as a local business. This is a sales "
            "email, and I'll send at most two short follow-ups. Reply \"no thanks\" and I won't contact you again.",
            cfg["you"]["mailing_address"]]


def first_email(lead, cfg):
    o, name, url = cfg["offer"], lead["name"], lead["sample_url"]
    moments = [m for m in lead.get("moments") or [] if m][:2]
    tied = f", tied to what's coming up ({' and '.join(moments)})" if moments else ""
    subject = f"I made {name} a week of posts"
    opener = (f"I came across {name} and made you a week of Instagram posts in your own brand: your "
              f"{'logo, ' if lead.get('has_logo') else ''}colors and fonts from {lead.get('domain') or 'your website'}{tied}."
              + (" There's a short Reel version too." if lead.get("has_reel") else "")
              + (f" I also redesigned your {lead['redesigned']} from your website, ready to print."
                 if lead.get("redesigned") else ""))
    keep = "Here they are, with captions you can copy. They're yours to keep and post, free:"
    offer = (f"If you'd like this every week, I do social media for local businesses: {o['posts_per_week']} designed posts "
             f"a week with captions, posted for you, for ${o['social_monthly']} a month"
             + (f" ({o['trial']})." if o.get("trial") else ".")
             + f" Design is its own plan: ${o['design_monthly']} a month for flyers, menus and promos, or "
               f"${o['bundle_monthly']} for both.")
    closing = "Just reply if you want them tweaked, or if you have any questions."
    footer = sales_footer(cfg, lead)
    text = "\n\n".join(["Hi,", opener, keep, url, offer, closing, "\n".join(signature(cfg)), "--\n" + "\n".join(footer)])
    if str(cfg.get("email_style", "card")).lower() == "plain":
        return Email(subject, text, None)
    body = "\n".join([_p("Hi,"), _p(_e(opener)), _p(_e(keep), "0 0 10px"), _thumbs(lead),
                      _p(f'<a href="{_e(url)}" target="_blank" style="color:{TEXT};font-weight:600;">See all the posts '
                         f'and captions</a>'), _p(_e(offer)), _p(_e(closing), "0")])
    return Email(subject, text, _page(subject, body, cfg, footer))


def followup_email(lead, cfg, n):
    name, url = lead["name"], lead["sample_url"]
    if n == 1:
        paras = ["Hi again,", f"Just checking you saw the posts I made for {name}:", url,
                 "Happy to change anything: a photo, the words, or make a few more for next week."]
    else:
        paras = ["Hi,", f"Last note from me. The page with {name}'s posts comes down on {lead.get('expires', 'soon')}, "
                 "so here's the link once more:", url,
                 'If the timing is just wrong, reply "later" and I\'ll check back in a few months.']
    subject = "Re: " + lead["subject"]
    footer = ["This is a sales email. Reply \"no thanks\" and I won't contact you again.", cfg["you"]["mailing_address"]]
    text = "\n\n".join(paras + ["\n".join(signature(cfg)), "--\n" + "\n".join(footer)])
    if str(cfg.get("email_style", "card")).lower() == "plain":
        return Email(subject, text, None)
    body = "\n".join(_p(f'<a href="{_e(p)}" style="color:{TEXT};">{_e(p)}</a>' if p == url else _e(p),
                        "0 0 16px" if i < len(paras) - 1 else "0") for i, p in enumerate(paras))
    return Email(subject, text, _page(subject, body, cfg, footer))


def week_email(client, cfg, url, posts, note, extra_files=()):
    """A client's posts for the week, with the images (and the Reel) attached so they can post them anywhere."""
    subject = f"{client['name']}: your posts for the week"
    lines = [f"- {p.get('day')} {p.get('time')}: {p['content'].get('headline')}" for p in posts]
    text = "\n\n".join([f"Hi {client.get('contact_name') or ''}".strip() + ",", note, url, "\n".join(lines),
                        'Reply "approved" and they go out on schedule, or tell me what to change.',
                        "\n".join(signature(cfg))])
    attachments = [p["image"] for p in posts if p.get("image") and pathlib.Path(p["image"]).exists()]
    attachments += [f for f in extra_files or () if f and pathlib.Path(f).exists()
                    and pathlib.Path(f).stat().st_size < 15_000_000]           # Gmail takes 25 MB in all
    body = "\n".join([_p(_e(text.split("\n\n")[0])), _p(_e(note)),
                      _p(f'<a href="{_e(url)}" target="_blank" style="color:{TEXT};font-weight:600;">See the posts and captions</a>'),
                      _p("<br>".join(_e(l) for l in lines)),
                      _p('Reply "approved" and they go out on schedule, or tell me what to change.', "0")])
    return Email(subject, text, _page(subject, body, cfg, [cfg["you"].get("business") or ""]), attachments)


def report_email(client, cfg, month_name, stats, coming):
    """A client's monthly report: what was made and posted, and what's worth posting about next month."""
    from .settings import plan_has
    subject = f"{client['name']}: your {month_name} report"
    made = []
    if plan_has(client, "social"):
        made.append(f"{stats['planned']} posts designed and written" + (f" ({stats['posted']} posted)" if stats["posted"] else ""))
        if stats["reels"]:
            made.append(f"{stats['reels']} Reel{'s' if stats['reels'] != 1 else ''}")
        if stats["google"]:
            made.append(f"{stats['google']} Google post{'s' if stats['google'] != 1 else ''}")
    if stats["designs"]:
        made.append(f"{stats['designs']} design{'s' if stats['designs'] != 1 else ''} you asked for")
    if not made:
        made.append("Your brand kit kept ready for whatever you need next")
    eng = (f"Your posts got {stats['likes']} likes and {stats['comments']} comments."
           if stats["likes"] or stats["comments"] else "")
    nice = lambda d: f"{dt.date.fromisoformat(d):%b %-d}"
    ahead = [f"{nice(x['date'])}: {x['title']}" for x in coming]
    hello = f"Hi {client.get('contact_name') or ''}".strip() + ","
    paras = [hello, f"Here's what I made for {client['name']} in {month_name}:", "\n".join("- " + x for x in made)]
    if eng:
        paras.append(eng)
    if ahead:
        paras += ["Coming up next month, worth a post (I'll plan them in):", "\n".join("- " + x for x in ahead)]
    paras.append("Anything you'd like to promote next month? Just reply and I'll build the posts around it."
                 if plan_has(client, "social") else
                 "Need a flyer, a menu or a promo next month? Just reply with what it's for.")
    text = "\n\n".join(paras + ["\n".join(signature(cfg))])
    body = "\n".join([_p(_e(hello)), _p(_e(paras[1]), "0 0 8px"),
                      _p("<br>".join("• " + _e(x) for x in made))]
                     + ([_p(_e(eng))] if eng else [])
                     + ([_p(_e("Coming up next month, worth a post (I'll plan them in):"), "0 0 8px"),
                         _p("<br>".join("• " + _e(x) for x in ahead))] if ahead else [])
                     + [_p(_e(paras[-1]), "0")])
    return Email(subject, text, _page(subject, body, cfg, [cfg["you"].get("business") or ""]))


def _hi(client):
    return f"Hi {(client.get('contact_name') or '').split(' ')[0]}".strip() + ","


def _simple(subject, paras, cfg, attachments=(), footer=None):
    """A short personal email: plain text plus the same in a light HTML layout."""
    text = "\n\n".join(paras + ["\n".join(signature(cfg))])
    body = "\n".join(_p("<br>".join(_e(line) for line in para.split("\n")), "0 0 16px" if i < len(paras) - 1 else "0")
                     for i, para in enumerate(paras))
    return Email(subject, text, _page(subject, body, cfg, footer or [cfg["you"].get("business") or ""]), list(attachments))


def design_email(client, cfg, request, paths, final=False):
    """Versions of a design to choose from (reply 1, 2 or 3), or the final, print-ready files of the one they chose."""
    subject = f"Re: {request[:60]}" if request else f"Designs for {client['name']}"
    n = sum(1 for p in paths if str(p).endswith(".png"))
    if final:
        paras = [_hi(client), "Here's the final version, ready to use: the picture for social media and a PDF to print "
                 "(Letter size), where there's one.", "If anything needs a tweak, just reply."]
    elif n > 1:
        nums = ", ".join(str(i) for i in range(1, n)) + f" or {n}"
        paras = [_hi(client), f"Here are {n} versions of what you asked for, in your brand.",
                 f"Reply with {nums} and I'll send you the final, print-ready file. Or tell me what to change "
                 "(the words, a color, the photo) and I'll redo it."]
    else:
        paras = [_hi(client), "Here's what you asked for, in your brand.",
                 "Reply \"good\" and I'll send the print-ready file, or tell me what to change."]
    return _simple(subject, paras, cfg, paths)


def poster_email(client, cfg, moment, date_text, paths):
    """Posters the design agent made on its own for something coming up."""
    subject = f"{client['name']}: a poster for {moment}"
    paras = [_hi(client), f"{moment} is coming up ({date_text}), so I made you a poster for it in your brand: "
             "a version to print (PDF, Letter size) for your window or counter, and one to post.",
             "Both versions are attached, ready to print or post. Want something changed? Just reply and tell me. "
             "No reply needed if you're happy."]
    return _simple(subject, paras, cfg, paths)


def post_today_email(client, cfg, post, pack_url=None):
    """For a client not connected to Meta yet: today's post, ready to share (picture attached, caption to copy)."""
    tags = " ".join("#" + t for t in post.get("hashtags") or [])
    when = post.get("time") or "today"
    paras = [_hi(client), f"Today's post is ready to share" + (f" (best time: {when})." if post.get("time") else "."),
             (post.get("caption") or "").strip() + ("\n\n" + tags if tags else ""),
             "The picture is attached" + (f", and the whole week is here: {pack_url}" if pack_url else "") + ".",
             "Want me to post these for you? Add me to your Facebook Page (Meta Business Suite > Settings > People) "
             "with your Instagram connected, and they'll go out on their own."]
    files = [post["image"]] if post.get("image") and pathlib.Path(post["image"]).exists() else []
    return _simple(f"Today's post: {post.get('headline') or client['name']}", paras, cfg, files)


def plans_reply(lead, cfg, sample_url=None):
    """The automatic answer to a business that replied interested: the plans, the prices and the next step."""
    o = cfg["offer"]
    saving = o["social_monthly"] + o["design_monthly"] - o["bundle_monthly"]
    paras = [
        "Thanks for getting back to me!",
        "Here's how it works. Each plan is month to month, no contract:",
        "\n".join([
            f"- Social media, ${o['social_monthly']}/month: {o['posts_per_week']} posts a week designed in your brand, "
            "with captions and hashtags, plus a Reel and a Google post every week. Posted for you.",
            f"- Design, ${o['design_monthly']}/month: {o['designs_per_month']} designs a month in your brand: flyers, posters, "
            "menus, price lists, promos. Print-ready.",
            f"- Both, ${o['bundle_monthly']}/month" + (f" (you save ${saving})." if saving > 0 else ".")]),
        (f"{o['trial'][0].upper() + o['trial'][1:]}, so you can see it working before you pay anything. "
         if o.get("trial") else "") + "Reply with the one you'd like (Social, Design or Both) and I'll get started.",
        "If you asked me something else, I'll answer it personally soon."]
    if sample_url:
        paras.insert(1, f"Your sample is still here: {sample_url}")
    return _simple("Re: " + (lead.get("subject") or f"Posts for {lead['name']}"), paras, cfg,
                   footer=['Not for you? Reply "no thanks" and I won\'t email you again.', cfg["you"]["mailing_address"]])


def plan_chosen_reply(lead, cfg, plan, price):
    paras = ["Great choice! I'll start on " + {"social": "your posts", "design": "your designs",
                                               "bundle": "your posts and designs"}[plan] + " right away.",
             f"I'll send you a payment request for ${price}/month to this email address"
             + (" after your free first week." if cfg["offer"].get("trial") else " shortly."),
             "Meanwhile, two things help a lot: reply with 10 to 20 photos (your place, your team, what you sell), "
             "and your logo file if you have one. Anything you'd like me to always (or never) say, tell me here too."]
    return _simple("Re: " + (lead.get("subject") or f"Posts for {lead['name']}"), paras, cfg,
                   footer=[cfg["you"].get("business") or "", cfg["you"]["mailing_address"]])


def welcome_email(client, cfg):
    """What happens next, for a new client, by plan."""
    from .settings import plan_has
    paras = [_hi(client), f"Welcome aboard! Here's how it works for {client['name']}:"]
    steps = []
    if plan_has(client, "social"):
        day = str(client.get("content_day") or "thursday").title()
        steps += [f"- Every {day} you'll get next week's posts by email: designed in your brand, with captions, a Reel "
                  "and a Google post. Reply \"approved\" or tell me what to change. No reply = they go out as planned.",
                  "- To have them posted for you automatically, add me to your Facebook Page with Instagram connected "
                  "(Meta Business Suite > Settings > People). Until then you get them ready to post."]
    if plan_has(client, "design"):
        steps += [f"- Need a design? Just email me what it's for (\"a flyer for our open mic, Friday 7pm\"). You get "
                  f"versions to pick from, then the print-ready file. {client.get('designs_per_month') or cfg['offer']['designs_per_month']} "
                  "designs a month are included.",
                  "- I'll also send you posters for what's coming up (holidays, local moments), ready to print."]
    paras += ["\n".join(steps), "Photos help most: reply with any you'd like me to use (your place, team, products)."]
    return _simple(f"Welcome to {cfg['you'].get('business') or 'the studio'}, {client['name']}", paras, cfg)


# Sending -----------------------------------------------------------------------------------------
def build_message(cfg, to, email, reply_to_id=None, sales=True):
    you = cfg["you"]
    msg = EmailMessage()
    msg["From"] = formataddr((you["name"], you["email"]))
    msg["To"] = to
    msg["Subject"] = email.subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=you["email"].split("@")[-1])
    if sales:
        msg["List-Unsubscribe"] = f"<mailto:{you['email']}?subject=unsubscribe>"
    if reply_to_id:
        msg["In-Reply-To"] = reply_to_id
        msg["References"] = reply_to_id
    msg.set_content(email.text)
    if email.html:
        msg.add_alternative(email.html, subtype="html")
    for path in email.attachments or ():
        p = pathlib.Path(path)
        kind = (mimetypes.guess_type(p.name)[0] or "application/octet-stream").split("/")
        msg.add_attachment(p.read_bytes(), maintype=kind[0], subtype=kind[1], filename=p.name)
    return msg


class Mailer:
    """One SMTP connection reused for a batch of sends."""

    def __init__(self, cfg):
        cfg.require("GMAIL_APP_PASSWORD")
        if not cfg["you"].get("email"):
            raise SystemExit("Add your Gmail address in config.yaml (you.email).")
        if not (cfg["you"].get("mailing_address") or "").strip():
            raise SystemExit("Add your mailing address in config.yaml (you.mailing_address). US law requires it.")
        self.cfg = cfg
        self.smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
        self.smtp.login(cfg["you"]["email"], cfg.secret("GMAIL_APP_PASSWORD"))

    def send(self, to, email, reply_to_id=None, sales=True):
        msg = build_message(self.cfg, to, email, reply_to_id, sales)
        self.smtp.send_message(msg)
        return msg["Message-ID"]

    def close(self):
        try:
            self.smtp.quit()
        except Exception:
            pass
