# `app/users.py` 函式說明

使用者的個人頁、頭像，以及設定頁（修改暱稱、自我介紹、頭像、用戶名、密碼）。Blueprint 名稱為 `users`。

## 常數

- `MAX_NICKNAME_LENGTH = 30`：暱稱長度上限。
- `MAX_BIO_LENGTH = 200`：自我介紹長度上限。
- `MAX_UPLOAD_MB = 5`：上傳大小上限，`create_app()` 用它設定 `MAX_CONTENT_LENGTH`。
- `AVATAR_SIZE = 256`：頭像輸出為 256×256 像素。
- `AVATAR_FORMATS`：接受的圖片格式 JPEG、PNG、WEBP、GIF。

## 函式

### `make_avatar(stream)`

- **參數**：`stream` 是上傳檔案的資料流。
- **用途**：把上傳的圖片轉成正方形的 WebP 頭像。
- **運作原理**：
  1. `Image.open(stream)` 開啟圖片。Pillow 依檔案內容判斷格式，不看副檔名。格式不在 `AVATAR_FORMATS` 中就回傳 `None`。
  2. `ImageOps.exif_transpose(...)`：手機照片常把旋轉方向記在 EXIF 裡，這一步依照 EXIF 把圖片轉正。
  3. `.convert("RGBA")`：統一色彩模式，保留透明度。GIF 動畫只會留下第一張影格。
  4. `ImageOps.fit(..., (256, 256))`：從中央裁切並縮放成 256×256 的正方形。
  5. 以 WebP 格式（品質 85）存進記憶體中的 `BytesIO`，回傳其中的 bytes。
  6. 發生以下例外時回傳 `None`：
     - `OSError`：無法辨識或已損壞的檔案。
     - `ValueError`：處理過程中的數值錯誤。
     - `Image.DecompressionBombError`：像素數量大得不合理的圖片（解壓縮炸彈），可能耗盡記憶體。
- **安全性**：圖片一律重新編碼，所以網站提供給別人的只會是這個函式產生的圖片，不會原封不動送出使用者上傳的檔案。
- **回傳**：WebP 的 bytes 或 `None`。

### `render_settings(**form)`

- **用途**：渲染設定頁 `settings.html`。
- **運作原理**：
  1. 先用目前使用者的 `nickname`、`bio`、`username` 當作表單預設值。
  2. 再用傳入的關鍵字參數覆蓋。例如驗證失敗時傳入使用者剛輸入的值，讓表單保留輸入內容。
- **回傳**：渲染後的頁面。

### `profile(user_id)`

- **路由**：`GET` `/users/<id>`（不需要登入）
- **運作原理**：`db.get_or_404(User, user_id)` 載入使用者（找不到回應 404），渲染 `profile.html` 個人頁。

### `avatar(user_id)`

- **路由**：`GET` `/users/<id>/avatar`（不需要登入）
- **運作原理**：
  1. 載入使用者；找不到或沒有頭像時回應 404。
  2. `make_response(user.avatar)` 把頭像 bytes 當作回應內容，`mimetype` 設為 `image/webp`。
  3. `X-Content-Type-Options: nosniff`：要求瀏覽器照著宣告的類型處理，不要自行猜測內容類型。
  4. `Cache-Control: no-cache`：瀏覽器可以快取，但每次使用前都要先向伺服器確認。
  5. 用頭像 bytes 的 SHA-256 雜湊值當作 ETag（內容的指紋）。
  6. `response.make_conditional(request)`：如果瀏覽器送來的 `If-None-Match` 與 ETag 相同，就回應 304 Not Modified，不傳送圖片；否則回應 200 並傳送圖片。
- **效果**：換了新頭像會立即顯示；頭像沒變時不會重複下載。

### `settings()`

- **路由**：`GET` `/settings`（需要登入）
- **運作原理**：呼叫 `render_settings()`，以使用者目前的資料顯示設定頁。

### `update_profile()`

- **路由**：`POST` `/settings/profile`（需要登入）
- **運作原理**：
  1. 讀取暱稱並去掉前後空白。
  2. 讀取自我介紹，先把 `\r\n` 換成 `\n` 再去掉前後空白。瀏覽器送出的換行是兩個字元，但輸入框計算長度時只算一個；不換掉的話，伺服器算出的長度會比使用者看到的長。
  3. 取得上傳的頭像檔案 `request.files.get("avatar")`。
  4. 依序驗證：
     - 暱稱不超過 30 字元。
     - 自我介紹不超過 200 字元。
     - 有選擇檔案（`upload.filename` 不是空的）時，呼叫 `make_avatar()`；轉換失敗就是錯誤「頭像請上傳 JPG、PNG、WebP 或 GIF 圖片」。
  5. 有錯誤：`flash` 錯誤，並用 `render_settings()` 帶著剛輸入的暱稱和自我介紹重新顯示（不重導向）。
  6. 沒有錯誤：
     - 更新暱稱和自我介紹。
     - 有新頭像就替換；沒有新頭像但勾選了「移除頭像」（`remove_avatar`）就設為 `None`。同時上傳又勾選移除時，以新上傳的為準。
  7. `commit`、`flash`「個人資料已更新」，重導向回設定頁。成功後重導向，使用者重新整理時就不會重複送出表單（Post/Redirect/Get）。

### `update_username()`

- **路由**：`POST` `/settings/username`（需要登入）
- **運作原理**：
  1. 讀取新用戶名並去掉前後空白，用 `validate_username()` 驗證。
  2. 沒有錯誤，而且和目前的用戶名不同時才更新並 `commit`。
  3. `commit` 發生 `IntegrityError`（用戶名已被別人使用，包括兩人同時選了同一個名字的情況）時 `rollback`，錯誤為「這個用戶名已被使用」。
  4. 有錯誤：`flash` 並保留輸入，重新顯示設定頁。
  5. 成功或沒有變更：`flash`「用戶名已更新」，重導向回設定頁。
- **備註**：登入狀態是用 `user_id` 記錄的，所以改用戶名不會被登出。

### `update_password()`

- **路由**：`POST` `/settings/password`（需要登入）
- **運作原理**：
  1. 用 `validate_password()` 檢查新密碼不是空白。
  2. 新密碼必須和「確認密碼」欄位相同，否則錯誤為「兩次輸入的密碼不一樣」。
  3. 有錯誤：`flash` 並重新顯示設定頁。
  4. 沒有錯誤：用 `generate_password_hash()` 雜湊新密碼後存入，`commit`、`flash`「密碼已更新」，重導向回設定頁。
- **備註**：這個函式不要求輸入目前的密碼。
