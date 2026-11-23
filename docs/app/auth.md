# `app/auth.py` 函式說明

負責帳號的註冊、登入、登出；每次請求前載入目前登入的使用者；提供 `login_required` 裝飾器保護需要登入的頁面。Blueprint 名稱為 `auth`，沒有 URL 前綴。

## 常數

- `MAX_USERNAME_LENGTH = 30`：用戶名長度上限，與 `User.username` 欄位的 `String(30)` 一致。

## 函式

### `load_logged_in_user()`

- **觸發時機**：以 `@bp.before_app_request` 註冊，整個 app 的每個請求進入視圖函式之前都會執行（不只 auth 的路由）。
- **運作原理**：
  1. 從 session 取出 `user_id`。
  2. 沒有 `user_id`：`g.user = None`。有的話用 `db.session.get(User, user_id)` 以主鍵查詢使用者。
  3. session 裡有 `user_id`，但資料庫查不到這個使用者（例如帳號已刪除，或換了資料庫）時，用 `session.clear()` 清掉這個過期的登入狀態。
- **結果**：視圖函式和模板都能用 `g.user` 取得目前使用者，未登入時為 `None`。

### `login_required(view)`

- **用途**：裝飾器，套在需要登入才能使用的視圖函式上。
- **運作原理**：
  1. 定義包裝函式 `wrapped(**kwargs)`，`kwargs` 用來接收 URL 參數（例如 `restaurant_id`）。
  2. `g.user` 為 `None`（未登入）時，重導向到登入頁 `auth.login`。
  3. 已登入就照常呼叫原本的 `view(**kwargs)`。
  4. `@wraps(view)` 讓包裝函式保留原函式的名稱。Flask 用函式名稱當 endpoint 名稱，少了它，所有被裝飾的視圖都會叫 `wrapped`，因而互相衝突。
- **前提**：依賴 `load_logged_in_user()` 事先設定好的 `g.user`。
- **回傳**：包裝後的函式。

### `validate_username(username)`

- **運作原理**：
  1. 空字串：回傳「請輸入用戶名」。
  2. 長度超過 30：回傳「用戶名不能超過 30 個字元」。
  3. 其他情況回傳 `None`，代表通過。
- **備註**：呼叫者會先 `strip()` 去掉前後空白。`users.update_username` 也重用這個函式。
- **回傳**：錯誤訊息字串或 `None`。

### `validate_password(password)`

- **運作原理**：`password.strip()` 是空的（空字串或只有空白）時回傳「請輸入密碼」，否則回傳 `None`。
- **備註**：`strip()` 只用來檢查，實際儲存的密碼保留原本的空白。`users.update_password` 也重用這個函式。

### `register()`

- **路由**：`GET`、`POST` `/register`
- **GET**：顯示 `register.html` 註冊頁。
- **POST 運作原理**：
  1. 從表單讀取 `username`（去掉前後空白）和 `password`（不去空白）。
  2. `validate_username(...) or validate_password(...)`：先驗證用戶名，有錯就用這個錯誤；沒錯才驗證密碼。結果是第一個錯誤或 `None`。
  3. 沒有錯誤時，建立 `User`，密碼經 `generate_password_hash` 雜湊後才存入，資料庫不保存明文密碼。接著加入 session 並 `commit`。
  4. `commit` 時若發生 `IntegrityError`，代表違反 `username` 的唯一限制（用戶名已存在），就 `rollback` 並把錯誤設為「這個用戶名已被使用」。這也能處理兩個人同時註冊同一個名字的情況。
  5. 成功：`flash`「註冊成功，請登入」並重導向到登入頁。
  6. 有錯誤：`flash` 錯誤訊息，然後重新顯示註冊頁。

### `login()`

- **路由**：`GET`、`POST` `/login`
- **GET**：顯示 `login.html` 登入頁。
- **POST 運作原理**：
  1. 讀取 `username`（去掉前後空白）和 `password`。
  2. 用 `db.select(User).filter_by(username=...)` 查詢使用者；`db.session.scalar` 回傳第一筆結果，查不到則是 `None`。
  3. 使用者存在，而且 `check_password_hash` 確認密碼與雜湊相符時：
     - 先 `session.clear()` 清掉舊的 session 內容（例如上一個帳號留下的位置資料）。
     - 設定 `session["user_id"] = user.id`，代表已登入。
     - 重導向到首頁 `main.home`。
  4. 否則 `flash`「用戶名或密碼錯誤」。不區分「帳號不存在」和「密碼錯誤」，避免讓人藉此得知哪些帳號存在。
  5. 重新顯示登入頁。

### `logout()`

- **路由**：`POST` `/logout`
- **運作原理**：`session.clear()` 清除所有 session 資料（登入狀態和瀏覽器分享的位置），再重導向到登入頁。
- **為什麼只接受 POST**：POST 會經過 CSRF 檢查，別的網站無法只用一個連結或圖片就讓使用者被登出。
