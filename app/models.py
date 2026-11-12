from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import deferred

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nickname = db.Column(db.String(30), nullable=False, default="")
    bio = db.Column(db.String(200), nullable=False, default="")
    # WebP bytes made by users.make_avatar; only loaded when a page needs it.
    avatar = deferred(db.Column(db.LargeBinary))

    @property
    def display_name(self):
        return self.nickname or self.username

    @property
    def has_avatar(self):
        return self.avatar is not None


class Restaurant(db.Model):
    """One table serves both the personal and the public database.

    - personal database: rows whose user_id is the current user
    - public database:   rows whose is_public is True (visible to everyone)
    """

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    address = db.Column(db.String(200), nullable=False, default="")
    category = db.Column(db.String(30), nullable=False, default="")
    note = db.Column(db.String(200), nullable=False, default="")
    is_public = db.Column(db.Boolean, nullable=False, default=False)
    # Optional coordinates, filled from the browser's "use my location" button.
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    # Set when this row is a private copy saved from a public restaurant.
    source_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"))

    owner = db.relationship("User", foreign_keys=[user_id])
    menu_items = db.relationship(
        "MenuItem",
        cascade="all, delete-orphan",
        order_by="MenuItem.id",
    )
    reviews = db.relationship(
        "Review",
        cascade="all, delete-orphan",
        order_by="Review.id",
    )
    favorites = db.relationship("Favorite", cascade="all, delete-orphan")


class MenuItem(db.Model):
    """A dish and its price. A restaurant can have any number of them."""

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(
        db.Integer, db.ForeignKey("restaurant.id"), nullable=False
    )
    name = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Integer)  # None means the price was left blank


class Review(db.Model):
    """One user's 1-5 star rating (and optional comment) for a restaurant."""

    __table_args__ = (
        db.UniqueConstraint("restaurant_id", "user_id"),
        db.CheckConstraint("stars BETWEEN 1 AND 5"),
    )

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(
        db.Integer, db.ForeignKey("restaurant.id"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    stars = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.String(200), nullable=False, default="")

    user = db.relationship("User", foreign_keys=[user_id])


class Favorite(db.Model):
    """A restaurant a user bookmarked (their own or someone else's public one)."""

    __table_args__ = (db.UniqueConstraint("user_id", "restaurant_id"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    restaurant_id = db.Column(
        db.Integer, db.ForeignKey("restaurant.id"), nullable=False
    )

