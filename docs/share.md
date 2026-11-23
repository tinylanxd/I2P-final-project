# `share.py` 函式說明

一鍵展示：用展示專用的資料庫 `instance/demo.db` 啟動網站，再透過 Cloudflare 的臨時通道（Quick Tunnel）取得一個 HTTPS 網址，並在終端機印出 QR code，讓手機或其他電腦連進來。一般使用的 `instance/app.db` 不會被公開。

- 啟動：`.venv\Scripts\python share.py`，或雙擊 `share.bat`
- 強制關閉：`.venv\Scripts\python share.py stop`，或雙擊 `stop_share.bat`

## 常數

- `PORT = 5050`：展示伺服器使用的 port，與一般開發用的 5000 錯開。
- `INSTANCE`：專案的 `instance/` 資料夾。
- `PID_FILE`：`instance/share.pid`，記錄展示伺服器和通道的 PID，供 `stop` 使用。
- `LOG_FILE`：`instance/share-cloudflared.log`，cloudflared 的完整輸出紀錄。
- `DEMO_DATABASE = "sqlite:///demo.db"`：展示用資料庫，相對路徑會放在 `instance/` 底下。
- `INSTALL_HINT`：找不到 cloudflared 時提示的安裝指令。
- `CLOUDFLARED_DIRS`：winget 安裝 cloudflared 的預設資料夾。剛安裝完時，已經開著的終端機 PATH 還沒更新，所以要另外到這些資料夾找。
- `EXPECTED = {"tunnel": "cloudflared", "server": "python"}`：PID 檔中每個角色應該對應的程式名稱開頭，用來確認這個 PID 還是當初的程式。
- `TUNNEL_URL`：比對通道網址的正規表示式（見 `find_tunnel_url`）。
- `URL_TIMEOUT = 30`：等 cloudflared 給出網址的秒數上限。
- `REACHABLE_TIMEOUT = 120`：等新網址可以連線的秒數上限。新的 trycloudflare 名稱要約 10 秒到一分多鐘才會出現在 DNS。

---

## 輔助函式

### `find_tunnel_url(line)`

- **運作原理**：用 `TUNNEL_URL`（`https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com`）在一行文字中搜尋。`(?!api\.)` 是負向前瞻，排除 `api.trycloudflare.com`：這個位址出現在 cloudflared 的錯誤訊息裡，不是通道網址。
- **回傳**：找到的網址，或 `None`。

### `find_cloudflared()`

- **運作原理**：
  1. 先用 `shutil.which("cloudflared")` 在 PATH 中尋找。
  2. 找不到時，依序檢查 `CLOUDFLARED_DIRS` 中是否有 `cloudflared.exe`。
- **回傳**：cloudflared 執行檔的路徑字串，或 `None`。

### `write_pids(path, pids)`

- **運作原理**：把 `{角色: PID}` 字典轉成 JSON 寫入檔案。

### `read_pids(path)`

- **運作原理**：
  1. 讀取並解析 JSON；檔案不存在或內容損壞（`OSError`、`ValueError`）時回傳 `{}`。
  2. 內容不是字典也回傳 `{}`。
  3. 只保留角色在 `EXPECTED`（`tunnel`、`server`）中、而且 PID 是整數的項目（排除 `bool`，因為 `True` 也算 `int`）。
- **回傳**：`{角色: PID}`。

### `process_name(pid)`

- **用途**：查詢某個 PID 目前是哪個程式。
- **運作原理**：
  - **Windows**：執行 `tasklist /FI "PID eq N" /FO CSV /NH`（只顯示這個 PID、CSV 格式、不要標題列）。
    - 找到時輸出一行以 `"` 開頭的 CSV，用 `csv.reader` 解析，第一欄就是程式名稱（例如 `cloudflared.exe`）。
    - 找不到時 tasklist 輸出的是一行說明文字（不以 `"` 開頭），回傳 `None`。
  - **其他系統**：執行 `ps -p PID -o comm=` 取得指令名稱，再用 `Path(...).name` 去掉路徑；輸出是空的則回傳 `None`。
- **回傳**：程式名稱或 `None`。

### `running_demo(pids)`

- **用途**：找出 PID 檔裡記錄的程式中，哪些仍是展示用的程式而且還在執行。
- **運作原理**：依序檢查 `tunnel` 和 `server` 兩個角色：
  1. 沒有記錄 PID，或 PID 是目前這個 Python 行程自己（`os.getpid()`）：跳過，避免把自己關掉。
  2. 用 `process_name()` 取得程式名稱，必須以 `EXPECTED` 中的名稱開頭（不分大小寫）才算數。PID 會被作業系統重複使用，舊的 PID 可能已經分配給別的程式，這個檢查可以避免誤殺。
- **回傳**：`[(角色, PID, 程式名稱), ...]`。

### `kill(pid)`

- **運作原理**：
  - **Windows**：`taskkill /PID N /T /F`。`/T` 會連同子行程一起結束，`/F` 是強制結束，不先詢問程式。
  - **其他系統**：送出 `SIGTERM`。

### `port_in_use(port)`

- **運作原理**：建立 socket 嘗試連線 `127.0.0.1:port`。`connect_ex` 回傳 0 代表連線成功，也就是有程式在這個 port 上監聽。`with` 區塊結束時自動關閉 socket。
- **回傳**：`True` 或 `False`。

### `port_owner(port)`

- **用途**：找出占用 port 的程式 PID（只支援 Windows，其他系統回傳 `None`）。
- **運作原理**：
  1. 執行 `netstat -ano -p TCP` 列出所有 TCP 連線。
  2. 把每行依空白切開，找出符合以下條件的行：
     - 剛好 5 欄（協定、本機位址、外部位址、狀態、PID）。
     - 本機位址以 `:port` 結尾。
     - 外部位址是 `0.0.0.0:0`，代表正在監聽。狀態欄的文字會依系統語言翻譯，不能直接比對 `LISTENING`，所以改用外部位址判斷。
  3. 回傳該行最後一欄的 PID。
- **回傳**：PID 或 `None`。

---

## 關閉

### `stop(pid_file=PID_FILE, port=PORT)`

- **用途**：`share.py stop` 的實作，強制關閉執行中或殘留的展示伺服器與通道。
- **運作原理**：
  1. `read_pids()` 讀取 PID 檔，再用 `running_demo()` 找出仍在執行的展示程式。
  2. 逐一用 `kill()` 結束。
  3. 刪除 PID 檔（`missing_ok=True`：檔案不存在也不報錯）。
  4. 有關閉任何程式：印出關閉了哪些程式和 PID，回傳 0。
  5. 沒有找到：印出「沒有正在執行的展示伺服器」。如果 port 仍被占用，用 `port_owner()` 找出 PID，提示使用者到工作管理員確認是什麼程式。回傳 0。
- **備註**：參數有預設值，測試時可以傳入暫存的 PID 檔路徑和其他 port。

---

## 啟動

### `TunnelOutput` 類別

在背景讀取 cloudflared 的輸出：寫進 log 檔、保留最後幾行供錯誤訊息使用，並從中找出通道網址。

#### `__init__(self, process, log_path)`

- **運作原理**：
  1. `self.url = None`：通道網址，還沒找到。
  2. `self.last_lines = collections.deque(maxlen=15)`：長度固定為 15 的佇列，加入新行時最舊的一行會自動被丟掉，所以永遠只保留最後 15 行。
  3. `self.done = threading.Event()`：找到網址或 cloudflared 結束時設定，通知主執行緒。
  4. 啟動一個 daemon 背景執行緒執行 `_read()`。daemon 代表主程式結束時不必等這個執行緒。
- **為什麼要背景執行緒**：cloudflared 的輸出必須持續被讀取，否則管線緩衝區滿了它會卡住；同時主執行緒可以設定逾時來等待網址。

#### `_read(self, process, log_path)`

- **運作原理**：
  1. 以 UTF-8 開啟 log 檔（覆寫舊內容）。
  2. 逐行讀取 cloudflared 的輸出。啟動時已把 stderr 合併到 stdout，所以錯誤訊息也會讀到。對每一行：
     - 寫入 log 檔並立即 `flush`，讓檔案即時更新。
     - 去掉行尾換行後加入 `last_lines`。
     - 還沒找到網址時，用 `find_tunnel_url()` 檢查這一行；找到就存進 `self.url`，並 `done.set()` 通知主執行緒。
  3. 輸出結束（cloudflared 已經結束）後也 `done.set()`，主執行緒就不必等到逾時。

### `wait_until_reachable(url, timeout=REACHABLE_TIMEOUT)`

- **用途**：等新的通道網址真的可以連線。
- **運作原理**：
  1. `deadline = time.monotonic() + timeout`。`monotonic` 只會往前走，不受使用者調整系統時間影響。
  2. 建立對 `url + "/login"` 的請求，並設定 `User-Agent` 標頭。
  3. 在期限內重複：
     - 用 `urlopen` 連線，單次逾時 10 秒；回應狀態 200 時換行並回傳 `True`。
     - 連線失敗時忽略例外繼續等待。`OSError` 涵蓋 DNS 還查不到名稱（`URLError`）、通道還在註冊時的錯誤狀態碼如 530（`HTTPError`）、逾時與連線中斷；`http.client.HTTPException` 涵蓋其他 HTTP 層錯誤。
     - 印一個 `.` 表示還在等，然後等 2 秒。
  4. 超過期限：換行並回傳 `False`。
- **回傳**：`True` 或 `False`。

### `show(url)`

- **運作原理**：
  1. 印出網址。
  2. 用 `qrcode.QRCode(border=2)` 產生 QR code：`add_data` 放入網址，`make(fit=True)` 自動選擇合適的尺寸。
  3. `print_ascii(invert=True)` 用文字方塊在終端機畫出 QR code。`invert=True` 讓淺色模組以方塊顯示，在深色背景的視窗中比較好掃。
  4. 印出範例帳號提示，並警告：通道開著時，任何拿到網址的人都能連進來。

### `wait_for_stop(tunnel)`

- **用途**：讓展示持續執行，直到使用者要求關閉。
- **內部函式 `warn_if_tunnel_dies()`**（在背景執行緒中執行）：
  1. `tunnel.wait()` 等待 cloudflared 結束。
  2. 等 1 秒。使用者按 Ctrl+C 時，cloudflared 也會收到並可能先結束，這 1 秒讓主執行緒有時間設定 `stopping`，這種情況就不會被誤報成意外關閉。
  3. 如果 `stopping` 還沒設定，代表通道是意外關閉的，印出警告，請使用者按 Enter 關閉後重新啟動。
- **主流程**：
  1. 建立 `stopping` 事件，啟動監看執行緒。
  2. 印出「按 Enter 或 Ctrl+C 關閉」，用 `input()` 等使用者按 Enter。
  3. 遇到 `EOFError`（沒有鍵盤輸入，例如在背景執行時 stdin 是 NUL 裝置）時，改用 `tunnel.wait()` 一直等到通道結束（使用者按 Ctrl+C 或執行 `share.py stop`）。程式碼註解說明了為什麼不用 `isatty()` 判斷：在 Windows 上，NUL 裝置的 `isatty()` 也是 True。
  4. `finally` 一定會設定 `stopping`，表示接下來的關閉是預期中的。
  5. 按 Ctrl+C 時，`input()` 丟出的 `KeyboardInterrupt` 會往上傳到 `start()` 處理。

### `stop_tunnel(tunnel)`

- **運作原理**：
  1. `tunnel.poll()` 是 `None` 代表 cloudflared 還在執行，才需要關閉。
  2. 先 `terminate()` 請它結束，最多等 5 秒。
  3. 逾時（`TimeoutExpired`）就 `kill()` 強制結束，再 `wait()` 回收行程。

### `start()`

- **用途**：啟動展示伺服器和通道，直到使用者關閉。
- **運作原理**：
  1. **前置檢查**（任一項失敗就印出原因並回傳 1）：
     - 用 `find_cloudflared()` 找不到 cloudflared：提示用 winget 安裝。
     - `running_demo(read_pids(PID_FILE))` 不是空的：已經有一個展示在執行。
     - `port_in_use(5050)`：port 被其他程式占用。
  2. **啟動網站**：
     - `create_app({"SQLALCHEMY_DATABASE_URI": DEMO_DATABASE})`：改用 `instance/demo.db`。
     - 在 app context 中呼叫 `add_demo_data()`；第一次加入範例資料時印出帳號資訊。
     - 把 werkzeug 的 log 等級設為 ERROR，不印出每個請求的紀錄，網址和 QR code 才不會被洗掉。
     - `make_server("127.0.0.1", 5050, app, threaded=True)` 建立 WSGI 伺服器，在 daemon 背景執行緒中執行 `serve_forever`。只監聽 127.0.0.1，外部只能透過通道連進來。
  3. **開啟通道**：
     - `subprocess.Popen` 執行 `cloudflared tunnel --url http://127.0.0.1:5050`，stdout 與 stderr 合併成一個文字管線。
     - `write_pids()` 記錄 `server`（目前的 Python 行程）和 `tunnel`（cloudflared）的 PID。
     - 建立 `TunnelOutput` 開始在背景讀取輸出。
  4. **等待與顯示**（`try` 區塊）：
     - `output.done.wait(30)`：最多等 30 秒取得網址。
     - 沒拿到網址：印出 cloudflared 最後 15 行輸出和 log 檔位置，狀態設為 1。
     - 拿到網址：用 `wait_until_reachable()` 確認可以連線（連不到也只印警告，繼續執行），接著 `show()` 顯示網址和 QR code，再用 `wait_for_stop()` 等使用者關閉。
  5. `except KeyboardInterrupt: pass`：Ctrl+C 是正常的關閉方式，不當成錯誤。
  6. **清理**（`finally`，一定會執行）：
     - `signal.signal(signal.SIGINT, signal.SIG_IGN)`：忽略之後的 Ctrl+C，避免使用者再按一次時中斷清理。
     - `stop_tunnel()` 關閉通道，`server.shutdown()` 關閉網站伺服器，刪除 PID 檔。
  7. 印出「已關閉伺服器和通道」。
- **回傳**：結束狀態碼（0 成功，1 失敗）。

### `main(argv)`

- **參數**：`argv` 是命令列參數（不含程式名稱）。
- **運作原理**：
  1. `sys.stdout.reconfigure(errors="replace")`：主控台的編碼無法顯示某些字元（例如 ⚠ 或 QR code 的方塊）時，以替代字元顯示，而不是讓程式崩潰。某些環境的 stdout 沒有 `reconfigure` 方法，這時忽略 `AttributeError`。
  2. 參數是 `["stop"]`：執行 `stop()`。
  3. 有其他參數：印出用法，回傳 2。
  4. 沒有參數：執行 `start()`。
- **程式進入點**：`if __name__ == "__main__": sys.exit(main(sys.argv[1:]))`，把 `main` 的回傳值當作程式的結束碼。`share.bat` 會在結束碼不是 0 時暫停視窗，讓使用者看得到錯誤訊息。
