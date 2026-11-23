# `app/restaurants.py` 函式說明

餐廳相關的所有功能：清單與搜尋、新增與編輯、詳細頁、隨機抽選、公開／取消公開、把公開餐廳存成私人副本、刪除、收藏、評價。Blueprint 名稱為 `restaurants`，URL 前綴是 `/restaurants`。

## 常數

- `LIMITS`：四個文字欄位的長度上限（name 50、address 200、category 30、note 200）。
- `LABELS`：這四個欄位的中文名稱，用在錯誤訊息裡。
- `SCOPES`：清單的三個分頁 `mine`（我的餐廳）、`public`（公用餐廳）、`favorites`（我的收藏）。
- `SCOPE_LABELS`：三個分頁的中文名稱。
- `PRICE_CHOICES`：表單字串對應到價位整數，`{"1": 1, "2": 2, "3": 3}`。
- `DISTANCE_CHOICES`：表單字串對應到公尺數，`{"500": 500, "1000": 1000, ...}`。
- `MAX_ITEMS = 30`：每間餐廳最多 30 項餐點。
- `MAX_ITEM_NAME = 50`：餐點名稱最多 50 字元。
- `MAX_COMMENT = 200`：評價內容最多 200 字元。

---

## 初始化

### `share_price_levels(state)`

- **觸發時機**：以 `@bp.record_once` 註冊，Blueprint 第一次註冊到 app 時執行一次。
- **運作原理**：把 `PRICE_LEVELS` 放進 Jinja 的全域變數 `app.jinja_env.globals`。
- **為什麼用全域變數**：用 `{% import %}` 匯入的 macro 預設拿不到 `render_template` 傳進來的變數，放在全域就所有模板和 macro 都能用。

---

## 輔助函式

### `get_scope(value)`

- **運作原理**：`value` 是 `SCOPES` 之一就照原樣回傳，否則回傳 `"mine"`。
- **用途**：URL 或表單裡的 scope 值可能被亂改，這裡統一成合法值。

### `blank_form()`

- **用途**：產生「新增餐廳」表單的初始值。
- **運作原理**：`LIMITS` 的四個文字欄位設為空字串，再加上 `is_public=False`，以及 `price_level`、`latitude`、`longitude`、`stars`、`review_comment` 空字串和 `items=[]`（菜單）。
- **回傳**：表單字典。

### `parse_stars(raw, comment)`

- **參數**：`raw` 是表單送來的星數字串，`comment` 是評價內容。
- **運作原理**：
  1. `raw` 是空的：
     - 有填評論：回傳 `(None, "請選擇評分星數才能留下評價內容")`，不能只寫評論不給星數。
     - 沒有評論：回傳 `(None, None)`，代表「不評分」。
  2. `raw` 不是 1 到 5 的單一數字（`re.fullmatch(r"[1-5]", raw)`）：回傳錯誤「評分必須是 1 到 5 顆星」。
  3. 其他：回傳 `(int(raw), None)`。
- **回傳**：`(星數或 None, 錯誤訊息或 None)`。

### `validate(form, parsed)`

- **參數**：`form` 是使用者輸入（全是字串），`parsed` 是要填入轉換後數值的空字典。
- **用途**：驗證餐廳表單。遇到第一個錯誤就回傳。
- **運作原理**（依序檢查）：
  1. 餐廳名稱必填。
  2. 四個文字欄位不超過 `LIMITS` 的長度。
  3. 評價內容不超過 200 字元。
  4. **價位**：可以不填（空字串代表「不確定」）。有填但不是 "1"、"2"、"3" 就是錯誤。`parsed["price_level"] = PRICE_CHOICES.get(...)`，空字串會得到 `None`。
  5. **座標**：兩個都填或都不填。
     - 只要有一個有值，兩個都必須能轉成 `float`；只填一個時另一個是空字串，`float("")` 會丟出 `ValueError`，於是回傳「座標格式不正確」。
     - 必須是有限數字，緯度在 −90 到 90、經度在 −180 到 180，否則「座標超出範圍」。
     - 通過後存入 `parsed`；都沒填則兩個都存 `None`。
  6. **菜單**：最多 30 項。每一項的名稱必填、不超過 50 字元；價格可以留空，有填就必須是 1 到 5 位數字（0–99999，`re.fullmatch(r"[0-9]{1,5}", ...)`）並轉成 `int`。結果存成 `parsed["items"] = [(名稱, 價格或 None), ...]`。
  7. **評分**：呼叫 `parse_stars()`，結果存入 `parsed["stars"]`。
- **設計**：`form` 保留原始字串，驗證失敗時可以原樣顯示回表單；`parsed` 存轉換後的型別，寫入資料庫時使用。
- **回傳**：錯誤訊息或 `None`。

### `read_form()`

- **用途**：讀取新增／編輯餐廳表單。
- **運作原理**：
  1. 讀取四個文字欄位並去掉前後空白。
  2. `is_public`：checkbox 有勾選才會被送出，所以用 `bool(...)` 轉成 True／False。
  3. 讀取 `price_level`、`latitude`、`longitude`、`stars`、`review_comment`，同樣去掉前後空白。
  4. **菜單**：表單中有多個同名的 `item_name` 和 `item_price` 欄位，`request.form.getlist()` 分別取得兩個串列。
     - `zip_longest(names, prices, fillvalue="")` 一對一配對，長度不同時用空字串補齊。
     - 每列去掉前後空白，再濾掉名稱和價格都空白的列（使用者留下的空白列）。
  5. 建立空的 `parsed`，呼叫 `validate(form, parsed)` 驗證並填值。
- **回傳**：`(form, parsed, error)`。

### `form_from_restaurant(restaurant, me)`

- **用途**：編輯頁要預先填好資料，把資料庫中的餐廳轉回表單格式（全部是字串）。
- **運作原理**：
  1. 用 `getattr` 複製四個文字欄位，再複製 `is_public`。
  2. `price_level`、`latitude`、`longitude` 是 `None` 時轉成空字串，否則轉成字串。
  3. 每個菜單項目轉成 `{"name": ..., "price": ...}`，沒有價格時是空字串。
  4. 用 `my_review()` 找出使用者自己的評價，填入 `stars` 和 `review_comment`；沒有評價則都是空字串。
- **回傳**：表單字典。

### `apply_form(restaurant, form, parsed)`

- **用途**：把驗證過的表單資料寫進餐廳物件（還沒 commit）。
- **運作原理**：
  1. 四個文字欄位和 `is_public` 從 `form` 寫入。
  2. `price_level`、`latitude`、`longitude` 從 `parsed` 寫入，這些已經是正確的型別。
  3. `restaurant.menu_items` 換成一個由 `parsed["items"]` 建立的全新 `MenuItem` 串列。模型設定了 `delete-orphan`，所以被換掉的舊項目會從資料庫刪除。

### `my_review(restaurant, me)`

- **運作原理**：`next((r for r in restaurant.reviews if r.user_id == me), None)` 在這間餐廳的評價中找出第一則屬於 `me` 的。`next` 的第二個參數是找不到時的預設值。
- **回傳**：`Review` 或 `None`。

### `set_my_review(restaurant, me, stars, comment)`

- **用途**：新增、更新或刪除使用者自己的評價（不 commit，由呼叫者 commit）。
- **運作原理**：
  1. 先用 `my_review()` 找出現有評價。
  2. `stars` 是 `None`：如果有現有評價，就從 `restaurant.reviews` 中移除（`delete-orphan` 會把它從資料庫刪除）。
  3. 有星數而且已有評價：更新星數和評論。
  4. 有星數但還沒有評價：新增一則 `Review`。

### `get_owned(restaurant_id)`

- **用途**：載入一間「必須是自己的」餐廳，用於編輯、刪除、切換公開。
- **運作原理**：
  1. `db.get_or_404(...)`：找不到就回應 404。
  2. 擁有者不是目前使用者：`abort(403)`（禁止存取）。
- **回傳**：`Restaurant`。

### `get_visible(restaurant_id)`

- **用途**：載入一間目前使用者「看得到」的餐廳，也就是自己的或公開的。
- **運作原理**：
  1. 找不到：404。
  2. 不是自己的而且沒有公開：也回應 404。這裡用 404 而不是 403，不讓人知道這個 id 底下有一間私人餐廳。
- **回傳**：`Restaurant`。

### `rating_stats(restaurant_ids)`

- **用途**：一次取得多間餐廳的評分統計。
- **運作原理**：
  1. 串列是空的就直接回傳 `{}`，省下一次查詢。
  2. 執行相當於以下的 SQL：
     ```sql
     SELECT restaurant_id, AVG(stars), COUNT(id)
     FROM review
     WHERE restaurant_id IN (...)
     GROUP BY restaurant_id
     ```
  3. 把結果轉成字典，平均值轉成 `float`。
- **優點**：整個清單只查一次資料庫，不必每間餐廳各查一次（避免 N+1 查詢）。
- **回傳**：`{餐廳 id: (平均星數, 評價數)}`。沒有任何評價的餐廳不會出現在字典裡。

### `favorite_ids(me)`

- **運作原理**：查詢 `Favorite` 表中 `user_id == me` 的所有 `restaurant_id`，轉成 `set`。
- **用途**：模板用它決定每間餐廳要顯示「收藏」還是「取消收藏」按鈕。
- **回傳**：餐廳 id 的集合。

### `saved_source_ids(me)`

- **運作原理**：查詢使用者自己的餐廳中 `source_id` 不是 `None` 的那些，取出 `source_id`，轉成 `set`。
- **意義**：使用者已經存過私人副本的公開餐廳 id。
- **使用場合**：清單和詳細頁用來顯示「已存入」；首頁推薦用來排除重複的店。
- **回傳**：餐廳 id 的集合。

### `scope_query(scope, me)`

- **用途**：依分頁產生對應的查詢敘述（select statement，還沒執行，呼叫者可以再加條件）。
- **運作原理**：
  - `public`：所有 `is_public` 為 True 的餐廳，包含自己公開的。
  - `favorites`：`Restaurant` JOIN `Favorite`，條件是收藏者是 `me`，而且餐廳是自己的或公開的。別人把餐廳改回私人後，它會從收藏分頁消失（`Favorite` 資料列仍然保留）。
  - 其他（`mine`）：`user_id == me` 的餐廳。
- **回傳**：SQLAlchemy `Select` 物件。

### `parse_pick_filters(distance, prices)`

- **參數**：`distance` 是距離選項字串（空字串代表不限），`prices` 是勾選的價位字串串列。
- **運作原理**：
  1. `distance` 有值但不在 `DISTANCE_CHOICES` 中：回傳錯誤「距離選項不正確」。
  2. 任何一個價位不在 `PRICE_CHOICES` 中：回傳錯誤「價位選項不正確」。
  3. 通過時，把距離轉成公尺數（空字串得到 `None`），價位轉成整數集合。
- **回傳**：`(公尺數或 None, 價位整數集合, 錯誤或 None)`。

### `draw(scope, me, max_m, levels, origin, last_id)`

- **用途**：依條件隨機抽出一間餐廳。
- **原則**：資料缺漏不會讓餐廳被排除。沒有座標或沒有價位的餐廳仍是候選，只是結果會標示「未知」。
- **運作原理**：
  1. 用 `scope_query()` 取得這個分頁的基本查詢。
  2. 有勾選價位時加上條件：價位在 `levels` 中，**或**價位是 `None`（沒填的不排除）。
  3. 執行查詢取得所有符合的餐廳。
  4. 距離：
     - `max_m` 是 `None`（不限距離）：每間餐廳都是候選，距離記為 `None`。
     - 有距離限制：用 `within_distance()` 篩選，沒有座標的也保留。
  5. 用 `choose(candidates, last_id)` 抽一間，盡量避開上一次抽到的。
  6. 沒有任何候選：回傳 `(None, 0)`。
  7. 組成結果字典：
     - `restaurant`：抽中的餐廳。
     - `distance`：格式化後的距離字串，不知道距離時是 `None`。
     - `unknown_distance`：有設距離限制，但這間沒有座標。
     - `unknown_price`：有勾選價位，但這間沒填價位。
- **回傳**：`(結果字典或 None, 候選數量)`。

### `back_to_list(restaurant_id=None)`

- **用途**：操作完成後，回到使用者按下按鈕的那一頁。
- **運作原理**：
  1. 有傳 `restaurant_id`，而且表單的 `return_to` 是 `"detail"`：回到這間餐廳的詳細頁。
  2. 否則回到清單頁，分頁由表單的 `scope` 決定（經 `get_scope()` 驗證）。
- **備註**：`delete()` 不傳 id，因為餐廳已經刪除，無法回到它的詳細頁。
- **回傳**：重導向回應。

---

## 頁面

### `index()`

- **路由**：`GET` `/restaurants/`（需要登入）
- **運作原理**：
  1. 從網址參數讀取 `scope`（分頁）和 `q`（搜尋字詞）。
  2. 用 `scope_query()` 取得基本查詢。
  3. 有搜尋字詞時，用 `%q%` 做不分大小寫的模糊比對（`ilike`），只要名稱、分類、地址或任一菜單項目名稱符合就列出。菜單的比對用 `menu_items.any(...)`，會產生一個 EXISTS 子查詢。
  4. 依 id 由大到小排序，最新的排在最前面。
  5. 渲染 `restaurants.html`，傳入餐廳清單，以及 `rating_stats`、`favorite_ids`、`saved_source_ids` 的結果。

### `pick()`

- **路由**：`GET` `/restaurants/pick`（需要登入）
- **為什麼用 GET**：抽選不會改動任何資料，所以用一般的 GET 表單，不需要 CSRF token，也可以重新整理頁面。
- **運作原理**：
  1. 讀取網址參數：`scope`、`distance`、`price`（可以複選，用 `getlist`）、`draw`。`draw=1` 代表按下了抽選按鈕；沒有的話只顯示表單。
  2. 按下抽選時：
     1. 用 `parse_pick_filters()` 驗證距離與價位。
     2. 有距離限制時用 `get_user_location()` 取得位置；取不到就顯示錯誤，請使用者允許定位，或把距離改成「不限」。
     3. 沒有錯誤時，讀取 `last`（上一次抽到的 id；`type=int` 讓無法轉換的值變成 `None`），再呼叫 `draw()`。
  3. 渲染 `restaurant_pick.html`。有抽到結果時，另外查詢那一間的評分統計。

### `detail(restaurant_id)`

- **路由**：`GET` `/restaurants/<id>`（需要登入）
- **運作原理**：用 `get_visible()` 載入餐廳（看不到的回應 404），渲染 `restaurant_detail.html`，傳入評分統計、自己的評價（`my_review`）、收藏與已存副本的 id 集合。

### `new()`

- **路由**：`GET`、`POST` `/restaurants/new`（需要登入）
- **GET**：用 `blank_form()` 顯示空白表單。
- **POST 運作原理**：
  1. `read_form()` 讀取並驗證表單。
  2. 沒有錯誤：建立 `Restaurant(user_id=me)`，用 `apply_form()` 填入資料，用 `set_my_review()` 加上評分（新增時可以順便評分），加入 session 並 `commit`，然後 `flash` 成功訊息並回到清單頁。
  3. 有錯誤：`flash` 錯誤，並帶著使用者剛輸入的內容重新顯示表單。

### `edit(restaurant_id)`

- **路由**：`GET`、`POST` `/restaurants/<id>/edit`（需要登入）
- **運作原理**：
  1. 用 `get_owned()` 載入餐廳，只能編輯自己的。
  2. 用 `form_from_restaurant()` 把現有資料轉成表單預填值。
  3. POST 時 `read_form()`；沒有錯誤就 `apply_form()`、`set_my_review()`（星數清空會刪除自己的評價），再 `commit` 並回到清單頁。有錯誤則 `flash` 並保留輸入重新顯示。

---

## 動作（都只接受 POST，需要登入）

### `toggle_share(restaurant_id)`

- **路由**：`POST` `/restaurants/<id>/share`
- **運作原理**：用 `get_owned()` 載入自己的餐廳，把 `is_public` 反轉後 `commit`，依新的狀態 `flash`「已公開到公用資料庫」或「已取消公開」，最後用 `back_to_list()` 回到原本的頁面。

### `save_copy(restaurant_id)`

- **路由**：`POST` `/restaurants/<id>/save`
- **用途**：把別人的公開餐廳存成自己的私人副本。
- **運作原理**：
  1. 載入來源餐廳，找不到回應 404。
  2. 來源沒有公開，或是自己的餐廳：回應 404，因為只有別人的公開餐廳可以存。
  3. 查詢是否已經存過（`user_id=me` 而且 `source_id=來源 id`）；存過就 `flash`「這間餐廳已在你的清單中」。
  4. 沒存過就建立新的 `Restaurant`：
     - 複製名稱、地址、分類、備註、價位、座標。
     - `is_public=False`，副本是私人的。
     - `source_id` 記錄來源餐廳。
     - 菜單建立全新的 `MenuItem` 物件來複製。
     - 評價和收藏屬於個人，不複製。
  5. `commit`、`flash`「已存入我的清單」，再 `back_to_list(來源 id)`。

### `delete(restaurant_id)`

- **路由**：`POST` `/restaurants/<id>/delete`
- **運作原理**：
  1. 用 `get_owned()` 載入自己的餐廳。
  2. 用一次 `UPDATE` 把所有 `source_id` 指向這間餐廳的副本改成 `None`。別人存的副本會保留，只是失去與來源的連結，也不會留下指向已刪除資料的外鍵。
  3. `db.session.delete(restaurant)`；菜單、評價和收藏由 ORM 的 cascade 一起刪除。
  4. `commit`、`flash`「已刪除餐廳」，回到清單頁。

### `favorite(restaurant_id)`

- **路由**：`POST` `/restaurants/<id>/favorite`
- **運作原理**：
  1. 用 `get_visible()` 載入，只能收藏看得到的餐廳。
  2. 查詢是否已經收藏過；沒有的話新增 `Favorite` 並 `commit`。
  3. 不論是否已經收藏過，都 `flash`「已加入收藏」。重複送出得到的結果相同。

### `unfavorite(restaurant_id)`

- **路由**：`POST` `/restaurants/<id>/unfavorite`
- **運作原理**：直接執行 `DELETE FROM favorite WHERE user_id = me AND restaurant_id = id`，再 `commit`、`flash`「已取消收藏」。
- **備註**：這裡不檢查餐廳是否還看得到，所以即使餐廳已被改回私人，使用者仍然可以取消收藏；本來就沒有收藏時，刪除不到任何東西，也不會出錯。

### `review(restaurant_id)`

- **路由**：`POST` `/restaurants/<id>/review`
- **運作原理**：
  1. 用 `get_visible()` 載入，只能評價看得到的餐廳。
  2. 讀取評論（去掉前後空白），用 `parse_stars()` 解析星數。
  3. 這個表單一定要評分：沒有錯誤但星數是 `None` 時，錯誤為「請選擇評分星數」。
  4. 評論不能超過 200 字元。
  5. 有錯誤就 `flash` 錯誤；否則 `set_my_review()` 新增或更新評價，`commit` 並 `flash`「已送出評價」。
  6. 回到這間餐廳的詳細頁。

### `delete_review(restaurant_id)`

- **路由**：`POST` `/restaurants/<id>/review/delete`
- **運作原理**：用 `get_visible()` 載入，呼叫 `set_my_review(restaurant, me, None, "")` 移除自己的評價，`commit`、`flash`「已刪除我的評價」，回到詳細頁。
