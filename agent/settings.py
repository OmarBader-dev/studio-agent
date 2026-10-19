"""Loads config.yaml and clients.yaml, plus secrets from the environment (or a local .env file)."""
import os
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "cache"                 # downloaded logos and photos, trend snapshots (not committed)
SITE = ROOT / "site"                   # pages published to Cloudflare Pages
OUTBOX = DATA / "outbox"               # draft emails in draft mode


# What each plan includes. The two agents are sold on their own; the bundle gets both.
PLANS = {"social": {"social"}, "design": {"design"}, "bundle": {"social", "design"}}


def plan_of(client):
    """A client's plan: social, design or bundle. A missing or misspelled plan counts as social (and the daily
    report tells you to fix it), so nobody gets work they didn't pay for."""
    plan = str(client.get("plan") or "").strip().lower()
    return plan if plan in PLANS else "social"


def plan_has(client, agent):
    """Whether a client's plan includes the social media agent ("social") or the design agent ("design")."""
    return agent in PLANS[plan_of(client)]


def public_repo():
    """With STATE_KEY set (a public repository), nothing private is committed: only the encrypted state."""
    return bool(os.environ.get("STATE_KEY", "").strip())


def client_folders(key):
    """Where a client's own files are: clients/<key> in the repository (photos you add yourself), plus, in a
    public repository, the run cache for photos they email (so their photos are never committed in public)."""
    folders = [ROOT / "clients" / key]
    if public_repo():
        folders.append(CACHE / "client-files" / key)
    return folders


def client_inbox_folder(key):
    """Where photos a client emails are saved."""
    return client_folders(key)[-1]

# The kinds of businesses the agents look for, with Overture Maps' category names for each.
NICHES = {
    "restaurant": [
        "restaurant", "pizza_restaurant", "mexican_restaurant", "american_restaurant", "sandwich_shop",
        "chinese_restaurant", "burger_restaurant", "bar_and_grill_restaurant", "italian_restaurant",
        "chicken_restaurant", "indian_restaurant", "breakfast_and_brunch_restaurant", "japanese_restaurant",
        "barbecue_restaurant", "seafood_restaurant", "sushi_restaurant", "delicatessen", "steakhouse", "diner",
        "mediterranean_restaurant", "taco_restaurant", "asian_restaurant", "asian_fusion_restaurant",
        "greek_restaurant", "latin_american_restaurant", "southern_american_restaurant", "vietnamese_restaurant",
        "thai_restaurant", "korean_restaurant", "soul_food", "african_restaurant", "caribbean_restaurant",
        "hot_dog_restaurant", "texmex_restaurant", "comfort_food_restaurant", "ramen_restaurant",
        "vegan_restaurant", "cajun_and_creole_restaurant", "middle_eastern_restaurant", "peruvian_restaurant",
        "jamaican_restaurant", "vegetarian_restaurant", "french_restaurant", "poke_restaurant", "halal_restaurant",
        "ethiopian_restaurant", "food_truck_stand", "health_food_restaurant", "salad_bar", "gastropub",
        "chicken_wings_restaurant", "theme_restaurant",
    ],
    "cafe": ["coffee_shop", "cafe", "tea_room", "bubble_tea_shop", "smoothie_juice_bar"],
    "bakery": ["bakery", "dessert_shop", "donut_shop", "ice_cream_shop", "cupcake_shop", "bagel_shop", "candy_store"],
    "gym": ["gym", "fitness_trainer", "yoga_studio", "pilates_studio", "martial_arts_club", "dance_studio",
            "sport_or_fitness_facility", "boxing_class", "boxing_gym", "cycling_class", "gymnastics_center"],
    "beauty": ["hair_salon", "beauty_salon", "nail_salon", "barber", "spa", "day_spa", "massage_therapy",
               "skin_care_and_makeup", "waxing", "tanning_salon", "makeup_artist", "tattoo_and_piercing",
               "health_spa"],
    "shop": ["clothing_store", "womens_clothing_store", "mens_clothing_store", "fashion_boutique", "jewelry_store",
             "flowers_and_gifts_store", "florist", "gift_shop", "shoe_store", "pet_store", "bookstore",
             "arts_crafts_and_hobby_store", "specialty_foods_store", "bridal_shop", "toy_store",
             "second_hand_clothing_store", "candle_store", "health_food_store"],
    "bar": ["bar", "sports_bar", "brewery", "pub", "cocktail_bar", "wine_bar", "beer_bar", "irish_pub", "winery",
            "tapas_bar"],
    "pets": ["pet_groomer", "pet_boarding", "dog_trainer", "animal_or_pet_service"],
}
CATEGORY_NICHE = {c: n for n, cats in NICHES.items() for c in cats}

SECRETS = [
    "GMAIL_APP_PASSWORD", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID",
    "GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "PEXELS_API_KEY", "YOUTUBE_API_KEY",
    "TICKETMASTER_API_KEY", "META_ACCESS_TOKEN",
]


def _load_dotenv(path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class Config(dict):
    """config.yaml as a dict, with secrets under cfg.secret(name)."""

    def secret(self, name):
        return os.environ.get(name, "").strip()

    @property
    def live(self):
        return str(self.get("mode", "draft")).lower() == "live"

    def require(self, *names):
        missing = [n for n in names if not self.secret(n)]
        if missing:
            raise SystemExit("Missing secrets: " + ", ".join(missing) + ". See the README, step 4.")


def _defaults(cfg):
    for section in ("you", "offer", "targets", "limits", "pages", "ai", "images", "trends", "posting", "autopilot"):
        cfg[section] = cfg.get(section) or {}
    o = cfg["offer"]
    for key, value in (("social_monthly", 99), ("design_monthly", 49), ("bundle_monthly", 129),
                       ("posts_per_week", 3), ("designs_per_month", 8), ("trial", "the first week free")):
        o.setdefault(key, value)
    t = cfg["targets"]
    t.setdefault("cities", ["Columbus, OH"])
    t.setdefault("niches", ["restaurant", "cafe", "bakery", "gym", "beauty", "shop"])
    t["niches"] = [n for n in t["niches"] if n in NICHES]
    lim = cfg["limits"]
    for key, value in (("new_prospects_per_day", 15), ("new_emails_per_day", 10), ("email_ramp_per_week", 5),
                       ("max_emails_per_day", 15), ("followups_per_day", 30),
                       ("dm_handover_per_day", 8), ("send_hours", [9, 16]), ("followup_days", [3, 7]),
                       ("sample_days", 30), ("prospect_minutes", 15), ("ai_calls_per_day", 150),
                       ("ai_images_per_day", 40), ("sample_reels_per_day", 6)):
        lim.setdefault(key, value)
    p = cfg["pages"]
    p.setdefault("cloudflare_project", "studio-samples")
    p.setdefault("base_url", "")
    a = cfg["ai"]
    a.setdefault("providers", ["gemini", "groq", "cloudflare", "openrouter"])
    a.setdefault("keyless_fallback", False)      # Pollinations: no key needed, community-run service
    im = cfg["images"]
    im.setdefault("ai_backgrounds", True)       # Cloudflare Workers AI, only when its secrets are set
    im.setdefault("stock_photos", True)         # Pexels with a key, else Openverse (no key)
    tr = cfg["trends"]
    tr.setdefault("country", "US")
    tr.setdefault("avoid", [])                  # extra words to keep out of posts
    cfg["posting"].setdefault("meta", "auto")     # posts through Meta when META_ACCESS_TOKEN is set
    ap = cfg["autopilot"] = cfg.get("autopilot") or {}
    ap.setdefault("clients", True)       # weekly posts and designs go straight to clients after the agent's own checks
    ap.setdefault("replies", True)       # businesses that reply interested get the plans and prices automatically
    ap.setdefault("posters", 2)          # posters a month the design agent makes on its own for each design client
    ap.setdefault("revisions", 3)        # rounds of changes a client can ask for by email before it comes to you
    cfg.setdefault("mode", "draft")
    cfg.setdefault("email_style", "card")
    return cfg


def with_saved_clients(cfg, saved):
    """Clients added from Telegram (/client) live in the agent's memory; clients.yaml can override any of them."""
    names = {str(c.get("name", "")).lower() for c in cfg["clients"]}
    for c in (saved or {}).values():
        if c.get("name") and c["name"].lower() not in names and (c.get("website") or c.get("brand")):
            cfg["clients"].append(dict(c))
    return cfg


def load(path=None, clients_path=None):
    _load_dotenv(ROOT / ".env")
    raw = yaml.safe_load((path or ROOT / "config.yaml").read_text()) or {}
    cfg = _defaults(Config(raw))
    cpath = clients_path or ROOT / "clients.yaml"
    clients = (yaml.safe_load(cpath.read_text()) or {}).get("clients") if cpath.exists() else None
    cfg["clients"] = [c for c in (clients or []) if c and c.get("name") and (c.get("website") or c.get("brand"))]
    return cfg
