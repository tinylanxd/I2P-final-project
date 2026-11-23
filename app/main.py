import random

from flask import Blueprint, redirect, render_template, session, url_for

from .auth import login_required
from .models import Restaurant, db
from .picker import weighted_sample
from .restaurants import rating_stats, saved_source_ids

bp = Blueprint("main", __name__)

HOME_PICKS = 6
# An unrated restaurant is weighted like one with an average of 3 stars.
UNRATED_STARS = 3


def recommend(me):
    """Pick restaurants for the home page. Returns (picks, rating stats).

    Up to half come from the user's own restaurants and the rest from other
    people's public ones; when one side has too few, the other fills the gap.
    The higher a restaurant's average rating, the more likely it is picked.
    """
    mine = db.session.scalars(
        db.select(Restaurant).where(Restaurant.user_id == me)
    ).all()
    public = db.session.scalars(
        db.select(Restaurant).where(
            Restaurant.is_public.is_(True),
            # The user's own public restaurants are already in `mine`,
            Restaurant.user_id != me,
            # and so are the private copies they saved of public ones.
            Restaurant.id.not_in(saved_source_ids(me)),
        )
    ).all()
    stats = rating_stats([r.id for r in mine + public])

    def weight(restaurant):
        average = stats[restaurant.id][0] if restaurant.id in stats else UNRATED_STARS
        # Squared, so a 5-star restaurant is clearly more likely than a 3-star one.
        return average**2

    mine_count = min(len(mine), max(HOME_PICKS // 2, HOME_PICKS - len(public)))
    picks = weighted_sample(mine, weight, mine_count)
    picks += weighted_sample(public, weight, HOME_PICKS - len(picks))
    random.shuffle(picks)
    return picks, stats


@bp.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("main.home"))
    return redirect(url_for("auth.login"))


@bp.route("/home")
@login_required
def home():
    me = session["user_id"]
    picks, stats = recommend(me)
    return render_template("home.html", restaurants=picks, stats=stats, me=me)
