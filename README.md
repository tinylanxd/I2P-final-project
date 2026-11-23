# I2P-final-project：美食地圖

用 Flask 寫的美食地圖網站：記錄餐廳、菜單與價格、評分和收藏，也可以把餐廳公開到公用資料庫。

## 事前準備

開始之前，請先安裝下面兩個工具：

| 工具 | 版本 | 備註 |
| --- | --- | --- |
| Python | 3.11 以上（開發時使用 3.14） | Windows 安裝時請勾選「Add python.exe to PATH」 |
| Git | 近期版本即可 | 用來下載和上傳程式碼 |

確認是否安裝成功（macOS / Linux 請用 `python3`）：

```
python --version
git --version
```

Flask 等 Python 套件不用手動安裝，下一步會用 `requirements.txt` 一次裝好。

## 安裝

```
git clone https://github.com/tinylanxd/I2P-final-project.git
cd I2P-final-project
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

macOS / Linux：把 `python` 換成 `python3`，把 `.venv\Scripts\python` 換成 `.venv/bin/python`（下面的指令也一樣）。

之後 pull 下來的程式如果改了 `requirements.txt`（例如新增套件），請再執行一次上面最後一行，安裝新的套件。

## 執行

```
.venv\Scripts\python run.py
```

打開 http://127.0.0.1:5000 。登入後會先看到首頁，從你的餐廳和公用餐廳隨機推薦幾間（評分越高越容易出現）。按 `Ctrl+C` 停止伺服器。

開發時如果想要存檔後自動重新啟動：

```
.venv\Scripts\python -m flask --app run run --debug
```

瀏覽器定位功能只能在 `127.0.0.1`、`localhost` 或 HTTPS 網站上使用。用手機連電腦的 IP 開網站時，無法取得位置。要用手機或其他電腦展示，請看下面的「用手機或其他電腦展示」。

## 範例資料（展示用）

想看看有資料時的樣子，可以加入範例帳號和餐廳。在專案資料夾執行一次：

```
.venv\Scripts\python -m flask --app run seed-demo
```

成功時會顯示「已加入範例資料：帳號 demo、foodie，密碼都是 demo」。接著照「執行」一節啟動網站，用帳號 `demo`、密碼 `demo` 登入。

會建立兩個帳號，密碼都是 `demo`：

- `demo`：有 6 間自己的餐廳，登入後首頁會同時推薦自己的和公用的餐廳。
- `foodie`：分享了 6 間公用餐廳。

餐廳名稱是虛構的，位置在新竹清大附近。

- 範例資料會加進 `instance/app.db`，原本的帳號和餐廳都會保留。
- 如果顯示「範例資料已經存在，沒有變更」，代表資料庫裡已經有 `demo` 或 `foodie` 帳號，這次不會加入任何資料。重複執行時也一樣，不會重複加入。
- 想清除範例資料或重新加入，刪除 `instance/app.db` 再重新啟動即可。其他帳號和餐廳也會一起消失。

## 用手機或其他電腦展示

手機或其他電腦用 `http://電腦的IP:5000` 開網站時，瀏覽器會封鎖定位。`share.py` 會一次啟動展示用的網站和 Cloudflare 的臨時通道（Quick Tunnel），拿到一個 HTTPS 網址，定位就能使用。不需要 Cloudflare 帳號，也不用改防火牆；手機用 Wi-Fi 或行動網路都連得到。

第一次使用前，先安裝 cloudflared（macOS 用 `brew install cloudflared`）：

```
winget install Cloudflare.cloudflared
```

**啟動**：在檔案總管雙擊 `share.bat`，或執行：

```
.venv\Scripts\python share.py
```

等幾秒到一分鐘，視窗會顯示 HTTPS 網址和 QR code，用手機掃描或打開網址即可，範例帳號是 `demo`／`demo`。按「🎲 抽一間」並選了距離時，瀏覽器會詢問位置權限，選「允許」。

**關閉**：在同一個視窗按 `Enter` 或 `Ctrl+C`，網站和通道會一起關掉。如果視窗卡住，或關掉視窗後網址還打得開，雙擊 `stop_share.bat`（或執行 `.venv\Scripts\python share.py stop`）強制關閉。

注意：

- 展示用另一份資料庫 `instance/demo.db`，第一次啟動時會自動加入範例資料。平常的 `instance/app.db` 不會被用到，也不會公開。想讓展示資料重新開始，先關閉展示，再刪除 `instance/demo.db`。
- 展示用的網站跑在 port 5050，可以和平常開發用的網站（port 5000）同時開著。
- 通道開著時，任何拿到網址的人都能連進來，展示完請立刻關掉。
- 每次啟動的網址都不一樣，要重新傳給大家。
- iPhone 要先在「設定 → 隱私權與安全性 → 定位服務 → Safari 網站」選「使用 App 期間」；Android 要開手機的定位。
- 開不了通道時，cloudflared 的完整紀錄在 `instance/share-cloudflared.log`。如果紀錄說不支援 quick tunnel，可能是使用者資料夾裡有 `.cloudflared\config.yaml`，先暫時把它改名再試。
- `share.bat` 和 `stop_share.bat` 只能在 Windows 使用。macOS / Linux 請執行 `.venv/bin/python share.py`，關閉用 `.venv/bin/python share.py stop`。

## 測試

```
.venv\Scripts\python -m unittest discover -s tests
```

## 資料庫與設定

- 第一次啟動時會自動建立 SQLite 資料庫 `instance/app.db`。`instance/` 資料夾不會上傳到 GitHub。
- 如果 pull 下來的程式改了資料表（例如新增欄位），請先刪除 `instance/app.db` 再啟動。舊的帳號和資料會消失。
- 可選的環境變數：
  - `DATABASE_URL`：改用其他資料庫，預設為 `sqlite:///app.db`。
  - `SECRET_KEY`：session 的加密金鑰。沒有設定時會自動產生，並存在 `instance/secret_key`。
