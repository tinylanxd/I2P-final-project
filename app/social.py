"""Following other users. Two people who follow each other are friends."""

import sqlalchemy as sa
from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from .auth import login_required
from .models import Follow, User, db

bp = Blueprint("social", __name__)

MAX_SEARCH_RESULTS = 20


# ---------------------------------------------------------------- queries


def is_following(follower_id, followed_id):
    return (
        db.session.scalar(
            db.select(Follow.id).filter_by(
                follower_id=follower_id, followed_id=followed_id
            )
        )
        is not None
    )


def follower_count(user_id):
    return db.session.scalar(
        db.select(sa.func.count()).where(Follow.followed_id == user_id)
    )


def following_count(user_id):
    return db.session.scalar(
        db.select(sa.func.count()).where(Follow.follower_id == user_id)
    )


def followers_of(user_id):
    return db.session.scalars(
        db.select(User)
        .join(Follow, Follow.follower_id == User.id)
        .where(Follow.followed_id == user_id)
        .order_by(Follow.id.desc())
    ).all()


def followed_by(user_id):
    return db.session.scalars(
        db.select(User)
        .join(Follow, Follow.followed_id == User.id)
        .where(Follow.follower_id == user_id)
        .order_by(Follow.id.desc())
    ).all()


def friends_of(user_id):
    """Users that user_id follows and who follow user_id back."""
    back = aliased(Follow)
    return db.session.scalars(
        db.select(User)
        .join(Follow, Follow.followed_id == User.id)
        .join(
            back,
            sa.and_(back.follower_id == User.id, back.followed_id == user_id),
        )
        .where(Follow.follower_id == user_id)
        .order_by(User.id)
    ).all()


def following_ids(user_id):
    return set(
        db.session.scalars(
            db.select(Follow.followed_id).where(Follow.follower_id == user_id)
        )
    )


def search_users(q, exclude_id):
    # Treat % and _ in the query as plain characters, not wildcards.
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    return db.session.scalars(
        db.select(User)
        .where(
            User.id != exclude_id,
            sa.or_(
                User.username.ilike(pattern, escape="\\"),
                User.nickname.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(User.id)
        .limit(MAX_SEARCH_RESULTS)
    ).all()


def back_to(user_id):
    """Return to the page the button was on, or to the user's profile."""
    target = request.form.get("next", "")
    # Only same-site paths, so the form cannot send people to another site.
    if target.startswith("/") and not target.startswith(("//", "/\\")):
        return redirect(target)
    return redirect(url_for("users.profile", user_id=user_id))


@bp.app_context_processor
def social_helpers():
    # Lets profile.html show counts and the follow button without each view passing them.
    return {
        "is_following": is_following,
        "follower_count": follower_count,
        "following_count": following_count,
    }


# ---------------------------------------------------------------- views


@bp.post("/users/<int:user_id>/follow")
@login_required
def follow(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == g.user.id:
        flash("不能追蹤自己", "error")
        return back_to(user.id)

    if not is_following(g.user.id, user.id):
        db.session.add(Follow(follower_id=g.user.id, followed_id=user.id))
        try:
            db.session.commit()
        except IntegrityError:
            # A double click raced us; the follow already exists.
            db.session.rollback()

    if is_following(user.id, g.user.id):
        flash(f"你和 {user.display_name} 已成為好友", "success")
    else:
        flash(f"已追蹤 {user.display_name}", "success")
    return back_to(user.id)


@bp.post("/users/<int:user_id>/unfollow")
@login_required
def unfollow(user_id):
    user = db.get_or_404(User, user_id)
    db.session.execute(
        sa.delete(Follow).where(
            Follow.follower_id == g.user.id, Follow.followed_id == user.id
        )
    )
    db.session.commit()
    flash(f"已取消追蹤 {user.display_name}", "success")
    return back_to(user.id)


@bp.get("/users/<int:user_id>/followers")
def followers(user_id):
    user = db.get_or_404(User, user_id)
    return render_user_list(user, "followers", followers_of(user.id))


@bp.get("/users/<int:user_id>/following")
def following(user_id):
    user = db.get_or_404(User, user_id)
    return render_user_list(user, "following", followed_by(user.id))


def render_user_list(user, kind, users):
    return render_template(
        "user_list.html",
        user=user,
        kind=kind,
        users=users,
        my_following=following_ids(g.user.id) if g.user else set(),
    )


@bp.get("/friends")
@login_required
def friends():
    # Usernames and nicknames are at most 30 characters, so longer input cannot match.
    q = request.args.get("q", "").strip()[:30]
    return render_template(
        "friends.html",
        q=q,
        friends=friends_of(g.user.id),
        results=search_users(q, g.user.id) if q else [],
        my_following=following_ids(g.user.id),
    )
