"""Distance and drawing helpers for the random pick and home pages (no Flask here)."""

import math
import random

EARTH_RADIUS_M = 6371000

# Distance limits offered on the pick page: metres -> label.
DISTANCE_OPTIONS = {500: "500 公尺", 1000: "1 公里", 3000: "3 公里", 5000: "5 公里"}


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


def weighted_sample(items, weight, k):
    """Up to k distinct items, picked one at a time. Each pick chooses among
    the items not picked yet, in proportion to weight(item)."""
    pool = list(items)
    picked = []
    while pool and len(picked) < k:
        chosen = random.choices(pool, weights=[weight(item) for item in pool])[0]
        pool.remove(chosen)
        picked.append(chosen)
    return picked
