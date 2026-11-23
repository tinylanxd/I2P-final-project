# `run.py` 說明

啟動網站的進入點。這個檔案**沒有定義任何函式**，只有模組層級的程式碼，以下逐行說明。

## 程式碼運作

1. `from app import create_app`：從 `app` 套件（`app/__init__.py`）匯入應用程式工廠。
2. `app = create_app()`：在模組層級建立 Flask app，並取名為 `app`。
   - `flask --app run ...` 會匯入 `run` 模組，再找名為 `app` 的變數，所以 `flask --app run run --debug` 和 `flask --app run seed-demo` 都能運作。
   - 建立 app 的同時會建立資料表（見 [app/__init__.md](app/__init__.md) 的 `create_app`）。
3. `if __name__ == "__main__": app.run()`：
   - 只有直接執行 `python run.py` 時，`__name__` 才會是 `"__main__"`，這時用 Flask 內建的開發伺服器啟動網站，網址是 http://127.0.0.1:5000 。
   - 被 `flask` 指令或其他程式匯入時，`__name__` 是 `"run"`，不會自動啟動伺服器。

## 使用方式

```
.venv\Scripts\python run.py                        一般啟動
.venv\Scripts\python -m flask --app run run --debug  除錯模式（修改程式碼後自動重新載入）
```
