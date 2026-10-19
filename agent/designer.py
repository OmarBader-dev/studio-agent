"""The graphic design agent: picks styles for a brand (its niche, its look, this week's design trends),
picks photos, renders each design and checks it, and makes the brand board."""
import html
import pathlib
import random
import re

from . import ai, colors, design, design_trends, images, styles

# Which styles suit which kind of business, best first.
STYLE_FIT = {
    "restaurant": ["bold", "photo", "retro", "brutal", "split", "editorial", "gradient", "duotone", "minimal"],
    "cafe": ["editorial", "photo", "retro", "minimal", "gradient", "split", "bold", "duotone", "brutal"],
    "bakery": ["editorial", "retro", "photo", "split", "minimal", "brutal", "gradient", "bold", "duotone"],
    "gym": ["bold", "duotone", "brutal", "gradient", "photo", "split", "minimal", "retro", "editorial"],
    "beauty": ["editorial", "minimal", "photo", "gradient", "split", "duotone", "retro", "bold", "brutal"],
    "shop": ["editorial", "minimal", "photo", "brutal", "split", "gradient", "retro", "bold", "duotone"],
    "bar": ["bold", "retro", "photo", "gradient", "duotone", "brutal", "split", "editorial", "minimal"],
    "pets": ["brutal", "photo", "retro", "bold", "split", "gradient", "editorial", "minimal", "duotone"],
}
FORMAT_STYLES = {   # styles that work at each size
    "landscape": ["bold", "minimal", "photo", "split", "duotone"],
    "gbp": ["photo", "bold", "minimal", "split", "duotone"],
    "cover": ["bold", "minimal", "photo", "split"],
}


def choose_styles(kit, n, fmt="post", seed=0, weights=None, has_photo=None):
    """n different styles for a brand, mixing what suits its niche with this week's design trends."""
    niche = kit.get("niche", "restaurant")
    order = STYLE_FIT.get(niche, STYLE_FIT["restaurant"])
    allowed = FORMAT_STYLES.get(fmt, list(styles.STYLES))
    has_photo = bool(kit.get("photos")) if has_photo is None else has_photo
    weights = weights if weights is not None else design_trends.radar().get("weights", {})
    rnd = random.Random(f"{kit.get('name')}-{seed}")
    scored = []
    for i, style in enumerate(order):
        if style not in allowed or (style in styles.NEEDS_PHOTO and not has_photo):
            continue
        score = (len(order) - i) / len(order) + 2.2 * weights.get(style, 0) + rnd.random() * 0.25
        scored.append((score, style))
    picked = [s for _, s in sorted(scored, reverse=True)][:n]
    if has_photo and not any(s in styles.NEEDS_PHOTO for s in picked) and n >= 2:
        photo_style = next((s for s in order if s in styles.NEEDS_PHOTO and s in allowed), None)
        if photo_style:
            picked[-1] = photo_style                      # show their own photos at least once
    if kit.get("photos") and fmt == "gbp" and picked[0] not in styles.NEEDS_PHOTO and "photo" in allowed:
        picked[0] = "photo"                               # Google favors real photos of the place: theirs
    first_photo = next((i for i, s in enumerate(picked) if s in styles.NEEDS_PHOTO), None)
    if first_photo:                                       # and lead with them: it's the first thing people see
        picked.insert(0, picked.pop(first_photo))
    while len(picked) < n:
        picked.append(picked[len(picked) % max(1, len(picked))] if picked else "bold")
    return picked


def fallback_styles(kit, fmt, first):
    allowed = FORMAT_STYLES.get(fmt, list(styles.STYLES))
    order = [s for s in STYLE_FIT.get(kit.get("niche", "restaurant"), STYLE_FIT["restaurant"]) if s in allowed]
    return [s for s in order if s != first and s not in styles.NEEDS_PHOTO][:3]


def design_posts(cfg, store, renderer, kit, posts, out_dir, fmt="post", extra_images=False, seed=0):
    """Render one design per post. extra_images: allow theme stock photos and AI backgrounds (client work).
    Returns the posts with 'image', 'style' and 'issues' added."""
    out_dir = pathlib.Path(out_dir)
    photos = [p["path"] for p in kit.get("photos") or [] if p.get("path")]
    picks = choose_styles(kit, len(posts), fmt, seed=seed, has_photo=bool(photos) or extra_images)
    used_photos = 0
    for i, (post, style) in enumerate(zip(posts, picks)):
        photo, credit = None, None
        if style in styles.NEEDS_PHOTO:
            if photos:
                photo = photos[used_photos % len(photos)]
                used_photos += 1
            elif extra_images:
                q = images.theme_query(post)
                found = images.stock(cfg, q) if q else None
                if not found:
                    found = images.ai_background(cfg, store, post.get("moment") or kit.get("niche"),
                                                 [kit["colors"]["primary"], kit["colors"]["accent"]])
                if found:
                    photo, credit = found["path"], found.get("credit")
            if not photo:
                style = next(s for s in fallback_styles(kit, fmt, style) + ["bold"])
        f = "story" if post.get("format") == "story" and fmt == "post" else fmt
        spec = {"format": f, "style": style, "brand": kit, "content": post["content"], "photo": photo, "seed": seed + i}
        name = re.sub(r"[^a-z0-9]+", "-", f"{i + 1}-{post.get('moment') or style}".lower()).strip("-")[:40]
        path, used, issues = design.render_best(renderer, spec, out_dir / f"{name}.png", fallback_styles(kit, f, style))
        post.update(image=str(path), style=used, issues=issues, photo_credit=credit, size=f, photo_path=photo)
    return posts


def reel(renderer, kit, post, out_path, seed=0):
    """A post as a short vertical video (Reels, TikTok, Stories): its design at 9:16, animated. The still is checked
    first, so the video never has cut-off text. Returns the MP4 path, or None (no ffmpeg, or it didn't fit)."""
    from . import motion
    if not motion.available():
        return None
    out_path = pathlib.Path(out_path)
    style = post.get("style") or "bold"
    spec = {"format": "story", "style": style, "brand": kit, "content": post["content"],
            "photo": post.get("photo_path") if style in styles.NEEDS_PHOTO else None, "seed": seed}
    if style in styles.NEEDS_PHOTO and not spec["photo"]:
        spec["style"] = style = fallback_styles(kit, "story", style)[0]
    _, used, issues = design.render_best(renderer, spec, out_path.with_suffix(".png"),
                                         fallback_styles(kit, "story", style))
    if issues:
        return None
    return motion.render(renderer, dict(spec, style=used), out_path)


def brand_board(renderer, kit, out_path):
    """A one-page brand board: logo, colors with their codes, fonts, and photos. 1600 x 1000."""
    pal = design.palette_of(kit)
    typ = design.type_of(kit, "editorial")
    logo = kit.get("logo")
    logo_html = (f'<img src="{design.data_uri(logo["path"], 600)}" class="lg">' if logo and logo.get("path")
                 else f'<div class="wm">{html.escape(kit.get("name") or "")}</div>')
    logo_card = "card dark" if logo and logo.get("tone") == "light" else "card"
    swatch = "".join(
        f'<div class="sw"><div class="chip" style="background:{pal[r]}"></div><b>{r.title()}</b><span>{pal[r].upper()}</span></div>'
        for r in ("primary", "secondary", "accent", "dark", "light"))
    photos = "".join(f'<div class="ph" style="background-image:url(\'{design.data_uri(p["path"], 700)}\')"></div>'
                     for p in (kit.get("photos") or [])[:3])
    from . import fonts
    link = fonts.css_url([typ["heading"], typ["body"]])
    page = f"""<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="{link}"><style>
html,body{{margin:0}}body{{width:1600px;height:1000px;font-family:'{typ['body']}',sans-serif;background:#f6f4ef;color:#141414}}
.wrap{{padding:70px 80px;display:grid;grid-template-columns:1.1fr 1fr;gap:60px;height:100%;box-sizing:border-box}}
h1{{font-family:'{typ['heading']}',serif;font-weight:{typ['hw']};font-size:64px;margin:0 0 6px;line-height:1}}
.k{{font-size:16px;letter-spacing:.2em;text-transform:uppercase;color:#777;margin-bottom:26px}}
.card{{background:#fff;border-radius:28px;padding:34px;box-shadow:0 10px 30px rgba(0,0,0,.06);margin-bottom:26px}}
.lg{{max-height:120px;max-width:420px;display:block}}.card.dark{{background:#161616}}.wm{{font-family:'{typ['heading']}',serif;font-weight:{typ['hw']};font-size:54px}}
.sws{{display:flex;gap:18px}}.sw{{flex:1;font-size:15px;display:flex;flex-direction:column;gap:6px}}
.chip{{height:110px;border-radius:18px;border:1px solid rgba(0,0,0,.08)}}.sw span{{color:#666;font-family:monospace}}
.ty .h{{font-family:'{typ['heading']}',serif;font-weight:{typ['hw']};font-size:52px;line-height:1.05}}
.ty .b{{font-size:22px;line-height:1.5;color:#333;margin-top:10px}}.ty small{{color:#777;font-size:15px;letter-spacing:.08em}}
.phs{{display:grid;grid-template-columns:1fr 1fr;grid-auto-rows:255px;gap:16px}}
.ph{{background-size:cover;background-position:center;border-radius:22px}}.ph:first-child{{grid-column:span 2}}
.empty{{height:100%;border-radius:22px;background:{pal['primary']};display:flex;align-items:center;justify-content:center;
color:{pal['on_primary']};font-family:'{typ['heading']}',serif;font-size:44px;padding:40px;text-align:center}}
</style></head><body><div class="wrap"><div>
<h1>{html.escape(kit.get('name') or '')}</h1><div class="k">Brand kit</div>
<div class="{logo_card}">{logo_html}</div>
<div class="card"><div class="sws">{swatch}</div></div>
<div class="card ty"><small>HEADINGS · {html.escape(typ['heading'])}</small><div class="h">Made for {html.escape((kit.get('city') or 'you').split(',')[0])}</div>
<small style="display:block;margin-top:18px">TEXT · {html.escape(typ['body'])}</small>
<div class="b">Every design uses your colors, your fonts and your logo, so your feed looks like you.</div></div>
</div><div class="phs">{photos or '<div class="empty">Your photos go here</div>'}</div></div></body></html>"""
    page_obj = renderer._page(1600, 1000, page)
    try:
        out_path = pathlib.Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        page_obj.screenshot(path=str(out_path), type="png")
    finally:
        page_obj.close()
    return out_path


def request_to_content(cfg, store, kit, request):
    """A client's (or your) design request in plain words -> the words for the design.
    Unlike outreach samples, offers here come from the client, so they're kept."""
    data = ai.ask(cfg, store, f"""A small business asked for a design. Turn the request into the words on the design.
BUSINESS: {kit.get('name')} ({kit.get('niche')}) in {kit.get('city') or ''}
REQUEST: {request}
Keep every fact, price, date and time from the request exactly. Don't add any.
Return JSON: {{"format": "post" or "story" or "flyer" or "landscape", "eyebrow": "2-4 words", "headline": "2-6 words",
"subhead": "under 90 characters", "cta": "2-4 words", "badge": "the offer in 1-3 words, or ''",
"bullets": ["up to 4 short details like date, time, place"], "icon": "one emoji"}}""",
                  system="You are a careful graphic designer's assistant. JSON only.", max_tokens=600, temperature=0.4)
    if not isinstance(data, dict) or not data.get("headline"):
        words = request.strip().rstrip(".")
        data = {"format": "post", "eyebrow": kit.get("name", "")[:28], "headline": " ".join(words.split()[:5]),
                "subhead": words[:90], "cta": "Learn more", "badge": "", "bullets": [], "icon": "✨"}
    data["footer"] = kit.get("domain") or ""
    fmt = data.pop("format", "post")
    return (fmt if fmt in design.FORMATS else "post"), {k: v for k, v in data.items() if not k.startswith("_")}


def variants(cfg, store, renderer, kit, content, fmt, out_dir, n=3, seed=0):
    """n versions of one design in different styles. Returns [(path, style, issues)]."""
    out = []
    photos = [p["path"] for p in kit.get("photos") or [] if p.get("path")]
    for i, style in enumerate(choose_styles(kit, n, fmt, seed=seed)):
        photo = photos[i % len(photos)] if photos and style in styles.NEEDS_PHOTO else None
        spec = {"format": fmt, "style": style, "brand": kit, "content": content, "photo": photo, "seed": seed + i}
        out.append(design.render_best(renderer, spec, pathlib.Path(out_dir) / f"v{i + 1}-{style}.png",
                                      fallback_styles(kit, fmt, style)))
    return out


def contrast_report(kit):
    """Quick accessibility notes on the brand's colors (shown on the brand board page)."""
    pal = design.palette_of(kit)
    notes = []
    if colors.contrast(pal["primary"], pal["on_primary"]) < 4.5:
        notes.append("Text on your main color is hard to read at small sizes; designs use it for big headlines only.")
    if colors.contrast(pal["accent"], pal["light"]) < 3:
        notes.append("Your accent color is light, so designs darken it slightly when it sits on white.")
    return notes
