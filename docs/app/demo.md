# `app/demo.py` 函式說明

提供展示用的範例資料。執行 `flask --app run seed-demo` 會加入兩個範例帳號和 12 間清大附近的虛構餐廳（含菜單和評價）。`share.py` 啟動時也會呼叫 `add_demo_data()`。

## 模組層級資料

- `DEMO_PASSWORD = "demo"`：所有範例帳號的密碼。
- `USERS`：兩個帳號 `demo`（示範帳號）和 `foodie`（清大吃貨）的 `username`、`nickname`、`bio`。
- `RESTAURANTS`：12 筆餐廳字典，每筆包含：
  - `owner`：擁有者的 username（`demo` 和 `foodie` 各 6 間）
  - `name`、`category`、`address`、`note`：文字欄位。店名是虛構的，街道是清大附近真實存在的路（沒有門牌號碼）。
  - `is_public`：是否公開。`demo` 有 2 間公開、4 間私人；`foodie` 的全部公開。
  - `price_level`：價位等級 1–3。
  - `latitude`、`longitude`：座標，分布在離清大大門約 250 公尺到 4 公里之間，讓隨機抽選的距離篩選會得到不同結果。
  - `menu`：`(餐點名稱, 價格)` 串列。
  - `reviews`：`(評價者 username, 星數, 評論)` 串列。每人對每間店最多評一次，而且只評自己的或公開的餐廳。
- `USERNAMES`：從 `USERS` 取出的帳號名稱串列 `["demo", "foodie"]`。
- `ADDED_MESSAGE`：加入成功時顯示的訊息，內容由 `USERNAMES` 和 `DEMO_PASSWORD` 組成。
- `EXISTS_MESSAGE`：資料已存在時顯示的訊息。

## 函式

### `add_demo_data()`

- **前提**：必須在 app context 中呼叫，因為要使用 `db`。
- **運作原理**：
  1. 查詢資料庫中是否已有任何一個 username 在 `USERNAMES` 裡的使用者（`User.username.in_(USERNAMES)`）。有的話直接回傳 `False`，什麼都不做，避免重複加入或違反 username 的唯一限制。
  2. 對 `USERS` 的每一筆建立 `User` 物件：密碼是 `DEMO_PASSWORD` 的雜湊，`**data` 把 `username`、`nickname`、`bio` 展開成關鍵字參數。這些物件存進字典 `users`（username → User 物件），後面用來指定擁有者和評價者。
  3. `db.session.add_all(...)` 把使用者加入 session。
  4. 對 `RESTAURANTS` 的每一筆建立 `Restaurant`：
     - `owner=users[...]`：透過 relationship 直接指向 User 物件。這時使用者還沒有 id，SQLAlchemy 會在寫入時自動填好外鍵。
     - `menu_items`：把 `menu` 串列轉成 `MenuItem` 物件。
     - `reviews`：把 `reviews` 串列轉成 `Review` 物件，`user` 同樣指向對應的 User 物件。
  5. 只在最後 `commit` 一次，所有資料在同一個交易中寫入，不會只寫進一部分。
- **回傳**：成功加入回傳 `True`；範例帳號已存在則回傳 `False`。

### `seed_demo()`

- **用途**：CLI 指令 `seed-demo` 的進入點。
- **運作原理**：
  1. `@click.command("seed-demo")` 定義指令名稱。
  2. `@with_appcontext` 確保執行時已經有 app context，可以使用 `db`。
  3. 這個指令在 `create_app()` 中以 `app.cli.add_command(seed_demo)` 註冊。
  4. 呼叫 `add_demo_data()`，依結果用 `click.echo` 印出 `ADDED_MESSAGE` 或 `EXISTS_MESSAGE`。
- **使用方式**：`.venv\Scripts\python -m flask --app run seed-demo`
