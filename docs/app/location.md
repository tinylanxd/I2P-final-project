# `app/location.py` 函式說明

接收瀏覽器（`static/location.js`）分享的定位，只存在 Flask 的 session 中，不寫入資料庫，也不寫進 log。登出或關閉瀏覽器後位置就會消失。隨機抽選頁的距離篩選會用到這個位置。Blueprint 名稱為 `location`。

## 常數與類別

- `SESSION_KEY = "location"`：位置在 session 中的鍵名。
- `KEYS = ("latitude", "longitude", "accuracy")`：位置資料的三個欄位，也決定欄位順序。
- `Location(NamedTuple)`：具名 tuple，欄位為 `latitude`（緯度）、`longitude`（經度）、`accuracy`（精確度，單位公尺）。既能用 `location.latitude` 取值，也能像 tuple 一樣用 `list(location)` 轉成串列。

## 函式

### `is_number(value)`

- **用途**：判斷一個值是否為有效的座標數字。
- **運作原理**（三個條件都成立才回傳 `True`）：
  1. 型別是 `int` 或 `float`。
  2. 不是 `bool`。Python 的 `bool` 是 `int` 的子類別，JSON 的 `true` 解碼後是 `True`，不排除的話會被當成 1。
  3. `math.isfinite(value)`：排除 NaN 和無限大。
- **回傳**：`True` 或 `False`。

### `parse_location(data)`

- **用途**：把解碼後的 JSON 驗證並轉成 `Location`。
- **運作原理**：
  1. `data` 不是字典：回傳 `None`。
  2. `KEYS` 的三個鍵必須都存在，而且值都通過 `is_number()`，否則回傳 `None`。
  3. 依 `KEYS` 的順序取值、轉成 `float`，建立 `Location`。
  4. 檢查範圍：緯度在 −90 到 90、經度在 −180 到 180、精確度不小於 0。不符合就回傳 `None`。
- **使用場合**：驗證瀏覽器 POST 進來的資料（`store_location`），以及從 session 讀回的資料（`get_user_location`）。
- **回傳**：`Location` 或 `None`。

### `get_user_location()`

- **用途**：取得瀏覽器在這個 session 中最後一次分享的位置。
- **運作原理**：
  1. 從 session 取出 `SESSION_KEY` 的值。
  2. 必須是長度為 3 的串列（存入時是 `list(location)`），否則回傳 `None`。
  3. `dict(zip(KEYS, stored))` 把串列配回欄位名稱，變回字典，再交給 `parse_location()` 重新驗證一次，防止 session 中的資料格式不對。
- **使用者**：`restaurants.pick` 在設定了距離限制時呼叫。
- **回傳**：`Location` 或 `None`。

### `store_location()`

- **路由**：`POST` `/location`（瀏覽器用 `fetch` 傳送 JSON，並在 `X-CSRFToken` 標頭帶上 CSRF token）
- **運作原理**：
  1. `request.get_json(silent=True)` 解析請求內容；不是合法 JSON 時回傳 `None`，不會丟出錯誤。
  2. 用 `parse_location()` 驗證。失敗時回傳 `{"error": "invalid location"}` 和 HTTP 400。
  3. 成功時存入 `session["location"] = list(location)`。轉成串列是因為 session 會被序列化成 JSON 存在 cookie 裡。
  4. 回傳空內容和 HTTP 204（No Content）。

### `forget_location()`

- **路由**：`DELETE` `/location`
- **運作原理**：`session.pop(SESSION_KEY, None)` 移除位置；原本就沒有也不會出錯。回傳 HTTP 204。
