"""Color helpers: reading colors from CSS and images, contrast (WCAG), and building a brand palette."""
import collections
import colorsys
import re

NAMED = {"white": "#ffffff", "black": "#000000", "red": "#ff0000", "green": "#008000", "blue": "#0000ff",
         "navy": "#000080", "orange": "#ffa500", "gold": "#ffd700", "teal": "#008080", "maroon": "#800000",
         "purple": "#800080", "crimson": "#dc143c", "tomato": "#ff6347", "coral": "#ff7f50",
         "darkgreen": "#006400", "forestgreen": "#228b22", "royalblue": "#4169e1", "firebrick": "#b22222",
         "goldenrod": "#daa520", "salmon": "#fa8072", "hotpink": "#ff69b4", "deeppink": "#ff1493",
         "darkred": "#8b0000", "steelblue": "#4682b4", "darkblue": "#00008b", "olive": "#808000"}
HEX = re.compile(r"#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")
RGB = re.compile(r"rgba?\(\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})(?:[\s,/]+([\d.]+%?))?\s*\)", re.I)
HSL = re.compile(r"hsla?\(\s*([\d.]+)(?:deg)?[\s,]+([\d.]+)%[\s,]+([\d.]+)%(?:[\s,/]+([\d.]+%?))?\s*\)", re.I)


def to_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(v))):02x}" for v in rgb[:3])


def rgb(color):
    """'#1a2b3c', '#abc', 'rgb(1,2,3)', 'hsl(..)' or a few names -> (r, g, b) ints, or None."""
    if isinstance(color, (tuple, list)):
        return tuple(int(v) for v in color[:3])
    c = (color or "").strip().lower()
    c = NAMED.get(c, c)
    m = HEX.fullmatch(c)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(ch * 2 for ch in h[:3])
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = RGB.fullmatch(c)
    if m:
        return tuple(min(255, int(m.group(i))) for i in (1, 2, 3))
    m = HSL.fullmatch(c)
    if m:
        r, g, b = colorsys.hls_to_rgb(float(m.group(1)) % 360 / 360, float(m.group(3)) / 100, float(m.group(2)) / 100)
        return round(r * 255), round(g * 255), round(b * 255)
    return None


def hexify(color):
    v = rgb(color)
    return to_hex(v) if v else None


def luminance(color):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(color)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_on(bg, dark="#111111", light="#ffffff"):
    """Near-black or white, whichever reads better on this background."""
    return dark if contrast(bg, dark) >= contrast(bg, light) else light


def mix(a, b, amount):
    """a moved toward b by amount (0-1)."""
    ra, rb = rgb(a), rgb(b)
    return to_hex([x + (y - x) * amount for x, y in zip(ra, rb)])


def hls(color):
    r, g, b = (v / 255 for v in rgb(color))
    return colorsys.rgb_to_hls(r, g, b)                 # hue 0-1, lightness 0-1, saturation 0-1


def from_hls(h, l, s):
    return to_hex([v * 255 for v in colorsys.hls_to_rgb(h % 1, max(0, min(1, l)), max(0, min(1, s)))])


def saturation(color):
    r, g, b = (v / 255 for v in rgb(color))
    mx, mn = max(r, g, b), min(r, g, b)
    return 0 if mx == 0 else (mx - mn) / mx            # HSV saturation: how colorful, regardless of lightness


def is_neutral(color, limit=0.12):
    """Whites, greys, blacks and very washed-out tints: not a brand color."""
    l = hls(color)[1]
    return saturation(color) < limit or l > 0.95 or l < 0.06


def distance(a, b):
    """Rough perceptual distance (redmean)."""
    (r1, g1, b1), (r2, g2, b2) = rgb(a), rgb(b)
    rm = (r1 + r2) / 2
    return ((2 + rm / 256) * (r1 - r2) ** 2 + 4 * (g1 - g2) ** 2 + (2 + (255 - rm) / 256) * (b1 - b2) ** 2) ** 0.5


def darken(color, amount=0.2):
    return mix(color, "#000000", amount)


def lighten(color, amount=0.2):
    return mix(color, "#ffffff", amount)


def readable(color, bg, minimum=4.5):
    """color, darkened or lightened just enough to reach the contrast ratio on bg."""
    c = hexify(color)
    if contrast(c, bg) >= minimum:
        return c
    toward = "#000000" if luminance(bg) > 0.4 else "#ffffff"
    for step in range(1, 21):
        cand = mix(c, toward, step / 20)
        if contrast(cand, bg) >= minimum:
            return cand
    return text_on(bg)


def in_css(css, weight=1):
    """Counter of colors used in CSS or inline styles, by hex."""
    found = collections.Counter()
    for m in HEX.finditer(css or ""):
        h = m.group(1)
        if len(h) == 8 and h[6:].lower() in ("00", "0f", "1a", "26"):
            continue                                    # nearly transparent
        found[hexify("#" + h[:6] if len(h) == 8 else "#" + h)] += weight
    for m in RGB.finditer(css or ""):
        alpha = m.group(4)
        if alpha and (float(alpha.rstrip("%")) / (100 if alpha.endswith("%") else 1)) < 0.5:
            continue
        found[to_hex([int(m.group(i)) for i in (1, 2, 3)])] += weight
    return found


def merge_similar(counter, closeness=40):
    """Fold near-identical shades together, keeping the most used one's hex."""
    out = []
    for color, n in counter.most_common():
        for item in out:
            if distance(item[0], color) < closeness:
                item[1] += n
                break
        else:
            out.append([color, n])
    return [(c, n) for c, n in sorted(out, key=lambda x: -x[1])]


def from_image(path, k=6, size=96):
    """Main colors of an image as [(hex, share)], ignoring transparent pixels."""
    from PIL import Image
    try:
        im = Image.open(path)
        im.load()
    except Exception:
        return []
    im = im.convert("RGBA")
    im.thumbnail((size, size))
    px = [p[:3] for p in im.getdata() if p[3] > 200]
    if not px:
        return []
    flat = Image.new("RGB", (len(px), 1))
    flat.putdata(px)
    q = flat.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[: k * 3]
    counts = sorted(q.getcolors() or [], reverse=True)
    total = sum(n for n, _ in counts) or 1
    return [(to_hex(pal[i * 3:i * 3 + 3]), n / total) for n, i in counts]


def palette(candidates, fallback="#1f3a5f"):
    """Pick brand roles from candidate colors (most important first).
    Returns {'primary', 'secondary', 'accent', 'dark', 'light'} as hex strings. A black-and-white brand
    keeps its near-black as the primary and gets the fallback color as its accent."""
    colorful = [c for c in candidates if c and not is_neutral(c)]
    unique = []
    for c in colorful:
        if all(distance(c, u) > 70 for u in unique):
            unique.append(c)
    if not unique:
        dark = next((c for c in candidates if c and luminance(c) < 0.03), "#161616")
        light = next((c for c in candidates if c and luminance(c) > 0.85), "#fafafa")
        return {"primary": hexify(dark), "secondary": hexify(mix(fallback, "#000000", 0.25)),
                "accent": hexify(fallback), "dark": hexify(dark), "light": hexify(light), "mono": True}
    primary = unique[0]
    if hls(primary)[1] > 0.78:                       # pastel primaries make text unreadable: deepen them
        primary = darken(primary, 0.35)
    secondary = next((c for c in unique[1:] if abs(hls(c)[0] - hls(primary)[0]) > 0.06), None)
    if not secondary:
        h, l, s = hls(primary)
        secondary = from_hls(h + 0.5, 0.5, max(0.45, s))   # complementary
    accent = next((c for c in unique[1:] if c != secondary), None)
    if not accent:
        h, l, s = hls(primary)
        accent = from_hls(h + 0.08, min(0.62, l + 0.18), min(1, s + 0.1))
    darks = [c for c in candidates if c and luminance(c) < 0.03]
    lights = [c for c in candidates if c and luminance(c) > 0.85 and saturation(c) < 0.2]
    dark = darks[0] if darks else mix(primary, "#0b0b0f", 0.85)
    light = lights[0] if lights else mix(primary, "#ffffff", 0.94)
    if contrast(dark, light) < 7:
        dark, light = "#111111", "#fafafa"
    return {"primary": hexify(primary), "secondary": hexify(secondary), "accent": hexify(accent),
            "dark": hexify(dark), "light": hexify(light)}
