import math
import re
from itertools import zip_longest

import sqlalchemy as sa
from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .auth import login_required
from .models import Favorite, MenuItem, Restaurant, Review, db

bp = Blueprint("restaurants", __name__, url_prefix="/restaurants")

LIMITS = {"name": 50, "address": 200, "category": 30, "note": 200}
LABELS = {"name": "餐廳名稱", "address": "地址", "category": "分類", "note": "備註"}
SCOPES = ("mine", "public", "favorites")

MAX_ITEMS = 30
MAX_ITEM_NAME = 50
MAX_COMMENT = 200


# ---------------------------------------------------------------- helpers


def get_scope(value):
    return value if value in SCOPES else "mine"


def blank_form():
    form = {key: "" for key in LIMITS}
    form.update(
        is_public=False,
        latitude="",
        longitude="",
        items=[],
        stars="",
        review_comment="",
    )
    return form


def parse_stars(raw, comment):
    """Returns (stars or None, error). An empty rating means "no rating"."""
    if not raw:
        if comment:
            return None, "請選擇評分星數才能留下評價內容"
        return None, None
    if not re.fullmatch(r"[1-5]", raw):
        return None, "評分必須是 1 到 5 顆星"
    return int(raw), None


def validate(form, parsed):
    """Validate a form dict; fill `parsed` with typed values. Returns an error or None."""
    if not form["name"]:
        return "請輸入餐廳名稱"
    for key, limit in LIMITS.items():
        if len(form[key]) > limit:
            return f"{LABELS[key]}不能超過 {limit} 個字元"
    if len(form["review_comment"]) > MAX_COMMENT:
        return f"評價內容不能超過 {MAX_COMMENT} 個字元"

    # Location: both coordinates or neither.
    if form["latitude"] or form["longitude"]:
        try:
            lat, lng = float(form["latitude"]), float(form["longitude"])
        except ValueError:
            return "座標格式不正確，請重新取得位置"
        if not (
            math.isfinite(lat)
            and math.isfinite(lng)
            and -90 <= lat <= 90
            and -180 <= lng <= 180
        ):
            return "座標超出範圍，請重新取得位置"
        parsed["latitude"], parsed["longitude"] = lat, lng
    else:
        parsed["latitude"] = parsed["longitude"] = None

    # Menu: blank rows were already dropped by read_form.
    if len(form["items"]) > MAX_ITEMS:
        return f"最多只能新增 {MAX_ITEMS} 項餐點"
    items = []
    for item in form["items"]:
        if not item["name"]:
            return "請輸入餐點名稱"
        if len(item["name"]) > MAX_ITEM_NAME:
            return f"餐點名稱不能超過 {MAX_ITEM_NAME} 個字元"
        price = None
        if item["price"]:
            if not re.fullmatch(r"[0-9]{1,5}", item["price"]):
                return "價格必須是 0 到 99999 的整數"
            price = int(item["price"])
        items.append((item["name"], price))
    parsed["items"] = items

    stars, error = parse_stars(form["stars"], form["review_comment"])
    if error:
        return error
    parsed["stars"] = stars
    return None


def read_form():
    """Read the restaurant form. Returns (form for re-display, parsed values, error)."""
    form = {key: request.form.get(key, "").strip() for key in LIMITS}
    form["is_public"] = bool(request.form.get("is_public"))
    form["latitude"] = request.form.get("latitude", "").strip()
    form["longitude"] = request.form.get("longitude", "").strip()
    form["stars"] = request.form.get("stars", "").strip()
    form["review_comment"] = request.form.get("review_comment", "").strip()

    names = request.form.getlist("item_name")
    prices = request.form.getlist("item_price")
    rows = [
        {"name": name.strip(), "price": price.strip()}
        for name, price in zip_longest(names, prices, fillvalue="")
    ]
    form["items"] = [row for row in rows if row["name"] or row["price"]]

    parsed = {}
    return form, parsed, validate(form, parsed)


def form_from_restaurant(restaurant, me):
    form = {key: getattr(restaurant, key) for key in LIMITS}
    form["is_public"] = restaurant.is_public
    form["latitude"] = "" if restaurant.latitude is None else str(restaurant.latitude)
    form["longitude"] = "" if restaurant.longitude is None else str(restaurant.longitude)
    form["items"] = [
        {"name": item.name, "price": "" if item.price is None else str(item.price)}
        for item in restaurant.menu_items
    ]
    mine = my_review(restaurant, me)
    form["stars"] = str(mine.stars) if mine else ""
    form["review_comment"] = mine.comment if mine else ""
    return form


def apply_form(restaurant, form, parsed):
    for key in LIMITS:
        setattr(restaurant, key, form[key])
    restaurant.is_public = form["is_public"]
    restaurant.latitude = parsed["latitude"]
    restaurant.longitude = parsed["longitude"]
    # Replacing the list also deletes the old rows (delete-orphan).
    restaurant.menu_items = [
        MenuItem(name=name, price=price) for name, price in parsed["items"]
    ]


def my_review(restaurant, me):
    return next((r for r in restaurant.reviews if r.user_id == me), None)


def set_my_review(restaurant, me, stars, comment):
    """Create, update or (when stars is None) remove the user's own review."""
    existing = my_review(restaurant, me)
    if stars is None:
        if existing:
            restaurant.reviews.remove(existing)
    elif existing:
        existing.stars = stars
        existing.comment = comment
    else:
        restaurant.reviews.append(Review(user_id=me, stars=stars, comment=comment))


def get_owned(restaurant_id):
    """Load a restaurant that must belong to the current user."""
    restaurant = db.get_or_404(Restaurant, restaurant_id)
    if restaurant.user_id != session["user_id"]:
        abort(403)
    return restaurant


def get_visible(restaurant_id):
    """Load a restaurant the current user may see: their own or a public one."""
    restaurant = db.get_or_404(Restaurant, restaurant_id)
    if restaurant.user_id != session["user_id"] and not restaurant.is_public:
        abort(404)
    return restaurant


def rating_stats(restaurant_ids):
    """{restaurant_id: (average stars, number of ratings)} for rated restaurants."""
    if not restaurant_ids:
        return {}
    rows = db.session.execute(
        db.select(Review.restaurant_id, sa.func.avg(Review.stars), sa.func.count(Review.id))
        .where(Review.restaurant_id.in_(restaurant_ids))
        .group_by(Review.restaurant_id)
    ).all()
    return {rid: (float(avg), count) for rid, avg, count in rows}


def favorite_ids(me):
    return set(
        db.session.scalars(
            db.select(Favorite.restaurant_id).where(Favorite.user_id == me)
        )
    )


def saved_source_ids(me):
    """Public restaurants the user already saved a private copy of."""
    return set(
        db.session.scalars(
            db.select(Restaurant.source_id).where(
                Restaurant.user_id == me, Restaurant.source_id.is_not(None)
            )
        )
    )


def back_to_list(restaurant_id=None):
    """Go back to where the action was triggered (detail page or a list tab)."""
    if restaurant_id is not None and request.form.get("return_to") == "detail":
        return redirect(url_for("restaurants.detail", restaurant_id=restaurant_id))
    scope = get_scope(request.form.get("scope"))
    return redirect(url_for("restaurants.index", scope=scope))


# ------------------------------------------------------------------ pages


@bp.route("/")
@login_required
def index():
    me = session["user_id"]
    scope = get_scope(request.args.get("scope"))
    q = request.args.get("q", "").strip()

    if scope == "public":
        stmt = db.select(Restaurant).where(Restaurant.is_public.is_(True))
    elif scope == "favorites":
        stmt = (
            db.select(Restaurant)
            .join(Favorite, Favorite.restaurant_id == Restaurant.id)
            .where(
                Favorite.user_id == me,
                # A favorite someone made private again simply disappears.
                sa.or_(Restaurant.user_id == me, Restaurant.is_public.is_(True)),
            )
        )
    else:
        stmt = db.select(Restaurant).where(Restaurant.user_id == me)

    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            sa.or_(
                Restaurant.name.ilike(pattern),
                Restaurant.category.ilike(pattern),
                Restaurant.address.ilike(pattern),
                Restaurant.menu_items.any(MenuItem.name.ilike(pattern)),
            )
        )

    items = db.session.scalars(stmt.order_by(Restaurant.id.desc())).all()

    return render_template(
        "restaurants.html",
        restaurants=items,
        scope=scope,
        q=q,
        me=me,
        stats=rating_stats([r.id for r in items]),
        fav_ids=favorite_ids(me),
        saved_ids=saved_source_ids(me),
    )


@bp.route("/<int:restaurant_id>")
@login_required
def detail(restaurant_id):
    me = session["user_id"]
    restaurant = get_visible(restaurant_id)
    return render_template(
        "restaurant_detail.html",
        r=restaurant,
        me=me,
        stats=rating_stats([restaurant.id]),
        mine=my_review(restaurant, me),
        fav_ids=favorite_ids(me),
        saved_ids=saved_source_ids(me),
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    me = session["user_id"]
    form = blank_form()
    if request.method == "POST":
        form, parsed, error = read_form()
        if error is None:
            restaurant = Restaurant(user_id=me)
            apply_form(restaurant, form, parsed)
            set_my_review(restaurant, me, parsed["stars"], form["review_comment"])
            db.session.add(restaurant)
            db.session.commit()
            flash("已新增餐廳", "success")
            return redirect(url_for("restaurants.index"))
        flash(error, "error")

    return render_template(
        "restaurant_form.html", form=form, heading="新增餐廳", submit_label="新增"
    )


@bp.route("/<int:restaurant_id>/edit", methods=["GET", "POST"])
@login_required
def edit(restaurant_id):
    me = session["user_id"]
    restaurant = get_owned(restaurant_id)
    form = form_from_restaurant(restaurant, me)

    if request.method == "POST":
        form, parsed, error = read_form()
        if error is None:
            apply_form(restaurant, form, parsed)
            set_my_review(restaurant, me, parsed["stars"], form["review_comment"])
            db.session.commit()
            flash("已更新餐廳", "success")
            return redirect(url_for("restaurants.index"))
        flash(error, "error")

    return render_template(
        "restaurant_form.html", form=form, heading="編輯餐廳", submit_label="儲存"
    )


# ---------------------------------------------------------------- actions


@bp.post("/<int:restaurant_id>/share")
@login_required
def toggle_share(restaurant_id):
    restaurant = get_owned(restaurant_id)
    restaurant.is_public = not restaurant.is_public
    db.session.commit()
    flash("已公開到公用資料庫" if restaurant.is_public else "已取消公開", "success")
    return back_to_list(restaurant.id)


@bp.post("/<int:restaurant_id>/save")
@login_required
def save_copy(restaurant_id):
    me = session["user_id"]
    source = db.get_or_404(Restaurant, restaurant_id)
    # Only other people's public restaurants can be saved.
    if not source.is_public or source.user_id == me:
        abort(404)

    already_saved = db.session.scalar(
        db.select(Restaurant.id).filter_by(user_id=me, source_id=source.id)
    )
    if already_saved:
        flash("這間餐廳已在你的清單中", "error")
    else:
        db.session.add(
            Restaurant(
                user_id=me,
                name=source.name,
                address=source.address,
                category=source.category,
                note=source.note,
                is_public=False,
                latitude=source.latitude,
                longitude=source.longitude,
                source_id=source.id,
                # Reviews and favorites are personal and are not copied.
                menu_items=[
                    MenuItem(name=item.name, price=item.price)
                    for item in source.menu_items
                ],
            )
        )
        db.session.commit()
        flash("已存入我的清單", "success")
    return back_to_list(source.id)


@bp.post("/<int:restaurant_id>/delete")
@login_required
def delete(restaurant_id):
    restaurant = get_owned(restaurant_id)
    # Copies saved by others keep working; they just lose the link to the source.
    db.session.execute(
        sa.update(Restaurant)
        .where(Restaurant.source_id == restaurant.id)
        .values(source_id=None)
    )
    # Menu items, reviews and favorites are removed by the ORM cascade.
    db.session.delete(restaurant)
    db.session.commit()
    flash("已刪除餐廳", "success")
    return back_to_list()


@bp.post("/<int:restaurant_id>/favorite")
@login_required
def favorite(restaurant_id):
    me = session["user_id"]
    restaurant = get_visible(restaurant_id)
    exists = db.session.scalar(
        db.select(Favorite.id).filter_by(user_id=me, restaurant_id=restaurant.id)
    )
    if not exists:
        db.session.add(Favorite(user_id=me, restaurant_id=restaurant.id))
        db.session.commit()
    flash("已加入收藏", "success")
    return back_to_list(restaurant.id)


@bp.post("/<int:restaurant_id>/unfavorite")
@login_required
def unfavorite(restaurant_id):
    me = session["user_id"]
    db.session.execute(
        sa.delete(Favorite).where(
            Favorite.user_id == me, Favorite.restaurant_id == restaurant_id
        )
    )
    db.session.commit()
    flash("已取消收藏", "success")
    return back_to_list(restaurant_id)


@bp.post("/<int:restaurant_id>/review")
@login_required
def review(restaurant_id):
    me = session["user_id"]
    restaurant = get_visible(restaurant_id)
    comment = request.form.get("review_comment", "").strip()
    stars, error = parse_stars(request.form.get("stars", "").strip(), comment)
    if error is None and stars is None:
        error = "請選擇評分星數"
    if error is None and len(comment) > MAX_COMMENT:
        error = f"評價內容不能超過 {MAX_COMMENT} 個字元"

    if error:
        flash(error, "error")
    else:
        set_my_review(restaurant, me, stars, comment)
        db.session.commit()
        flash("已送出評價", "success")
    return redirect(url_for("restaurants.detail", restaurant_id=restaurant.id))


@bp.post("/<int:restaurant_id>/review/delete")
@login_required
def delete_review(restaurant_id):
    me = session["user_id"]
    restaurant = get_visible(restaurant_id)
    set_my_review(restaurant, me, None, "")
    db.session.commit()
    flash("已刪除我的評價", "success")
    return redirect(url_for("restaurants.detail", restaurant_id=restaurant.id))
