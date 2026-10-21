"""Design styles. Each takes a context (brand palette, fonts, logo, photo, content, format) and returns
(html, css). Sizes use rem, where 1rem is 1% of the design's width, so every style works at any size.

The styles follow current design directions (bold type, editorial serifs, grain gradients, neo-brutalism,
duotone photos, Swiss minimalism, retro sunbursts) without copying anyone's work.
"""
import html
import re

from . import colors

NOISE = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='400' height='400'>"
         "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/>"
         "<feColorMatrix values='0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 .55 0'/></filter>"
         "<rect width='100%' height='100%' filter='url(%23n)'/></svg>")


def e(text):
    return html.escape(str(text or ""), quote=True)


def is_emoji(icon):
    return bool(icon) and not re.fullmatch(r"[a-z0-9_]+", icon)


def icon(ctx, cls="deco"):
    ic = (ctx["content"].get("icon") or "").strip()
    if not ic:
        return ""
    if is_emoji(ic):
        return f'<span class="emoji {cls}">{e(ic)}</span>'
    return f'<span class="ms {cls}">{e(ic)}</span>'


def logo(ctx, on="dark", cls="logo"):
    """The logo (with a backing chip when it would disappear on this background) or the name as a wordmark."""
    uri, tone = ctx["logo_uri"], ctx["logo_tone"]
    if uri:
        chip = ((on == "dark" and tone in ("dark", "unknown", "mid")) or (on == "light" and tone == "light")
                or (on == "photo" and tone in ("dark", "mid", "unknown")))
        dark_chip = on == "light" and tone == "light"
        klass = "logo-wrap" + (" chip" if chip else "") + (" chip-dark" if dark_chip else "") + (
            " boxed" if tone == "boxed" else "")
        return f'<div class="{klass}"><img class="{cls}" src="{uri}" alt=""></div>'
    name = ctx["brand"].get("name") or ""
    return f'<div class="wordmark{" onphoto" if on == "photo" else ""}">{e(name)}</div>'


def hl(ctx, text, role="headline", cls="", min_px=28, floor=0):
    upper = " upper" if ctx["type"]["upper"] else ""
    return (f'<h1 class="hl{upper} {cls}" data-fit data-role="{role}" data-min="{min_px}" '
            f'data-floor="{floor}">{e(text)}</h1>')


def sub(text, cls="sub", min_px=18, floor=22):
    if not text:
        return ""
    return f'<p class="{cls}" data-fit data-role="subhead" data-min="{min_px}" data-floor="{floor}">{e(text)}</p>'


def eyebrow(ctx, cls="eyebrow"):
    t = ctx["content"].get("eyebrow")
    return f'<div class="{cls}" data-fit data-role="eyebrow" data-min="14">{e(t)}</div>' if t else ""


def cta(ctx, cls="cta"):
    t = ctx["content"].get("cta")
    return f'<div class="{cls}" data-fit data-role="cta" data-min="16">{e(t)}</div>' if t else ""


def badge(ctx, cls="badge"):
    t = ctx["content"].get("badge")
    return f'<div class="{cls}"><span data-fit data-role="badge" data-min="12">{e(t)}</span></div>' if t else ""


def footer(ctx, cls="foot"):
    t = ctx["content"].get("footer")
    return f'<div class="{cls}" data-fit data-role="footer" data-min="12">{e(t)}</div>' if t else ""


def bullets(ctx, cls="bullets"):
    items = [b for b in (ctx["content"].get("bullets") or []) if b][:6]
    if not items:
        return ""
    lis = "".join(f"<li>{e(b)}</li>" for b in items)
    return f'<ul class="{cls}" data-fit data-role="bullets" data-min="14">{lis}</ul>'


def pad(ctx):
    """Outer padding; stories keep clear of the app's top and bottom bars."""
    if ctx["kind"] == "tall":
        return "13rem 7.5rem 17rem"
    if ctx["kind"] == "wide":
        return "5rem 5.5rem"
    return "7rem 7rem 6.5rem"


COMMON = """
.logo-wrap{display:inline-flex;align-items:center;justify-content:center;max-width:34rem}
.logo-wrap .logo{display:block;max-height:9rem;max-width:30rem;object-fit:contain}
.logo-wrap.chip{background:#ffffff;padding:1.6rem 2.2rem;border-radius:2.2rem;box-shadow:0 .6rem 2rem rgba(0,0,0,.18)}
.logo-wrap.chip-dark{background:#151515}
.logo-wrap.boxed .logo{border-radius:1.6rem}
.wordmark{font-family:var(--hf);font-weight:var(--hw);font-size:4.4rem;line-height:1;letter-spacing:.01em;max-width:60rem}
.wordmark.onphoto{background:rgba(0,0,0,.32);padding:1.2rem 2.2rem;border-radius:1.4rem;color:#fff;
  text-shadow:0 .2rem 1.2rem rgba(0,0,0,.35);backdrop-filter:blur(1.2rem)}
.cta{display:inline-flex;align-items:center;gap:1.2rem;font-weight:700;font-size:3.6rem;line-height:1.1;padding:2.2rem 4rem;
  border-radius:99rem;max-width:100%;white-space:nowrap;max-height:9rem}
.foot{font-size:2.6rem;opacity:.85;line-height:1.25;max-height:7rem}
.bullets{margin:0;padding:0;list-style:none;font-size:3.6rem;line-height:1.35;max-height:30rem}
.bullets li{padding-left:4.2rem;position:relative}
.bullets li:before{content:"";position:absolute;left:0;top:.45em;width:1.8rem;height:1.8rem;border-radius:50%;background:var(--accent)}
"""


def _shade(tone):
    """How dark a scrim must get for white words over a photo this light (0-1)."""
    return .66 if tone < .5 else (.8 if tone < .68 else .9)


# 1. Bold type --------------------------------------------------------------------------------------
def bold(ctx):
    c, k = ctx["content"], ctx["kind"]
    wide = k == "wide"
    hsize = 15 if ctx["type"]["condensed"] else 12.5
    if k == "square":
        hsize *= .86
    if wide:
        hsize *= .62
    body = f"""
<div class="bg"></div>{icon(ctx, "deco")}
<div class="frame">
  <div class="top">{logo(ctx, "dark" if colors.luminance(ctx['pal']['primary']) < .4 else "light")}{eyebrow(ctx)}</div>
  <div class="mid">{hl(ctx, c.get('headline'), min_px=34, floor=60)}<div class="bar"></div>{sub(c.get('subhead'))}{bullets(ctx)}</div>
  <div class="bottom">{cta(ctx)}{footer(ctx)}</div>
</div>{badge(ctx)}"""
    css = COMMON + f"""
.bg{{position:absolute;inset:0;background:var(--primary)}}
.frame{{position:absolute;inset:0;padding:{pad(ctx)};display:flex;flex-direction:column;color:var(--on-primary)}}
.top{{display:flex;justify-content:space-between;align-items:center;gap:3rem}}
.eyebrow{{font-weight:700;font-size:2.8rem;letter-spacing:.14em;text-transform:uppercase;padding:1.3rem 2.6rem;
  border:.35rem solid currentColor;border-radius:99rem;white-space:nowrap;max-width:52rem}}
.mid{{flex:1;display:flex;flex-direction:column;justify-content:center;gap:3.2rem;min-height:0;{'max-width:62%' if wide else ''}}}
.hl{{font-size:{hsize}rem;max-height:{'34rem' if wide else ('60rem' if k=='tall' else '52rem')};color:var(--on-primary)}}
.bar{{width:16rem;height:1.6rem;background:var(--accent-on-primary);border-radius:1rem;flex:none}}
.sub{{font-size:{3.4 if wide else 4.3}rem;line-height:1.3;max-height:{'12rem' if wide else '20rem'};opacity:.94;max-width:{'100%' if wide else '88%'}}}
.bottom{{display:flex;align-items:center;justify-content:space-between;gap:3rem}}
.cta{{background:var(--accent-on-primary);color:{colors.text_on(ctx['pal']['accent_on_primary'])}}}
.deco{{position:absolute;right:-6rem;bottom:{'-4rem' if k!='tall' else '8rem'};font-size:{38 if not wide else 30}rem;
  color:var(--on-primary);opacity:.11;transform:rotate(-12deg)}}
.emoji.deco{{opacity:.22;filter:saturate(.9)}}
.badge{{position:absolute;right:6rem;top:{'24rem' if k=='tall' else '20rem'};width:22rem;height:22rem;border-radius:50%;
  background:var(--accent-on-primary);color:{colors.text_on(ctx['pal']['accent_on_primary'])};display:flex;align-items:center;
  justify-content:center;text-align:center;transform:rotate(10deg);font-family:var(--hf);font-weight:var(--hw);font-size:4.2rem;
  line-height:1;padding:3rem}}
.badge span{{max-height:15rem;display:block}}
"""
    return body, css


# 2. Full-bleed photo ---------------------------------------------------------------------------------
def photo(ctx):
    if not ctx["photo_uri"]:
        return gradient(ctx)
    c, k = ctx["content"], ctx["kind"]
    wide = k == "wide"
    hsize = (11 if ctx["type"]["condensed"] else 9.5) * (.7 if wide else 1)
    body = f"""
<div class="ph" style="background-image:url('{ctx['photo_uri']}')"></div><div class="scrim"></div>
<div class="frame">
  <div class="top">{logo(ctx, "photo")}{badge(ctx)}</div>
  <div class="txt">{hl(ctx, c.get('headline'), min_px=30, floor=56)}{sub(c.get('subhead'))}
  <div class="row">{cta(ctx)}{footer(ctx)}</div></div>
</div>"""
    css = COMMON + f"""
.ph{{position:absolute;inset:0;background-size:cover;background-position:center}}
.scrim{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.34) 0%,rgba(0,0,0,0) 20%,rgba(0,0,0,0) 40%,
  rgba(0,0,0,{_shade(ctx.get('photo_tone_bottom', .5)) * .7:.2f}) 68%,rgba(0,0,0,{_shade(ctx.get('photo_tone_bottom', .5)) + .1:.2f}) 100%)}}
.frame{{position:absolute;inset:0;padding:{pad(ctx)};display:flex;flex-direction:column;justify-content:space-between;color:#fff}}
.top{{display:flex;justify-content:space-between;align-items:flex-start}}
.txt{{display:flex;flex-direction:column;gap:2.6rem;{'max-width:70%' if wide else ''}}}
.eyebrow{{align-self:flex-start;background:var(--accent);color:var(--on-accent);font-weight:700;font-size:2.6rem;
  letter-spacing:.12em;text-transform:uppercase;padding:1.1rem 2.2rem;border-radius:1rem;max-width:60rem;white-space:nowrap}}
.hl{{font-size:{hsize}rem;max-height:{'30rem' if wide else '44rem'};text-shadow:0 .4rem 3rem rgba(0,0,0,.35)}}
.sub{{font-size:{3.3 if wide else 4}rem;line-height:1.32;max-height:{'11rem' if wide else '17rem'};opacity:.95}}
.row{{display:flex;align-items:center;gap:3rem;justify-content:space-between}}
.cta{{background:var(--accent);color:var(--on-accent)}}
.foot{{color:#fff}}
.badge{{width:21rem;height:21rem;border-radius:50%;background:var(--accent);color:var(--on-accent);display:flex;align-items:center;
  justify-content:center;text-align:center;font-family:var(--hf);font-weight:var(--hw);font-size:4rem;line-height:1;padding:3rem;
  transform:rotate(8deg)}}
.badge span{{max-height:14rem;display:block}}
"""
    return body, css


# 3. Split: photo and color panel -----------------------------------------------------------------------
def split(ctx):
    if not ctx["photo_uri"]:
        return editorial(ctx)
    c, k = ctx["content"], ctx["kind"]
    wide = k == "wide"
    hsize = (10 if ctx["type"]["condensed"] else 8.4) * (.72 if wide else 1)
    ph_pos = "left:0;top:0;bottom:0;width:48%" if wide else f"left:0;right:0;top:0;height:{'50%' if k == 'tall' else '54%'}"
    panel = "right:0;top:0;bottom:0;width:52%" if wide else f"left:0;right:0;bottom:0;height:{'50%' if k == 'tall' else '46%'}"
    body = f"""
<div class="ph" style="background-image:url('{ctx['photo_uri']}');{ph_pos}"></div>
<div class="panel" style="{panel}">
  <div class="inner">{hl(ctx, c.get('headline'), min_px=28, floor=50)}{sub(c.get('subhead'))}
  <div class="row">{cta(ctx)}{footer(ctx)}</div></div>
</div>
<div class="lg">{logo(ctx, "photo")}</div>{badge(ctx)}"""
    inner_pad = "4.5rem 5rem" if wide else ("6rem 7.5rem 16rem" if k == "tall" else "5.5rem 7rem")
    css = COMMON + f"""
.ph{{position:absolute;background-size:cover;background-position:center}}
.panel{{position:absolute;background:var(--primary);color:var(--on-primary);display:flex}}
.panel:before{{content:"";position:absolute;{'left:0;top:0;bottom:0;width:1.2rem' if wide else 'left:0;right:0;top:0;height:1.2rem'};
  background:var(--accent)}}
.inner{{padding:{inner_pad};display:flex;flex-direction:column;justify-content:center;gap:2.4rem;width:100%}}
.eyebrow{{font-weight:700;font-size:2.6rem;letter-spacing:.14em;text-transform:uppercase;color:var(--accent-on-primary);
  max-width:80rem;white-space:nowrap}}
.hl{{font-size:{hsize}rem;max-height:{'24rem' if wide else ('34rem' if k=='tall' else '27rem')}}}
.sub{{font-size:{3.1 if wide else 3.7}rem;line-height:1.32;max-height:{'11rem' if wide else '14rem'};opacity:.93}}
.row{{display:flex;align-items:center;gap:3rem;justify-content:space-between}}
.cta{{background:var(--accent-on-primary);color:{colors.text_on(ctx['pal']['accent_on_primary'])};font-size:3.2rem;padding:1.9rem 3.4rem}}
.lg{{position:absolute;left:{'5rem' if wide else '6rem'};top:{'14rem' if k=='tall' else '5.5rem'}}}
.badge{{position:absolute;right:6rem;top:{'14rem' if k=='tall' else '5.5rem'};background:var(--accent);color:var(--on-accent);
  padding:1.8rem 3rem;border-radius:1.4rem;font-family:var(--hf);font-weight:var(--hw);font-size:4rem;line-height:1;
  transform:rotate(-4deg);max-width:40rem}}
.badge span{{display:block;max-height:10rem}}
"""
    return body, css


# 4. Editorial serif ----------------------------------------------------------------------------------
def editorial(ctx):
    c, k = ctx["content"], ctx["kind"]
    wide = k == "wide"
    fallback_icon = '<span class="ms mic">auto_awesome</span>'
    medallion = icon(ctx, "mic") or fallback_icon
    photo_style = "background-image:url('" + (ctx["photo_uri"] or "") + "')"
    visual = (f'<div class="inset" style="{photo_style}"></div>' if ctx["photo_uri"]
              else f'<div class="medallion">{medallion}</div>')
    hsize = (9.6 if not ctx["type"]["condensed"] else 11) * (.68 if wide else 1)
    if k == "square":
        hsize *= .88
    body = f"""
<div class="paper"></div>
<div class="frame">
  <div class="top"><span class="kick">{e(c.get('eyebrow') or ctx['brand'].get('name') or '')}</span></div>
  <div class="rule"></div>
  <div class="body">
    <div class="copy">{hl(ctx, c.get('headline'), min_px=30, floor=54)}{sub(c.get('subhead'), 'sub ital')}{bullets(ctx)}</div>
    {visual}
  </div>
  <div class="rule"></div>
  <div class="bottom">{logo(ctx, "light")}{cta(ctx, 'link')}</div>
</div>"""
    css = COMMON + f"""
.paper{{position:absolute;inset:0;background:var(--light)}}
.paper:after{{content:"";position:absolute;inset:0;background-image:url("{NOISE}");opacity:.09;mix-blend-mode:multiply}}
.frame{{position:absolute;inset:0;padding:{pad(ctx)};display:flex;flex-direction:column;gap:3rem;color:var(--on-light)}}
.top{{display:flex;justify-content:space-between;align-items:baseline;font-size:2.5rem;letter-spacing:.2em;text-transform:uppercase;
  font-weight:600}}
.kick{{color:var(--accent-on-light);max-width:70%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.num{{font-family:var(--hf);letter-spacing:.05em}}
.rule{{height:.3rem;background:currentColor;opacity:.85;flex:none}}
.body{{flex:1;display:flex;flex-direction:{'row' if wide else 'column'};gap:4rem;min-height:0;align-items:{'center' if wide else 'stretch'}}}
.copy{{display:flex;flex-direction:column;gap:2.6rem;{'flex:1.2' if wide else ''}}}
.hl{{font-size:{hsize}rem;line-height:1.02;letter-spacing:-.02em;max-height:{'30rem' if wide else '40rem'};color:var(--primary-on-light)}}
.ital{{font-style:italic;font-size:{3.3 if wide else 4}rem;line-height:1.35;max-height:{'12rem' if wide else '16rem'}}}
.inset{{flex:1;min-height:{'0' if wide else '24rem'};{'height:100%' if wide else ''};border-radius:3rem;background-size:cover;
  background-position:center;box-shadow:0 2rem 4rem rgba(0,0,0,.12)}}
.medallion{{flex:1;display:flex;align-items:center;justify-content:center;min-height:20rem}}
.medallion:before{{content:"";position:absolute;width:{44 if not wide else 26}rem;height:{44 if not wide else 26}rem;border-radius:50%;
  background:var(--accent-on-light);opacity:.12}}
.mic{{font-size:{30 if not wide else 18}rem;color:var(--accent-on-light);position:relative}}
.emoji.mic{{font-size:{26 if not wide else 15}rem}}
.bottom{{display:flex;justify-content:space-between;align-items:center;gap:3rem}}
.bottom .logo-wrap .logo{{max-height:7.5rem}}
.wordmark{{font-size:3.6rem;color:var(--primary-on-light)}}
.link{{font-weight:700;font-size:3.4rem;color:var(--primary-on-light);border-bottom:.45rem solid var(--accent-on-light);padding-bottom:.6rem;
  white-space:nowrap;max-height:7rem;max-width:60%}}
"""
    return body, css


# 5. Grain gradient with a glass card -------------------------------------------------------------------
def gradient(ctx):
    c, k, pal = ctx["content"], ctx["kind"], ctx["pal"]
    wide = k == "wide"
    base = colors.mix(pal["primary"], "#000000", .35)
    text = "#ffffff" if colors.luminance(base) < .35 else "#111111"
    hsize = (11 if ctx["type"]["condensed"] else 9) * (.66 if wide else 1)
    body = f"""
<div class="mesh"></div><div class="grain"></div>
<div class="frame">
  <div class="top">{logo(ctx, "dark" if text == '#ffffff' else "light")}{icon(ctx, "ic")}</div>
  <div class="glass">{eyebrow(ctx)}{hl(ctx, c.get('headline'), min_px=30, floor=54)}{sub(c.get('subhead'))}{bullets(ctx)}
    <div class="row">{cta(ctx)}</div></div>
  {footer(ctx)}
</div>{badge(ctx)}"""
    css = COMMON + f"""
.mesh{{position:absolute;inset:-10%;background:
  radial-gradient(45% 40% at 18% 22%, {pal['accent']} 0%, transparent 70%),
  radial-gradient(50% 45% at 85% 30%, {pal['secondary']} 0%, transparent 72%),
  radial-gradient(60% 55% at 70% 88%, {pal['primary']} 0%, transparent 75%),
  radial-gradient(55% 50% at 12% 85%, {colors.mix(pal['accent'], pal['secondary'], .5)} 0%, transparent 70%),
  {base};filter:blur(2rem) saturate(1.08)}}
.grain{{position:absolute;inset:0;background-image:url("{NOISE}");opacity:.22;mix-blend-mode:overlay}}
.frame{{position:absolute;inset:0;padding:{pad(ctx)};display:flex;flex-direction:column;justify-content:space-between;gap:3rem;color:{text}}}
.top{{display:flex;justify-content:space-between;align-items:center}}
.ic{{font-size:9rem;opacity:.9}}
.glass{{background:rgba(255,255,255,{'.14' if text == '#ffffff' else '.42'});border:.25rem solid rgba(255,255,255,.35);
  border-radius:4.5rem;padding:{'4.5rem 5rem' if wide else '6rem 6rem'};backdrop-filter:blur(2.4rem);display:flex;flex-direction:column;
  gap:2.6rem;box-shadow:0 3rem 8rem rgba(0,0,0,.18);{'max-width:72%' if wide else ''}}}
.eyebrow{{font-weight:700;font-size:2.5rem;letter-spacing:.16em;text-transform:uppercase;opacity:.9;white-space:nowrap}}
.hl{{font-size:{hsize}rem;max-height:{'28rem' if wide else '42rem'}}}
.sub{{font-size:{3.2 if wide else 3.9}rem;line-height:1.34;max-height:{'11rem' if wide else '16rem'};opacity:.95}}
.row{{display:flex}}
.cta{{background:{text};color:{'#111111' if text == '#ffffff' else '#ffffff'}}}
.foot{{text-align:center}}
.badge{{position:absolute;right:6rem;top:{'26rem' if k=='tall' else '19rem'};background:var(--accent);color:var(--on-accent);
  border-radius:99rem;padding:1.6rem 3rem;font-weight:800;font-size:3.2rem;transform:rotate(6deg);max-width:44rem}}
.badge span{{display:block;max-height:8rem}}
"""
    return body, css


# 6. Neo-brutalism ------------------------------------------------------------------------------------
def brutal(ctx):
    c, k, pal = ctx["content"], ctx["kind"], ctx["pal"]
    wide = k == "wide"
    paper = colors.mix(pal["accent"], "#ffffff", .82)
    hsize = (11.5 if ctx["type"]["condensed"] else 9) * (.66 if wide else 1)
    subbox = ('<div class="box subbox">' + sub(c.get("subhead")) + bullets(ctx) + "</div>"
              if c.get("subhead") or c.get("bullets") else "")
    if c.get("badge"):
        sticker = '<div class="sticker"><span data-fit data-role="badge" data-min="12">' + e(c["badge"]) + "</span></div>"
    elif c.get("icon"):
        sticker = '<div class="sticker ic">' + icon(ctx, "sic") + "</div>"
    else:
        sticker = ""
    body = f"""
<div class="paper"></div>
<div class="frame">
  <div class="top"><div class="box lg">{logo(ctx, "light")}</div>{eyebrow(ctx, "eyebrow box")}</div>
  <div class="box head">{hl(ctx, c.get("headline"), min_px=30, floor=54)}</div>
  {subbox}
  <div class="bottom">{cta(ctx, "cta box")}{footer(ctx)}</div>
</div>
{sticker}"""
    css = COMMON + f"""
.paper{{position:absolute;inset:0;background:{paper};background-image:radial-gradient(rgba(0,0,0,.13) .25rem, transparent .3rem);
  background-size:4rem 4rem}}
.frame{{position:absolute;inset:0;padding:{pad(ctx)};display:flex;flex-direction:column;justify-content:{'center' if wide else 'space-between'};
  gap:{'2.4rem' if wide else '3.6rem'};color:#111}}
.box{{background:#fff;border:.6rem solid #111;border-radius:2rem;box-shadow:1.4rem 1.4rem 0 #111}}
.top{{display:flex;justify-content:space-between;align-items:center;gap:3rem}}
.lg{{padding:1.6rem 2.6rem;display:inline-flex}}
.lg .logo-wrap.chip{{box-shadow:none;padding:0;background:transparent}}
.eyebrow{{font-weight:800;font-size:2.7rem;letter-spacing:.1em;text-transform:uppercase;padding:1.4rem 2.6rem;background:var(--accent);
  color:var(--on-accent);white-space:nowrap;max-width:50rem}}
.head{{background:var(--primary);color:var(--on-primary);padding:{'3.5rem 4rem' if wide else '5rem 5.5rem'};transform:rotate(-1.2deg);
  {'max-width:78%' if wide else ''}{';padding-right:27rem' if (c.get('badge') or c.get('icon')) and not wide else ''}}}
.hl{{font-size:{hsize}rem;max-height:{'24rem' if wide else '40rem'}}}
.subbox{{padding:{'2.8rem 3.6rem' if wide else '4rem 4.5rem'};transform:rotate(.8deg);{'max-width:70%' if wide else ''}}}
.sub{{font-size:{3.2 if wide else 3.9}rem;line-height:1.32;font-weight:600;max-height:{'10rem' if wide else '16rem'}}}
.bottom{{display:flex;align-items:center;justify-content:space-between;gap:3rem}}
.cta.box{{background:#111;color:#fff;border-radius:2rem;box-shadow:1.2rem 1.2rem 0 var(--accent)}}
.foot{{font-weight:700}}
.sticker{{position:absolute;right:{'5rem' if wide else '6rem'};top:{'23rem' if k=='tall' else ('5rem' if wide else '27rem')};width:24rem;height:24rem;
  border-radius:50%;background:var(--accent);color:var(--on-accent);border:.6rem solid #111;box-shadow:1rem 1rem 0 #111;
  display:flex;align-items:center;justify-content:center;text-align:center;transform:rotate(12deg);font-weight:900;
  font-size:4rem;line-height:1;padding:3rem;font-family:var(--hf)}}
.sticker span{{display:block;max-height:16rem}}
.sic{{font-size:12rem}}
"""
    return body, css


# 7. Duotone photo ------------------------------------------------------------------------------------
def duotone(ctx):
    if not ctx["photo_uri"]:
        return bold(ctx)
    c, k = ctx["content"], ctx["kind"]
    wide = k == "wide"
    pal = ctx["pal"]
    dark = colors.mix(pal["primary"], "#000000", .45)
    hsize = (13 if ctx["type"]["condensed"] else 10.5) * (.66 if wide else 1)
    body = f"""
<div class="ph" style="background-image:url('{ctx['photo_uri']}')"></div><div class="t1"></div><div class="t2"></div>
<div class="grain"></div>
<div class="frame">
  <div class="top">{logo(ctx, "dark")}{eyebrow(ctx)}</div>
  <div class="txt">{hl(ctx, c.get('headline'), min_px=32, floor=58)}{sub(c.get('subhead'))}</div>
  <div class="row">{cta(ctx)}{footer(ctx)}</div>
</div>{badge(ctx)}"""
    css = COMMON + f"""
.ph{{position:absolute;inset:0;background-size:cover;background-position:center;filter:grayscale(1) contrast(1.15) brightness(1.05)}}
.t1{{position:absolute;inset:0;background:{dark};mix-blend-mode:multiply}}
.t2{{position:absolute;inset:0;background:{pal['accent']};mix-blend-mode:screen;opacity:.42}}
.grain{{position:absolute;inset:0;background-image:url("{NOISE}");opacity:.18;mix-blend-mode:overlay}}
.frame{{position:absolute;inset:0;padding:{pad(ctx)};display:flex;flex-direction:column;justify-content:space-between;color:#fff}}
.top{{display:flex;justify-content:space-between;align-items:center;gap:3rem}}
.eyebrow{{font-weight:700;font-size:2.6rem;letter-spacing:.16em;text-transform:uppercase;white-space:nowrap;max-width:50rem}}
.txt{{display:flex;flex-direction:column;gap:2.6rem;{'max-width:74%' if wide else ''}}}
.hl{{font-size:{hsize}rem;max-height:{'30rem' if wide else '50rem'};text-shadow:0 .5rem 3rem rgba(0,0,0,.3)}}
.sub{{font-size:{3.3 if wide else 4}rem;line-height:1.32;max-height:{'11rem' if wide else '16rem'}}}
.row{{display:flex;align-items:center;justify-content:space-between;gap:3rem}}
.cta{{background:#fff;color:#111}}
.badge{{position:absolute;right:6rem;top:{'26rem' if k=='tall' else '20rem'};width:21rem;height:21rem;border-radius:50%;
  border:.5rem solid #fff;color:#fff;display:flex;align-items:center;justify-content:center;text-align:center;
  font-family:var(--hf);font-weight:var(--hw);font-size:3.8rem;line-height:1;padding:3rem;transform:rotate(-8deg)}}
.badge span{{display:block;max-height:14rem}}
"""
    return body, css


# 8. Swiss minimal ------------------------------------------------------------------------------------
def minimal(ctx):
    c, k = ctx["content"], ctx["kind"]
    wide = k == "wide"
    big = c.get("big") or ""
    big_icon = icon(ctx, "bi") or '<span class="ms bi">north_east</span>'
    hero = (f'<div class="big" data-fit data-role="big" data-min="40">{e(big)}</div>' if big
            else f'<div class="bigicon">{big_icon}</div>')
    hsize = (8 if ctx["type"]["condensed"] else 6.6) * (.8 if wide else 1)
    body = f"""
<div class="paper"></div><div class="grid"></div>
<div class="frame">
  <div class="top">{logo(ctx, "light")}<span class="meta">{e(c.get('eyebrow') or '')}</span></div>
  {hero}
  <div class="txt">{hl(ctx, c.get('headline'), min_px=26, floor=44)}{sub(c.get('subhead'))}
    <div class="row">{cta(ctx, 'arrow')}{footer(ctx)}</div></div>
</div>"""
    css = COMMON + f"""
.paper{{position:absolute;inset:0;background:var(--light)}}
.grid{{position:absolute;inset:0;background-image:linear-gradient(to right, rgba(0,0,0,.07) .2rem, transparent .2rem);
  background-size:{'20%' if not wide else '12.5%'} 100%}}
.frame{{position:absolute;inset:0;padding:{pad(ctx)};display:flex;flex-direction:column;justify-content:space-between;
  color:var(--on-light);gap:3rem}}
.top{{display:flex;justify-content:space-between;align-items:center;gap:3rem}}
.top .logo-wrap .logo{{max-height:7rem}}
.wordmark{{font-size:3.4rem;color:var(--primary-on-light)}}
.meta{{font-size:2.5rem;letter-spacing:.18em;text-transform:uppercase;font-weight:700;color:var(--accent-on-light);white-space:nowrap}}
.big{{font-family:var(--hf);font-weight:var(--hw);font-size:{42 if not wide else 26}rem;line-height:.8;letter-spacing:-.05em;
  color:var(--accent-on-light);max-height:{'48rem' if not wide else '26rem'};white-space:nowrap}}
.bigicon{{display:flex;align-items:center}}
.bi{{font-size:{34 if not wide else 22}rem;color:var(--accent-on-light)}}
.emoji.bi{{font-size:{26 if not wide else 18}rem}}
.txt{{display:flex;flex-direction:column;gap:2.2rem;max-width:{'70%' if wide else '92%'}}}
.hl{{font-size:{hsize}rem;line-height:1;letter-spacing:-.025em;max-height:{'20rem' if wide else '28rem'};color:var(--primary-on-light)}}
.sub{{font-size:{3 if wide else 3.5}rem;line-height:1.38;max-height:{'9rem' if wide else '15rem'};opacity:.85}}
.row{{display:flex;align-items:center;justify-content:space-between;gap:3rem}}
.arrow{{font-weight:800;font-size:3.2rem;color:var(--primary-on-light);white-space:nowrap;max-height:6rem}}
.arrow:after{{content:" →";color:var(--accent-on-light)}}
"""
    return body, css


# 9. Retro sunburst -----------------------------------------------------------------------------------
def retro(ctx):
    c, k, pal = ctx["content"], ctx["kind"], ctx["pal"]
    wide = k == "wide"
    bg = colors.mix(pal["secondary"], "#fff4e0", .55)
    ink = colors.readable(pal["primary"], bg, 4.5)
    hsize = (12 if ctx["type"]["condensed"] else 9.8) * (.66 if wide else 1)
    body = f"""
<div class="sky"></div><div class="rays"></div><div class="sun"></div><div class="grain"></div>
<div class="frame">
  <div class="top">{logo(ctx, "light")}{badge(ctx)}</div>
  <div class="txt">{eyebrow(ctx)}{hl(ctx, c.get('headline'), min_px=30, floor=54)}{sub(c.get('subhead'))}</div>
  <div class="row">{cta(ctx)}{footer(ctx)}</div>
</div>"""
    css = COMMON + f"""
.sky{{position:absolute;inset:0;background:{bg}}}
.rays{{position:absolute;left:50%;top:{'100%' if not wide else '130%'};width:280rem;height:280rem;transform:translate(-50%,-50%);
  background:repeating-conic-gradient(from 0deg, {colors.mix(pal['accent'], bg, .72)} 0deg 7deg, transparent 7deg 14deg);opacity:.6;
  border-radius:50%}}
.sun{{position:absolute;left:50%;top:{'100%' if not wide else '130%'};width:{78 if not wide else 70}rem;height:{78 if not wide else 70}rem;
  transform:translate(-50%,-50%);border-radius:50%;background:{colors.mix(pal['accent'], bg, .25)}}}
.grain{{position:absolute;inset:0;background-image:url("{NOISE}");opacity:.16;mix-blend-mode:multiply}}
.frame{{position:absolute;inset:0;padding:{pad(ctx)};display:flex;flex-direction:column;justify-content:space-between;color:{ink};
  text-align:{'left' if wide else 'center'};align-items:{'flex-start' if wide else 'center'}}}
.top{{display:flex;justify-content:space-between;align-items:center;width:100%}}
.txt{{display:flex;flex-direction:column;gap:2.4rem;align-items:{'flex-start' if wide else 'center'};{'max-width:70%' if wide else ''};
  margin-bottom:{'0' if wide else '14rem'}}}
.eyebrow{{font-weight:800;font-size:2.6rem;letter-spacing:.2em;text-transform:uppercase;white-space:nowrap}}
.hl{{font-size:{hsize}rem;max-height:{'28rem' if wide else '44rem'};color:{ink};text-shadow:.7rem .7rem 0 {colors.mix(pal['accent'], bg, .1)}}}
.sub{{font-size:{3.2 if wide else 3.9}rem;line-height:1.32;max-height:{'10rem' if wide else '15rem'};font-weight:600;max-width:84rem}}
.row{{display:flex;align-items:center;gap:3rem;justify-content:{'space-between' if wide else 'center'};flex-direction:{'row' if wide else 'column'}}}
.cta{{background:{ink};color:{colors.text_on(ink)};border:.5rem solid {ink}}}
.badge{{width:20rem;height:20rem;border-radius:50%;background:{ink};color:{colors.text_on(ink)};display:flex;align-items:center;
  justify-content:center;text-align:center;font-family:var(--hf);font-weight:var(--hw);font-size:3.8rem;line-height:1;padding:3rem;
  transform:rotate(-10deg)}}
.badge span{{display:block;max-height:13rem}}
"""
    return body, css


# Photo-led layouts for samples and clients' posts: the picture does the talking, the words stay short -----
def _mark(ctx):
    """The logo for a brand-color band."""
    return logo(ctx, "dark" if colors.luminance(ctx["pal"]["primary"]) < .4 else "light")


BAND_CSS = """
.mat{{position:absolute;inset:0;background:var(--primary)}}
.pic,.cell{{position:relative;overflow:hidden;background:var(--dark)}}
.ph{{position:absolute;inset:0;background-size:cover;background-position:center}}
.band{{position:absolute;bottom:0;display:flex;align-items:flex-end;justify-content:space-between;gap:4rem;color:var(--on-primary)}}
.words{{display:flex;flex-direction:column;gap:1.8rem;min-width:0;flex:1}}
.hl{{color:var(--on-primary)}}
.sub{{font-size:3.4rem;line-height:1.3;opacity:.9}}
.mark{{flex:none;max-width:26rem;display:flex;justify-content:flex-end}}
.mark .logo-wrap .logo{{max-height:8rem;max-width:24rem}}
.mark .logo-wrap.chip{{padding:1.2rem 1.8rem;border-radius:1.6rem}}
.mark .wordmark{{font-size:3.2rem;text-align:right;color:var(--on-primary)}}
.badge{{position:absolute;background:var(--accent);color:var(--on-accent);border-radius:99rem;padding:1.6rem 3rem;
  font-weight:800;font-size:3.2rem;line-height:1.1;max-width:44rem;box-shadow:0 .8rem 2.4rem rgba(0,0,0,.2)}}
.badge span{{display:block;max-height:8rem}}
"""


# 10. Framed: the photo inset on a brand-color mat, the words beneath it, like a printed card -------------
def frame(ctx):
    if not ctx["photo_uri"]:
        return bold(ctx)
    c, k = ctx["content"], ctx["kind"]
    if k == "wide":
        return split(ctx)
    tall, square = k == "tall", k == "square"
    m = 5.5                                                     # the mat around the photo, in rem
    top = 12 if tall else m
    ph_h = 100 if tall else (58 if square else 79)
    hsize = (9 if ctx["type"]["condensed"] else 7.6) * (.9 if square else 1)
    body = f"""
<div class="mat"></div>
<div class="pic" style="position:absolute;left:{m}rem;right:{m}rem;top:{top}rem;height:{ph_h}rem;border-radius:1.6rem">
  <div class="ph" style="background-image:url('{ctx['photo_uri']}')"></div></div>
<div class="frame band" style="left:{m + .5}rem;right:{m + .5}rem;top:{top + ph_h}rem">
  <div class="words">{hl(ctx, c.get('headline'), min_px=28, floor=50)}{sub(c.get('subhead'))}</div>
  <div class="mark">{_mark(ctx)}</div>
</div>{badge(ctx)}"""
    css = COMMON + BAND_CSS.format() + f"""
.band{{padding:{'4.5rem 0 17rem' if tall else '3.8rem 0 5.5rem'}}}
.hl{{font-size:{hsize}rem;max-height:{'30rem' if tall else '19rem'}}}
.sub{{max-height:{'13rem' if tall else '9rem'}}}
.badge{{right:{m + 3}rem;top:{top + 3}rem;transform:rotate(-3deg)}}
"""
    return body, css


# 11. Collage: two or three of their photos edge to edge, the words on a brand-color band ------------------
def collage(ctx):
    uris = [u for u in ctx.get("photo_uris") or [] if u]
    if len(uris) < 2:
        return frame(ctx)
    c, k = ctx["content"], ctx["kind"]
    if k == "wide":
        return split(ctx)
    tall, square = k == "tall", k == "square"
    three = len(uris) >= 3
    grid_h = 112 if tall else (62 if square else 83)
    cells = "".join(f'<div class="cell{" big" if i == 0 else ""}"><div class="ph" style="background-image:url(\'{u}\')"></div></div>'
                    for i, u in enumerate(uris[:3]))
    hsize = (8.6 if ctx["type"]["condensed"] else 7.2) * (.9 if square else 1)
    body = f"""
<div class="mat"></div>
<div class="grid" style="height:{grid_h}rem">{cells}</div>
<div class="frame band" style="left:6rem;right:6rem;top:{grid_h}rem">
  <div class="words">{hl(ctx, c.get('headline'), min_px=28, floor=48)}{sub(c.get('subhead'))}</div>
  <div class="mark">{_mark(ctx)}</div>
</div>{badge(ctx)}"""
    css = COMMON + BAND_CSS.format() + f"""
.grid{{position:absolute;left:0;right:0;top:0;display:grid;gap:1.1rem;
  grid-template-columns:{'1.3fr 1fr' if three else '1fr 1fr'};grid-template-rows:{'1fr 1fr' if three else '1fr'}}}
.cell.big{{grid-row:{'1 / span 2' if three else 'auto'}}}
.band{{padding:{'4rem 0 17rem' if tall else '3.6rem 0 5.5rem'}}}
.hl{{font-size:{hsize}rem;max-height:{'30rem' if tall else '18rem'}}}
.sub{{max-height:{'13rem' if tall else '8.5rem'}}}
.badge{{right:4rem;top:{'15rem' if tall else '4rem'};transform:rotate(-3deg)}}
"""
    return body, css


# 12. Cover: a full-bleed photo with the headline set large at the top, like a magazine cover --------------
def cover(ctx):
    if not ctx["photo_uri"]:
        return gradient(ctx)
    c, k = ctx["content"], ctx["kind"]
    if k == "wide":
        return photo(ctx)
    hsize = (12.5 if ctx["type"]["condensed"] else 10.5) * (.86 if k == "square" else 1)
    body = f"""
<div class="ph" style="background-image:url('{ctx['photo_uri']}')"></div><div class="scrim"></div>
<div class="frame">
  <div class="txt">{hl(ctx, c.get('headline'), min_px=32, floor=58)}{sub(c.get('subhead'))}</div>
  <div class="row">{logo(ctx, "photo")}{badge(ctx)}</div>
</div>"""
    css = COMMON + f"""
.ph{{position:absolute;inset:0;background-size:cover;background-position:center}}
.scrim{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,{_shade(ctx.get('photo_tone_top', .5)):.2f}) 0%,
  rgba(0,0,0,{_shade(ctx.get('photo_tone_top', .5)) * .6:.2f}) 30%,rgba(0,0,0,0) 54%,rgba(0,0,0,0) 72%,
  rgba(0,0,0,{_shade(ctx.get('photo_tone_bottom', .5)) * .6:.2f}) 100%)}}
.frame{{position:absolute;inset:0;padding:{pad(ctx)};display:flex;flex-direction:column;justify-content:space-between;color:#fff}}
.txt{{display:flex;flex-direction:column;gap:2.4rem;max-width:92%}}
.hl{{font-size:{hsize}rem;max-height:{'50rem' if k=='tall' else '40rem'};text-shadow:0 .4rem 3rem rgba(0,0,0,.3)}}
.sub{{font-size:3.8rem;line-height:1.3;max-height:15rem;max-width:80rem;text-shadow:0 .2rem 1.6rem rgba(0,0,0,.4)}}
.row{{display:flex;justify-content:space-between;align-items:flex-end;gap:3rem}}
.badge{{background:var(--accent);color:var(--on-accent);border-radius:99rem;padding:1.6rem 3rem;font-weight:800;font-size:3.2rem;
  line-height:1.1;max-width:44rem}}
.badge span{{display:block;max-height:8rem}}
"""
    return body, css


STYLES = {"bold": bold, "photo": photo, "split": split, "editorial": editorial, "gradient": gradient,
          "brutal": brutal, "duotone": duotone, "minimal": minimal, "retro": retro, "frame": frame, "collage": collage,
          "cover": cover}
NEEDS_PHOTO = {"photo", "split", "duotone", "frame", "collage", "cover"}
