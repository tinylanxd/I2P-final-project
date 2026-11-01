from flask import Blueprint, redirect, render_template, session, url_for

from .auth import login_required

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("main.home"))
    return redirect(url_for("auth.login"))


@bp.route("/home")
@login_required
def home():
    return render_template("home.html")
