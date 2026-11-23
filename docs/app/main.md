# `app/main.py` 函式說明

網站入口與首頁：`/` 依登入狀態導向，`/home` 依評分加權，從使用者自己的餐廳和別人的公開餐廳中隨機推薦。Blueprint 名稱為 `main`。

## 常數

- `HOME_PICKS = 6`：首頁最多推薦幾間餐廳。
- `UNRATED_STARS = 3`：沒有任何評價的餐廳，權重視同平均 3 顆星。

## 函式

### `recommend(me)`

- **參數**：`me` 是目前使用者的 id。
- **用途**：挑選首頁要顯示的餐廳。
- **運作原理**：
  1. `mine`：查詢使用者自己的所有餐廳，不論是否公開。
  2. `public`：查詢其他人的公開餐廳，並排除：
     - 使用者自己的公開餐廳（`Restaurant.user_id != me`），因為已經在 `mine` 裡。
     - 使用者已存成私人副本的公開餐廳（`saved_source_ids(me)`），因為副本已經在 `mine` 裡，避免同一間店出現兩次。
  3. `rating_stats(...)` 用一次查詢取得所有候選餐廳的（平均星數，評價數）。
  4. 內部函式 `weight(restaurant)` 計算權重：有評價就用平均星數，沒有就用 3，再取平方。平方會放大差距：5 星的權重 25、3 星是 9，約差 2.8 倍；不平方只差約 1.7 倍。
  5. 決定要從 `mine` 取幾間：
     `mine_count = min(len(mine), max(HOME_PICKS // 2, HOME_PICKS - len(public)))`
     - 一般情況取一半（3 間）。
     - 公開餐廳不到 3 間時，由自己的餐廳補上空缺（`HOME_PICKS - len(public)`）。
     - 但不能超過自己實際擁有的數量。
     - 例：自己 10 間、公開 1 間 → `max(3, 5) = 5`，`min(10, 5) = 5`，從自己的取 5 間，公開的取 1 間。
     - 例：自己 1 間、公開 10 間 → `min(1, 3) = 1`，自己的取 1 間，公開的取 5 間。
  6. `weighted_sample(mine, weight, mine_count)` 依權重不重複地抽出自己的餐廳。
  7. 再從 `public` 抽 `HOME_PICKS - len(picks)` 間補滿。公開的不夠時就全部取出。
  8. `random.shuffle(picks)` 打亂順序，讓自己的和公開的混在一起。
- **回傳**：`(picks, stats)`，即餐廳串列和評分統計字典 `{餐廳 id: (平均星數, 評價數)}`。

### `index()`

- **路由**：`GET` `/`
- **運作原理**：session 中有 `user_id`（已登入）就重導向到 `/home`，否則重導向到 `/login`。

### `home()`

- **路由**：`GET` `/home`（需要登入，套用 `login_required`）
- **運作原理**：
  1. 從 session 取出 `me`。
  2. 呼叫 `recommend(me)` 取得推薦餐廳和評分統計。
  3. 渲染 `home.html`，傳入 `restaurants`、`stats` 和 `me`。模板用 `me` 判斷哪些餐廳是使用者自己的。
