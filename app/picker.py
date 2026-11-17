"""Distance and drawing helpers for the random pick page (no Flask here)."""

import math
import random

EARTH_RADIUS_M = 6371000

# Distance limits offered on the pick page: metres -> label.
DISTANCE_OPTIONS = {500: "500 公尺", 1000: "1 公里", 3000: "3 公里", 5000: "5 公里"}

# How many restaurants one draw may return (the page offers 1..MAX_PICK_COUNT).
MAX_PICK_COUNT = 5


def distance_m(lat1, lng1, lat2, lng2):
    """Straight-line (haversine) distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def format_distance(metres):
    if metres < 1000:
        return f"約 {round(metres)} 公尺"
    return f"約 {metres / 1000:.1f} 公里"


def within_distance(restaurants, origin, max_m):
    """Each restaurant paired with its distance from origin, keeping those
    <= max_m. Restaurants without coordinates are kept, paired with None,
    because we cannot tell that they are too far."""
    candidates = []
    for restaurant in restaurants:
        if restaurant.latitude is None or restaurant.longitude is None:
            candidates.append((restaurant, None))
            continue
        metres = distance_m(*origin, restaurant.latitude, restaurant.longitude)
        if metres <= max_m:
            candidates.append((restaurant, metres))
    return candidates


def choose(candidates, last_id=None):
    """Pick one (restaurant, distance) pair at random, avoiding the previous
    pick when there is anything else to choose. None for an empty list."""
    if len(candidates) > 1:
        others = [c for c in candidates if c[0].id != last_id]
        candidates = others or candidates
    return random.choice(candidates) if candidates else None


def choose_many(candidates, count, avoid_ids=()):
    """Pick up to `count` different (restaurant, distance) pairs, in random order.

    Restaurants whose id is in avoid_ids (the previous draw) are only used when
    there are not enough other candidates. Returns fewer than `count` pairs
    when there are fewer candidates, and [] for an empty list."""
    if count < 1:
        return []
    avoid = set(avoid_ids)
    fresh = [c for c in candidates if c[0].id not in avoid]
    repeats = [c for c in candidates if c[0].id in avoid]
    random.shuffle(fresh)
    random.shuffle(repeats)
    chosen = (fresh + repeats)[:count]
    # Shuffle again so that repeats are not always listed last.
    random.shuffle(chosen)
    return chosen
