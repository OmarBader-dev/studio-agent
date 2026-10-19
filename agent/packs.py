"""Pages people see: the free sample for a business ("a week of posts, made for you") and the weekly pack for
a paying client. Static HTML with the designs next to it, published by publish.py."""
import datetime as dt
import html
import pathlib
import secrets
import shutil
import string
import urllib.parse

from . import design, fonts
from .settings import SITE

ALPHABET = string.ascii_lowercase + string.digits


def new_token(n=18):
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def e(text):
    return html.escape(str(text or ""), quote=True)


def to_jpeg(src, dest, quality=88, max_side=1350):
    from PIL import Image
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        im.save(dest, "JPEG", quality=quality, optimize=True, progressive=True)
    return dest


def site_root(folder):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text('<!doctype html><meta name="robots" content="noindex"><title>Samples</title>')
    (folder / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    # removed.json is read by sample pages on older deployments (other subdomains), so it allows any origin.
    (folder / "_headers").write_text("/*\n  X-Robots-Tag: noindex, nofollow\n  Referrer-Policy: no-referrer\n"
                                     "/removed.json\n  Access-Control-Allow-Origin: *\n  Cache-Control: no-store\n")


def reply_links(cfg, name):
    you = cfg["you"]
    subject = f"Posts for {name}"
    body = f"Hi {you.get('name', '').split()[0] if you.get('name') else ''}, I saw the posts you made for {name} and I'd like to know more."
    q = urllib.parse.urlencode({"view": "cm", "fs": "1", "to": you.get("email", ""), "su": subject, "body": body},
                               quote_via=urllib.parse.quote)
    mail = f"mailto:{you.get('email', '')}?" + urllib.parse.urlencode({"subject": subject, "body": body},
                                                                       quote_via=urllib.parse.quote)
    return "https://mail.google.com/mail/?" + q, mail


def nice_date(value):
    try:
        return f"{dt.date.fromisoformat(str(value)):%a %b %-d}"
    except ValueError:
        return str(value or "")


def _when(post):
    try:
        d = dt.date.fromisoformat(post["day"])
        h, m = (int(x) for x in post.get("time", "12:00").split(":"))
        t = dt.time(h, m).strftime("%-I:%M %p").replace(":00 ", " ")
        return f"{d:%a %b %-d} · {t}"
    except (ValueError, KeyError):
        return ""


CSS = """
:root{--ink:#16181d;--muted:#5d6470;--line:#e6e2da;--paper:#faf8f3}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 'Inter',system-ui,sans-serif}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px}
.top{padding:18px 0;border-bottom:1px solid var(--line);background:#fff}
.top .wrap{display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:14px;color:var(--muted)}
.top b{color:var(--ink)}
.hero{padding:56px 0 30px}
.kicker{display:inline-block;font-size:13px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--brand-ink);
  background:var(--brand-tint);padding:6px 12px;border-radius:99px;margin:0 0 18px}
h1{font-family:var(--hf);font-weight:var(--hw);font-size:clamp(34px,6vw,60px);line-height:1.04;margin:0 0 18px;letter-spacing:-.01em;max-width:900px}
.lede{font-size:clamp(17px,2.2vw,20px);color:#333;max-width:760px;margin:0}
.moments-inline{margin-top:14px;display:flex;flex-wrap:wrap;gap:8px}
.chip{font-size:13px;background:#fff;border:1px solid var(--line);border-radius:99px;padding:5px 11px;color:#333}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:26px;padding:20px 0 50px}
.post{background:#fff;border:1px solid var(--line);border-radius:22px;overflow:hidden;display:flex;flex-direction:column}
.post img{width:100%;display:block;background:#eee}
.post .body{padding:18px 18px 20px;display:flex;flex-direction:column;gap:10px;flex:1}
.meta{display:flex;justify-content:space-between;gap:10px;font-size:13px;color:var(--muted);flex-wrap:wrap}
.tag{background:var(--brand-tint);color:var(--brand-ink);border-radius:99px;padding:2px 10px;font-weight:600}
.why{font-size:14px;color:var(--muted);margin:0}
.cap{white-space:pre-wrap;margin:0;font-size:15px}
.tags{color:var(--brand-ink);font-size:14px;margin:0;word-break:break-word}
.btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:auto;padding-top:6px}
button,.dl{font:600 14px/1 'Inter',sans-serif;border-radius:99px;padding:11px 16px;border:1px solid var(--ink);background:var(--ink);color:#fff;cursor:pointer;text-decoration:none}
.dl{background:#fff;color:var(--ink)}
section h2{font-family:var(--hf);font-weight:var(--hw);font-size:clamp(26px,4vw,38px);line-height:1.1;margin:0 0 14px}
.brand{background:#fff;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:50px 0}
.two{display:grid;grid-template-columns:1fr 1.5fr;gap:34px;align-items:center}
.two img{width:100%;border-radius:18px;border:1px solid var(--line)}
.notes{padding-left:18px;color:#333}
.coming{padding:46px 0}
.coming ul{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px}
.coming li{background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px 14px}
.coming small{display:block;color:var(--muted)}
.offer{background:var(--ink);color:#fff;padding:56px 0}
.offer h2{color:#fff}
.plans{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin:24px 0}
.plan{border:1px solid rgba(255,255,255,.18);border-radius:20px;padding:22px}
.plan.best{background:#fff;color:var(--ink)}
.plan h3{margin:0 0 4px;font-size:18px}.price{font-size:40px;font-weight:800;margin:4px 0 10px}.price span{font-size:15px;font-weight:500;opacity:.7}
.plan ul{padding-left:18px;margin:0;font-size:15px}
.trial{opacity:.85}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}
.btn{display:inline-block;background:var(--brand);color:var(--on-brand);padding:15px 22px;border-radius:99px;font-weight:700;text-decoration:none}
.btn.alt{background:transparent;color:#fff;border:1px solid rgba(255,255,255,.4)}
.write{opacity:.8;font-size:14px}
footer{padding:30px 0 50px;font-size:13px;color:var(--muted)}
.reel{padding:10px 0 54px}
.reel .two{grid-template-columns:1.2fr 1fr}
.reel video{width:100%;max-width:340px;justify-self:center;border-radius:20px;border:1px solid var(--line);background:#111;
  aspect-ratio:9/16;display:block}
.reel .steps{padding-left:18px;color:#333;margin:0 0 16px}
@media (max-width:760px){.two,.reel .two{grid-template-columns:1fr}.hero{padding-top:34px}}
"""


def _reel_section(title, lede, steps):
    """The short video (reel.mp4 next to the page), playing on its own, muted, with a download button."""
    items = "".join(f"<li>{e(s)}</li>" for s in steps)
    return f"""<section class="reel"><div class="wrap two"><div><h2>{e(title)}</h2><p>{e(lede)}</p>
<ul class="steps">{items}</ul><div class="btns"><a class="dl" href="reel.mp4" download>Download the video</a></div></div>
<video src="reel.mp4" poster="reel.jpg" autoplay muted loop playsinline preload="metadata"></video></div></section>"""


def _listing_section(listing):
    """The design agent's part of a free sample: their own menu (price list, schedule), redesigned to print."""
    kind = listing.get("kind") or "menu"
    pdf = '<a class="dl" href="design.pdf" download>Download the PDF</a> ' if listing.get("pdf") else ""
    return f"""<section class="brand"><div class="wrap two"><div><h2>And your {e(kind)}, redesigned</h2>
<p>I put the {e(kind)} from your website into your brand, ready to print (Letter size). Everything on it is
copied from your site, so give it a quick check before printing.</p>
<div class="btns">{pdf}<a class="dl" href="design.jpg" download>Download the picture</a></div></div>
<img src="design.jpg" alt="Your {e(kind)}, redesigned in your brand" loading="lazy"></div></section>"""


def _copy_reel(reel, folder):
    if reel and pathlib.Path(reel).exists():
        shutil.copy(reel, folder / "reel.mp4")
        cover = pathlib.Path(reel).with_suffix(".jpg")
        if cover.exists():
            to_jpeg(cover, folder / "reel.jpg", max_side=1280)
        return True
    return False


def _page(cfg, kit, title, inner):
    pal = design.palette_of(kit)
    typ = design.type_of(kit, "editorial")
    link = fonts.css_url([typ["heading"], "Inter"], weights=(400, 500, 600, 700, 800))
    brand_ink = pal["primary_on_light"]
    tint = design.colors.mix(pal["accent"], "#ffffff", .84)
    root = (f":root{{--brand:{pal['accent']};--on-brand:{pal['on_accent']};--brand-ink:{brand_ink};--brand-tint:{tint};"
            f"--hf:'{typ['heading']}',serif;--hw:{typ['hw']}}}")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>{e(title)}</title><link rel="stylesheet" href="{link}"><style>{root}{CSS}</style></head><body>
<header class="top"><div class="wrap"><span>Made for <b>{e(kit.get('name'))}</b></span><span>by {e(cfg['you'].get('business') or cfg['you'].get('name'))}</span></div></header>
{inner}
<script>document.querySelectorAll('button[data-copy]').forEach(b=>b.addEventListener('click',()=>{{
const t=document.getElementById(b.dataset.copy).innerText;navigator.clipboard.writeText(t).then(()=>{{const o=b.textContent;b.textContent='Copied';setTimeout(()=>b.textContent=o,1500)}})}}))</script>
</body></html>"""


def _post_cards(posts, prefix="post"):
    cards = []
    for i, p in enumerate(posts, 1):
        img = f"{prefix}-{i}.jpg"
        tags = " ".join("#" + t for t in p.get("hashtags") or [])
        cards.append(f"""<article class="post"><img src="{img}" alt="{e(p.get('alt_text'))}" loading="lazy">
<div class="body"><div class="meta"><span>{e(_when(p))}</span><span class="tag">{e(p.get('moment') or ('Reel idea' if p.get('format') == 'reel' else 'Everyday post'))}</span></div>
<p class="why">{e(p.get('idea'))}</p>
<p class="cap" id="cap{i}">{e(p.get('caption'))}

{e(tags)}</p>
<div class="btns"><button data-copy="cap{i}">Copy caption</button><a class="dl" href="{img}" download>Download image</a></div>
{f'<p class="why">Photo: {e(p["photo_credit"])}</p>' if p.get('photo_credit') else ''}</div></article>""")
    return "\n".join(cards)


def removed_check(status_url, token):
    """A sample page hides itself if its business asked for it to be removed (the list lives on the newest site)."""
    if not status_url:
        return ""
    return (f"<script>fetch({status_url!r},{{cache:'no-store'}}).then(r=>r.ok?r.json():[]).then(l=>{{if(l.includes({token!r}))"
            "document.body.innerHTML='<p style=\"padding:40px;font:18px sans-serif\">This page was removed.</p>'}).catch(()=>{});</script>")


def sample_page(cfg, kit, posts, upcoming, expires, status_url="", token="", reel=False, listing=None):
    """The free sample page for a business."""
    o, name = cfg["offer"], kit.get("name") or "you"
    moments = [p.get("moment") for p in posts if p.get("moment")]
    gmail, mail = reply_links(cfg, name)
    from_site = "logo, colors and fonts" if kit.get("logo") else "colors and fonts"
    notes = []
    if kit.get("colors", {}).get("mono"):
        notes.append("Your site is black and white, so I added one accent color. Easy to change.")
    if kit.get("fonts", {}).get("from_site"):
        notes.append(f"Headlines use {kit['fonts']['heading']}, like your website.")
    if kit.get("photos"):
        notes.append("The photos are yours, from your website.")
    else:
        notes.append("Your site had no photos I could use, so these designs are type-led. With your photos they get even better.")
    upcoming_html = "".join(f"<li>{e(u.get('icon', ''))} <b>{e(u['title'])}</b><small>{e(nice_date(u.get('when')))}</small></li>"
                            for u in upcoming[:8])
    saving = o["social_monthly"] + o["design_monthly"] - o["bundle_monthly"]
    save = f"<li>Save ${saving} a month</li>" if saving > 0 else ""
    inner = f"""
<section class="hero"><div class="wrap">
<p class="kicker">Free sample · {e(name)}</p>
<h1>A week of posts for {e(name)}, in your own brand</h1>
<p class="lede">I used the {from_site} from {e(kit.get('domain'))} and what people are talking about this week to make
these {len(posts)} posts. They're yours to keep and post, free.</p>
<div class="moments-inline">{''.join(f'<span class="chip">{e(m)}</span>' for m in moments)}</div>
</div></section>
<section><div class="wrap grid">{_post_cards(posts)}</div></section>
{_reel_section("And a Reel", "The first post as a short video for Instagram Reels, TikTok and Stories. Videos reach more "
               "people than still posts, so it's yours to keep too.",
               ["Download it and post it as a Reel.", "Add a trending sound from Instagram's own library when you post "
                "(their music is free to use there)."]) if reel else ""}
{_listing_section(listing) if listing else ""}
<section class="brand"><div class="wrap two"><div><h2>Matched to your brand</h2>
<p>Every design starts from your brand kit, so your feed looks like you, not like a template.</p>
<ul class="notes">{''.join(f'<li>{e(n)}</li>' for n in notes)}</ul></div>
<img src="brand-board.jpg" alt="Brand kit for {e(name)}: logo, colors and fonts" loading="lazy"></div></section>
<section class="coming"><div class="wrap"><h2>Coming up, worth a post</h2><ul>{upcoming_html}</ul></div></section>
<section class="offer"><div class="wrap"><h2>Want this every week?</h2>
<p>Pick what you need. Each plan works on its own, or get both for less.</p>
<div class="plans">
<div class="plan"><h3>Social media</h3><p class="price">${o['social_monthly']}<span>/month</span></p><ul>
<li>{o['posts_per_week']} posts a week, designed in your brand and tied to what's happening</li>
<li>Captions, hashtags and the best time to post</li><li>Story versions, a Reel and a Google post every week</li>
<li>Posted for you, plus a short monthly report</li></ul></div>
<div class="plan best"><h3>Social + Design</h3><p class="price">${o['bundle_monthly']}<span>/month</span></p><ul>
<li>Everything in both plans</li>{save}</ul></div>
<div class="plan"><h3>Design</h3><p class="price">${o['design_monthly']}<span>/month</span></p><ul>
<li>{o['designs_per_month']} designs a month in your brand</li><li>Flyers, promos, menus, price lists, class schedules</li>
<li>3 versions of each, print-ready PDFs</li><li>Your brand kit, kept ready</li></ul></div></div>
<p class="trial">{e((o.get('trial') or '').capitalize() + '. ' if o.get('trial') else '')}No contract, cancel anytime.</p>
<div class="actions"><a class="btn" href="{e(gmail)}" target="_blank" rel="noopener">Reply in Gmail</a>
<a class="btn alt" href="{e(mail)}">Use my email app</a></div>
<p class="write">Or write to {e(cfg['you'].get('email'))}</p></div></section>
<footer><div class="wrap"><p>Captions are drafts: I'd check every detail with you before anything is posted.</p>
<p>This page is private (it isn't listed anywhere) and comes down on {e(expires)}. Want it gone sooner? Reply "remove".</p>
<p>{e(cfg['you'].get('name'))} · {e(cfg['you'].get('business'))} · {e(cfg['you'].get('mailing_address'))}</p></div></footer>
{removed_check(status_url, token)}"""
    return _page(cfg, kit, f"{name}: a week of posts, made for you", inner)


def write_sample(cfg, kit, posts, board_png, upcoming, token, expires, root=None, status_url="", reel=None, listing=None):
    """Write a business's sample page and images into the site folder. Returns the folder."""
    folder = (root or SITE) / "s" / token
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    for i, p in enumerate(posts, 1):
        to_jpeg(p["image"], folder / f"post-{i}.jpg")
    if board_png and pathlib.Path(board_png).exists():
        to_jpeg(board_png, folder / "brand-board.jpg", max_side=1600)
    has_reel = _copy_reel(reel, folder)
    if listing and pathlib.Path(listing.get("image", "")).exists():
        to_jpeg(listing["image"], folder / "design.jpg", quality=90, max_side=1650)
        if pathlib.Path(listing.get("pdf", "")).exists():
            shutil.copy(listing["pdf"], folder / "design.pdf")
    else:
        listing = None
    (folder / "index.html").write_text(sample_page(cfg, kit, posts, upcoming, expires, status_url, token, has_reel,
                                                   listing))
    return folder


def week_page(cfg, kit, posts, week_label, approve_note, stories=(), reel=False, gbp=None):
    """A paying client's posts for the week."""
    gmail, mail = reply_links(cfg, kit.get("name") or "")
    story_html = ""
    if stories:
        cells = "".join(f'<article class="post"><img src="story-{i}.jpg" alt="Story {i}" loading="lazy"><div class="body">'
                        f'<div class="btns"><a class="dl" href="story-{i}.jpg" download>Download story</a></div></div></article>'
                        for i in range(1, len(stories) + 1))
        story_html = f'<section><div class="wrap"><h2>Stories</h2></div><div class="wrap grid">{cells}</div></section>'
    reel_html = _reel_section("This week's Reel", "A short video of your first post, for Instagram Reels, TikTok and "
                              "Facebook. Post it any day this week.",
                              ["Pick a trending sound from Instagram's library when you post it.",
                               "Use the first post's caption, or a shorter one."]) if reel else ""
    gbp_html = ""
    if gbp:
        gbp_html = f"""<section class="brand"><div class="wrap two"><div><h2>Your Google post</h2>
<p>Posts on your Google Business Profile keep your listing fresh in Google Search and Maps. Add it from your profile:
Add update, then paste the text and the picture.</p>
<p class="cap" id="gbp">{e(gbp.get('text'))}</p>
<div class="btns"><button data-copy="gbp">Copy text</button><a class="dl" href="google-post.jpg" download>Download picture</a></div>
{f'<p class="why">Button: {e(gbp["button"])} → {e(gbp["link"])}</p>' if gbp.get('link') else ''}</div>
<img src="google-post.jpg" alt="Google post picture" loading="lazy"></div></section>"""
    inner = f"""
<section class="hero"><div class="wrap"><p class="kicker">{e(week_label)}</p>
<h1>Your posts for {e(week_label.lower())}</h1>
<p class="lede">{e(approve_note)}</p></div></section>
<section><div class="wrap grid">{_post_cards(posts)}</div></section>{reel_html}{story_html}{gbp_html}
<section class="offer"><div class="wrap"><h2>All good?</h2>
<p>Reply "approved" and they go out on schedule. Or tell me what to change: a word, a photo, a whole post.</p>
<div class="actions"><a class="btn" href="{e(gmail)}" target="_blank" rel="noopener">Reply in Gmail</a>
<a class="btn alt" href="{e(mail)}">Use my email app</a></div></div></section>
<footer><div class="wrap"><p>{e(cfg['you'].get('name'))} · {e(cfg['you'].get('business'))}</p></div></footer>"""
    return _page(cfg, kit, f"{kit.get('name')}: {week_label}", inner)


def write_week(cfg, kit, posts, client_key, week_label, approve_note, token, root=None, stories=(), reel=None, gbp=None):
    folder = (root or SITE) / "c" / client_key / token
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    for i, p in enumerate(posts, 1):
        to_jpeg(p["image"], folder / f"post-{i}.jpg", quality=92, max_side=1920)
    stories = [s for s in stories if s.get("image")]
    for i, st in enumerate(stories, 1):
        to_jpeg(st["image"], folder / f"story-{i}.jpg", quality=92, max_side=1920)
    has_reel = _copy_reel(reel, folder)
    if gbp and gbp.get("image") and pathlib.Path(gbp["image"]).exists():
        to_jpeg(gbp["image"], folder / "google-post.jpg", quality=92, max_side=1600)
    else:
        gbp = None
    (folder / "index.html").write_text(week_page(cfg, kit, posts, week_label, approve_note, stories, has_reel, gbp))
    return folder
