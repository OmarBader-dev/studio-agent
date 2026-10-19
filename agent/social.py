"""The social media agent: turns what's happening (the trend radar) into posts that fit one brand.

For each brand it works out the voice, audience and what the business really sells (from its website),
picks the moments worth posting about this week (holidays, national days, seasons, weather, local events,
and live trends filtered for safety), and writes each post: the idea, a designed image's words, the caption,
hashtags, alt text and the best time to post.

Rules it never breaks: no invented prices, discounts or products (only what the website shows); no
celebrity, team or brand names that suggest an endorsement ("the big game", not "Super Bowl"); no
tragedies, politics or illness; alcohol posts are 21+ and never push drinking.
"""
import datetime as dt
import json
import random
import re

from . import ai

POST_TIMES = {   # local times that usually do well, by niche
    "restaurant": ["11:30", "17:00"], "cafe": ["07:30", "14:00"], "bakery": ["08:00", "15:00"],
    "gym": ["06:00", "17:30"], "beauty": ["10:00", "19:00"], "shop": ["12:00", "19:00"],
    "bar": ["16:00", "19:30"], "pets": ["09:00", "18:00"],
}
PILLARS = {
    "restaurant": ["signature dish", "behind the kitchen", "regulars and reviews", "local love", "what's new"],
    "cafe": ["the drink of the week", "cozy corner", "behind the bar", "local love", "pastry case"],
    "bakery": ["fresh from the oven", "custom orders", "behind the scenes", "seasonal flavors", "local love"],
    "gym": ["quick tip", "class spotlight", "member wins", "coach intro", "motivation"],
    "beauty": ["trending looks", "before and after", "meet the team", "self-care tip", "booking reminder"],
    "shop": ["new arrivals", "styled three ways", "gift ideas", "behind the brand", "customer favorites"],
    "bar": ["drink spotlight", "event night", "food pairing", "regulars", "behind the bar"],
    "pets": ["happy clients", "care tip", "before and after", "meet the team", "booking reminder"],
}
HASHTAGS = {
    "restaurant": ["foodie", "eatlocal", "supportlocal", "foodstagram", "dinnertime"],
    "cafe": ["coffeetime", "coffeeshop", "latteart", "supportlocal", "cafevibes"],
    "bakery": ["bakery", "freshbaked", "pastry", "supportlocal", "sweettooth"],
    "gym": ["fitness", "workout", "gymlife", "fitfam", "strongertogether"],
    "beauty": ["salon", "hairgoals", "selfcare", "beauty", "supportlocal"],
    "shop": ["shoplocal", "smallbusiness", "newarrivals", "giftideas", "supportlocal"],
    "bar": ["happyhour", "cocktails", "nightout", "drinklocal", "cheers"],
    "pets": ["dogsofinstagram", "petcare", "groomer", "dogmom", "supportlocal"],
}
CTA = {"restaurant": "Order now", "cafe": "Stop by today", "bakery": "Order ahead", "gym": "Book a class",
       "beauty": "Book now", "shop": "Shop now", "bar": "See you tonight", "pets": "Book a visit"}
OFFER_WORDS = re.compile(r"\$\s?\d|\d+\s?% ?off|\bbogo\b|buy one|half off|half price|\bfree\b|discount|\bdeal\b|"
                         r"\bsale\b|coupon|promo code", re.I)
SEASON_LINES = {   # headlines for a season when the post's own headline named something the business doesn't sell
    "Fall flavors": "Hello, cozy season", "Football season": "Game day, sorted", "Gift season": "Gifts made easy",
    "New Year, new goals": "New year, new goals", "Dry January": "Cheers to fresh starts", "Prom season": "Prom ready",
    "Wedding season": "Wedding ready", "Patio season": "Patio season is on", "Summer body season": "Summer starts now",
    "Back to school": "Back to routine", "Halloween": "Spooky season", "Thanksgiving": "Thankful for you",
}
TRADEMARKS = {"super bowl": "the big game", "superbowl": "the big game", "march madness": "tournament season",
              "olympics": "the games", "olympic": "the games", "world series": "the big series",
              "final four": "tournament weekend", "world cup": "the big tournament"}

SYSTEM = """You are the social media manager for a small local business. You write posts that feel human,
local and on-brand, and that people actually stop scrolling for.

Hard rules:
- Only mention products, services, prices and offers that appear in the WEBSITE TEXT. Never invent a deal,
  discount, price, menu item, award or claim. If unsure, talk about the moment and the vibe instead.
- Never use a real person's name, a celebrity, a sports team, a league, a TV show or another brand's name.
  Use the theme instead ("the big game", "spooky season", "the season finale everyone's talking about").
- Nothing about politics, tragedies, crime, illness, disasters or religion (major holidays are fine).
- Alcohol: only for 21+ venues, never encourage heavy drinking.
- Headlines on the image: 2 to 6 words, punchy. Image subhead: under 90 characters.
- Never promise anything for the business: no giveaways, prizes, contests, surprises, or "we'll feature you",
  and no events, parties or opening hours the WEBSITE TEXT doesn't mention.
- Feed posts: never say "swipe up" (it no longer exists), and no polls or stickers (those are story features).
  To start a conversation, ask people to answer in the comments.
- Captions: 40 to 120 words, warm and specific, 0 to 3 emojis, one clear call to action, no hashtags inside.
- Hashtags: 6 to 10, mixing local (city), niche and moment tags, no spaces, no celebrity or brand tags.
Reply with JSON only."""


def _clip(text, n):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def city_tag(city):
    return re.sub(r"[^A-Za-z]", "", (city or "").split(",")[0].title())


def safe_text(text):
    out = text or ""
    for mark, plain in TRADEMARKS.items():
        out = re.sub(re.escape(mark), plain, out, flags=re.I)
    return out


# Products and services a post might name. A post may only name one the business's own website mentions.
PRODUCTS = {
    "cafe": ["pumpkin spice", "pumpkin", "latte", "cold brew", "nitro", "matcha", "chai", "mocha", "cappuccino",
             "espresso", "americano", "macchiato", "flat white", "cortado", "frappe", "oat milk", "croissant", "muffin",
             "scone", "bagel", "pastry", "pastries", "smoothie", "hot chocolate", "tea", "apple", "cinnamon", "maple",
             "peppermint", "gingerbread", "sandwich", "breakfast", "avocado toast", "drive-thru", "delivery"],
    "bakery": ["cupcake", "croissant", "sourdough", "macaron", "cookie", "cake", "donut", "doughnut", "pie", "bread",
               "brownie", "cinnamon roll", "muffin", "scone", "pumpkin", "apple", "gluten-free", "vegan", "delivery"],
    "restaurant": ["pizza", "burger", "taco", "wings", "pasta", "sushi", "salad", "steak", "brunch", "pancake", "waffle",
                   "burrito", "nachos", "fries", "sandwich", "soup", "chili", "bbq", "ribs", "seafood", "lobster",
                   "pumpkin", "apple", "cocktail", "margarita", "beer", "wine", "happy hour", "delivery", "catering",
                   "patio", "live music", "trivia", "gluten-free", "vegan", "kids eat"],
    "gym": ["spin", "cycling", "yoga", "pilates", "hiit", "crossfit", "bootcamp", "boot camp", "zumba", "kickboxing",
            "boxing", "personal training", "sauna", "pool", "childcare", "smoothie bar", "24/7", "open gym",
            "nutrition", "meal plan", "challenge", "free trial", "class pass"],
    "beauty": ["balayage", "highlights", "keratin", "lash", "lashes", "brow", "brows", "facial", "manicure",
               "pedicure", "gel", "acrylic", "dip", "waxing", "massage", "blowout", "extensions", "perm", "botox",
               "filler", "spray tan", "microblading", "color", "bridal"],
    "shop": ["new arrivals", "sale", "gift card", "free shipping", "candles", "jewelry", "dresses", "shoes", "online"],
    "bar": ["cocktail", "margarita", "beer", "wine", "happy hour", "trivia", "karaoke", "live music", "wings", "brunch"],
    "pets": ["grooming", "boarding", "daycare", "training", "nail trim", "bath", "teeth", "pickup"],
}
WEATHER_WORDS = re.compile(r"\b(rain|rainy|snow|snowy|sunny|sunshine|storm|stormy|chilly|freezing|heat wave|"
                           r"scorching|hot day|cold snap|first frost)\b", re.I)
PRICE = re.compile(r"\$\s?\d+(?:[.,]\d+)?|\b\d+\s?%")
# Promises the business never made: giveaways, prizes, surprises, "we'll feature the winner"...
PROMISE = re.compile(r"\b(give-?aways?|raffles?|contests?|sweepstakes|prizes?|winners?|win|enter to|"
                     r"(?:a |special )?surprise (?:from us|for)|will (?:get|receive|win)|we'?ll (?:feature|send|give|pick|choose|"
                     r"announce|reward)|helps? us (?:decide|choose|pick)|first \d+ (?:people|customers|guests|callers))\b", re.I)
CODE = re.compile(r"\b(?:promo |discount |coupon )?code:?\s+[\"']?([A-Za-z0-9]{3,20})\b", re.I)
# Events the business never announced ("join us for a night of...", "see you tonight!")
EVENT = re.compile(r"\bjoin us for (?:a|an|our) (?:night|evening|party|celebration|event|bash)\b|\bpart(?:y|ies)\b|"
                   r"\bspecial event\b|\btonight\b", re.I)
NOT_IN_FEED = re.compile(r"\b(?:swipe|slide) up\b|\bpolls?\b|\bstickers?\b|\b(?:this|the|our) story\b|\blink in (?:the )?story\b",
                         re.I)
LEANS_BACK = re.compile(r"(?:pair|grab|try|get|enjoy|order|sip|share) (?:it|them|this|that|one)\b|"
                        r"(?:it|it'?s|its|this|that|these|those|they|them|then|plus|also|and|but)\b", re.I)


def unsupported(text, site_text, niche, allowed=""):
    """Product words in text that the website never mentions (and the moment's own name doesn't cover)."""
    site, allow, low = (site_text or "").lower(), (allowed or "").lower(), (text or "").lower()
    found = []
    for term in PRODUCTS.get(niche, []) + [t for n, terms in PRODUCTS.items() if n != niche for t in terms]:
        if re.search(r"\b" + re.escape(term) + r"s?\b", low) and term not in site and term not in allow:
            found.append(term)
    for price in PRICE.findall(text or ""):
        if price.replace(" ", "") not in site.replace(" ", ""):
            found.append(price)
    return found


def grounded(text, site_text, niche="restaurant", allowed="", weather_ok=False):
    """The text without sentences that claim something the website doesn't back up: a price, a discount,
    a freebie, a giveaway or other promise, a product it doesn't list, or weather that isn't in the forecast.
    Also drops "swipe up" and poll/sticker talk (they don't work in a feed post), and a sentence that leans on
    one that was dropped ("Pair it with..." after the "it" went)."""
    if not text:
        return text
    site = (site_text or "").lower()
    keep, dropped = [], False
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        bad = False
        if any(o.group(0).lower().strip() not in site for o in OFFER_WORDS.finditer(sentence)):
            bad = True
        if any(c.lower() not in site for c in CODE.findall(sentence)):     # a promo code must be theirs, exactly
            bad = True
        promise = PROMISE.search(sentence) or EVENT.search(sentence)
        if promise and promise.group(0).lower() not in site:
            bad = True
        if NOT_IN_FEED.search(sentence) or unsupported(sentence, site_text, niche, allowed):
            bad = True
        if not weather_ok and WEATHER_WORDS.search(sentence):
            bad = True
        if not bad and dropped and LEANS_BACK.match(sentence):
            bad = True
        dropped = bad
        if not bad:
            keep.append(sentence)
    return " ".join(keep).strip()


# The brand -------------------------------------------------------------------------------------
def profile(cfg, store, kit):
    """Voice, audience and real offerings for a brand (AI when available, else sensible defaults)."""
    if kit.get("profile"):
        return kit["profile"]
    niche = kit.get("niche", "restaurant")
    default = {"voice": {"gym": "energetic and encouraging", "beauty": "warm and polished",
                         "shop": "friendly and stylish", "bar": "fun and laid-back"}.get(niche, "warm and friendly"),
               "audience": f"locals in {kit.get('city') or 'town'}", "offerings": [], "vibe": [], "source": "default"}
    if not kit.get("text"):
        kit["profile"] = default
        return default
    prompt = f"""From this website, describe the business for its social media manager.
BUSINESS: {kit.get('name')} ({niche}) in {kit.get('city') or 'the US'}
WEBSITE TEXT:
{kit['text'][:5000]}

Return JSON: {{"voice": "how they talk, 3-6 words", "audience": "who they serve, under 12 words",
"offerings": ["up to 10 real products/services named on the site, exactly as written"],
"signature": "the one thing they're known for, from the site, or empty",
"vibe": ["3 adjectives for the look and feel"], "hashtags": ["3-5 niche hashtags without #"],
"facts": ["up to 4 short true facts from the site: since when, family-owned, location, hours..."]}}"""
    data = ai.ask(cfg, store, prompt, system="You read websites carefully and never invent facts. JSON only.",
                  max_tokens=900, temperature=0.3)
    if not isinstance(data, dict) or not data.get("voice"):
        kit["profile"] = default
        return default
    site = kit["text"].lower()
    offerings = [o for o in data.get("offerings") or [] if isinstance(o, str) and o.lower()[:12] in site][:10]
    prof = {"voice": _clip(data.get("voice"), 60) or default["voice"], "audience": _clip(data.get("audience"), 90),
            "offerings": offerings, "signature": _clip(data.get("signature"), 80) if data.get("signature") and
            str(data["signature"]).lower()[:10] in site else "", "vibe": [str(v) for v in (data.get("vibe") or [])][:3],
            "hashtags": [re.sub(r"[^A-Za-z0-9]", "", str(h)) for h in (data.get("hashtags") or [])][:5],
            "facts": [_clip(f, 90) for f in (data.get("facts") or []) if isinstance(f, str)][:4], "source": "ai"}
    kit["profile"] = prof
    return prof


# The moments ------------------------------------------------------------------------------------
def moments(radar, niche, start, days=14, site_text=None):
    """Things worth a post between start and start+days, for this niche, best first. With the website text,
    product days only count when the business sells the product (no Chocolate Day for a jeweler)."""
    from .observances import fits
    out = []
    for c in radar.get("calendar", []):
        if niche not in c.get("niches", []) or (site_text is not None and not fits(c["title"], site_text)):
            continue
        d = dt.date.fromisoformat(c["date"])
        lead = (d - start).days
        if c["kind"] == "season" or -1 <= lead <= days:
            score = 3 if c["kind"] in ("day", "holiday") else 1.5
            score += 2 if c["title"] in ("Halloween", "Thanksgiving", "Christmas", "Valentine's Day", "Mother's Day",
                                         "Small Business Saturday", "Independence Day", "New Year's Eve") else 0
            out.append(dict(c, score=score, lead=lead))
    for w in radar.get("weather", []):
        out.append({"title": w["title"], "date": w["date"], "angle": w["angle"], "icon": w.get("icon", "🌤️"),
                    "kind": "weather", "score": 2.5, "niches": [niche]})
    if niche in ("restaurant", "bar", "cafe"):
        for ev in radar.get("events", [])[:3]:
            out.append({"title": ev["title"], "date": ev["date"], "angle": ev.get("context", ""), "icon": "🎟️",
                        "kind": "event", "score": 2, "niches": [niche]})
    return sorted(out, key=lambda m: -m["score"])


# Writing the week --------------------------------------------------------------------------------
def plan(cfg, store, kit, radar, n=3, start=None, kinds=("post",), span=7):
    """n posts for the week starting at start (a date). Each post is a dict ready for the design agent.
    span: how many days the posts may be spread over (a client's week is 7; a free sample can run up to a
    moment two weeks out, like Halloween)."""
    start = start or dt.date.today()
    niche = kit.get("niche", "restaurant")
    prof = profile(cfg, store, kit)
    moms = moments(radar, niche, start, site_text=kit.get("text") or "")
    live = [f"{x['title']} ({x.get('context', '')[:100]})" for x in radar.get("live", [])[:16]]
    days = [(start + dt.timedelta(days=i)) for i in range(7)]
    times = POST_TIMES.get(niche, ["12:00", "18:00"])
    prompt = f"""Plan {n} social posts for this business for the week of {start:%B %d, %Y}.

BUSINESS: {kit.get('name')} — {kit.get('category') or niche} in {kit.get('city') or ''} {kit.get('state') or ''}
VOICE: {prof.get('voice')} | AUDIENCE: {prof.get('audience')}
KNOWN FOR: {prof.get('signature') or 'n/a'} | OFFERINGS ON THE SITE: {', '.join(prof.get('offerings') or []) or 'not listed'}
{('RULES FROM THE CLIENT (always follow them): ' + kit['rules'][:600]) if kit.get('rules') else ''}
FACTS: {'; '.join(prof.get('facts') or []) or 'n/a'}
BOOKING/ORDERING LINKS ON THE SITE: {'yes' if kit.get('booking') or kit.get('ordering') else 'no'}
WEBSITE TEXT (for facts only):
{(kit.get('text') or '')[:2500]}

MOMENTS THIS WEEK (calendar, weather, local):
{json.dumps([{k: m.get(k) for k in ('title', 'date', 'angle', 'kind')} for m in moms[:8]], ensure_ascii=False)}
TRENDING ONLINE TODAY (use only a safe theme, never the names): {json.dumps(live, ensure_ascii=False)}

Mix: at least one post tied to a moment above, one about what the business actually offers, and one that
starts a conversation (a question, this-or-that, or a fun local angle). Spread them over the week.
If a moment suggests a product this business doesn't list (say, pumpkin drinks), write about the feeling of
the moment instead ("cozy fall mornings"), never the product. Don't describe the weather unless it's listed above.

Return JSON: {{"posts": [{{"day": "YYYY-MM-DD", "time": "HH:MM", "moment": "the moment's title or ''",
"idea": "one line, why this post works", "format": "post" or "story" or "reel",
"eyebrow": "2-4 words above the headline", "headline": "2-6 words", "subhead": "under 90 characters",
"cta": "2-4 words", "icon": "one emoji that fits", "photo_subject": "what a photo would show",
"caption": "...", "hashtags": ["..."], "alt_text": "describes the image for screen readers",
"reel_script": "for reels only: 3-5 short shots, else ''"}}]}}"""
    data = ai.ask(cfg, store, prompt, system=SYSTEM, max_tokens=3500, temperature=0.85)
    posts = data.get("posts") if isinstance(data, dict) else None
    if not posts:
        posts = offline_posts(kit, prof, moms, n, start)
        source = "templates"
    else:
        source = data.get("_model", "ai")
    weather_ok = bool(radar.get("weather"))
    last = start + dt.timedelta(days=max(span, 7) - 1)
    when = {}                                            # a moment's own date, for posts tied to it
    for m in moms:
        try:
            d = dt.date.fromisoformat(str(m.get("date")))
        except ValueError:
            continue
        if start <= d <= last and m.get("kind") != "season":
            when[m["title"]] = d
    out = []
    weather_days = {w["title"] for w in radar.get("weather", [])}
    for i, p in enumerate(posts[:n]):
        default = when.get(str(p.get("moment") or ""), days[min(i * 2, 6)])
        if str(p.get("moment") or "") in weather_days and str(p.get("moment")) in when:
            p = dict(p, day=when[str(p["moment"])].isoformat())   # weather posts go out on that day, not before
        out.append(clean_post(p, kit, prof, default, times[i % len(times)], source, weather_ok, week=(start, last)))
    return out


def clean_post(p, kit, prof, day, time, source, weather_ok=False, week=None):
    niche = kit.get("niche", "restaurant")
    site = kit.get("text") or ""
    allowed = str(p.get("moment") or "")
    tags = [re.sub(r"[^A-Za-z0-9]", "", str(h)) for h in (p.get("hashtags") or [])]
    city = city_tag(kit.get("city"))
    if city and city.lower() not in [t.lower() for t in tags]:
        tags.insert(0, city)
    for extra in prof.get("hashtags") or []:
        if len(tags) < 8 and extra.lower() not in [t.lower() for t in tags]:
            tags.append(extra)
    for extra in HASHTAGS.get(niche, []):
        if len(tags) < 8 and extra.lower() not in [t.lower() for t in tags]:
            tags.append(extra)
    caption = grounded(safe_text(p.get("caption")), site, niche, allowed, weather_ok)
    if len(caption.split()) < 15:                     # too much was unsupported: fall back to a safe caption
        caption = (f"{safe_text(p.get('headline') or p.get('moment') or 'Something good')} at {kit.get('name')}"
                   + (f", {city_tag(kit.get('city'))}" if kit.get("city") else "") + ". "
                   + "Come say hi this week, and tell us in the comments what you'd love to see from us next!")
    headline = _clip(safe_text(p.get("headline")), 40)
    if not headline or (OFFER_WORDS.search(headline) and not grounded(headline, site, niche, allowed, True)) or \
            unsupported(headline, site, niche, allowed) or PROMISE.search(headline):
        moment = safe_text(p.get("moment") or "")
        headline = _clip(SEASON_LINES.get(moment) or moment or {
            "cafe": "Your daily ritual", "bakery": "Fresh this week", "gym": "Show up for you", "beauty": "Your next look",
            "shop": "Just for you"}.get(niche, "Made for you"), 40)
    subhead = grounded(safe_text(p.get("subhead")), site, niche, allowed, weather_ok)
    if not subhead or unsupported(subhead, site, niche, allowed):
        subhead = f"From all of us at {kit.get('name')}" + (f", {kit['city']}" if kit.get("city") else "") + "."
    try:
        asked = dt.date.fromisoformat(str(p.get("day")))
        if not week or week[0] <= asked <= week[1]:      # a day outside the week (in the past, say) is ignored
            day = asked
    except ValueError:
        pass
    when = str(p.get("time") or time)
    if not re.fullmatch(r"\d{1,2}:\d{2}", when):
        when = time
    return {
        "day": day.isoformat(), "time": when, "moment": _clip(p.get("moment"), 60), "idea": _clip(p.get("idea"), 160),
        "format": p.get("format") if p.get("format") in ("post", "story", "reel") else "post",
        "content": {"eyebrow": _clip(safe_text(p.get("eyebrow")), 28), "headline": headline,
                    "subhead": _clip(subhead, 100),
                    "cta": _clip(safe_text(p.get("cta")) or CTA.get(niche, "Visit us"), 22),
                    "icon": (p.get("icon") or "")[:4], "footer": kit.get("domain") or ""},
        "photo_subject": _clip(p.get("photo_subject"), 80),
        "caption": caption.strip(), "hashtags": [t for t in tags if t][:10],
        "alt_text": _clip(p.get("alt_text") or f"{headline} — {kit.get('name')}", 200),
        "reel_script": _clip(p.get("reel_script"), 500) if p.get("format") == "reel" else "", "source": source,
    }


def offline_posts(kit, prof, moms, n, start):
    """Posts from templates, for when no AI provider is available. Plain but on-brand and safe."""
    niche = kit.get("niche", "restaurant")
    name, city = kit.get("name") or "us", (kit.get("city") or "").split(",")[0]
    rnd = random.Random(f"{name}{start}")
    offer = (prof.get("signature") or (prof.get("offerings") or [""])[0] or "").strip()
    posts = []
    for m in [m for m in moms if m["kind"] != "season"][:max(1, n - 2)] or moms[:1]:
        title = m["title"]
        posts.append({
            "moment": title, "idea": f"Ride {title} while people are already thinking about it.",
            "eyebrow": f"{title}" if len(title) <= 28 else "This week", "icon": m.get("icon", "✨"),
            "headline": {"day": f"Happy {title}", "holiday": f"Happy {title}", "season": title,
                         "weather": f"{title}? We've got you", "event": "Big night in town"}.get(m["kind"], title),
            "subhead": f"Celebrate {m.get('angle') or title} with {name}" + (f" in {city}" if city else "") + ".",
            "caption": (f"{title} is here{' ' + m.get('icon', '') if m.get('icon') else ''}! "
                        f"We're celebrating {m.get('angle') or 'it'} at {name}. "
                        + (f"Our {offer} is the perfect excuse to stop by. " if offer else "")
                        + f"Tag who you're bringing and we'll see you soon."),
            "hashtags": [re.sub(r"[^A-Za-z0-9]", "", title)],
        })
    pillar = rnd.choice(PILLARS.get(niche, ["what's new"]))
    posts.append({
        "moment": "", "idea": f"A '{pillar}' post keeps the feed about the business, not just the calendar.",
        "eyebrow": pillar.title()[:28], "icon": "✨",
        "headline": (offer[:36] if offer else {"gym": "Show up for you", "beauty": "Your next look",
                                               "shop": "Just landed", "cafe": "Your daily ritual",
                                               "bakery": "Fresh this morning"}.get(niche, "Made with love")),
        "subhead": f"From all of us at {name}" + (f", {city}" if city else "") + ".",
        "caption": (f"A little {pillar} from {name}. " + (f"Have you tried our {offer} yet? " if offer else "")
                    + "Tell us your favorite in the comments!"),
        "hashtags": [],
    })
    while len(posts) < n:
        posts.append({"moment": "", "idea": "A question gets people talking, which helps the next posts reach more.",
                      "eyebrow": "Your turn", "icon": "💬", "headline": "This or that?",
                      "subhead": "Tell us in the comments — we read every one.",
                      "caption": f"Settle it for us: what's your go-to at {name}? Comment below 👇", "hashtags": []})
    return posts[:n]


# Google Business Profile -------------------------------------------------------------------------------
PHONE = re.compile(r"\(?\b\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
LINKS = re.compile(r"(?:https?://|www\.)\S+?(?=[.,!?;:)]*(?:\s|$))|\b[\w-]+\.(?:com|net|org|co|us|shop|store|cafe|coffee|fit)\b(?:/\S*?(?=[.,!?;:)]*(?:\s|$)))?", re.I)


def gbp_post(kit, post):
    """A Google Business Profile update made from a post: the caption without hashtags, links or phone numbers
    (Google turns down posts with those; the post's button does that job), at most 1,500 characters, and the
    button that fits the business (Order online, Book or Learn more)."""
    text = re.sub(r"(?:^|\s)#[\w-]+", "", post.get("caption") or "")
    text = re.sub(r"\b(call|text)(?: us)?(?: at| on)?\s+" + PHONE.pattern, r"\1 us", text, flags=re.I)
    text = re.sub(r"\b(visit|see|check out)\s+(?:" + LINKS.pattern + ")", r"\1 our website", text, flags=re.I)
    text = re.sub(r"\s+(?:at|on|via)\s+(?:" + LINKS.pattern + ")", " online", text, flags=re.I)
    text = re.sub(r"(?:\s+(?:at|on|via))?\s+(?:" + LINKS.pattern + "|" + PHONE.pattern + ")", "", text, flags=re.I)
    text = re.sub(r"[ \t]+([,.!?])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(l.rstrip() for l in text.splitlines())).strip()
    if len(text) > 1500:
        text = text[:1500].rsplit(". ", 1)[0].rstrip(".") + "."
    first = lambda links: sorted(links or [], key=len)[0] if links else None
    if first(kit.get("ordering")):
        button, url = "Order online", first(kit.get("ordering"))
    elif first(kit.get("booking")):
        button, url = "Book", first(kit.get("booking"))
    else:
        button, url = "Learn more", kit.get("website")
    return {"text": text, "button": button, "link": url}
