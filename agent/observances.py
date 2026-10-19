"""Days businesses post about: holidays, "national days" and seasons, with the niches each one suits.

Rules: ("fixed", month, day) | ("nth", month, weekday 0=Mon, n; -1 = last) | ("easter", offset days) |
("thanksgiving", offset days). Only well-established days are listed. Public holidays also come from the
free Nager.Date service (trends.py), so this list adds the marketing days on top.
"""
import datetime as dt
import re

ALL =["restaurant", "cafe", "bakery", "gym", "beauty", "shop", "bar", "pets"]
FOOD = ["restaurant", "cafe", "bakery", "bar"]

DAYS = [
    # name, rule, niches, icon, angle
    ("New Year's Day", ("fixed", 1, 1), ALL, "🎉", "fresh starts and thank-yous"),
    ("National Bagel Day", ("fixed", 1, 15), ["bakery", "cafe"], "🥯", "bagels"),
    ("National Pie Day", ("fixed", 1, 23), ["bakery", "restaurant"], "🥧", "pie"),
    ("National Croissant Day", ("fixed", 1, 30), ["bakery", "cafe"], "🥐", "croissants and pastries"),
    ("National Hot Chocolate Day", ("fixed", 1, 31), ["cafe", "bakery"], "☕", "hot chocolate and warm drinks"),
    ("National Pizza Day", ("fixed", 2, 9), ["restaurant"], "🍕", "pizza"),
    ("Valentine's Day", ("fixed", 2, 14), ALL, "❤️", "love, dates and treats"),
    ("National Margarita Day", ("fixed", 2, 22), ["bar", "restaurant"], "🍹", "margaritas (21+)"),
    ("Pi Day", ("fixed", 3, 14), ["bakery", "restaurant"], "🥧", "pies and pizza pies (3.14)"),
    ("St. Patrick's Day", ("fixed", 3, 17), ["restaurant", "bar", "bakery", "cafe", "shop"], "☘️", "green and lucky"),
    ("First day of spring", ("fixed", 3, 20), ALL, "🌷", "spring menus, fresh looks, new arrivals"),
    ("National Burrito Day", ("nth", 4, 3, 1), ["restaurant"], "🌯", "burritos"),
    ("National Beer Day", ("fixed", 4, 7), ["bar", "restaurant"], "🍺", "beer (21+)"),
    ("World Health Day", ("fixed", 4, 7), ["gym", "beauty"], "💪", "healthy habits"),
    ("National Pet Day", ("fixed", 4, 11), ["pets", "shop", "cafe"], "🐾", "pets and pet-friendly spots"),
    ("National Grilled Cheese Day", ("fixed", 4, 12), ["restaurant", "cafe"], "🧀", "grilled cheese"),
    ("Independent Bookstore Day", ("nth", 4, 5, -1), ["shop"], "📚", "shopping local"),
    ("National Hairstylist Appreciation Day", ("fixed", 4, 30), ["beauty"], "💇", "the stylists behind the chair"),
    ("Cinco de Mayo", ("fixed", 5, 5), ["restaurant", "bar"], "🌮", "Mexican food and drinks"),
    ("Mother's Day", ("nth", 5, 6, 2), ALL, "💐", "brunch, gifts and pampering for moms"),
    ("National Wine Day", ("fixed", 5, 25), ["bar", "restaurant"], "🍷", "wine (21+)"),
    ("National Burger Day", ("fixed", 5, 28), ["restaurant", "bar"], "🍔", "burgers"),
    ("National Nail Polish Day", ("fixed", 6, 1), ["beauty"], "💅", "nail colors"),
    ("Global Running Day", ("nth", 6, 2, 1), ["gym"], "🏃", "running and cardio"),
    ("National Donut Day", ("nth", 6, 4, 1), ["bakery", "cafe"], "🍩", "donuts"),
    ("National Rosé Day", ("nth", 6, 5, 2), ["bar", "restaurant"], "🌸", "rosé (21+)"),
    ("International Sushi Day", ("fixed", 6, 18), ["restaurant"], "🍣", "sushi"),
    ("Father's Day", ("nth", 6, 6, 3), ALL, "👔", "treats and gifts for dads"),
    ("International Day of Yoga", ("fixed", 6, 21), ["gym", "beauty"], "🧘", "yoga and mindfulness"),
    ("First day of summer", ("fixed", 6, 21), ALL, "☀️", "summer menus, classes and looks"),
    ("Independence Day", ("fixed", 7, 4), ALL, "🇺🇸", "the Fourth: cookouts, red-white-and-blue"),
    ("National Fried Chicken Day", ("fixed", 7, 6), ["restaurant"], "🍗", "fried chicken"),
    ("National French Fry Day", ("fixed", 7, 13), ["restaurant", "bar"], "🍟", "fries"),
    ("National Hot Dog Day", ("nth", 7, 2, 3), ["restaurant"], "🌭", "hot dogs"),
    ("National Ice Cream Day", ("nth", 7, 6, 3), ["bakery", "restaurant", "cafe"], "🍦", "ice cream"),
    ("International Self-Care Day", ("fixed", 7, 24), ["beauty", "gym"], "🛁", "self-care"),
    ("National Tequila Day", ("fixed", 7, 24), ["bar"], "🥃", "tequila (21+)"),
    ("National Chicken Wing Day", ("fixed", 7, 29), ["restaurant", "bar"], "🍗", "wings"),
    ("National Lipstick Day", ("fixed", 7, 29), ["beauty", "shop"], "💄", "lipstick and makeup"),
    ("National Avocado Day", ("fixed", 7, 31), ["restaurant", "cafe"], "🥑", "avocado everything"),
    ("International Beer Day", ("nth", 8, 4, 1), ["bar"], "🍻", "beer (21+)"),
    ("National Waffle Day", ("fixed", 8, 24), ["restaurant", "cafe"], "🧇", "waffles and brunch"),
    ("National Dog Day", ("fixed", 8, 26), ["pets", "shop", "cafe"], "🐶", "dogs and dog-friendly spots"),
    ("National Cheeseburger Day", ("fixed", 9, 18), ["restaurant", "bar"], "🍔", "cheeseburgers"),
    ("First day of fall", ("fixed", 9, 22), ALL, "🍂", "fall menus, cozy looks, new routines"),
    ("National Women's Health & Fitness Day", ("nth", 9, 2, -1), ["gym"], "🏋️", "women's fitness"),
    ("National Coffee Day", ("fixed", 9, 29), ["cafe", "bakery"], "☕", "coffee"),
    ("International Coffee Day", ("fixed", 10, 1), ["cafe"], "☕", "coffee"),
    ("National Taco Day", ("fixed", 10, 4), ["restaurant"], "🌮", "tacos"),
    ("World Mental Health Day", ("fixed", 10, 10), ["gym", "beauty"], "🌿", "rest, movement and feeling good"),
    ("National Pasta Day", ("fixed", 10, 17), ["restaurant"], "🍝", "pasta"),
    ("National Chocolate Day", ("fixed", 10, 28), ["bakery", "cafe", "shop"], "🍫", "chocolate"),
    ("National Cat Day", ("fixed", 10, 29), ["pets", "shop"], "🐱", "cats"),
    ("Halloween", ("fixed", 10, 31), ALL, "🎃", "costumes, spooky treats, fall fun"),
    ("World Vegan Day", ("fixed", 11, 1), ["restaurant", "cafe", "bakery"], "🌱", "plant-based options"),
    ("National Sandwich Day", ("fixed", 11, 3), ["restaurant", "cafe"], "🥪", "sandwiches"),
    ("National Nacho Day", ("fixed", 11, 6), ["restaurant", "bar"], "🧀", "nachos"),
    ("National Cappuccino Day", ("fixed", 11, 8), ["cafe"], "☕", "cappuccinos"),
    ("National Espresso Day", ("fixed", 11, 23), ["cafe"], "☕", "espresso"),
    ("Thanksgiving", ("thanksgiving", 0), ALL, "🦃", "gratitude, pies, family time"),
    ("Black Friday", ("thanksgiving", 1), ["shop", "beauty", "gym"], "🛍️", "deals and gift cards"),
    ("Small Business Saturday", ("thanksgiving", 2), ALL, "🛍️", "shopping and eating local"),
    ("Cyber Monday", ("thanksgiving", 4), ["shop"], "💻", "online orders"),
    ("National Cookie Day", ("fixed", 12, 4), ["bakery", "cafe"], "🍪", "cookies"),
    ("National Cupcake Day", ("fixed", 12, 15), ["bakery"], "🧁", "cupcakes"),
    ("First day of winter", ("fixed", 12, 21), ALL, "❄️", "winter warmers and cozy vibes"),
    ("Christmas Eve", ("fixed", 12, 24), ALL, "🎄", "holiday hours, last-minute gifts"),
    ("Christmas", ("fixed", 12, 25), ALL, "🎄", "holiday wishes"),
    ("New Year's Eve", ("fixed", 12, 31), ALL, "🥂", "celebrations and a look back at the year"),
    ("Easter", ("easter", 0), ["restaurant", "bakery", "cafe", "shop"], "🐣", "brunch, treats and spring"),
]

# Longer stretches that shape content for weeks (month, day) to (month, day).
SEASONS = [
    ("New Year, new goals", (12, 26), (1, 31), ["gym", "beauty"], "🎯", "resolutions and fresh starts"),
    ("Dry January", (1, 1), (1, 31), ["bar", "cafe", "restaurant"], "🍋", "zero-proof drinks"),
    ("Prom season", (4, 1), (5, 20), ["beauty", "shop"], "👗", "prom looks"),
    ("Wedding season", (5, 1), (10, 15), ["beauty", "shop", "bakery"], "💍", "wedding-ready"),
    ("Patio season", (5, 1), (9, 15), ["restaurant", "bar", "cafe"], "🌞", "eating and drinking outside"),
    ("Summer body season", (4, 1), (6, 15), ["gym"], "🏖️", "getting summer-ready"),
    ("Back to school", (8, 1), (9, 10), ALL, "🎒", "routines, lunches, back-to-school looks"),
    ("Fall flavors", (9, 1), (11, 25), ["cafe", "bakery", "restaurant"], "🍁", "pumpkin, apple, cinnamon"),
    ("Football season", (9, 1), (2, 10), ["restaurant", "bar"], "🏈", "game-day food and watch parties"),
    ("Gift season", (11, 15), (12, 24), ["shop", "beauty", "bakery", "gym", "cafe"], "🎁", "gift cards and gift ideas"),
]


# Days about one product or service: used only for businesses whose own website mentions it, so a jeweler
# doesn't get a Chocolate Day post and a coffee shop without pastries doesn't get Croissant Day.
NEEDS = {
    "National Bagel Day": r"bagel", "National Pie Day": r"\bpies?\b", "National Croissant Day": r"croissant",
    "National Hot Chocolate Day": r"hot chocolate|hot cocoa|mocha", "National Pizza Day": r"pizza",
    "National Margarita Day": r"margarita", "Pi Day": r"\bpies?\b|pizza", "National Burrito Day": r"burrito",
    "National Beer Day": r"\bbeers?\b|brew|\bipas?\b|lager|on tap", "National Grilled Cheese Day": r"grilled cheese",
    "Independent Bookstore Day": r"\bbooks?\b", "National Wine Day": r"\bwines?\b", "National Burger Day": r"burger",
    "National Nail Polish Day": r"\bnails?\b|manicure|pedicure|polish", "Global Running Day": r"\brun(?:s|ning|ners?)?\b",
    "National Donut Day": r"donut|doughnut", "National Rosé Day": r"ros[eé]\b", "International Sushi Day": r"sushi",
    "International Day of Yoga": r"yoga", "National Fried Chicken Day": r"fried chicken",
    "National French Fry Day": r"\bfries\b", "National Hot Dog Day": r"hot ?dogs?",
    "National Ice Cream Day": r"ice cream|gelato|frozen custard|soft serve", "National Tequila Day": r"tequila",
    "National Chicken Wing Day": r"\bwings\b", "National Lipstick Day": r"lipstick|lip color|makeup",
    "National Avocado Day": r"avocado|guac", "International Beer Day": r"\bbeers?\b|brew|on tap",
    "National Waffle Day": r"waffle", "National Dog Day": r"\bdogs?\b|pupp|\bpets?\b",
    "National Cheeseburger Day": r"burger", "National Coffee Day": r"coffee|espresso",
    "International Coffee Day": r"coffee|espresso", "National Taco Day": r"\btacos?\b",
    "National Pasta Day": r"pasta|spaghetti|lasagna|ravioli|fettuccine|penne",
    "National Chocolate Day": r"chocolat|cocoa|mocha|truffle", "National Cat Day": r"\bcats?\b|kitten|feline",
    "World Vegan Day": r"vegan|plant[- ]based", "National Sandwich Day": r"sandwich|hoagie|panini|\bsubs\b",
    "National Nacho Day": r"nacho", "National Cappuccino Day": r"cappuccino",
    "National Espresso Day": r"espresso", "National Cookie Day": r"cookie", "National Cupcake Day": r"cupcake",
    "National Pet Day": r"\bpets?\b|\bdogs?\b|\bcats?\b|pupp", "National Hairstylist Appreciation Day": r"\bhair|stylist",
    "Cinco de Mayo": r"mexican|\btacos?\b|burrito|margarita|tequila|enchilada|quesadilla",
    "Dry January": r"mocktail|zero[- ]proof|non-?alcoholic|n/a beer|spirit-free",
    "Football season": r"\bgame ?day|\btvs?\b|screens|watch part|sports bar|football",
    "Prom season": r"\bprom\b|formal|updo|gown|tux", "Wedding season": r"wedding|bridal|bride",
}


def fits(title, site_text):
    """Whether a day or season suits a business, judging by what its own website mentions."""
    need = NEEDS.get(title)
    return not need or bool(re.search(need, site_text or "", re.I))


def _easter(year):
    """Western Easter Sunday (Anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(year, month, day)


def _nth(year, month, weekday, n):
    if n > 0:
        first = dt.date(year, month, 1)
        return first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    last = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def date_of(rule, year):
    kind = rule[0]
    if kind == "fixed":
        return dt.date(year, rule[1], rule[2])
    if kind == "nth":
        return _nth(year, rule[1], rule[2], rule[3])
    if kind == "easter":
        return _easter(year) + dt.timedelta(days=rule[1])
    if kind == "thanksgiving":
        return _nth(year, 11, 3, 4) + dt.timedelta(days=rule[1])
    raise ValueError(rule)


def upcoming(start, days=21):
    """Days and seasons from start (a date) through the next `days` days, soonest first."""
    end = start + dt.timedelta(days=days)
    out = []
    for name, rule, niches, icon, angle in DAYS:
        for year in (start.year, start.year + 1):
            d = date_of(rule, year)
            if start <= d <= end:
                out.append({"title": name, "date": d.isoformat(), "days_away": (d - start).days, "niches": niches,
                            "icon": icon, "angle": angle, "kind": "day"})
    for name, (m1, d1), (m2, d2), niches, icon, angle in SEASONS:
        for year in (start.year - 1, start.year):
            a = dt.date(year, m1, d1)
            b = dt.date(year + (1 if (m2, d2) < (m1, d1) else 0), m2, d2)
            if a <= end and b >= start:
                out.append({"title": name, "date": max(a, start).isoformat(), "until": b.isoformat(),
                            "days_away": max(0, (a - start).days), "niches": niches, "icon": icon, "angle": angle,
                            "kind": "season"})
                break
    return sorted(out, key=lambda t: (t["days_away"], t["kind"] != "day"))
