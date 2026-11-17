"""Remember the location the browser shares, in the Flask session only.

The browser side lives in static/location.js. The location is never written to
the database or to logs; it disappears on logout or when the browser closes.
"""

import math
from typing import NamedTuple

from flask import Blueprint, request, session

bp = Blueprint("location", __name__)

SESSION_KEY = "location"
KEYS = ("latitude", "longitude", "accuracy")


class Location(NamedTuple):
    latitude: float
    longitude: float
    accuracy: float  # metres


def is_number(value):
    # bool is a subclass of int, but `true` is not a coordinate.
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def parse_location(data):
    """Return a Location from a decoded JSON body, or None if it is invalid."""
    if not isinstance(data, dict):
        return None
    if not all(key in data and is_number(data[key]) for key in KEYS):
        return None
    location = Location(*(float(data[key]) for key in KEYS))
    if not (
        -90 <= location.latitude <= 90
        and -180 <= location.longitude <= 180
        and location.accuracy >= 0
    ):
        return None
    return location


def get_user_location():
    """Return the location the browser last shared in this session, or None."""
    stored = session.get(SESSION_KEY)
    if not isinstance(stored, list) or len(stored) != len(KEYS):
        return None
    return parse_location(dict(zip(KEYS, stored)))


@bp.post("/location")
def store_location():
    location = parse_location(request.get_json(silent=True))
    if location is None:
        return {"error": "invalid location"}, 400
    session[SESSION_KEY] = list(location)
    return "", 204


@bp.delete("/location")
def forget_location():
    session.pop(SESSION_KEY, None)
    return "", 204
