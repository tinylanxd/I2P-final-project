"""Demo data for showing the app: `flask --app run seed-demo`.

The restaurant names are made up. The streets are real ones near 清大 (no house
numbers), and the coordinates spread from about 250 m to about 4 km from the
main gate, so the random pick's distance filter gives different results.
"""

import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from .models import MenuItem, Restaurant, Review, User, db

DEMO_PASSWORD = "demo"

USERS = [
    {"username": "demo", "nickname": "示範帳號", "bio": "範例帳號：登入看看首頁推薦"},
    {"username": "foodie", "nickname": "清大吃貨", "bio": "範例帳號：分享清大附近的店"},
]

# Reviews are (username, stars, comment). Each user rates a restaurant at most once,
# and only their own restaurants or public ones.
RESTAURANTS = [
    {
        "owner": "demo",
        "name": "小巷拉麵",
        "category": "日式拉麵",
        "address": "新竹市東區建功一路",
        "note": "湯頭濃郁，可以免費加麵一次",
        "is_public": True,
        "price_level": 2,
        "latitude": 24.7925,
        "longitude": 120.9945,
        "menu": [("豚骨拉麵", 180), ("醬油拉麵", 170), ("叉燒飯", 120), ("溏心蛋", 30)],
        "reviews": [
            ("demo", 5, "湯頭超濃，冬天必吃"),
            ("foodie", 4, "麵偏硬，但湯很好喝"),
        ],
    },
    {
        "owner": "demo",
        "name": "阿嬤滷肉飯",
        "category": "台式小吃",
        "address": "新竹市東區建新路",
        "note": "銅板價，宵夜時段也有開",
        "is_public": True,
        "price_level": 1,
        "latitude": 24.7905,
        "longitude": 120.9918,
        "menu": [("滷肉飯", 40), ("雞肉飯", 45), ("貢丸湯", 35), ("燙青菜", 40)],
        "reviews": [("demo", 4, "便宜又大碗")],
    },
    {
        "owner": "demo",
        "name": "晨光早午餐",
        "category": "早午餐",
        "address": "新竹市東區光復路二段",
        "note": "假日早上要排隊",
        "is_public": False,
        "price_level": 2,
        "latitude": 24.7962,
        "longitude": 120.9990,
        "menu": [("班尼迪克蛋", 220), ("鬆餅套餐", 200), ("拿鐵", 90)],
        "reviews": [("demo", 3, "好吃但等太久")],
    },
    {
        "owner": "demo",
        "name": "綠葉沙拉吧",
        "category": "健康餐",
        "address": "新竹市東區關新路",
        "note": "配料可以自己選",
        "is_public": False,
        "price_level": 2,
        "latitude": 24.7860,
        "longitude": 121.0175,
        "menu": [("雞胸肉沙拉", 180), ("鮭魚藜麥碗", 260), ("每日濃湯", 60)],
        "reviews": [],
    },
    {
        "owner": "demo",
        "name": "山城咖啡",
        "category": "咖啡廳",
        "address": "新竹市東區寶山路",
        "note": "有插座，適合讀書",
        "is_public": False,
        "price_level": 2,
        "latitude": 24.7900,
        "longitude": 120.9800,
        "menu": [("手沖咖啡", 150), ("巴斯克乳酪蛋糕", 130), ("美式咖啡", 90)],
        "reviews": [("demo", 5, "很安靜，可以待一整個下午")],
    },
    {
        "owner": "demo",
        "name": "夜貓鹹酥雞",
        "category": "炸物",
        "address": "新竹市東區學府路",
        "note": "晚上六點以後才開",
        "is_public": False,
        "price_level": 1,
        "latitude": 24.7880,
        "longitude": 120.9935,
        "menu": [("鹹酥雞", 70), ("甜不辣", 40), ("炸杏鮑菇", 50), ("四季豆", 40)],
        "reviews": [("demo", 2, "有點太油")],
    },
    {
        "owner": "foodie",
        "name": "竹塹牛肉麵",
        "category": "麵食",
        "address": "新竹市東區東門街",
        "note": "牛肉塊很大",
        "is_public": True,
        "price_level": 2,
        "latitude": 24.8035,
        "longitude": 120.9700,
        "menu": [("紅燒牛肉麵", 200), ("清燉牛肉麵", 210), ("牛肉湯餃", 120)],
        "reviews": [
            ("foodie", 5, "新竹最愛的牛肉麵"),
            ("demo", 4, "湯有點鹹，但肉很嫩"),
        ],
    },
    {
        "owner": "foodie",
        "name": "風城火鍋",
        "category": "火鍋",
        "address": "新竹市東區中央路",
        "note": "人多的時候要先訂位",
        "is_public": True,
        "price_level": 3,
        "latitude": 24.8090,
        "longitude": 120.9755,
        "menu": [("麻辣鴛鴦鍋", 420), ("牛五花套餐", 380), ("海鮮拼盤", 520)],
        "reviews": [("foodie", 4, "適合聚餐")],
    },
    {
        "owner": "foodie",
        "name": "清夜豆花",
        "category": "甜點",
        "address": "新竹市東區建功二路",
        "note": "冬天有熱的",
        "is_public": True,
        "price_level": 1,
        "latitude": 24.7900,
        "longitude": 121.0005,
        "menu": [("花生豆花", 50), ("芋圓綜合冰", 70), ("薑汁豆花", 55)],
        "reviews": [
            ("foodie", 5, "芋圓很Q"),
            ("demo", 5, "夏天必吃"),
        ],
    },
    {
        "owner": "foodie",
        "name": "巷口水餃",
        "category": "麵食",
        "address": "新竹市東區大學路",
        "note": "可以外帶冷凍水餃",
        "is_public": True,
        "price_level": 1,
        "latitude": 24.7880,
        "longitude": 121.0000,
        "menu": [("高麗菜水餃（10 顆）", 70), ("韭菜水餃（10 顆）", 70), ("酸辣湯", 40)],
        "reviews": [],
    },
    {
        "owner": "foodie",
        "name": "南洋小廚",
        "category": "東南亞料理",
        "address": "新竹市東區金山街",
        "note": "辣度可以調整",
        "is_public": True,
        "price_level": 2,
        "latitude": 24.7790,
        "longitude": 121.0210,
        "menu": [("打拋豬飯", 160), ("綠咖哩雞", 190), ("月亮蝦餅", 220), ("泰式奶茶", 60)],
        "reviews": [
            ("foodie", 3, "普通，月亮蝦餅不錯"),
            ("demo", 2, "對我來說太辣了"),
        ],
    },
    {
        "owner": "foodie",
        "name": "湖畔義式廚房",
        "category": "義式料理",
        "address": "新竹市東區明湖路",
        "note": "靠窗的位子看得到湖",
        "is_public": True,
        "price_level": 3,
        "latitude": 24.7720,
        "longitude": 120.9690,
        "menu": [("松露燉飯", 380), ("瑪格麗特披薩", 340), ("提拉米蘇", 160)],
        "reviews": [("foodie", 4, "價格偏高，但氣氛很好")],
    },
]


USERNAMES = [data["username"] for data in USERS]
ADDED_MESSAGE = f"已加入範例資料：帳號 {'、'.join(USERNAMES)}，密碼都是 {DEMO_PASSWORD}"
EXISTS_MESSAGE = "範例資料已經存在，沒有變更"


def add_demo_data():
    """Add the demo accounts and restaurants. Needs an app context.

    Returns True when the data was added, False when a demo account already
    exists (then nothing changes).
    """
    if db.session.scalar(db.select(User.id).where(User.username.in_(USERNAMES))):
        return False

    users = {}
    for data in USERS:
        users[data["username"]] = User(
            password_hash=generate_password_hash(DEMO_PASSWORD), **data
        )
    db.session.add_all(users.values())

    for data in RESTAURANTS:
        db.session.add(
            Restaurant(
                owner=users[data["owner"]],
                name=data["name"],
                category=data["category"],
                address=data["address"],
                note=data["note"],
                is_public=data["is_public"],
                price_level=data["price_level"],
                latitude=data["latitude"],
                longitude=data["longitude"],
                menu_items=[
                    MenuItem(name=name, price=price) for name, price in data["menu"]
                ],
                reviews=[
                    Review(user=users[username], stars=stars, comment=comment)
                    for username, stars, comment in data["reviews"]
                ],
            )
        )
    db.session.commit()
    return True


@click.command("seed-demo")
@with_appcontext
def seed_demo():
    """Add demo accounts and sample restaurants near 清大 (only once)."""
    click.echo(ADDED_MESSAGE if add_demo_data() else EXISTS_MESSAGE)
