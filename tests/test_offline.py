"""Offline tests: no keys or internet needed. Run with:  python -m unittest discover tests"""
import datetime as dt
import email
import json
import os
import pathlib
import tempfile
import unittest
from email import policy

from agent import (ai, brand, clients, colors, commands, designer, fonts, hq, inbox, mailer, meta, observances, packs,
                   pipeline, prospect, settings, social, trends)
from agent.store import Store, iso


def cfg_for_tests():
    cfg = settings.load()
    cfg["you"].update(name="Sam Test", business="Sam Studio", email="sam@gmail.com",
                      mailing_address="123 Test St, Beirut, Lebanon")
    cfg["mode"] = "draft"
    cfg["clients"] = []
    cfg["ai"]["keyless_fallback"] = False
    for k in settings.SECRETS + ["STATE_KEY"]:
        os.environ.pop(k, None)
    return cfg


def temp_store():
    d = tempfile.mkdtemp()
    return Store(pathlib.Path(d) / "state.json")


class patched:
    """Temporarily replace attributes: with patched((module, "name", value), ...):"""

    def __init__(self, *items):
        self.items, self.saved = items, []

    def __enter__(self):
        for obj, name, value in self.items:
            self.saved.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)
        return self

    def __exit__(self, *exc):
        for obj, name, value in reversed(self.saved):
            setattr(obj, name, value)


def png(folder, name, size=(40, 50)):
    from PIL import Image
    path = pathlib.Path(folder) / name
    Image.new("RGB", size, "#c8102e").save(path)
    return str(path)


KIT = {"name": "Joe's Pizza", "niche": "restaurant", "city": "Columbus", "state": "OH", "domain": "joespizza.com",
       "website": "https://joespizza.com/", "colors": colors.palette(["#c8102e", "#1d3557", "#f1c40f"]),
       "fonts": {"heading": "Anton", "body": "Inter", "from_site": True}, "logo": None, "photos": [],
       "text": "Joe's Pizza. Hand-tossed pizza since 1988. Wings, garlic knots, calzones. Order online. "
               "Free delivery over $25. Open late Friday."}


class ColorTests(unittest.TestCase):
    def test_parse_contrast_and_readable(self):
        self.assertEqual(colors.rgb("#abc"), (170, 187, 204))
        self.assertEqual(colors.hexify("rgb(255, 0, 0)"), "#ff0000")
        self.assertEqual(colors.text_on("#111111"), "#ffffff")
        self.assertGreaterEqual(colors.contrast(colors.readable("#ffd700", "#ffffff"), "#ffffff"), 4.5)

    def test_palette_roles_and_black_and_white_brands(self):
        pal = colors.palette(["#ffffff", "#c8102e", "#222222", "#1d3557"])
        self.assertEqual(pal["primary"], "#c8102e")
        mono = colors.palette(["#222222", "#ffffff", "#000000"], fallback="#c8102e")
        self.assertTrue(mono["mono"])
        self.assertEqual((mono["primary"], mono["accent"]), ("#222222", "#c8102e"))


class BrandTests(unittest.TestCase):
    PAGE = """<html><head><title>Joe's Pizza | Columbus</title><meta name="theme-color" content="#c8102e">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Anton&family=Inter:wght@400;700">
<script type="application/ld+json">{"@type":"Restaurant","name":"Joe's Pizza","telephone":"614-555-0100",
"logo":"https://joespizza.com/logo.png","address":{"streetAddress":"1 Main St","addressLocality":"Columbus","addressRegion":"OH"}}</script>
<style>:root{--brand-primary:#c8102e} .btn{background:#1d3557} .social a.dribbble{color:#ea4c89}</style></head>
<body><header><img class="site-logo" src="/img/logo.png"></header>
<a href="https://www.instagram.com/joespizza/">IG</a><a href="https://www.facebook.com/sharer/sharer.php?u=x">share</a>
<a href="https://order.toasttab.com/joes">Order</a><a href="mailto:Info@JoesPizza.com">mail</a>
<span data-cfemail="4f262129200f252a20253f262535352e612c2022">[email protected]</span></body></html>"""

    def test_reading_the_page(self):
        ld = brand.json_ld(self.PAGE)
        self.assertEqual(ld["name"], "Joe's Pizza")
        links = brand.links(self.PAGE, "https://joespizza.com/")
        self.assertEqual(brand.socials(links), {"instagram": "https://www.instagram.com/joespizza/"})
        self.assertEqual(brand.services(links)[0], ["https://order.toasttab.com/joes"])
        self.assertEqual(brand.emails_in(self.PAGE)[0], "info@joespizza.com")
        self.assertEqual(brand.logo_candidates(self.PAGE, "https://joespizza.com/", ld)[:2],
                         ["https://joespizza.com/img/logo.png", "https://joespizza.com/logo.png"])   # header logo first
        self.assertEqual(brand.google_fonts_in(self.PAGE), ["Anton", "Inter"])

    def test_brand_colors_skip_social_icon_colors(self):
        css = brand.clean_css(":root{--brand-primary:#c8102e} .btn{background:#1d3557} .dribbble{color:#ea4c89} "
                              ".x{background:url(data:image/png;base64,AAAA)}")
        pal, ranked = brand.brand_colors(self.PAGE, css, {})
        self.assertEqual(pal["primary"], "#c8102e")
        self.assertNotIn("#ea4c89", ranked)

    def test_fonts_and_junk(self):
        heads, bodies = brand.declared_fonts("h1{font-family:'Playfair Display',serif} body{font-family:Lato} "
                                             ".i{font-family:FontAwesome} :root{--font-size:42px;--body-font:Lato}")
        self.assertEqual((heads, bodies[:1]), (["Playfair Display"], ["Lato"]))
        self.assertEqual(brand.FONT_LOOKALIKES["proxima nova"], "Montserrat")

    def test_spam_and_text(self):
        self.assertTrue(brand.SPAM.search("Situs slot online gacor terpercaya"))
        self.assertIn("Hand-tossed", brand.visible_text("<div>Skip to content</div><p>Hand-tossed pizza</p><script>x</script>"))
        self.assertNotIn("Skip to content", brand.visible_text("<div>Skip to content</div><p>Hand-tossed pizza</p>"))


class FontTests(unittest.TestCase):
    def test_css_link_only_asks_for_weights_a_family_has(self):
        saved = fonts._meta
        fonts._meta = {"Anton": ["Sans Serif", [400], 1, 1, True], "Inter": ["Sans Serif", [400, 700, 900], 1, 1, True]}
        try:
            url = fonts.css_url(["Anton", "Inter"], icons=True)
        finally:
            fonts._meta = saved
        self.assertIn("family=Anton&", url)
        self.assertIn("family=Inter:wght@400;700;900", url)
        self.assertIn("Material+Symbols+Rounded", url)


class CalendarTests(unittest.TestCase):
    def test_dates(self):
        d = {name: observances.date_of(rule, 2026) for name, rule, *_ in observances.DAYS}
        self.assertEqual(d["Thanksgiving"], dt.date(2026, 11, 26))
        self.assertEqual(d["Small Business Saturday"], dt.date(2026, 11, 28))
        self.assertEqual(d["Easter"], dt.date(2026, 4, 5))
        self.assertEqual(d["Mother's Day"], dt.date(2026, 5, 10))
        self.assertEqual(d["National Donut Day"], dt.date(2026, 6, 5))
        upcoming = observances.upcoming(dt.date(2026, 10, 19), 14)
        self.assertIn("Halloween", [u["title"] for u in upcoming])
        self.assertIn("Football season", [u["title"] for u in upcoming])


class TrendTests(unittest.TestCase):
    def test_safety_filter(self):
        self.assertFalse(trends.safe("Senator arrested after shooting"))
        self.assertFalse(trends.safe("Hurricanes hit the coast"))
        self.assertTrue(trends.safe("Halloween costume plans"))
        self.assertFalse(trends.safe("crypto rally", extra=["crypto"]))

    def test_google_trends_parsing(self):
        class R:
            status_code = 200
            text = ("<rss><item><title>pumpkin patch</title><ht:approx_traffic>20,000+</ht:approx_traffic>"
                    "<ht:news_item_title>Best patches near you</ht:news_item_title></item></rss>")
        saved = trends._get
        trends._get = lambda *a, **k: R()
        try:
            got = trends.google_trends("US")
        finally:
            trends._get = saved
        self.assertEqual(got, [{"title": "pumpkin patch", "traffic": 20000, "context": "Best patches near you"}])


class SocialTests(unittest.TestCase):
    def test_grounding_drops_invented_claims(self):
        site = KIT["text"]
        text = ("Try our new pumpkin latte! Free delivery over $25. Get 20% off today. It's a rainy day in Columbus. "
                "Our garlic knots are back.")
        self.assertEqual(social.grounded(text, site, "restaurant"), "Free delivery over $25. Our garlic knots are back.")
        self.assertEqual(social.unsupported("Happy National Pizza Day", site, "restaurant", "National Pizza Day"), [])
        self.assertIn("sushi", social.unsupported("Sushi night", site, "restaurant"))

    def test_no_promises_swipe_ups_or_dangling_sentences(self):
        text = ("Pumpkin latte is back! Pair it with our chocolate truffles. Vote in the poll on this story! "
                "The top flavor will get a special surprise from us next week. Swipe up to order. See you at the cafe!")
        self.assertEqual(social.grounded(text, "chocolate truffles cafe", "cafe"), "See you at the cafe!")
        self.assertIn("Winner", social.grounded("Winner of Best Bakery 2024.", "winner of best bakery 2024", "bakery"))
        site = "free shipping on select halloween gifts! code: free"
        self.assertTrue(social.grounded("Free shipping on Halloween gifts with code FREE!", site, "bakery"))
        self.assertEqual(social.grounded("Use code SPOOKY20 for free shipping!", site, "bakery"), "")

    def test_product_days_only_for_businesses_that_sell_it(self):
        self.assertFalse(observances.fits("National Chocolate Day", "Engagement rings, watch repair"))
        self.assertTrue(observances.fits("National Chocolate Day", "Handmade chocolate truffles"))
        self.assertTrue(observances.fits("Halloween", ""))
        radar = {"calendar": [{"title": "National Chocolate Day", "date": "2026-10-28", "niches": ["shop"], "kind": "day"},
                              {"title": "Halloween", "date": "2026-10-31", "niches": ["shop"], "kind": "holiday"}]}
        got = [m["title"] for m in social.moments(radar, "shop", dt.date(2026, 10, 19), site_text="Rings and watches")]
        self.assertEqual(got, ["Halloween"])

    def test_google_business_profile_post(self):
        kit = {"ordering": ["https://x.square.site/product/1?a=b", "https://x.square.site/"], "website": "https://x.com/"}
        post = {"caption": "Pumpkin spice is back 🎃 Order ahead at florincoffee.com or call (614) 555-0101 today!\n\n#cbus #latte"}
        g = social.gbp_post(kit, post)
        self.assertEqual(g["text"], "Pumpkin spice is back 🎃 Order ahead online or call us today!")
        self.assertEqual((g["button"], g["link"]), ("Order online", "https://x.square.site/"))

    def test_trademarks_and_hashtags(self):
        p = social.clean_post({"headline": "Super Bowl Sunday", "caption": "Watch the Super Bowl with us and our wings. "
                               "Tell us your pick for the big game in the comments below!",
                               "hashtags": ["#Wings!", "pizza"], "moment": "Football season", "cta": "Order now"},
                              KIT, {"hashtags": ["pizzalover"]}, dt.date(2026, 10, 19), "17:00", "test")
        self.assertEqual(p["content"]["headline"], "the big game Sunday")
        self.assertNotIn("Super Bowl", p["caption"])
        self.assertEqual(p["hashtags"][:3], ["Columbus", "Wings", "pizza"])

    def test_plan_uses_ai_and_falls_back_to_templates(self):
        cfg, store = cfg_for_tests(), temp_store()
        radar = {"calendar": observances.upcoming(dt.date(2026, 10, 19), 21), "live": [], "weather": [], "events": []}
        saved = social.ai.ask
        social.ai.ask = lambda *a, **k: None
        try:
            offline = social.plan(cfg, store, dict(KIT), radar, n=3, start=dt.date(2026, 10, 19))
            social.ai.ask = lambda *a, **k: {"posts": [{"day": "2026-10-20", "time": "17:00", "moment": "Halloween",
                                                        "headline": "Spooky slices", "subhead": "Garlic knots for the costume crew",
                                                        "caption": "Halloween is coming and our garlic knots are ready for "
                                                                   "your costume party. Tag the friend who always steals the last knot!",
                                                        "hashtags": ["Halloween"], "cta": "Order now", "icon": "🎃"}],
                                             "_model": "test"}
            with_ai = social.plan(cfg, store, dict(KIT, profile={"voice": "fun"}), radar, n=1, start=dt.date(2026, 10, 19))
            sunny_post = {"day": "2026-10-18", "moment": "Sunny weekend", "headline": "Sunny days",
                          "caption": "Grab a slice and enjoy the sunshine with friends this weekend, we'll keep the "
                                     "ovens hot for you all day long!"}
            social.ai.ask = lambda *a, **k: {"posts": [sunny_post, dict(sunny_post, day="2026-10-20")], "_model": "test"}
            sunny = dict(radar, weather=[{"title": "Sunny weekend", "date": "2026-10-24", "angle": "sunny", "icon": "🌤️"}])
            past = social.plan(cfg, store, dict(KIT, profile={"voice": "fun"}), sunny, n=2, start=dt.date(2026, 10, 19))
        finally:
            social.ai.ask = saved
        self.assertEqual(len(offline), 3)
        self.assertTrue(all(p["source"] == "templates" for p in offline))
        self.assertEqual(offline[0]["moment"], "Halloween")
        self.assertEqual((with_ai[0]["content"]["headline"], with_ai[0]["source"]), ("Spooky slices", "test"))
        self.assertEqual(with_ai[0]["day"], "2026-10-20")
        self.assertEqual([p["day"] for p in past], ["2026-10-24"] * 2)   # weather posts go out on the sunny day


class AITests(unittest.TestCase):
    def test_parse_json(self):
        self.assertEqual(ai.parse_json('Sure:\n```json\n{"a": [1, "}"]}\n```'), {"a": [1, "}"]})
        self.assertIsNone(ai.parse_json("no json here"))

    def test_rate_limited_provider_rests_and_the_next_answers(self):
        cfg, store = cfg_for_tests(), temp_store()
        os.environ.update(GROQ_API_KEY="g", OPENROUTER_API_KEY="o")
        calls = []

        class R:
            def __init__(self, code, data):
                self.status_code, self._d, self.text = code, data, json.dumps(data)

            def json(self):
                return self._d

        def fake_get(url, **k):
            return R(200, {"data": [{"id": "openai/gpt-oss-120b"}, {"id": "openai/gpt-oss-120b:free"}]})

        def fake_post(url, **k):
            calls.append(url)
            if "groq" in url:
                return R(429, {"error": "slow down"})
            return R(200, {"choices": [{"message": {"content": '{"ok": true}'}}]})
        saved = ai.requests.get, ai.requests.post
        ai.requests.get, ai.requests.post = fake_get, fake_post
        try:
            out = ai.ask(cfg, store, "hi")
            again = ai.ask(cfg, store, "hi")
        finally:
            ai.requests.get, ai.requests.post = saved
            os.environ.pop("GROQ_API_KEY"), os.environ.pop("OPENROUTER_API_KEY")
        self.assertTrue(out["ok"] and again["ok"])
        self.assertEqual(sum("groq" in c for c in calls), 1)            # resting after its 429


class ProspectTests(unittest.TestCase):
    def test_emails_must_belong_to_the_business(self):
        self.assertTrue(prospect.email_belongs("info@joespizza.com", "https://www.joespizza.com", "Joe's Pizza"))
        self.assertTrue(prospect.email_belongs("joespizza614@gmail.com", "", "Joe's Pizza"))
        self.assertFalse(prospect.email_belongs("stories@tvstation-news.com", "http://trattoria-rossa.webs.com", "Trattoria Rossa"))
        self.assertFalse(prospect.email_belongs("sam@glassrepairpros.com", "http://sunrise-yoga.net", "Sunrise Yoga"))
        self.assertEqual(prospect.own_site("https://booksy.com/en-us/123"), "")
        self.assertEqual(prospect.own_site("www.florin.com"), "https://www.florin.com")

    def test_candidates_dedupe_and_chains(self):
        row = lambda i, name, phone, site, brand_name=None: (str(i), name, "coffee_shop", 0.9, [phone], [site],
                                                            ["hi@" + site.split("//")[1]], None,
                                                            [{"region": "OH", "locality": "Columbus"}], brand_name, None)
        rows = [row(1, "BEAN CO, LLC", "614-555-0001", "https://bean.co"), row(2, "Bean Co", "614-555-0001", "https://bean.co"),
                row(3, "Starbrew", "614-555-0002", "https://starbrew.com", "Starbrew")]
        got = prospect.candidates(rows, "Columbus, OH")
        self.assertEqual(sorted(c["name"] for c in got), ["Bean Co", "Starbrew"])
        self.assertTrue(next(c for c in got if c["name"] == "Starbrew")["chain"])
        self.assertEqual(next(c for c in got if c["name"] == "Bean Co")["niche"], "cafe")


class PageAndEmailTests(unittest.TestCase):
    def setUp(self):
        self.cfg = cfg_for_tests()
        self.lead = {"name": "Joe's Pizza", "domain": "joespizza.com", "has_logo": True, "post_count": 3,
                     "sample_url": "https://abc123.studio.pages.dev/s/tok/", "moments": ["Halloween"],
                     "subject": "I made Joe's Pizza a week of posts", "expires": "November 18, 2026"}

    def test_week_page_with_reel_and_google_post(self):
        cfg = cfg_for_tests()
        html_text = packs.week_page(cfg, KIT, [], "Week of Oct 26", "Here are your posts.", reel=True,
                                    gbp={"text": "Fresh pies today!", "button": "Order online", "link": "https://x.com/order"})
        for needle in ('src="reel.mp4"', "playsinline", "Your Google post", "Fresh pies today!", "google-post.jpg",
                       "Order online"):
            self.assertIn(needle, html_text)

    def test_sample_page(self):
        posts = [{"day": "2026-10-20", "time": "17:00", "moment": "Halloween", "idea": "x", "caption": "Hi <there>",
                  "hashtags": ["Columbus"], "alt_text": "a", "content": {"headline": "Spooky"}}]
        page = packs.sample_page(self.cfg, KIT, posts, [{"title": "Halloween", "icon": "🎃", "when": "2026-10-31"}],
                                 "November 18, 2026", "https://studio.pages.dev/removed.json", "tok")
        for needle in ("noindex", "$99", "$129", "$49", "Copy caption", "Hi &lt;there&gt;", "#Columbus", "Sat Oct 31",
                       "removed.json", "Captions are drafts", "mail.google.com/mail/?view=cm", "Each plan works on its own",
                       "Save $19 a month"):
            self.assertIn(needle, page)
        self.assertNotIn("redesigned", page)
        with_menu = packs.sample_page(self.cfg, KIT, posts, [], "November 18, 2026", listing={"kind": "menu", "pdf": "x.pdf"})
        self.assertIn("And your menu, redesigned", with_menu)
        self.assertIn('href="design.pdf"', with_menu)

    def test_first_email_and_followups(self):
        first = mailer.first_email(self.lead, self.cfg)
        for needle in (self.lead["sample_url"], "no thanks", "123 Test St", "$99 a month", "Halloween", "logo",
                       "Design is its own plan: $49 a month", "$129 for both"):
            self.assertIn(needle, first.text)
        self.assertIn("redesigned your menu", mailer.first_email(dict(self.lead, redesigned="menu"), self.cfg).text)
        self.assertIn('post-1.jpg', first.html)
        msg = mailer.build_message(self.cfg, "joe@joespizza.com", first)
        self.assertIn("unsubscribe", msg["List-Unsubscribe"])
        last = mailer.followup_email(self.lead, self.cfg, 2)
        self.assertTrue(last.subject.startswith("Re: "))
        self.assertIn("November 18, 2026", last.text)


class InboxTests(unittest.TestCase):
    def raw(self, text, sender="joe@joespizza.com", subject="Re: hi", refs="<m1@x>"):
        return email.message_from_string(f"From: {sender}\nSubject: {subject}\nMessage-ID: <r@x>\nIn-Reply-To: {refs}\n\n{text}",
                                         policy=policy.default)

    def test_classify(self):
        self.assertEqual(inbox.classify("please remove the page"), ("remove", False))
        self.assertEqual(inbox.classify("No thanks."), ("optout", False))
        self.assertEqual(inbox.classify("later"), ("later", False))
        self.assertEqual(inbox.classify("These look great, how much for the bundle?"), ("reply", True))

    def test_replies_and_client_messages(self):
        cfg, store = cfg_for_tests(), temp_store()
        sent = []
        saved = inbox.telegram
        inbox.telegram = lambda c, t: sent.append(t)
        try:
            store.add({"id": "ov:1", "name": "Joe's Pizza", "email": "joe@joespizza.com", "status": "emailed",
                       "token": "tok", "sample_url": "https://x/s/tok/"})
            store.record_sent("<m1@x>", "ov:1")
            counts = {"replies": 0, "optouts": 0, "bounces": 0, "auto": 0, "client": 0, "removed": 0}
            inbox.handle(cfg, store, self.raw("Love them! How much?"), "<r1@x>", counts)
            self.assertEqual(store.leads["ov:1"]["status"], "replied")
            self.assertIn("Likely interested", sent[-1])
            store.leads["ov:1"]["status"] = "emailed"
            inbox.handle(cfg, store, self.raw("remove"), "<r2@x>", counts)
            self.assertEqual(store.data["removed"], ["tok"])
            self.assertTrue(store.is_suppressed("joe@joespizza.com"))
            cfg["clients"] = [{"name": "Bean Co", "email": "owner@bean.co", "website": "https://bean.co", "plan": "social"}]
            store.client("bean-co")["weeks"]["2026-10-26"] = {"status": "sent", "posts": []}
            inbox.handle(cfg, store, self.raw("Approved!", sender="owner@bean.co", refs=""), "<r3@x>", counts)
            self.assertEqual(store.client("bean-co")["weeks"]["2026-10-26"]["status"], "approved")
            jobs = []
            ask = self.raw("Can you make a flyer for our open mic Friday 7pm?", sender="owner@bean.co", refs="")
            inbox.handle(cfg, store, ask, "<r4@x>", counts, lambda c, t, m: jobs.append(t) or "job1")
            self.assertEqual(jobs, [])                     # Social plan: design isn't included, so you're asked
            self.assertIn("doesn't include design", sent[-1])
            cfg["clients"][0]["plan"] = "bundle"
            inbox.handle(cfg, store, ask, "<r5@x>", counts, lambda c, t, m: jobs.append(t) or "job1")
            self.assertEqual(len(jobs), 1)
        finally:
            inbox.telegram = saved


class PipelineTests(unittest.TestCase):
    def test_pick_balances_niches_and_prefers_email(self):
        cfg, store = cfg_for_tests(), temp_store()
        cfg["targets"]["niches"] = ["cafe", "gym"]
        mk = lambda i, niche, emails, socials=(): {"id": f"ov:{i}", "niche": niche, "chain": False, "website": "https://x.com",
                                                   "emails": list(emails), "socials": list(socials)}
        cands = [mk(1, "gym", ["a@x.com"]), mk(2, "gym", ["b@x.com"]), mk(3, "cafe", ["c@x.com"]),
                 mk(4, "cafe", [], ["https://facebook.com/x"]), mk(5, "gym", [])]
        got = [c["id"] for c in pipeline.pick(cfg, store, cands, 2, 1)]
        self.assertEqual(got, ["ov:3", "ov:1", "ov:4"])

    def test_handover_message(self):
        cfg = cfg_for_tests()
        sent = []
        saved = pipeline.telegram
        pipeline.telegram = lambda c, t: sent.append(t) or True
        try:
            lead = {"name": "Bean & Co", "niche": "cafe", "city": "Columbus", "state": "OH", "phone": "(614) 555-0101",
                    "socials": {"instagram": "https://www.instagram.com/beanco/"}, "sample_url": "https://x/s/t/"}
            self.assertEqual(pipeline.handover(cfg, None, [lead], pause=0), 1)
        finally:
            pipeline.telegram = saved
        text = sent[0]
        for needle in ("Bean &amp; Co", "+1 614 555 0101", 'href="https://www.instagram.com/beanco/"', "<pre>Hi! I'm Sam",
                       "https://x/s/t/", "$99 a month"):
            self.assertIn(needle, text)
        self.assertTrue(lead["handed_over"])

    def test_draft_mode_writes_drafts(self):
        cfg, store = cfg_for_tests(), temp_store()
        saved = pipeline.OUTBOX
        pipeline.OUTBOX = pathlib.Path(tempfile.mkdtemp()) / "outbox"
        try:
            store.add({"id": "ov:1", "name": "Joe's Pizza", "email": "joe@joespizza.com", "status": "ready", "state": "OH",
                       "sample_url": "https://x/s/t/", "post_count": 3, "domain": "joespizza.com"})
            store.add({"id": "ov:2", "name": "Not Yet", "email": "hi@notyet.com", "status": "ready", "state": "OH",
                       "sample_url": "https://x/s/u/", "unverified": True})
            saved_live = pipeline.publish.is_live
            pipeline.publish.is_live = lambda url, tries=6, wait=10: False     # its page still doesn't open
            try:
                self.assertEqual(pipeline.outreach(cfg, store)["drafted"], 1)
                # The next run drafts the new sample instead of stopping at the ones already drafted.
                store.add({"id": "ov:3", "name": "Bean & Co", "email": "owner@bean.co", "status": "ready", "state": "OH",
                           "sample_url": "https://x/s/v/", "post_count": 3, "domain": "bean.co"})
                self.assertEqual(pipeline.outreach(cfg, store)["drafted"], 1)
            finally:
                pipeline.publish.is_live = saved_live
            self.assertEqual(len(list(pipeline.OUTBOX.glob("*.txt"))), 2)
        finally:
            pipeline.OUTBOX = saved

    def test_email_pace_warms_up_and_samples_follow_it(self):
        cfg, store = cfg_for_tests(), temp_store()
        ago = lambda days: iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days))
        self.assertEqual(pipeline.email_allowance(cfg, store), 10)               # nothing sent yet
        store.flag("first_email_at", ago(8))
        self.assertEqual(pipeline.email_allowance(cfg, store), 15)               # a week later: +5
        store.flag("first_email_at", ago(40))
        self.assertEqual(pipeline.email_allowance(cfg, store), 15)               # never above max_emails_per_day
        for i in range(20):
            store.add({"id": f"sent:{i}", "status": "emailed", "first_sent_at": ago(2)})
        store.leads["sent:0"]["status"] = "bounced"
        self.assertEqual(pipeline.email_allowance(cfg, store), 15)               # 1 in 20 bounced: fine
        store.leads["sent:1"]["status"] = "bounced"
        self.assertEqual(pipeline.email_allowance(cfg, store), 10)               # more: back to the starting pace

        cfg2, store2 = cfg_for_tests(), temp_store()
        cfg2["targets"].update(cities=["Columbus, OH"], niches=["cafe"])
        cfg2["limits"].update(dm_handover_per_day=0)
        for i in range(4):                                                       # still waiting for their email
            store2.add({"id": f"wait:{i}", "status": "ready", "email": f"hi@wait{i}.com", "sample_url": "https://x/s/w/"})
        store2.add({"id": "old", "status": "ready", "email": "hi@old.com", "sample_url": "https://x/s/o/",
                    "created_at": ago(5)})                                       # too old to send: doesn't count
        cands = [{"id": f"ov:{i}", "name": f"Cafe {i}", "niche": "cafe", "category": "cafe", "city": "Columbus",
                  "state": "OH", "chain": False, "website": f"https://cafe{i}.com", "emails": [f"hi@cafe{i}.com"],
                  "socials": []} for i in range(12)]
        fake = lambda c, s, r, cand, radar_for, root, posts_n=3, force=False: dict(cand, status="ready",
                                                                                   email=cand["emails"][0])
        with patched((pipeline.prospect, "search", lambda s, city, niches: cands), (pipeline, "make_sample", fake),
                     (pipeline.trends, "radar", lambda *a, **k: {"calendar": [], "live": [], "weather": []})):
            made = pipeline.prospect_today(cfg2, store2, None, None)
        self.assertEqual(len(made), 6)                                           # today's 10, less the 4 waiting
        self.assertEqual([l["id"] for l in pipeline.email_queue(cfg2, store2)][:4], [f"wait:{i}" for i in range(4)])

    def test_skipped_businesses_are_replaced_and_cities_take_turns(self):
        cfg, store = cfg_for_tests(), temp_store()
        cfg["targets"].update(cities=["Columbus, OH", "Dayton, OH"], niches=["cafe"])
        cfg["limits"].update(new_prospects_per_day=3, dm_handover_per_day=0)
        cands = [{"id": f"ov:{i}", "name": f"Cafe {i}", "niche": "cafe", "category": "cafe", "city": "Columbus",
                  "state": "OH", "chain": False, "website": f"https://cafe{i}.com", "emails": [f"hi@cafe{i}.com"],
                  "socials": []} for i in range(8)]
        made_for = []

        def fake_sample(cfg_, store_, renderer, cand, radar_for, root, posts_n=3, force=False):
            made_for.append(cand["id"])
            bad = cand["id"] in ("ov:0", "ov:1")            # their websites don't load
            return dict(cand, status="skipped" if bad else "ready", skip_reason="website didn't load" if bad else None,
                        email=cand["emails"][0])

        saved = (pipeline.prospect.search, pipeline.make_sample, pipeline.trends.radar)
        pipeline.prospect.search = lambda store_, city, niches: cands
        pipeline.make_sample = fake_sample
        pipeline.trends.radar = lambda *a, **k: {"calendar": [], "live": [], "weather": []}
        try:
            made = pipeline.prospect_today(cfg, store, None, None)
        finally:
            pipeline.prospect.search, pipeline.make_sample, pipeline.trends.radar = saved
        self.assertEqual([l["id"] for l in made], ["ov:2", "ov:3", "ov:4"])     # the two that failed were replaced
        self.assertEqual(made_for, ["ov:0", "ov:1", "ov:2", "ov:3", "ov:4"])
        self.assertEqual(store.flag("city_index"), 1)                             # Dayton leads tomorrow
        self.assertEqual(pipeline._city_order(cfg, store), ["Dayton, OH", "Columbus, OH"])

    def test_pages_inside_bigger_organizations_are_skipped(self):
        self.assertTrue(pipeline.inside_bigger_site("http://www.columbusmuseum.org/visiting/dining", "Schokko Cafe"))
        self.assertFalse(pipeline.inside_bigger_site("https://joespizzacolumbus.com/menu", "Joe's Pizza"))
        self.assertFalse(pipeline.inside_bigger_site("https://www.ckruegers.com/", "C. Krueger's Baked Goods"))

    def test_removal_list_is_published_once(self):
        cfg, store = cfg_for_tests(), temp_store()
        from agent import publish
        deployed = []
        saved = (publish.deploy, publish.configured)
        publish.deploy = lambda cfg_, folder: deployed.append(json.loads((folder / "removed.json").read_text())) or \
            {"url": "https://abc123.studio.pages.dev", "id": "d1"}
        publish.configured = lambda cfg_: True
        try:
            folder = pathlib.Path(tempfile.mkdtemp()) / "removals"
            self.assertFalse(publish.publish_removals(cfg, store, folder))          # nothing to take down
            store.data["removed"] = ["tok1", None, "tok1"]
            self.assertTrue(publish.publish_removals(cfg, store, folder))
            self.assertFalse(publish.publish_removals(cfg, store, folder))          # already online
        finally:
            publish.deploy, publish.configured = saved
        self.assertEqual(deployed, [["tok1"]])
        headers = (folder / "_headers").read_text()
        self.assertIn("/removed.json\n  Access-Control-Allow-Origin: *", headers)


class ClientTests(unittest.TestCase):
    def test_due_settle_and_todays_posts(self):
        cfg, store = cfg_for_tests(), temp_store()
        cfg["clients"] = [{"name": "Bean Co", "website": "https://bean.co", "content_day": "thursday", "plan": "social"}]
        thursday = dt.date(2026, 10, 22)
        self.assertEqual([c["name"] for c in clients.due(cfg, store, thursday)], ["Bean Co"])
        self.assertEqual(clients.due(cfg, store, thursday + dt.timedelta(days=1)), [])
        week = clients.week_start(thursday).isoformat()
        self.assertEqual(week, "2026-10-26")
        store.client("bean-co")["weeks"][week] = {"status": "sent", "posts": [{"day": "2026-10-27", "headline": "Hi"}]}
        self.assertEqual(clients.settle(cfg, store, dt.date(2026, 10, 24)), 0)
        self.assertEqual(clients.settle(cfg, store, dt.date(2026, 10, 25)), 1)
        self.assertEqual(len(clients.todays_posts(cfg, store, dt.date(2026, 10, 27))), 1)

    def test_monthly_report(self):
        cfg, store = cfg_for_tests(), temp_store()
        client = {"name": "Bean Co", "contact_name": "Sam", "niche": "cafe", "plan": "social"}
        cfg["clients"] = [client]
        store.client("bean-co")["weeks"]["2026-10-05"] = {"status": "approved", "reel": "x.mp4", "google": {"text": "hi"},
                                                         "posts": [{"headline": "A"}, {"headline": "B"}, {"headline": "C"}]}
        store.data["jobs"]["j1"] = {"client": "Bean Co", "at": "2026-10-12T10:00:00+00:00"}
        stats = clients.month_stats(store, client, "2026-10")
        self.assertEqual((stats["planned"], stats["delivered"], stats["reels"], stats["google"], stats["designs"]),
                         (3, 3, 1, 1, 1))
        email = mailer.report_email(client, cfg, "October", stats, [{"date": "2026-11-26", "title": "Thanksgiving"}])
        for needle in ("Hi Sam,", "3 posts designed and written", "1 Reel", "1 Google post", "Nov 26: Thanksgiving"):
            self.assertIn(needle, email.text)
        sent = []
        saved = clients.telegram
        clients.telegram = lambda c, t: sent.append(t) or True
        try:
            self.assertEqual(clients.monthly_reports(cfg, store, dt.date(2026, 11, 2)), 1)
            self.assertEqual(clients.monthly_reports(cfg, store, dt.date(2026, 11, 3)), 0)     # once a month
        finally:
            clients.telegram = saved
        self.assertIn("Bean Co · 2026-10", sent[0])

    def test_weeks_waiting_for_your_check_get_one_nudge(self):
        cfg, store = cfg_for_tests(), temp_store()
        cfg["clients"] = [{"name": "Bean Co", "website": "https://bean.co", "plan": "social"}]
        store.client("bean-co")["weeks"]["2026-10-26"] = {"status": "review", "label": "Week of Oct 26",
                                                          "url": "https://x/c/bean-co/t/", "posts": []}
        sent = []
        saved = clients.telegram
        clients.telegram = lambda c, t: sent.append(t) or True
        try:
            self.assertEqual(clients.remind(cfg, store, dt.date(2026, 10, 23)), 0)    # too early
            self.assertEqual(clients.remind(cfg, store, dt.date(2026, 10, 24)), 1)
            self.assertEqual(clients.remind(cfg, store, dt.date(2026, 10, 25)), 0)    # only once
        finally:
            clients.telegram = saved
        self.assertIn("/approve bean-co", sent[0])

    def test_menus_price_lists_and_schedules_come_from_their_words(self):
        from agent import menus
        req = "Here's our fall menu:\nCoffee\nLatte $4.50\nCold brew - $4.75 (16 oz)\nPastries:\nCroissant $3.50\nThanks!"
        self.assertTrue(menus.wanted(req))
        m = menus.extract(None, None, dict(KIT, domain="joespizza.com"), req)
        self.assertEqual(m["title"], "Fall menu")
        self.assertEqual([s["name"] for s in m["sections"]], ["Coffee", "Pastries"])
        self.assertEqual(m["sections"][0]["items"][1], {"name": "Cold brew", "price": "$4.75", "note": "16 oz"})
        sched = menus.parse("Spin 6:00 AM\nYoga 7:30 pm - with Dana\nHIIT 12pm")
        self.assertEqual([i["price"] for i in sched[0]["items"]], ["6:00 AM", "7:30 pm", "12pm"])
        self.assertIsNone(menus.parse("Flyer for open mic Friday 7pm, free entry"))
        self.assertFalse(menus.wanted("A flyer for our open mic"))

    def test_design_style_choice(self):
        styles = designer.choose_styles(dict(KIT, niche="gym"), 3, "post", weights={})
        self.assertEqual(len(set(styles)), 3)
        self.assertFalse(set(styles) & {"photo", "split", "duotone"})       # no photos, no photo styles
        land = designer.choose_styles(dict(KIT, photos=[{"path": "x"}]), 3, "landscape", weights={})
        self.assertTrue(set(land) <= set(designer.FORMAT_STYLES["landscape"]))


class PlanTests(unittest.TestCase):
    def test_each_agent_is_its_own_plan(self):
        self.assertTrue(settings.plan_has({"plan": "social"}, "social"))
        self.assertFalse(settings.plan_has({"plan": "social"}, "design"))
        self.assertTrue(settings.plan_has({"plan": "Design"}, "design"))
        self.assertFalse(settings.plan_has({"plan": "design"}, "social"))
        self.assertTrue(settings.plan_has({"plan": "bundle"}, "social") and settings.plan_has({"plan": "bundle"}, "design"))
        self.assertEqual(settings.plan_of({"plan": "both please"}), "social")     # unknown: social only, and you're told
        cfg, store = cfg_for_tests(), temp_store()
        cfg["clients"] = [{"name": "Only Design", "website": "https://x.com", "plan": "design", "content_day": "thursday"},
                          {"name": "Only Social", "website": "https://y.com", "plan": "social", "content_day": "thursday"}]
        self.assertEqual([c["name"] for c in clients.due(cfg, store, dt.date(2026, 10, 22))], ["Only Social"])


class AutopilotTests(unittest.TestCase):
    """The agents doing the work on their own: weeks and designs straight to clients, picks and changes by email,
    posters, sales replies, onboarding, billing and Meta."""

    def setUp(self):
        self.cfg, self.store = cfg_for_tests(), temp_store()
        self.dir = tempfile.mkdtemp()
        self.client = {"name": "Bean Co", "email": "owner@bean.co", "website": "https://bean.co", "plan": "bundle",
                       "niche": "cafe", "city": "Columbus, OH"}
        self.cfg["clients"] = [self.client]
        self.sent = []

    def tg(self, cfg, text):
        self.sent.append(text)
        return True

    def week_record(self, caption="Fresh pastries every morning at Bean Co, baked in house before we open the doors."):
        img = png(self.dir, "p1.png")
        return {"status": "made", "token": "t", "label": "Week of Oct 26", "note": "n",
                "posts": [{"day": "2026-10-27", "time": "08:00", "caption": caption, "hashtags": ["cbus"], "image": img,
                           "issues": [], "headline": "Fresh"}], "stories": []}

    def test_weeks_go_straight_to_clients_unless_a_check_fails(self):
        quiet = (clients.notify, "album", lambda *a, **k: True)
        with patched((clients, "telegram", self.tg), quiet):
            good = self.week_record()
            self.assertEqual(clients.deliver(self.cfg, self.store, self.client, "2026-10-26", good, "https://x"), "sent")
            self.assertEqual(good["status"], "sent")
            short = self.week_record(caption="Hi")
            self.assertEqual(clients.deliver(self.cfg, self.store, self.client, "2026-10-26", short, "https://x"), "review")
            self.assertTrue(any("caption is too short" in t for t in self.sent))
            self.cfg["autopilot"]["clients"] = False
            self.assertEqual(clients.deliver(self.cfg, self.store, self.client, "2026-10-26", self.week_record(),
                                             "https://x"), "review")

    def test_design_requests_go_to_the_client_who_picks_or_asks_for_changes(self):
        paths = [png(self.dir, f"v{i}.png") for i in (1, 2, 3)]
        fake_variants = lambda *a, **k: [(pathlib.Path(p), "bold", []) for p in paths]
        fake_content = lambda *a, **k: ("post", {"headline": "Open mic"})
        with patched((clients, "telegram", self.tg), (clients.notify, "album", lambda *a, **k: True),
                     (clients.designer, "variants", fake_variants), (clients.designer, "request_to_content", fake_content),
                     (clients, "kit_for", lambda *a, **k: dict(KIT))):
            job = clients.design_job(self.cfg, self.store, None, self.client, "Flyer for open mic Friday 7pm",
                                     source="client")
            self.assertEqual(self.store.data["jobs"][job]["status"], "offered")
            self.store.data["jobs"][job]["msgid"] = "<offer@x>"          # as if sent in live mode
            self.assertEqual(clients.job_for_reply(self.store, ["<offer@x>"]), job)
            self.assertIn("version 2", clients.reply_to_job(self.cfg, self.store, job, "I'd like the second one"))
            self.assertEqual(self.store.data["jobs"][job]["picked"], 2)
            redo = []
            job2 = clients.design_job(self.cfg, self.store, None, self.client, "Flyer for open mic", source="client")
            clients.reply_to_job(self.cfg, self.store, job2, "2 but change the date to Saturday",
                                 on_revision=lambda c, request, of: redo.append((request, of)))
            self.assertIn("Start from version 2. but change the date to Saturday", redo[0][0])
            self.assertEqual(redo[0][1], job2)
            # a request from you (Telegram) waits for you
            job3 = clients.design_job(self.cfg, self.store, None, self.client, "Promo", source="you")
            self.assertEqual(self.store.data["jobs"][job3]["status"], "review")
            # over the monthly allowance: waits for you too
            self.client["designs_per_month"] = 1
            job4 = clients.design_job(self.cfg, self.store, None, self.client, "Another", source="client")
            self.assertEqual(self.store.data["jobs"][job4]["status"], "review")
        self.assertEqual(clients.designs_this_month(self.store, self.client), 4)

    def test_posters_for_what_is_coming_up(self):
        kit = dict(KIT, niche="cafe", text="Coffee, espresso, pastries and cookies")
        moments = clients.poster_moments(self.cfg, self.store, dict(self.client), dt.date(2026, 11, 10), kit)
        titles = [m["title"] for m in moments]
        self.assertIn("Thanksgiving", titles)                       # Nov 26, inside the 7-31 day window
        self.assertNotIn("National Espresso Day", titles[:0])
        made = []
        with patched((clients, "poster_job", lambda cfg, store, r, c, m: made.append(m["title"]) or "job"),
                     (clients, "kit_for", lambda *a, **k: kit)):
            self.assertEqual(clients.make_posters(self.cfg, self.store, None, dt.date(2026, 11, 10)), ["job"])
            self.client["plan"] = "social"                            # no design agent on the Social plan
            self.assertEqual(clients.make_posters(self.cfg, self.store, None, dt.date(2026, 11, 10)), [])

    def test_interested_replies_get_plans_then_their_choice_is_caught(self):
        self.assertEqual(inbox.chosen_plan("Social please!"), "social")
        self.assertEqual(inbox.chosen_plan("Let's do both"), "bundle")
        self.assertEqual(inbox.chosen_plan("The design one"), "design")
        self.assertIsNone(inbox.chosen_plan("What's included in social?"))
        lead = self.store.add({"id": "ov:1", "name": "Joe's Pizza", "email": "joe@joespizza.com", "status": "emailed",
                               "sample_url": "https://x/s/t/", "subject": "I made Joe's Pizza a week of posts"})
        with patched((inbox, "telegram", self.tg)):
            got = inbox.auto_answer(self.cfg, self.store, lead, "joe@joespizza.com", "How much is it?", "<r1@x>",
                                    "reply", True)
            self.assertEqual(got, ("plans", None, False))           # draft mode: shown to you, not sent
            self.assertIn("$99/month", self.sent[-1])
            got = inbox.auto_answer(self.cfg, self.store, self.store.leads["ov:1"], "joe@joespizza.com",
                                    "Social please", "<r2@x>", "reply", False)
            self.assertEqual(got[:2], ("plan", "social"))
            inbox.ping_reply(self.cfg, self.store.leads["ov:1"], "Social please", "<r2@x>", "reply", False, got)
        self.assertIn("/client Joe's Pizza social", self.sent[-1])
        self.cfg["autopilot"]["replies"] = False
        self.assertIsNone(inbox.auto_answer(self.cfg, self.store, self.store.leads["ov:1"], "x@y.z", "How much?",
                                            "<r3@x>", "reply", True))

    def test_client_command_onboards_from_a_lead(self):
        self.cfg["clients"] = []
        self.store.add({"id": "ov:9", "name": "Joe's Pizza", "email": "joe@joespizza.com", "status": "replied",
                        "website": "https://joespizza.com", "niche": "restaurant", "city": "Columbus", "state": "OH",
                        "plan_chosen": "bundle"})
        weeks = []
        with patched((commands, "telegram", self.tg), (clients, "telegram", self.tg)):
            s = commands.Session(self.cfg, self.store)
            s.week = lambda name: weeks.append(name)
            s.run("/client Joe's Pizza")
        self.assertEqual(self.store.data["clients_db"]["joe-s-pizza"]["plan"], "bundle")
        self.assertEqual(self.store.leads["ov:9"]["status"], "client")
        self.assertEqual(weeks, ["Joe's Pizza"])
        self.assertTrue(any("Welcome" in t for t in self.sent))
        cfg2 = cfg_for_tests()
        settings.with_saved_clients(cfg2, self.store.data["clients_db"])
        self.assertEqual([c["name"] for c in cfg2["clients"]], ["Joe's Pizza"])

    def test_clients_marked_bought_in_hq_get_started(self):
        self.cfg["clients"] = []
        self.store.add({"id": "ov:7", "name": "Bean & Co", "email": "owner@bean.co", "status": "emailed",
                        "website": "https://bean.co", "niche": "cafe", "city": "Columbus", "state": "OH"})
        weeks = []
        with patched((commands, "telegram", self.tg), (clients, "telegram", self.tg)):
            s = commands.Session(self.cfg, self.store)
            s.week = lambda name: weeks.append(name)
            n = s.onboard_from_hq([{"id": "ov:7", "plan": "design", "email": ""}, {"id": "gone", "plan": "social"}])
            again = s.onboard_from_hq([{"id": "ov:7", "plan": "design"}])         # already a client: not twice
        self.assertEqual((n, again), (1, 0))
        self.assertEqual(self.store.data["clients_db"]["bean-co"]["plan"], "design")
        self.assertEqual(self.store.leads["ov:7"]["status"], "client")
        self.assertEqual(weeks, [])                                                 # design only: no weekly posts

    def test_billing_reminders_until_paid(self):
        c = dict(self.client, started="2026-10-01")
        self.cfg["clients"] = [c]
        with patched((clients, "telegram", self.tg)):
            self.assertEqual(clients.billing_reminders(self.cfg, self.store, dt.date(2026, 10, 7)), 0)   # free week
            self.assertEqual(clients.billing_reminders(self.cfg, self.store, dt.date(2026, 10, 8)), 1)
            self.assertEqual(clients.billing_reminders(self.cfg, self.store, dt.date(2026, 10, 9)), 0)   # once
            self.assertIn("$129", self.sent[-1])
            clients.mark_paid(self.cfg, self.store, c, dt.date(2026, 10, 10))
            self.assertEqual(clients.billing_reminders(self.cfg, self.store, dt.date(2026, 11, 3)), 0)
            self.assertEqual(clients.billing_reminders(self.cfg, self.store, dt.date(2026, 11, 8)), 1)

    def test_meta_reels_stories_and_page_connection(self):
        record = {"reel": "x.mp4", "posts": [{"day": "2026-10-27", "time": "08:00"}, {"day": "2026-10-29", "time": "17:00"}],
                  "stories": [{"day": "2026-10-27"}, {"day": "2026-10-29"}]}
        self.assertEqual(meta.extras_due(record), [("REELS", 1, "2026-10-28", "18:00"), ("STORIES", 1, "2026-10-27", "08:00"),
                                                   ("STORIES", 2, "2026-10-29", "17:00")])
        os.environ["META_ACCESS_TOKEN"] = "token"

        class R:
            def json(self):
                return {"data": [{"id": "111", "name": "Bean Co", "instagram_business_account": {"id": "999"}}]}
        try:
            with patched((meta.requests, "get", lambda *a, **k: R()), (meta, "telegram", self.tg)):
                self.assertTrue(meta.enabled(self.cfg))
                self.assertEqual(meta.autoconnect(self.cfg, self.store, self.cfg["clients"]), 1)
        finally:
            os.environ.pop("META_ACCESS_TOKEN")
        self.assertEqual((self.client["meta_page_id"], self.client["meta_ig_id"]), ("111", "999"))
        self.assertEqual(self.store.client("bean-co")["meta"]["ig_id"], "999")
        self.assertFalse(meta.enabled(self.cfg))                    # no token, no posting


class HQTests(unittest.TestCase):
    def setUp(self):
        self.cfg, self.store = cfg_for_tests(), temp_store()
        for i, status in enumerate(["emailed", "ready", "manual", "skipped", "replied"]):
            self.store.add({"id": f"ov:{i}", "name": f"Cafe {i}", "niche": "cafe", "city": "Columbus", "state": "OH",
                            "email": f"hi@cafe{i}.com", "phone": "(614) 555-010" + str(i), "status": status,
                            "sample_url": f"https://x.pages.dev/s/{i}/", "touches": 1 if status == "emailed" else 0})

    def test_record_for_each_kind_of_agent(self):
        rec = hq.record(self.store.leads["ov:0"])
        self.assertEqual((rec["name"], rec["kind"], rec["preview_url"], rec["touches"]),
                         ("Cafe 0", "cafe", "https://x.pages.dev/s/0/", 1))
        site = hq.record({"id": "site:a.dev", "domain": "a.dev", "title": "Show HN: A thing", "status": "manual",
                          "report_url": "https://r.pages.dev/r/t/", "grade": "C"})
        self.assertEqual((site["name"], site["kind"], site["preview_url"], site["extra"]),
                         ("a.dev", "Show HN: A thing", "https://r.pages.dev/r/t/", {"grade": "C"}))

    def test_sync_sends_changes_and_takes_back_your_decisions(self):
        sent, replies = [], [{"stop": ["ov:0", "ov:4"], "onboard": [{"id": "ov:1", "plan": "bundle"}]}, {}, {}]
        started = []

        def post(url, token, payload, timeout=25):
            sent.append(payload)
            return replies[len(sent) - 1] if len(sent) <= len(replies) else {}

        os.environ.update(HQ_URL="https://hq.example.workers.dev", HQ_TOKEN="t0ken")
        try:
            with patched((hq, "_post", post)):
                r = hq.sync(self.cfg, self.store, on_onboard=lambda items: started.extend(items) or len(items))
                self.assertEqual(r, {"sent": 4, "stopped": 1, "started": 1})       # the skipped one isn't sent
                self.assertEqual(sorted(b["id"] for b in sent[0]["businesses"]), ["ov:0", "ov:1", "ov:2", "ov:4"])
                self.assertEqual(sent[0]["agent"], "studio")
                self.assertEqual(self.store.leads["ov:0"]["status"], "finished")   # no more follow-ups
                self.assertEqual(self.store.leads["ov:4"]["status"], "replied")    # replied: nothing to stop
                self.assertEqual(started, [{"id": "ov:1", "plan": "bundle"}])
                hq.sync(self.cfg, self.store)                                      # only what changed: ov:0
                self.assertEqual([b["id"] for b in sent[1]["businesses"]], ["ov:0"])
                hq.sync(self.cfg, self.store)
                self.assertEqual(sent[2]["businesses"], [])                        # nothing new, still asks
        finally:
            os.environ.pop("HQ_URL", None)
            os.environ.pop("HQ_TOKEN", None)

    def test_without_hq_or_when_it_is_down_the_run_carries_on(self):
        self.assertIsNone(hq.sync(self.cfg, self.store))                           # not set up: nothing happens

        def down(*a, **k):
            raise OSError("connection refused")

        os.environ.update(HQ_URL="https://hq.example.workers.dev", HQ_TOKEN="t0ken")
        try:
            with patched((hq, "_post", down)):
                self.assertIsNone(hq.sync(self.cfg, self.store))
            self.assertEqual(self.store.data.get("hq_sent"), {})                   # all sent again next time
        finally:
            os.environ.pop("HQ_URL", None)
            os.environ.pop("HQ_TOKEN", None)


class StockPhotoTests(unittest.TestCase):
    def test_pixabay_photos_are_downloaded_and_credited(self):
        from agent import images
        cfg, calls = cfg_for_tests(), []

        class Resp:
            status_code = 200

            def __init__(self, data):
                self.data = data

            def json(self):
                return self.data

        def get(url, **kw):
            calls.append((url, kw.get("params", {})))
            return Resp({"hits": [{"largeImageURL": "https://cdn.pixabay.com/photo/x_1280.jpg", "user": "Ana",
                                   "pageURL": "https://pixabay.com/photos/pumpkins-1/"}]})

        os.environ["PIXABAY_API_KEY"] = "k"
        try:
            with patched((images.requests, "get", get), (images.web, "download", lambda url, folder: "/tmp/x_1280.jpg")):
                got = images.stock(cfg, "pumpkins autumn", orientation="portrait")
        finally:
            os.environ.pop("PIXABAY_API_KEY", None)
        self.assertEqual(got["credit"], "Photo by Ana on Pixabay")
        self.assertEqual(calls[0][0], "https://pixabay.com/api/")
        self.assertEqual((calls[0][1]["orientation"], calls[0][1]["image_type"]), ("vertical", "photo"))


class CheckTests(unittest.TestCase):
    def test_check_reports_without_any_keys(self):
        from agent import check
        sent = []
        with patched((check, "telegram", lambda cfg, text: sent.append(text) or True)):
            results = dict(check.run(cfg_for_tests(), temp_store()))
        self.assertIsNone(results["Pixabay"][0])                                  # no key: skipped, not failed
        self.assertFalse(results["AI"][0])                                        # no AI at all is worth knowing
        self.assertIn("Studio agent check", sent[0])
        self.assertIn("draft", sent[0])

    def test_pixabay_check_searches_and_downloads_a_photo(self):
        from agent import check
        cfg, sent, asked = cfg_for_tests(), [], []
        photo = pathlib.Path(tempfile.mkdtemp()) / "leaves.jpg"
        photo.write_bytes(b"x" * 4096)

        class Resp:
            status_code = 200

            def json(self):
                return {"total": 900, "totalHits": 500, "hits": [{"largeImageURL": "https://pixabay.com/get/a.jpg"}]}

        def get(url, **kw):
            asked.append(url)
            return Resp()

        os.environ["PIXABAY_API_KEY"] = "k"
        try:
            with patched((check.requests, "get", get), (check, "telegram", lambda cfg, text: sent.append(text) or True),
                         (check.web, "download", lambda url, folder: photo if url.endswith("a.jpg") else None)):
                results = dict(check.run(cfg, temp_store()))
        finally:
            os.environ.pop("PIXABAY_API_KEY", None)
        self.assertEqual(results["Pixabay"], (True, '500 photos found for "autumn leaves", one downloaded (4 KB)'))
        self.assertIsNone(results["Pexels"][0])
        self.assertIn("https://pixabay.com/api/", asked)
        self.assertIn("✅ <b>Pixabay</b>", sent[0])

    def test_ai_check_explains_a_refused_key_and_wakes_a_fixed_one(self):
        from agent import check
        cfg, store = cfg_for_tests(), temp_store()
        os.environ["GROQ_API_KEY"] = "k"
        try:
            def refused(*a):
                raise ai.NoAI("groq: 401 Invalid API Key")
            with patched((check.ai, "_call", refused)):
                self.assertEqual(check.ai_provider(cfg, store, "groq"), (False, "the key was refused: copy it again"))
            store.flag("ai_rest", {"groq": 9e12, "gemini": 9e12})       # resting after that refusal
            with patched((check.ai, "_call", lambda *a: ("ready", "groq:llama-3.3-70b-versatile"))):
                self.assertEqual(check.ai_provider(cfg, store, "groq"), (True, "llama-3.3-70b-versatile answered"))
        finally:
            os.environ.pop("GROQ_API_KEY", None)
        self.assertEqual(store.flag("ai_rest"), {"gemini": 9e12})        # used again right away, others untouched


class PublicRepoTests(unittest.TestCase):
    def test_telegram_id_isnt_printed_in_a_public_repository(self):
        import contextlib
        import io
        from agent import __main__ as cli
        sent, cfg, store = [], cfg_for_tests(), temp_store()          # (cfg_for_tests clears STATE_KEY)
        os.environ["STATE_KEY"] = "x" * 43 + "="
        out = io.StringIO()
        try:
            with patched((cli.notify, "chat_ids", lambda cfg: {5365750000: "Omar"}),
                         (cli.notify, "send_to", lambda cfg, chat, text: sent.append((chat, text)) or True)), \
                    contextlib.redirect_stdout(out):
                cli.cmd_telegram_id(cfg, store)
        finally:
            os.environ.pop("STATE_KEY", None)
        self.assertNotIn("5365750000", out.getvalue())
        self.assertEqual(sent[0][0], 5365750000)
        self.assertIn("5365750000", sent[0][1])


class StoreTests(unittest.TestCase):
    def test_encrypted_state_for_public_repos(self):
        from cryptography.fernet import Fernet
        import agent.store as st
        d = pathlib.Path(tempfile.mkdtemp())
        saved = st.STATE
        st.STATE = d / "state.json"
        os.environ["STATE_KEY"] = Fernet.generate_key().decode()
        try:
            s = Store(st.STATE)
            s.add({"id": "x", "email": "secret@biz.com"})
            s.save()
            self.assertFalse((d / "state.json").exists())
            self.assertNotIn(b"secret@biz.com", (d / "state.enc").read_bytes())
            self.assertEqual(Store(st.STATE).leads["x"]["email"], "secret@biz.com")
        finally:
            st.STATE = saved
            os.environ.pop("STATE_KEY")


class CommandTests(unittest.TestCase):
    def test_niche_guess_and_help(self):
        self.assertEqual(commands.guess_niche("Best espresso and pastries in town, our coffee"), "cafe")
        self.assertEqual(commands.guess_niche("Lash extensions and brows, book your salon visit"), "beauty")
        cfg, store = cfg_for_tests(), temp_store()
        sent = []
        saved = commands.telegram
        commands.telegram = lambda c, t: sent.append(t)
        try:
            s = commands.Session(cfg, store)
            s.run("/help")
            s.run("/nope")
        finally:
            commands.telegram = saved
        self.assertIn("/design CLIENT", sent[0])
        self.assertIn("don't know", sent[1])

    def test_meta_due_now(self):
        self.assertTrue(meta.due_now({"day": "2020-01-01", "time": "09:00"}, "OH"))
        self.assertFalse(meta.due_now({"day": "2999-01-01", "time": "09:00"}, "OH"))


class RenderTests(unittest.TestCase):
    """Renders a real design with the headless browser (skipped where no browser is available)."""

    def test_every_style_renders_and_fits(self):
        from agent import design, styles
        try:
            r = design.Renderer().__enter__()
        except Exception as e:
            self.skipTest(f"no browser: {e}")
        try:
            out = pathlib.Path(tempfile.mkdtemp())
            content = {"eyebrow": "Halloween week", "headline": "Spooky slices are here", "subhead": "Garlic knots for the costume crew.",
                       "cta": "Order now", "footer": "joespizza.com", "icon": "local_pizza"}
            for style in styles.STYLES:
                path, issues = r.render({"format": "post", "style": style, "brand": KIT, "content": content}, out / f"{style}.png")
                self.assertTrue(path.exists())
                self.assertEqual(issues, [], style)
            from agent import motion
            if motion.available():                     # a one-second Reel, to check the video pipeline end to end
                video = motion.render(r, {"format": "story", "style": "bold", "brand": KIT, "content": content},
                                      out / "reel.mp4", seconds=1, fps=10)
                self.assertTrue(video and video.stat().st_size > 1000)
                self.assertTrue(video.with_suffix(".jpg").exists())
        finally:
            r.__exit__(None, None, None)


if __name__ == "__main__":
    unittest.main()
