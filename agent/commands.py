"""Commands you send the Telegram bot (read on every inbox run):

  a website link            make that business a free sample, and get the link plus a DM to copy
  /sample URL [niche]       the same, with the kind of business (restaurant, cafe, bakery, gym, beauty, shop...)
  /kit URL                  the brand kit (logo, colors, fonts, photos) of any website, as a picture
  /design CLIENT: request   three versions of a design for a client ("/design maple: open mic flyer, Fri 7pm")
                            a menu, price list or class schedule: "/design maple: menu" then one item per
                            line ("Latte $4.50"), or "/design maple: our menu" to use the one on their website
  /send JOB [N]             email a design job to the client: the versions to pick from, or the final files of N
  /week CLIENT              make the client's posts for next week now
  /approve CLIENT           send the posts you checked to the client
  /client NAME PLAN [email] make a business a client (social, design or bundle): welcome email, first posts now.
                            NAME is a business from your leads, or its website
  /paid CLIENT              mark this month as paid (stops the payment reminders)
  /pause CLIENT, /resume CLIENT, /plan CLIENT PLAN
  /trends [City, ST]        what's worth posting about this week
  /status                   counts
  /help                     this list
"""
import datetime as dt
import re

from . import brand, clients, design, designer, notify, packs, pipeline, publish, trends
from .notify import esc, link, telegram
from .settings import CACHE, NICHES, PLANS, SITE, plan_has, plan_of

PLAN_ALIASES = {"social": "social", "design": "design", "bundle": "bundle", "both": "bundle", "all": "bundle"}
from .store import iso

URL = re.compile(r"https?://[^\s<>\"']+|(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?:/[^\s]*)?", re.I)
NICHE_WORDS = {
    "cafe": r"coffee|cafe|café|espresso|tea house|boba|bubble tea|smoothie|juice",
    "bakery": r"bakery|bakeshop|cake|cupcake|donut|doughnut|pastry|patisserie|cookie|bagel|ice cream|gelato|dessert",
    "gym": r"gym|fitness|yoga|pilates|crossfit|boxing|martial arts|personal train|dance studio|barre|spin|cycling class",
    "beauty": r"salon|barber|nail|spa|lash|brow|beauty|hair|wax|massage|esthetic|makeup|tattoo",
    "bar": r"\bbar\b|pub|brewery|taproom|cocktail|wine bar|tavern|lounge",
    "pets": r"groom|pet |dog|cat|kennel|boarding|vet",
    "shop": r"boutique|shop|store|jewelry|florist|flowers|gift|clothing|apparel|candle|books",
    "restaurant": r"restaurant|pizza|grill|kitchen|taco|burger|sushi|bbq|diner|bistro|eatery|menu",
}


def guess_niche(text):
    low = (text or "").lower()
    scores = {n: len(re.findall(w, low)) for n, w in NICHE_WORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else "restaurant"


class Session:
    """One inbox run's commands: a browser only when a design is needed, and one publish at the end."""

    def __init__(self, cfg, store):
        self.cfg, self.store = cfg, store
        self._renderer = None
        self.root = SITE / "commands"
        self.samples, self.weeks = [], []

    @property
    def renderer(self):
        if self._renderer is None:
            self._renderer = design.Renderer().__enter__()
        return self._renderer

    def close(self):
        if self._renderer is not None:
            self._renderer.__exit__(None, None, None)

    # -- commands ------------------------------------------------------------------------------
    def run(self, text):
        t = text.strip()
        cmd, _, rest = t.partition(" ")
        cmd = cmd.lower().split("@")[0]
        try:
            if cmd in ("/help", "/start"):
                telegram(self.cfg, "<pre>" + esc(__doc__.strip()) + "</pre>")
            elif cmd == "/sample" or (not t.startswith("/") and URL.search(t)):
                self.sample(rest if cmd == "/sample" else t)
            elif cmd == "/kit":
                self.kit(rest)
            elif cmd == "/design":
                self.design(rest)
            elif cmd == "/send":
                job, _, pick = rest.strip().partition(" ")
                telegram(self.cfg, esc(clients.send_job(self.cfg, self.store, job, pick.strip() or None)))
            elif cmd == "/week":
                self.week(rest)
            elif cmd == "/approve":
                self.approve(rest)
            elif cmd == "/client":
                self.add_client(rest)
            elif cmd == "/paid":
                self.paid(rest)
            elif cmd in ("/pause", "/resume"):
                self.pause(rest, cmd == "/pause")
            elif cmd == "/plan":
                self.change_plan(rest)
            elif cmd == "/trends":
                self.trends(rest)
            elif cmd == "/status":
                self.status()
            elif t.startswith("/"):
                telegram(self.cfg, "I don't know that command. Send /help for the list.")
        except Exception as e:                           # a failed command shouldn't stop the inbox run
            telegram(self.cfg, f"That didn't work: {esc(str(e)[:300])}")

    def sample(self, text):
        m = URL.search(text or "")
        if not m:
            telegram(self.cfg, "Send the business's website, like: /sample https://example.com cafe")
            return
        url = m.group(0)
        niche = next((n for n in NICHES if re.search(rf"\b{n}\b", text, re.I)), None)
        kit = brand.read(url, niche=niche or "restaurant", budget=45)
        if not kit["ok"]:
            telegram(self.cfg, f"I couldn't read {esc(url)}: {esc(kit.get('problem'))}.")
            return
        niche = niche or guess_niche(kit.get("title", "") + " " + kit.get("text", "")[:3000])
        name = kit.get("name") or kit["domain"]
        cand = {"id": "tg:" + kit["domain"], "name": name, "niche": niche, "category": niche, "city": "", "state": "",
                "phone": kit.get("phone"), "website": kit["website"], "socials": list((kit.get("socials") or {}).values()),
                "emails": [], "maps_url": "", "source": "telegram"}
        lead = pipeline.make_sample(self.cfg, self.store, self.renderer, cand,
                                    lambda city: trends.radar(self.cfg, self.store, city=city or None), self.root,
                                    force=True)
        if lead["status"] == "skipped" and lead.get("skip_reason") != "no email and no social pages to message":
            telegram(self.cfg, f"Skipped {esc(name)}: {esc(lead.get('skip_reason'))}.")
            return
        lead["status"] = "manual" if not lead.get("email") else "ready"
        lead["from_telegram"] = True
        self.store.add(lead)
        self.samples.append(lead)

    def kit(self, text):
        m = URL.search(text or "")
        if not m:
            telegram(self.cfg, "Send a website, like: /kit https://example.com")
            return
        kit = brand.read(m.group(0), niche=guess_niche(text), budget=45)
        if not kit["ok"]:
            telegram(self.cfg, f"I couldn't read it: {esc(kit.get('problem'))}.")
            return
        path = designer.brand_board(self.renderer, kit, CACHE / "boards" / f"{kit['domain']}.png")
        c = kit["colors"]
        notify.photo(self.cfg, path, f"<b>{esc(kit.get('name'))}</b>\nColors: {esc(', '.join(c[r] for r in ('primary', 'secondary', 'accent')))}"
                                     f"\nFonts: {esc(kit['fonts']['heading'])} / {esc(kit['fonts']['body'])}")

    def design(self, text):
        text = (text or "").strip()
        lead_url = URL.match(text)
        if lead_url:                                      # "/design https://cafe.com: menu" (a website, not a client)
            who, request = lead_url.group(0).rstrip(":,.;"), text[lead_url.end():].lstrip(" :\n")
        else:
            who, _, request = text.partition(":")
        client = clients.find(self.cfg, who.strip()) if not lead_url else None
        if not client:
            m = URL.search(who)
            if m:
                client = {"name": brand.web.host_of(m.group(0)), "website": m.group(0), "niche": guess_niche(request)}
        if not client or not request.strip():
            telegram(self.cfg, "Like this: /design maple: flyer for our open mic, Friday 7pm, free entry")
            return
        clients.design_job(self.cfg, self.store, self.renderer, client, request.strip())

    def week(self, text):
        client = clients.find(self.cfg, text.strip())
        if not client:
            telegram(self.cfg, f"No client called {esc(text)} in clients.yaml.")
            return
        if not plan_has(client, "social"):
            telegram(self.cfg, f"{esc(client['name'])} is on the {esc(plan_of(client).title())} plan, which doesn't include "
                               "weekly posts. Change their plan to social or bundle in clients.yaml first.")
            return
        start = clients.week_start()
        record = clients.make_week(self.cfg, self.store, self.renderer, client, self.root, start)
        self.weeks.append((client, start.isoformat(), record))

    def approve(self, text):
        client = clients.find(self.cfg, text.strip())
        if not client:
            telegram(self.cfg, f"No client called {esc(text)} in clients.yaml.")
            return
        book = self.store.client(clients.key_of(client))
        waiting = sorted(w for w, r in book["weeks"].items() if r.get("status") == "review")
        if not waiting:
            telegram(self.cfg, f"Nothing from {esc(client['name'])} is waiting for your check.")
            return
        clients.send_to_client(self.cfg, self.store, client, waiting[-1], book["weeks"][waiting[-1]])
        telegram(self.cfg, f"Sent {esc(client['name'])} their posts for {esc(book['weeks'][waiting[-1]]['label'].lower())}.")

    # -- clients you add and manage from Telegram -----------------------------------------------------------
    def _lead(self, name):
        want = (name or "").strip().lower()
        if not want:
            return None
        leads = sorted(self.store.leads.values(), key=lambda l: (l.get("status") != "replied", l.get("updated_at", "")))
        for lead in leads:
            if want == (lead.get("name") or "").lower() or (lead.get("website") and want in lead["website"].lower()):
                return lead
        return next((l for l in leads if want in (l.get("name") or "").lower()), None)

    def add_client(self, text):
        words = (text or "").split()
        plan = next((PLAN_ALIASES[w.lower()] for w in words if w.lower() in PLAN_ALIASES), None)
        email = next((w.strip("<>,") for w in words if "@" in w), "")
        name = " ".join(w for w in words if w.lower() not in PLAN_ALIASES and "@" not in w).strip()
        if not name:
            telegram(self.cfg, "Like this: /client Joe's Pizza social (or design, or bundle)")
            return
        lead = self._lead(name)
        if not lead and URL.search(name):
            kit = brand.read(URL.search(name).group(0), niche=guess_niche(name), budget=40)
            if not kit.get("ok"):
                telegram(self.cfg, f"I couldn't read {esc(name)}: {esc(kit.get('problem'))}.")
                return
            lead = {"id": "tg:" + kit["domain"], "name": kit.get("name") or kit["domain"], "website": kit["website"],
                    "niche": guess_niche(kit.get("title", "") + " " + kit.get("text", "")[:3000]), "city": "", "state": ""}
        if not lead:
            telegram(self.cfg, f"No business called {esc(name)} in your leads. Use its website instead: "
                               "/client https://their-site.com social")
            return
        self.onboard(lead, plan or lead.get("plan_chosen") or "social", email)

    def onboard_from_hq(self, items):
        """Businesses you marked as bought in HQ with "start their service now"."""
        n = 0
        for item in items:
            lead = self.store.leads.get(item.get("id"))
            if not lead or lead.get("status") == "client":
                continue
            plan = item.get("plan") if item.get("plan") in PLANS else "social"
            try:
                self.onboard(lead, plan, item.get("email") or "")
                n += 1
            except Exception as e:
                telegram(self.cfg, f"HQ asked me to start {esc(lead.get('name', ''))}'s service, but it failed: "
                                   f"{esc(str(e)[:200])}")
        return n

    def onboard(self, lead, plan, email=""):
        client = clients.add_client(self.cfg, self.store, lead, plan, email)
        key = clients.key_of(client)
        telegram(self.cfg, f"✅ <b>{esc(client['name'])}</b> is now a client ({esc(plan)}). "
                           + ("Welcome email sent." if self.cfg.live and client.get("email") else
                              "Welcome email shown above (draft mode or no email).")
                           + (f"\nTheir email: {esc(client['email'])}" if client.get("email") else
                              f"\nNo email for them yet: add it with /client {esc(key)} {plan} their@email.com")
                           + ("\nTheir first week of posts is being made now." if plan_has(client, "social") else ""))
        if plan_has(client, "social"):
            self.week(client["name"])

    def paid(self, text):
        client = clients.find(self.cfg, text.strip())
        if not client:
            telegram(self.cfg, f"No client called {esc(text)}.")
            return
        month = clients.mark_paid(self.cfg, self.store, client)
        telegram(self.cfg, f"💰 Marked {esc(client['name'])} paid for {esc(month)}.")

    def pause(self, text, paused):
        client = clients.find(self.cfg, text.strip())
        if not client:
            telegram(self.cfg, f"No client called {esc(text)}.")
            return
        self.store.client(clients.key_of(client))["paused"] = paused
        client["paused"] = paused
        telegram(self.cfg, f"{'⏸ Paused' if paused else '▶️ Resumed'} {esc(client['name'])}.")

    def change_plan(self, text):
        words = (text or "").split()
        plan = next((PLAN_ALIASES[w.lower()] for w in words if w.lower() in PLAN_ALIASES), None)
        client = clients.find(self.cfg, " ".join(w for w in words if w.lower() not in PLAN_ALIASES))
        if not client or not plan:
            telegram(self.cfg, "Like this: /plan maple bundle (social, design or bundle)")
            return
        self.store.client(clients.key_of(client))["plan"] = plan
        client["plan"] = plan
        telegram(self.cfg, f"{esc(client['name'])} is now on the {esc(plan.title())} plan.")

    # -- client emails that need the browser (called from the inbox) --------------------------------------
    def design_from_email(self, client, text, msgid=None):
        return clients.design_job(self.cfg, self.store, self.renderer, client, text, source="client")

    def revise_design(self, client, request, revision_of):
        return clients.design_job(self.cfg, self.store, self.renderer, client, request, source="client",
                                  revision_of=revision_of)

    def redo_week(self, client, week, feedback):
        """A client asked for changes to their week: make it again with their changes, and send it again."""
        record = self.store.client(clients.key_of(client))["weeks"].get(week) or {}
        rounds = int(record.get("round", 0)) + 1
        if rounds > self.cfg["autopilot"]["revisions"]:
            return "too many rounds of changes, so it's yours to handle"
        changed = dict(client, feedback=f"Changes they asked for this week: {feedback.strip()[:500]}")
        new = clients.make_week(self.cfg, self.store, self.renderer, changed, self.root, dt.date.fromisoformat(week))
        new["round"] = rounds
        self.weeks.append((client, week, new))
        return "redone with their changes; it goes back to them in this run"

    def trends(self, text):
        city = text.strip() or self.cfg["targets"]["cities"][0]
        r = trends.radar(self.cfg, self.store, city=city)
        cal = "\n".join(f"{c.get('icon', '')} {esc(c['title'])} · {dt.date.fromisoformat(c['date']):%a %b %-d}"
                        for c in r["calendar"][:10])
        live = "\n".join(f"• {esc(x['title'])} <i>({esc(x['source'])})</i>" for x in r["live"][:10])
        weather = "\n".join(f"{w.get('icon', '')} {esc(w['title'])}: {esc(w['angle'])}" for w in r["weather"])
        telegram(self.cfg, f"<b>Worth posting about · {esc(city)}</b>\n\n{cal}\n\n<b>Trending today</b>\n{live or 'nothing safe'}"
                           + (f"\n\n<b>Weather</b>\n{weather}" if weather else ""))

    def status(self):
        import collections
        counts = collections.Counter(l.get("status") for l in self.store.leads.values())
        telegram(self.cfg, "\n".join(f"{esc(k)}: {v}" for k, v in counts.most_common()) or "Nothing yet.")

    # -- publishing what the commands made ----------------------------------------------------------------
    def finish(self):
        if not (self.samples or self.weeks):
            return
        packs.site_root(self.root)
        removed = publish.write_removed(self.store, self.root)
        base = None
        if publish.configured(self.cfg):
            dep = publish.deploy(self.cfg, self.root)
            if dep:
                publish.remember(self.store, dict(dep, removed=removed), "commands")
                base = dep["url"]
        for lead in self.samples:
            if base:
                lead["sample_url"] = f"{base}/s/{lead['token']}/"
                telegram(self.cfg, f"<b>Sample for {esc(lead['name'])}</b>: {link(lead['sample_url'], 'open it')}\n\n"
                                   f"Message to send them (tap to copy):\n<pre>{esc(pipeline.dm_draft(self.cfg, lead))}</pre>")
                lead["handed_over"] = iso()
            else:
                telegram(self.cfg, f"Made a sample for {esc(lead['name'])}, but Cloudflare isn't set up to publish it.")
        for client, week, record in self.weeks:
            if base:
                clients.deliver(self.cfg, self.store, client, week, record, base)
