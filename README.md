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

## 執行

```
.venv\Scripts\python run.py
```

打開 http://127.0.0.1:5000 。登入後會先看到首頁，從你的餐廳和公用餐廳隨機推薦幾間（評分越高越容易出現）。按 `Ctrl+C` 停止伺服器。

開發時如果想要存檔後自動重新啟動：

```
.venv\Scripts\python -m flask --app run run --debug
```

瀏覽器定位功能只能在 `127.0.0.1`、`localhost` 或 HTTPS 網站上使用。用手機連電腦的 IP 開網站時，無法取得位置。

## 範例資料（展示用）

想看看有資料時的樣子，可以加入範例餐廳（只需要執行一次）：

```
.venv\Scripts\python -m flask --app run seed-demo
```

會建立兩個帳號，密碼都是 `demo`：

- `demo`：有 6 間自己的餐廳，登入後首頁會同時推薦自己的和公用的餐廳。
- `foodie`：分享了 6 間公用餐廳。

餐廳名稱是虛構的，位置在新竹清大附近。重複執行不會重複加入。想清除範例資料，刪除 `instance/app.db` 再重新啟動即可（其他資料也會一起消失）。

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
