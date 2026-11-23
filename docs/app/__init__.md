# `app/__init__.py` 函式說明

這個檔案是 Flask 的「應用程式工廠」（application factory）：負責建立 app，並把設定、資料庫、CSRF 保護、所有 Blueprint、CLI 指令和錯誤處理接在一起。`run.py`、`share.py` 和測試都透過 `create_app()` 取得 app。

## 模組層級物件

- `csrf = CSRFProtect()`：Flask-WTF 的 CSRF 保護物件，在 `create_app()` 中綁定到 app。綁定後，每個 POST、DELETE 請求都必須帶正確的 CSRF token，否則會觸發 `handle_csrf_error`。

## 函式

### `load_secret_key(instance_path)`

- **用途**：取得 Flask 用來簽署 session cookie 的密鑰（`SECRET_KEY`）。
- **運作原理**：
  1. 先讀環境變數 `SECRET_KEY`，有值就直接回傳（正式部署時用）。
  2. 沒有的話，檢查 `instance/secret_key` 檔案是否存在，存在就讀出內容、去掉前後空白後回傳。
  3. 都沒有時，用 `secrets.token_hex(32)` 產生 64 個十六進位字元的隨機密鑰，寫進 `instance/secret_key` 後回傳。
- **為什麼這樣做**：密鑰存在 `instance/`（已被 `.gitignore` 排除），所以不會被提交到 Git；而且每次重啟伺服器都讀到同一把密鑰，使用者不會因為重啟而被登出。
- **回傳**：密鑰字串。

### `add_missing_columns()`

- **用途**：簡易的資料庫升級。模型新增了欄位、但舊的 `app.db` 裡還沒有時，自動把欄位補上。
- **背景**：`db.create_all()` 只會建立不存在的資料表，不會替既有的資料表加欄位，舊資料庫查詢新欄位時會出現 `no such column` 錯誤。
- **運作原理**：
  1. `sa.inspect(db.engine)` 取得檢查器，用來讀取資料庫裡實際的資料表結構。
  2. `db.engine.begin()` 開啟一個交易，區塊正常結束才提交。
  3. 依相依順序（`db.metadata.sorted_tables`）走訪每個模型的資料表，取得資料庫中這張表已有的欄位名稱集合。
  4. 檢查模型中的每個欄位：
     - 資料庫已有這個欄位：跳過。
     - 缺少而且是必填欄位（`nullable=False`）：丟出 `RuntimeError`，請使用者刪除 `instance/app.db` 後重新啟動。原因是舊的資料列沒有值可以填入必填欄位。
     - 缺少但可為空：把欄位型別編譯成該資料庫的 SQL 型別（例如 `FLOAT`），執行 `ALTER TABLE "表名" ADD COLUMN "欄位名" 型別`。舊資料列的新欄位值為 NULL。
- **前提**：必須在 app context 中呼叫，因為用到 `db.engine`。
- **回傳**：無；副作用是修改資料庫結構。

### `create_app(test_config=None)`

- **用途**：建立並回傳設定好的 Flask app。
- **參數**：`test_config` 是可選的字典，內容會覆蓋預設設定。測試用它換成測試用的資料庫，`share.py` 用它改用 `demo.db`。
- **運作原理**：
  1. 建立 `Flask(__name__)`，並用 `os.makedirs(..., exist_ok=True)` 確保 `instance/` 資料夾存在。
  2. 寫入預設設定：
     - `SESSION_COOKIE_SAMESITE="Lax"`：從別的網站發出的 POST 請求不會帶上 session cookie，降低 CSRF 風險。
     - `SQLALCHEMY_DATABASE_URI`：優先使用環境變數 `DATABASE_URL`，否則用 `sqlite:///app.db`。Flask-SQLAlchemy 3 會把相對的 SQLite 路徑放在 `instance/` 底下，所以實際檔案是 `instance/app.db`。
     - `MAX_CONTENT_LENGTH`：請求內容上限為 `MAX_UPLOAD_MB`（5）MB，超過時 Flask 會丟出 `RequestEntityTooLarge`。
  3. 用 `test_config` 覆蓋上述設定。
  4. 如果設定中還沒有 `SECRET_KEY`，就呼叫 `load_secret_key()` 取得。
  5. `db.init_app(app)`、`csrf.init_app(app)`：把資料庫與 CSRF 保護綁定到這個 app。
  6. 註冊五個 Blueprint：`auth`、`location`、`main`、`users`、`restaurants`。
  7. `app.cli.add_command(seed_demo)`：註冊 `flask seed-demo` 指令。
  8. 定義兩個錯誤處理函式（見下方）。
  9. 在 app context 中執行 `db.create_all()` 建立缺少的資料表，再呼叫 `add_missing_columns()` 補上缺少的欄位。
- **回傳**：Flask app 物件。

### `handle_csrf_error(error)`（定義在 `create_app` 內）

- **觸發時機**：表單或請求的 CSRF token 缺少、錯誤或過期，Flask-WTF 丟出 `CSRFError` 時。
- **運作原理**：用 `flash` 顯示「頁面已過期，請再試一次」，再重導向到 `main.index`。`index` 會依登入狀態導向首頁或登入頁。

### `handle_too_large(error)`（定義在 `create_app` 內）

- **觸發時機**：請求內容超過 `MAX_CONTENT_LENGTH`（5 MB），Flask 丟出 `RequestEntityTooLarge` 時。
- **運作原理**：整個網站只有頭像表單會上傳檔案，所以直接 `flash`「圖片不能超過 5 MB」，再重導向回設定頁 `users.settings`。
