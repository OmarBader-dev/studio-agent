"""Menus, price lists and class schedules, in the brand: a Letter page to print (PDF) and a version to post.

The items come from the client's own words (their email or your Telegram message), or, when they only say
"our menu", from their website. Nothing is invented: every item has to appear in that text, and so does every
price. Typed lists ("Latte $4.50") are read directly, without AI.
"""
import html
import pathlib
import re

from . import ai, design, fonts

ASK = re.compile(r"\b(menus?|price ?lists?|prices|price sheet|service menu|list of services|class schedule|"
                 r"schedule of classes|timetable|class times)\b", re.I)
PRICE = r"(?:\$\s?\d+(?:[.,]\d{2})?(?:\s?[-–]\s?\$?\d+(?:[.,]\d{2})?)?\+?|\d{1,2}(?::\d{2})?\s?(?:am|pm|AM|PM))"
LINE = re.compile(r"^\s*[-*•·]?\s*(?P<name>[^$\n]{2,60}?)\s*(?:[.…·_\-–—:|]{1,}\s*|\s{2,}|\s)(?P<price>" + PRICE + r")"
                  r"\s*(?:[-–—:(]\s*(?P<note>[^)\n]{2,90})\)?)?\s*$")
HEADER = re.compile(r"^\s*(?P<name>[A-Za-z][A-Za-z &'/+-]{1,30}?)\s*:?\s*$")
NOT_HEADER = re.compile(r"\b(menu|price|list|schedule|here|please|our|attached|below|thanks?|hi|hello)\b", re.I)
# Lines on a website that look like "name $price" but aren't things they sell
JUNK = re.compile(r"\b(orders?|shipping|delivery|deliveries|minimum|tax|fees?|tips?|gift ?cards?|call|phone|hours|"
                  r"open|closed|save|off|coupon|deposit|cancellation|reward|points?)\b", re.I)
# What to redesign from a business's website for its free sample, by kind of business
LISTING = {"restaurant": "menu", "cafe": "menu", "bakery": "menu", "bar": "menu", "beauty": "price list",
           "gym": "class schedule"}


def wanted(request):
    """Whether a design request is for a menu, a price list or a schedule."""
    return bool(ASK.search(request or ""))


def kind_of(request):
    low = (request or "").lower()
    if re.search(r"schedule|timetable|class times", low):
        return "schedule"
    if re.search(r"price|service", low):
        return "prices"
    return "menu"


SECTION_WORDS = re.compile(r"(?:all day |late night |weekend )?(?:breakfast|brunch|lunch|dinner|supper|after dinner|"
                           r"desserts?|drinks|beverages|cocktails|starters|appetizers|small plates|shareables|mains|"
                           r"entr[eé]es|salads|soups|sandwiches|kids|specials|happy hour)(?: menu)?", re.I)
PRICE_ONLY = re.compile(r"^(?:(?:sale |regular |from )?price:?\s*)?(?P<price>" + PRICE + r")\s*$", re.I)


def _plausible(name):
    """Whether a line from a website could be the name of something they sell: short, starts with a capital or a
    number, no commas (a line with commas is a description: "pork belly, tamari, honey")."""
    name = (name or "").strip()
    return bool(2 <= len(name) <= 45 and len(name.split()) <= 6 and re.match(r"[A-Z0-9]", name)
                and re.search(r"[A-Za-z]{2}", name) and "," not in name and not JUNK.search(name)
                and not re.search(r"\b(today|selections?|season|add-?ons?|sides?|choice of|served with|see )\b", name, re.I)
                and not SECTION_WORDS.fullmatch(name.strip(" :"))
                and not re.fullmatch(r"(?:sale |regular )?price|quick view|add to cart|buy now|shop now|order now",
                                     name, re.I))


def parse_site(text):
    """Items in a website's text, where the price is on the same line ("Latte $4.50") or on the line under the
    name ("Latte" then "$4.50", or "Price $4.50"). One list, no headings (a website's headings are unreliable)."""
    items, pending, before, last_line = [], None, None, None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or len(line) > 160:
            continue
        only = PRICE_ONLY.match(line)
        if only:
            zero = re.fullmatch(r"\$\s?0+(?:[.,]0+)?", only.group("price"))
            if pending and not zero:
                items.append({"name": pending.strip(" .:-–"), "price": only.group("price").strip(), "note": ""})
            elif before and last_line and not zero and len(last_line) <= 90:
                # "Name" / "a description, with commas" / "$13": the name is two lines up
                items.append({"name": before.strip(" .:-–"), "price": only.group("price").strip(), "note": last_line})
            pending = before = last_line = None
            continue
        same = LINE.match(line)
        if same and _plausible(same.group("name").strip()) and not re.fullmatch(r"\$\s?0+(?:[.,]0+)?", same.group("price")):
            items.append({"name": same.group("name").strip(" .:-–"), "price": same.group("price").strip(),
                          "note": (same.group("note") or "").strip()})
            pending = None
            continue
        before = pending                                  # a name, then maybe its description, then the price
        pending, last_line = (line if _plausible(line) else None), line
    seen, unique = set(), []
    for it in items:                                   # the same item twice (a featured strip and the list)
        if it["name"].lower() not in seen:
            seen.add(it["name"].lower())
            unique.append(it)
    return [{"name": "", "items": unique}] if len(unique) >= 3 else None


def parse(text, strict=False):
    """Items typed as lines ("Latte $4.50", "Gel manicure - $35", "Spin 6:00 AM"), with headers between them.
    strict (text from a website): read it with parse_site instead."""
    if strict:
        return parse_site(text)
    sections, current = [], None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or len(line) > 160:                    # list lines are short; long ones are paragraphs
            continue
        m = LINE.match(line)
        if m:
            if current is None:
                current = {"name": "", "items": []}
                sections.append(current)
            current["items"].append({"name": m.group("name").strip(" .:-–"), "price": m.group("price").strip(),
                                     "note": (m.group("note") or "").strip()})
            continue
        h = HEADER.match(line)
        if h and len(line.split()) <= 4 and not NOT_HEADER.search(line):
            current = {"name": h.group("name").strip(), "items": []}
            sections.append(current)
    sections = [s for s in sections if s["items"]]
    return sections if sum(len(s["items"]) for s in sections) >= 3 else None


def _norm(text):
    return re.sub(r"[^a-z0-9$.:]", "", (text or "").lower())


def _ai_sections(cfg, store, kit, kind, request, source, website=False):
    """The list in source, copied by AI, then checked: an item, price or note that isn't in source is dropped.
    Returns (title or None, sections) or (None, None) without AI."""
    data = ai.ask(cfg, store, f"""Copy the {kind} below into JSON, exactly as written. Use only items that appear in
the TEXT, with their exact names and prices (or times). When one price is shown for a group of items, give each
item in the group that price. Never add an item, a price or a description.
BUSINESS: {kit.get('name')}
REQUEST: {request[:600]}
TEXT:
{source[:6000]}
Return JSON: {{"title": "a short title, like 'Fall menu'", "subtitle": "under 60 characters, or ''",
"sections": [{{"name": "section name or ''", "items": [{{"name": "...", "price": "as written, or ''",
"note": "a short description only if the text has one, else ''"}}]}}]}}""",
                  system="You copy lists exactly and never invent anything. JSON only.", max_tokens=2500,
                  temperature=0.1)
    if not isinstance(data, dict):
        return None, None
    src = _norm(source)
    sections = []
    for s in data.get("sections") or []:
        items = []
        for it in (s.get("items") if isinstance(s, dict) else None) or []:
            if not isinstance(it, dict) or not it.get("name") or _norm(it["name"])[:24] not in src:
                continue                                   # not in their text: never shown
            if website and not _plausible(str(it["name"])):
                continue                                   # gift cards, delivery fees... aren't on a menu
            price = str(it.get("price") or "")
            if re.fullmatch(r"\$\s?0+(?:[.,]0+)?", price.strip()):
                continue
            if price and _norm(price) not in src:
                price = ""
            note = str(it.get("note") or "")
            if note and _norm(note)[:20] not in src:
                note = ""
            items.append({"name": str(it["name"])[:60], "price": price[:16], "note": note[:90]})
        if items:
            sections.append({"name": str(s.get("name") or "")[:30] if _norm(s.get("name"))[:12] in src else "",
                             "items": items})
    return (str(data.get("title") or "")[:40] or None), sections


def _listing(kit, kind, title, sections, request=""):
    m = re.search(r"\b(fall|autumn|winter|spring|summer|holiday|brunch|lunch|dinner|happy hour|drinks?|dessert)\b",
                  request or "", re.I)
    if m and kind == "menu" and title == "Menu":
        title = f"{m.group(1).title()} menu"
    contact = " · ".join(x for x in (kit.get("address"), kit.get("phone"), kit.get("domain")) if x)
    return {"kind": kind, "title": title, "subtitle": "", "sections": sections, "footer": contact}


def _count(sections):
    return sum(len(s["items"]) for s in sections or [])


def extract(cfg, store, kit, request, site_text=None):
    """The list to design: {"kind", "title", "subtitle", "sections": [...], "footer"}, or None if there aren't
    at least three real items. From the client's own words first; when they only say "our menu", from their
    website (site_text, or the whole site)."""
    kind = kind_of(request)
    title = {"menu": "Menu", "prices": "Price list", "schedule": "Class schedule"}[kind]
    sections = parse(request)
    if not sections:
        own = len(re.findall(PRICE, request or "")) >= 3
        source = request if own else (site_text or kit.get("text") or "")
        ai_title, sections = _ai_sections(cfg, store, kit, kind, request, source, website=not own)
        if not own and _count(sections) < 6:               # their website: the AI's reading first (it's checked
            typed = parse_site(source)                     # word for word), the plain reading only when it's clean
            if _count(typed) >= 6:
                sections, ai_title = typed, None
        title = ai_title or title
    if _count(sections) < 3:
        return None
    name = (kit.get("name") or "").lower()
    if name and (title.lower() in name or name in title.lower()):
        title = {"menu": "Menu", "prices": "Price list", "schedule": "Class schedule"}[kind]   # the logo says who
    if len(sections) == 1 and sections[0]["name"] and kind != "schedule":
        title = f"{sections[0]['name'].title()} {'menu' if kind == 'menu' else 'prices'}"     # "Waxing prices"
        sections = [dict(sections[0], name="")]
    return _listing(kit, kind, title, sections, request)


def from_website(cfg, store, kit, niche):
    """The business's own menu (or price list, or class schedule) from its website, ready to design, or None.
    Only lists with at least 6 items, most of them priced (or timed), so a sample shows the real thing."""
    kind = LISTING.get(niche)
    if not kind:
        return None
    text = kit.get("text") or ""
    m = re.search(r"\n\n\[[^\]\n]+\]\n(.*)$", text, re.S)        # the menu/services page the brand reader added
    listing = extract(cfg, store, kit, f"our {kind}", site_text=m.group(1) if m else text)
    if not listing:
        return None
    items = [i for s in listing["sections"] for i in s["items"]]
    if len(items) < 6 or sum(1 for i in items if i.get("price")) < 0.8 * len(items):
        return None
    return listing


VARIANTS = ("paper", "dark", "brand")


def build(kit, menu, fmt="flyer", variant="paper"):
    w, h = design.FORMATS[fmt]
    pal = design.palette_of(kit)
    typ = design.type_of(kit, "editorial")
    bg, ink, head, price, rule = {
        "paper": (pal["light"], "#1d1d1f", pal["primary_on_light"], pal["accent_on_light"], pal["primary_on_light"]),
        "dark": ("#141414", "#f4f1ea", "#ffffff", pal["accent"] if design.colors.contrast(pal["accent"], "#141414") >= 3
                 else "#f4f1ea", "#f4f1ea"),
        "brand": (pal["primary"], pal["on_primary"], pal["on_primary"], pal["accent_on_primary"], pal["on_primary"]),
    }[variant]
    logo = kit.get("logo") or {}
    logo_html = ""
    if logo.get("path") and pathlib.Path(logo["path"]).exists():
        chip = (variant != "paper" and logo.get("tone") in ("dark", "mid", "unknown")) or \
            (variant == "paper" and logo.get("tone") == "light")
        logo_html = (f'<div class="lg{" chip" if chip else ""}{" chipdark" if variant == "paper" and chip else ""}">'
                     f'<img src="{design.data_uri(logo["path"], 600)}" alt=""></div>')
    else:
        logo_html = f'<div class="wm">{html.escape(kit.get("name") or "")}</div>'
    n_items = sum(len(s["items"]) for s in menu["sections"])
    cols = 1 if n_items <= (12 if fmt == "flyer" else 8) or fmt == "story" else 2
    secs = []
    for s in menu["sections"]:
        rows = "".join(
            f'<div class="it"><div class="row"><span class="nm">{html.escape(i["name"])}</span>'
            + (f'<span class="dots"></span><span class="pr">{html.escape(i["price"])}</span>' if i.get("price") else "")
            + '</div>'
            + (f'<div class="nt">{html.escape(i["note"])}</div>' if i.get("note") else "") + "</div>"
            for i in s["items"])
        heading = "<h2>" + html.escape(s["name"]) + "</h2>" if s.get("name") else ""
        secs.append(f'<section class="sec">{heading}{rows}</section>')
    link = fonts.css_url([typ["heading"], typ["body"]])
    return f"""<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="{link}"><style>
html{{font-size:{w / 100}px}}html,body{{margin:0;padding:0}}*{{box-sizing:border-box}}
body{{width:{w}px;height:{h}px;overflow:hidden;background:{bg};color:{ink};font-family:'{typ['body']}',sans-serif;
  font-weight:{typ['bw']};-webkit-font-smoothing:antialiased}}
.page{{position:absolute;inset:0;padding:{'7rem 8rem 6rem' if fmt == 'flyer' else '8rem 7rem 7rem'};display:flex;flex-direction:column}}
.page:before{{content:"";position:absolute;inset:2.6rem;border:.25rem solid {rule};opacity:.22;border-radius:1.4rem;pointer-events:none}}
header{{text-align:center;display:flex;flex-direction:column;align-items:center;gap:1.6rem;margin-bottom:4rem}}
.lg img{{max-height:{'9rem' if fmt == 'flyer' else '8rem'};max-width:34rem;display:block;object-fit:contain}}
.lg.chip{{background:#fff;padding:1.4rem 2rem;border-radius:1.6rem}}.lg.chipdark{{background:#161616}}
.wm{{font-family:'{typ['heading']}',serif;font-weight:{typ['hw']};font-size:4rem;color:{head}}}
h1{{margin:0;font-family:'{typ['heading']}',serif;font-weight:{typ['hw']};color:{head};font-size:{'8.4rem' if fmt == 'flyer' else '9rem'};
  line-height:1;letter-spacing:-.01em{';text-transform:uppercase' if typ['upper'] else ''}}}
.sub{{font-size:2.6rem;opacity:.75}}
.bar{{width:12rem;height:.5rem;background:{price};border-radius:1rem;margin-top:1.2rem}}
.list{{flex:1;min-height:0;display:flex;flex-direction:column;justify-content:center;overflow:hidden}}
.cols{{column-count:{cols};column-gap:6rem;font-size:var(--fs,3rem){';max-width:78rem;width:100%;margin:0 auto' if cols == 1 else ''}}}
.sec{{margin:0 0 1.6em}}
h2{{font-family:'{typ['heading']}',serif;font-weight:{typ['hw']};color:{head};font-size:1.25em;margin:0 0 .55em;
  letter-spacing:.06em;text-transform:uppercase;break-after:avoid}}
.it{{break-inside:avoid;margin:0 0 .62em}}
.row{{display:flex;align-items:baseline;gap:.4em}}
.nm{{font-weight:600}}.dots{{flex:1;border-bottom:.12em dotted currentColor;opacity:.35;transform:translateY(-.25em);min-width:1em}}
.pr{{font-weight:700;color:{price};white-space:nowrap}}
.nt{{font-size:.74em;opacity:.72;line-height:1.35;margin-top:.15em;max-width:92%}}
footer{{margin-top:3rem;text-align:center;font-size:2.2rem;opacity:.7}}
</style></head><body><div class="page">
<header>{logo_html}<h1>{html.escape(menu['title'])}</h1>{f'<div class="sub">{html.escape(menu["subtitle"])}</div>' if menu.get('subtitle') else ''}<div class="bar"></div></header>
<main class="list"><div class="cols">{''.join(secs)}</div></main>
<footer>{html.escape(menu.get('footer') or '')}</footer></div></body></html>"""


FIT = """() => {
  const list = document.querySelector('.list'), cols = document.querySelector('.cols');
  let size = parseFloat(getComputedStyle(cols).fontSize), guard = 0;
  const min = 15, max = 44;
  const set = (s) => cols.style.setProperty('--fs', s + 'px');
  const rows = [...document.querySelectorAll('.row')];
  const over = () => cols.offsetHeight > list.clientHeight + 2 || cols.scrollWidth > cols.clientWidth + 2
    || rows.some((r) => r.scrollWidth > r.clientWidth + 2);
  while (over() && size > min && guard < 80) { size = Math.max(min, size * 0.95); set(size); guard++; }
  // grow a short list so it fills the page instead of looking lost (up to a comfortable size)
  guard = 0;
  while (!over() && size < max && guard < 40) { size *= 1.04; set(size); guard++; }
  while (over() && size > min && guard < 120) { size *= 0.97; set(size); guard++; }
  return over() ? ['crowded:list'] : (size < 18 ? ['small:list'] : []);
}"""


def render(renderer, kit, menu, out_path, fmt="flyer", variant="paper"):
    """One menu design to PNG (and a print PDF for the flyer size). Returns (path, issues)."""
    w, h = design.FORMATS[fmt]
    page = renderer._page(w, h, build(kit, menu, fmt, variant))
    try:
        issues = page.evaluate(FIT)
        out_path = pathlib.Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out_path), type="png", clip={"x": 0, "y": 0, "width": w, "height": h})
        if fmt in design.PRINT:
            pw, ph = design.PRINT[fmt]
            page.pdf(path=str(out_path.with_suffix(".pdf")), width=pw, height=ph, print_background=True,
                     page_ranges="1", scale=816 / w)
    finally:
        page.close()
    return out_path, issues


def variants(renderer, kit, menu, out_dir):
    """The three looks at print size (PNG + PDF), each also as an Instagram post ("our new menu").
    Returns ([(path, look, issues)], [post paths])."""
    out_dir = pathlib.Path(out_dir)
    results, posts = [], []
    for i, v in enumerate(VARIANTS, 1):
        path, issues = render(renderer, kit, menu, out_dir / f"v{i}-{v}.png", "flyer", v)
        results.append((path, v, issues))
        post, _ = render(renderer, kit, menu, out_dir / f"v{i}-{v}-post.png", "post", v)
        posts.append(str(post))
    return results, posts
