"""The design engine: brand-styled designs written as HTML/CSS and rendered to PNG (or PDF) by a headless
browser. Text is fitted to its box automatically, then checked: nothing may overflow or get too small to read.

A design spec is a dict:
  format   post (1080x1350), square, story (1080x1920), landscape (1200x630), gbp (1200x900), flyer (Letter)
  style    one of styles.STYLES (bold, photo, split, editorial, gradient, brutal, duotone, minimal, retro, frame,
           collage, cover)
  brand    the brand kit (colors, fonts, logo, name, photos...)
  content  eyebrow, headline, subhead, cta, badge, footer, icon (a Material Symbol name or an emoji)
  photo    path to a photo, or None
  photos   for a collage: the photo first, then up to two more
"""
import base64
import io
import json
import mimetypes
import os
import pathlib
import re

from . import colors, fonts, styles

FORMATS = {
    "post": (1080, 1350), "square": (1080, 1080), "story": (1080, 1920), "landscape": (1200, 630),
    "gbp": (1200, 900), "flyer": (1275, 1650), "cover": (1640, 624),
}
PRINT = {"flyer": ("8.5in", "11in")}

FIT_JS = """
() => {
  // Tight line-heights let glyphs poke a little past their line boxes; that isn't overflow.
  const over = (el) => {
    const size = parseFloat(getComputedStyle(el).fontSize);
    return el.scrollHeight > el.clientHeight + Math.max(2, size * 0.3) || el.scrollWidth > el.clientWidth + 2;
  };
  const issues = [];
  const fits = [...document.querySelectorAll('[data-fit]')];
  for (const el of fits) {
    let size = parseFloat(getComputedStyle(el).fontSize);
    const min = parseFloat(el.dataset.min || '10');
    let guard = 0;
    while (over(el) && size > min && guard < 120) {
      size = Math.max(min, size * 0.96);
      el.style.fontSize = size + 'px';
      guard++;
    }
  }
  // Then make whole layouts fit: if a frame's content runs past its edges, shrink all its text together.
  for (const fr of document.querySelectorAll('.frame, .panel')) {
    let guard = 0;
    while ((fr.scrollHeight > fr.clientHeight + 2 || fr.scrollWidth > fr.clientWidth + 2) && guard < 40) {
      let changed = false;
      for (const el of fr.querySelectorAll('[data-fit]')) {
        const size = parseFloat(getComputedStyle(el).fontSize), min = parseFloat(el.dataset.min || '10');
        if (size > min) { el.style.fontSize = Math.max(min, size * 0.95) + 'px'; changed = true; }
      }
      if (!changed) break;
      guard++;
    }
    if (fr.scrollHeight > fr.clientHeight + 2) issues.push('crowded:' + fr.className);
  }
  const canvas = document.querySelector('.canvas').getBoundingClientRect();
  for (const el of fits) {
    const r = el.getBoundingClientRect();
    if (over(el)) issues.push('overflow:' + (el.dataset.role || el.className));
    const size = parseFloat(getComputedStyle(el).fontSize), floor = parseFloat(el.dataset.floor || '0');
    if (floor && size < floor) issues.push('small:' + (el.dataset.role || el.className));
    if (r.width && (r.left < canvas.left - 1 || r.right > canvas.right + 1 || r.top < canvas.top - 1 || r.bottom > canvas.bottom + 1))
      issues.push('outside:' + (el.dataset.role || el.className));
  }
  return issues;
}
"""


IMAGES_JS = """
() => {
  const out = [];
  for (const img of document.images) {
    const src = img.currentSrc || img.src;
    if (src && !src.startsWith('data:') && img.naturalWidth >= 500 && img.naturalHeight >= 360) out.push(src);
  }
  for (const el of document.querySelectorAll('div,section,figure,a,span,li,header')) {
    const r = el.getBoundingClientRect();
    if (r.width < 400 || r.height < 300) continue;
    const m = (getComputedStyle(el).backgroundImage || '').match(/url\\(["']?([^"')]+)["']?\\)/);
    if (m && !m[1].startsWith('data:')) out.push(m[1]);
  }
  return [...new Set(out)].slice(0, 60);
}
"""


def data_uri(path, max_side=1600, quality=84):
    """A file as a data: URI. Photos are shrunk first so designs stay light."""
    path = pathlib.Path(path)
    if path.suffix.lower() == ".svg":
        return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode()
    from PIL import Image
    try:
        with Image.open(path) as im:
            im.load()
            has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
            im = im.convert("RGBA" if has_alpha else "RGB")
            im.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            if has_alpha:
                im.save(buf, "PNG", optimize=True)
                kind = "image/png"
            else:
                im.save(buf, "JPEG", quality=quality, optimize=True)
                kind = "image/jpeg"
    except Exception:
        kind = mimetypes.guess_type(str(path))[0] or "image/png"
        return f"data:{kind};base64," + base64.b64encode(path.read_bytes()).decode()
    return f"data:{kind};base64," + base64.b64encode(buf.getvalue()).decode()


def photo_tone(path, aspect=None, band=None):
    """Average brightness (0-1) of a photo, to pick text colors and scrims. aspect (width / height of the
    design) looks only at the part a cover crop shows; band (top, bottom as shares of it) at a strip of that."""
    from PIL import Image
    try:
        with Image.open(path) as im:
            im = im.convert("L")
            w, h = im.size
            if aspect:
                if w / h > aspect:
                    cut = (w - h * aspect) / 2
                    im = im.crop((int(cut), 0, int(w - cut), h))
                else:
                    cut = (h - w / aspect) / 2
                    im = im.crop((0, int(cut), w, int(h - cut)))
            if band:
                ww, hh = im.size
                im = im.crop((0, int(band[0] * hh), ww, max(int(band[0] * hh) + 1, int(band[1] * hh))))
            px = list(im.resize((32, 32)).getdata())
    except Exception:
        return 0.5
    return sum(px) / len(px) / 255


def palette_of(brand):
    pal = dict(brand.get("colors") or colors.palette([]))
    for role in ("primary", "secondary", "accent", "dark", "light"):
        pal[role] = colors.hexify(pal.get(role)) or {"primary": "#1f3a5f", "secondary": "#c08a3f", "accent": "#e4572e",
                                                       "dark": "#111111", "light": "#fafafa"}[role]
    for role in ("primary", "secondary", "accent", "dark", "light"):
        pal["on_" + role] = colors.text_on(pal[role])
    # an accent that stays readable on the primary and on the light background
    pal["accent_on_primary"] = pal["accent"] if colors.contrast(pal["accent"], pal["primary"]) >= 2.2 else (
        pal["light"] if colors.contrast(pal["light"], pal["primary"]) >= 3 else pal["on_primary"])
    pal["accent_on_light"] = colors.readable(pal["accent"], pal["light"], 3)
    pal["primary_on_light"] = colors.readable(pal["primary"], pal["light"], 4.5)
    return pal


def type_of(brand, style):
    """Heading and body fonts for this design, and how the heading is set."""
    f = brand.get("fonts") or {}
    heading = fonts.find(f.get("heading")) or "Bricolage Grotesque"
    body = fonts.find(f.get("body")) or "Inter"
    if style == "editorial" and not fonts.is_serif(heading) and not f.get("from_site"):
        heading = "DM Serif Display"
    upper = fonts.is_condensed(heading) or style in ("bold", "brutal") and not fonts.is_serif(heading)
    return {"heading": heading, "body": body, "hw": fonts.best_weight(heading, 800), "bw": fonts.best_weight(body, 500),
            "upper": upper, "condensed": fonts.is_condensed(heading), "serif": fonts.is_serif(heading)}


def build(spec):
    """The full HTML page for a design spec."""
    fmt = spec.get("format", "post")
    w, h = FORMATS[fmt]
    brand, content = spec.get("brand") or {}, dict(spec.get("content") or {})
    from .social import plain_dashes
    content = {k: ([plain_dashes(x) for x in v] if isinstance(v, list) else plain_dashes(v) if isinstance(v, str) else v)
               for k, v in content.items()}
    style = spec.get("style") or "bold"
    if style not in styles.STYLES:
        style = "bold"
    pal = palette_of(brand)
    typ = type_of(brand, style)
    logo = brand.get("logo") or None
    ctx = {
        "w": w, "h": h, "fmt": fmt, "kind": "tall" if h / w > 1.5 else "wide" if w / h > 1.4 else "portrait" if h > w else "square",
        "pal": pal, "type": typ, "brand": brand, "content": content, "seed": int(spec.get("seed", 0)),
        "logo_uri": data_uri(logo["path"], 600) if logo and logo.get("path") and os.path.exists(logo["path"]) else None,
        "logo_tone": (logo or {}).get("tone", "unknown"),
        "photo_uri": data_uri(spec["photo"]) if spec.get("photo") and os.path.exists(spec["photo"]) else None,
        "photo_tone": photo_tone(spec["photo"]) if spec.get("photo") and os.path.exists(spec["photo"]) else 0.5,
    }
    if ctx["photo_uri"]:                       # how light the parts under the words are, for the scrims
        ctx["photo_tone_top"] = photo_tone(spec["photo"], w / h, (0, .45))
        ctx["photo_tone_bottom"] = photo_tone(spec["photo"], w / h, (.55, 1))
    extra = [p for p in (spec.get("photos") or [])[1:3] if p and os.path.exists(p)]      # a collage's other photos
    ctx["photo_uris"] = ([ctx["photo_uri"]] if ctx["photo_uri"] else []) + [data_uri(p, 1100) for p in extra]
    body_html, css = styles.STYLES[style](ctx)
    font_link = fonts.css_url([typ["heading"], typ["body"]], icons=True)
    root = (f":root{{--w:{w}px;--h:{h}px;--primary:{pal['primary']};--secondary:{pal['secondary']};"
            f"--accent:{pal['accent']};--dark:{pal['dark']};--light:{pal['light']};--on-primary:{pal['on_primary']};"
            f"--on-secondary:{pal['on_secondary']};--on-accent:{pal['on_accent']};--on-dark:{pal['on_dark']};"
            f"--on-light:{pal['on_light']};--accent-on-primary:{pal['accent_on_primary']};"
            f"--accent-on-light:{pal['accent_on_light']};--primary-on-light:{pal['primary_on_light']};"
            f"--hf:'{typ['heading']}',{'serif' if typ['serif'] else 'sans-serif'};--bf:'{typ['body']}',sans-serif;"
            f"--hw:{typ['hw']};--bw:{typ['bw']}}}")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<link rel="stylesheet" href="{font_link}">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Color+Emoji&display=block">
<style>
{root}
html{{font-size:calc(var(--w) / 100)}}
html,body{{margin:0;padding:0;background:transparent}}
body{{width:var(--w);height:var(--h);overflow:hidden;font-family:var(--bf);font-weight:var(--bw);
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}}
*{{box-sizing:border-box}}
.canvas{{position:relative;width:var(--w);height:var(--h);overflow:hidden}}
.ms{{font-family:'Material Symbols Rounded';font-weight:normal;font-style:normal;line-height:1;letter-spacing:normal;
  text-transform:none;display:inline-block;white-space:nowrap;-webkit-font-feature-settings:'liga';font-feature-settings:'liga';
  font-variation-settings:'FILL' 1,'wght' 500,'GRAD' 0,'opsz' 48}}
.emoji{{font-family:'Noto Color Emoji',sans-serif;line-height:1}}
[data-fit]{{overflow:hidden}}
h1,h2,p{{margin:0}}
.hl{{font-family:var(--hf);font-weight:var(--hw);line-height:.98;letter-spacing:-.01em;text-wrap:balance;padding-bottom:.06em}}
.upper{{text-transform:uppercase;letter-spacing:.005em;line-height:.92}}
.sub{{text-wrap:pretty}}
{css}
</style></head><body><div class="canvas s-{style} f-{fmt}">{body_html}</div></body></html>"""


class Renderer:
    """A headless browser that turns design HTML into images. Use as a context manager."""

    def __init__(self):
        self._pw = self._browser = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        channel = os.environ.get("STUDIO_BROWSER_CHANNEL") or None     # "chrome" on GitHub's runners
        try:
            self._browser = self._pw.chromium.launch(channel=channel) if channel else self._pw.chromium.launch()
        except Exception:
            self._browser = self._pw.chromium.launch()
        return self

    def __exit__(self, *exc):
        try:
            self._browser.close()
        finally:
            self._pw.stop()

    def _page(self, w, h, html_text):
        page = self._browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        page.set_content(html_text, wait_until="networkidle", timeout=45000)
        page.evaluate("document.fonts.ready.then(() => true)")
        page.wait_for_timeout(150)
        return page

    def render(self, spec, out_path):
        """Render a spec to a PNG (and a PDF for print formats). Returns (path, issues)."""
        fmt = spec.get("format", "post")
        w, h = FORMATS[fmt]
        page = self._page(w, h, build(spec))
        try:
            issues = page.evaluate(FIT_JS)
            out_path = pathlib.Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out_path), clip={"x": 0, "y": 0, "width": w, "height": h}, type="png")
            if fmt in PRINT:
                pw, ph = PRINT[fmt]
                page.pdf(path=str(out_path.with_suffix(".pdf")), width=pw, height=ph, print_background=True,
                         page_ranges="1", scale=816 / w)
        finally:
            page.close()
        return out_path, issues

    def images_on(self, url, timeout=25000):
        """Big pictures a page shows once its scripts have run (site builders often load them late)."""
        page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            for _ in range(5):                                   # lazy pictures load as the page scrolls
                page.mouse.wheel(0, 1400)
                page.wait_for_timeout(400)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(600)
            return page.evaluate(IMAGES_JS)
        except Exception:
            return []
        finally:
            page.close()

    def screenshot(self, url, out_path, w=1280, h=800):
        page = self._browser.new_page(viewport={"width": w, "height": h})
        try:
            page.goto(url, wait_until="load", timeout=30000)
            page.wait_for_timeout(1200)
            page.screenshot(path=str(out_path), type="jpeg", quality=80)
            return out_path
        except Exception:
            return None
        finally:
            page.close()


def render_best(renderer, spec, out_path, styles_to_try=None):
    """Render the spec; if text overflows, shorten the supporting text, then try other styles.
    Returns (path, style used, issues left)."""
    tried = []
    for style in [spec.get("style")] + list(styles_to_try or []):
        if not style or style in tried:
            continue
        tried.append(style)
        s = dict(spec, style=style)
        path, issues = renderer.render(s, out_path)
        if not issues:
            return path, style, []
        content = dict(s.get("content") or {})
        if content.get("subhead") and len(content["subhead"]) > 60:
            content["subhead"] = shorten(content["subhead"], 60)
            path, issues = renderer.render(dict(s, content=content), out_path)
            if not issues:
                return path, style, []
    return path, tried[-1], issues


def shorten(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:-–—")
    return cut + "…"


def spec_json(spec):
    """The spec without the brand's long fields, for saving next to a design."""
    brand = {k: v for k, v in (spec.get("brand") or {}).items() if k in ("name", "colors", "fonts", "domain")}
    return json.dumps(dict(spec, brand=brand), indent=1, default=str)
