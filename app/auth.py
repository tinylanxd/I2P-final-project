from functools import wraps

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .models import User, db

bp = Blueprint("auth", __name__)

MAX_USERNAME_LENGTH = 30


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None if user_id is None else db.session.get(User, user_id)
    if user_id is not None and g.user is None:
        # The account no longer exists, so drop the stale login.
        session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        return view(**kwargs)

    return wrapped


def validate_username(username):
    if not username:
        return "請輸入用戶名"
    if len(username) > MAX_USERNAME_LENGTH:
        return f"用戶名不能超過 {MAX_USERNAME_LENGTH} 個字元"
    return None


def validate_password(password):
    if not password.strip():
        return "請輸入密碼"
    return None


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        error = validate_username(username) or validate_password(password)

        if error is None:
            user = User(
                username=username,
                password_hash=generate_password_hash(password),
            )
            db.session.add(user)
            try:
                # The unique constraint also covers simultaneous sign-ups.
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                error = "這個用戶名已被使用"
            else:
                flash("註冊成功，請登入", "success")
                return redirect(url_for("auth.login"))

        flash(error, "error")

    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.session.scalar(db.select(User).filter_by(username=username))

        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            return redirect(url_for("main.home"))

        flash("用戶名或密碼錯誤", "error")

    return render_template("login.html")


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
