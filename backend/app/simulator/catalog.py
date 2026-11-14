"""Shared behavioural model: cities, merchants, cardholders and normal spending.

Both the live traffic generator and the ML baseline trainer draw from this
module, so "normal" means the same thing to the simulator and the model.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from app.schemas import CardholderProfile

# --------------------------------------------------------------------------- geo
CITIES: dict[str, list[tuple[str, float, float]]] = {
    "IL": [
        ("Tel Aviv", 32.0853, 34.7818),
        ("Haifa", 32.7940, 34.9896),
        ("Jerusalem", 31.7683, 35.2137),
        ("Be'er Sheva", 31.2520, 34.7915),
        ("Netanya", 32.3215, 34.8532),
        ("Rishon LeZion", 31.9730, 34.7925),
        ("Eilat", 29.5577, 34.9519),
    ],
    "GB": [("London", 51.5072, -0.1276), ("Manchester", 53.4808, -2.2426), ("Edinburgh", 55.9533, -3.1883)],
    "US": [
        ("New York", 40.7128, -74.0060),
        ("Los Angeles", 34.0522, -118.2437),
        ("Chicago", 41.8781, -87.6298),
        ("Miami", 25.7617, -80.1918),
    ],
    "DE": [("Berlin", 52.5200, 13.4050), ("Munich", 48.1351, 11.5820), ("Frankfurt", 50.1109, 8.6821)],
    "FR": [("Paris", 48.8566, 2.3522), ("Lyon", 45.7640, 4.8357), ("Nice", 43.7102, 7.2620)],
}
HOME_COUNTRY_WEIGHTS: dict[str, float] = {"IL": 0.6, "GB": 0.1, "US": 0.1, "DE": 0.1, "FR": 0.1}
COUNTRY_LABEL: dict[str, str] = {"IL": "IL", "GB": "UK", "US": "US", "DE": "DE", "FR": "FR"}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# --------------------------------------------------------------------- merchants
@dataclass(frozen=True, slots=True)
class Category:
    """Merchant category with its spend multiplier relative to a user's average."""

    name: str
    multiplier: float
    merchants: tuple[str, ...]


CATEGORIES: dict[str, Category] = {
    c.name: c
    for c in (
        Category("grocery", 0.6, ("GreenLeaf Market", "Corner Fresh", "Daily Basket", "Harvest Grocers")),
        Category("restaurant", 0.8, ("Olive & Thyme", "Blue Harbor Grill", "Noodle Theory", "Café Meridian")),
        Category("fuel", 0.7, ("Rapid Fuel", "Northstar Gas", "Petro Point")),
        Category("pharmacy", 0.5, ("WellCare Pharmacy", "CityMed Drugs")),
        Category("fashion", 1.3, ("Thread & Loom", "Urban Fit", "Linen Lane")),
        Category("electronics", 2.0, ("Voltix Electronics", "Circuit Hub", "PixelPoint")),
        Category("online_retail", 1.0, ("ShopNimbus", "CartFlow", "ParcelBay")),
        Category("entertainment", 0.7, ("Starlight Cinemas", "ArcadeVerse", "StreamBox")),
        Category("travel", 2.5, ("SkyRoute Airlines", "Nomad Stays", "TrailRail")),
    )
}
CARD_TESTING_MERCHANTS: tuple[str, ...] = ("DigiKeys Store", "QuickTopUp", "GiftCodes Online", "AppCredit Hub")
FIRST_NAMES = ("Noa", "Itai", "Maya", "Yonatan", "Tamar", "Amit", "Shira", "Daniel", "Emma", "Liam",
               "Olivia", "Lucas", "Sofia", "Max", "Chloé", "Hugo", "Lea", "Ben", "Ava", "Noah")
LAST_NAMES = ("Cohen", "Levi", "Mizrahi", "Peretz", "Friedman", "Smith", "Brown", "Miller", "Garcia",
              "Schmidt", "Weber", "Martin", "Bernard", "Dubois", "Klein", "Avraham", "Biton", "Taylor")

# Relative likelihood of a normal purchase in each local hour.
HOUR_WEIGHTS: tuple[float, ...] = (
    0.3, 0.2, 0.1, 0.1, 0.1, 0.2, 0.6, 1.2, 2.0, 3.0, 3.5, 4.0,
    5.0, 5.0, 4.0, 3.5, 3.5, 4.5, 5.0, 5.0, 4.5, 3.5, 2.2, 1.2,
)


def generate_profiles(n: int, rng: random.Random) -> list[CardholderProfile]:
    """Create ``n`` persistent cardholders with home city and spend baselines."""
    profiles: list[CardholderProfile] = []
    used_ids: set[str] = set()
    countries, weights = zip(*HOME_COUNTRY_WEIGHTS.items(), strict=True)
    for _ in range(n):
        while True:
            card_id = f"{rng.choice(('4580', '5326', '4111', '5412'))}-****-****-{rng.randint(0, 9999):04d}"
            if card_id not in used_ids:
                used_ids.add(card_id)
                break
        country = rng.choices(countries, weights)[0]
        city, lat, lon = rng.choice(CITIES[country])
        tier = "premium" if rng.random() < 0.15 else "standard"
        median = 250.0 if tier == "premium" else 60.0
        avg = round(min(max(rng.lognormvariate(math.log(median), 0.5), 12.0), 1_500.0), 2)
        profiles.append(
            CardholderProfile(
                card_id=card_id,
                name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                tier=tier,
                home_city=city,
                home_country=country,
                home_lat=lat,
                home_lon=lon,
                avg_amount=avg,
                categories=rng.sample(sorted(CATEGORIES), k=rng.randint(3, 5)),
            )
        )
    return profiles


@dataclass(slots=True)
class PurchaseDraft:
    """Location/amount/time of a purchase before it becomes a TransactionIn."""

    amount: float
    merchant: str
    category: str
    city: str
    country: str
    lat: float
    lon: float
    local_hour: int


def sample_normal_purchase(profile: CardholderProfile, rng: random.Random) -> PurchaseDraft:
    """Draw a purchase consistent with the cardholder's habits and location."""
    cat_name = rng.choice(profile.categories) if rng.random() < 0.9 else rng.choice(sorted(CATEGORIES))
    category = CATEGORIES[cat_name]
    amount = max(1.5, profile.avg_amount * category.multiplier * rng.lognormvariate(0.0, 0.45))

    if rng.random() < 0.88:
        city, lat, lon = profile.home_city, profile.home_lat, profile.home_lon
    else:
        city, lat, lon = rng.choice(CITIES[profile.home_country])
    lat += rng.uniform(-0.03, 0.03)
    lon += rng.uniform(-0.03, 0.03)

    return PurchaseDraft(
        amount=round(amount, 2),
        merchant=rng.choice(category.merchants),
        category=cat_name,
        city=city,
        country=profile.home_country,
        lat=round(lat, 5),
        lon=round(lon, 5),
        local_hour=rng.choices(range(24), HOUR_WEIGHTS)[0],
    )


def sample_prior_tx_count(rng: random.Random) -> int:
    """Typical number of a card's transactions in the previous 10 minutes."""
    return rng.choices(range(11), (40, 25, 13, 8, 5, 3, 2, 1.5, 1, 0.8, 0.7))[0]
