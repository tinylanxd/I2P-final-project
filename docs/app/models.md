# `app/models.py` 函式與模型說明

用 Flask-SQLAlchemy 定義資料庫模型。每個類別對應一張資料表，表名由 Flask-SQLAlchemy 自動從類別名稱轉成小寫底線格式：`user`、`restaurant`、`menu_item`、`review`、`favorite`。這個檔案只有兩個函式（都是 `User` 的 property），其餘是模型定義，也一併說明。

## 模組層級物件

- `db = SQLAlchemy()`：資料庫物件，所有模型都繼承 `db.Model`。在 `create_app()` 中以 `db.init_app(app)` 綁定到 app。
- `PRICE_LEVELS`：價位等級對照表 `{1: "每人 150 元以下", 2: "每人 150–300 元", 3: "每人 300 元以上"}`。`Restaurant.price_level` 存的是這裡的鍵。

## `User`：使用者

| 欄位 | 說明 |
|---|---|
| `id` | 主鍵 |
| `username` | 用戶名，最多 30 字元，唯一、必填 |
| `password_hash` | 密碼雜湊，不存明文 |
| `nickname` | 暱稱，最多 30 字元，預設空字串 |
| `bio` | 自我介紹，最多 200 字元，預設空字串 |
| `avatar` | 頭像的 WebP 二進位資料（由 `users.make_avatar` 產生），可為空 |

- `avatar` 用 `deferred(...)` 包起來：查詢 User 時不會一起載入圖片資料，第一次存取 `user.avatar` 時才另外查詢，避免每次載入使用者都讀取大量 bytes。

### `display_name`（property）

- **運作原理**：`return self.nickname or self.username`。暱稱是空字串時視為假值，於是改用 username。
- **用途**：模板顯示使用者名稱時使用，例如 `user.display_name`，不需要加括號。

### `has_avatar`（property）

- **運作原理**：`self.avatar is not None`，判斷是否有上傳頭像。
- **備註**：因為 `avatar` 是 deferred 欄位，第一次讀取這個 property 時會觸發一次查詢來載入頭像資料。

## `Restaurant`：餐廳

同一張表同時扮演兩個資料庫：
- **個人資料庫**：`user_id` 等於目前使用者的資料列。
- **公用資料庫**：`is_public` 為 True 的資料列，所有人都看得到。

| 欄位 | 說明 |
|---|---|
| `id` | 主鍵 |
| `user_id` | 擁有者，外鍵指向 `user.id`，必填 |
| `name` | 餐廳名稱，最多 50 字元，必填 |
| `address` | 地址，最多 200 字元 |
| `category` | 分類，最多 30 字元 |
| `note` | 備註，最多 200 字元 |
| `is_public` | 是否公開，預設 False |
| `price_level` | `PRICE_LEVELS` 的鍵；`None` 表示未選擇 |
| `latitude`、`longitude` | 座標，可為空，由瀏覽器的「使用我的位置」按鈕填入 |
| `source_id` | 如果這筆是從公開餐廳存下的私人副本，記錄來源餐廳的 id |

關聯（relationship）：
- `owner`：擁有者的 `User` 物件。`foreign_keys=[user_id]` 明確指定用 `user_id` 這個外鍵。
- `menu_items`：這間餐廳的 `MenuItem` 串列，依 id 排序。
- `reviews`：這間餐廳的 `Review` 串列，依 id 排序。
- `favorites`：收藏這間餐廳的 `Favorite` 串列。
- 這三個關聯都設定了 `cascade="all, delete-orphan"`：
  - 刪除餐廳時，一併刪除它的菜單、評價和收藏。
  - 從串列中移除的物件（孤兒）也會被刪除。`restaurants.apply_form` 就是把整個菜單串列換掉來更新菜單，`set_my_review` 則是從 `reviews` 中移除來刪除評價。

## `MenuItem`：菜單項目

| 欄位 | 說明 |
|---|---|
| `id` | 主鍵 |
| `restaurant_id` | 所屬餐廳，必填 |
| `name` | 餐點名稱，最多 50 字元，必填 |
| `price` | 價格（整數），`None` 表示沒有填價格 |

## `Review`：評價

| 欄位 | 說明 |
|---|---|
| `id` | 主鍵 |
| `restaurant_id` | 被評價的餐廳 |
| `user_id` | 評價者 |
| `stars` | 星數 1–5，必填 |
| `comment` | 評論，最多 200 字元，預設空字串 |

- `__table_args__` 設定兩個資料庫層級的限制：
  - `UniqueConstraint("restaurant_id", "user_id")`：每個使用者對同一間餐廳最多一則評價。
  - `CheckConstraint("stars BETWEEN 1 AND 5")`：程式驗證之外，資料庫再檢查一次星數範圍。
- `user`：評價者的 `User` 物件，模板用來顯示是誰評的。

## `Favorite`：收藏

| 欄位 | 說明 |
|---|---|
| `id` | 主鍵 |
| `user_id` | 收藏者 |
| `restaurant_id` | 被收藏的餐廳（自己的，或別人公開的） |

- `UniqueConstraint("user_id", "restaurant_id")`：同一個使用者不能重複收藏同一間餐廳。
