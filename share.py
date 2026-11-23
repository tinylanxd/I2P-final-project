"""One-click demo: run the app on the demo database behind a Cloudflare tunnel.

    .venv\\Scripts\\python share.py        start (or double-click share.bat)
    .venv\\Scripts\\python share.py stop   force-stop a running or left-over demo
                                           (or double-click stop_share.bat)

The demo uses instance/demo.db, so the normal instance/app.db is never exposed.
See README.md, section 「用手機或其他電腦展示」.
"""

import collections
import csv
import http.client
import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import qrcode
from werkzeug.serving import make_server

from app import create_app
from app.demo import ADDED_MESSAGE, add_demo_data

PORT = 5050
INSTANCE = Path(__file__).resolve().parent / "instance"
PID_FILE = INSTANCE / "share.pid"
LOG_FILE = INSTANCE / "share-cloudflared.log"
DEMO_DATABASE = "sqlite:///demo.db"  # relative paths live in instance/
INSTALL_HINT = "winget install Cloudflare.cloudflared"
# winget installs here, but PATH only changes for terminals opened afterwards.
CLOUDFLARED_DIRS = [
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "cloudflared",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "cloudflared",
]
# The process each PID-file entry must still be, so a reused PID is never killed.
EXPECTED = {"tunnel": "cloudflared", "server": "python"}
# Error lines mention api.trycloudflare.com, which is not the tunnel's address.
TUNNEL_URL = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com")
URL_TIMEOUT = 30
# A new trycloudflare name takes a while to appear in DNS: about 10 s to over a minute.
REACHABLE_TIMEOUT = 120


# --------------------------------------------------------------- helpers


def find_tunnel_url(line):
    match = TUNNEL_URL.search(line)
    return match.group(0) if match else None


def find_cloudflared():
    found = shutil.which("cloudflared")
    if found:
        return found
    for folder in CLOUDFLARED_DIRS:
        exe = folder / "cloudflared.exe"
        if exe.is_file():
            return str(exe)
    return None


def write_pids(path, pids):
    path.write_text(json.dumps(pids))


def read_pids(path):
    """{role: pid} from the PID file; {} when it is missing or broken."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        role: pid
        for role, pid in data.items()
        if role in EXPECTED and isinstance(pid, int) and not isinstance(pid, bool)
    }


def process_name(pid):
    """The program name of a running process, or None if there is none."""
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="replace",
        )
        line = result.stdout.strip()
        return next(csv.reader([line]))[0] if line.startswith('"') else None
    result = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True)
    return Path(result.stdout.strip()).name or None


def running_demo(pids):
    """[(role, pid, name)] for PID-file entries that are still the demo's processes."""
    running = []
    for role in ("tunnel", "server"):
        pid = pids.get(role)
        if pid is None or pid == os.getpid():
            continue
        name = process_name(pid)
        if name and name.lower().startswith(EXPECTED[role]):
            running.append((role, pid, name))
    return running


def kill(pid):
    if os.name == "nt":
        # /T also ends the process's children, /F does not ask the program first.
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        os.kill(pid, signal.SIGTERM)


def port_in_use(port):
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def port_owner(port):
    """PID listening on the port (Windows only), or None."""
    if os.name != "nt":
        return None
    result = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, errors="replace")
    for parts in (line.split() for line in result.stdout.splitlines()):
        # Proto, local address, foreign address, state, PID. The state is localized,
        # but a listening socket always has foreign address 0.0.0.0:0.
        if len(parts) == 5 and parts[1].endswith(f":{port}") and parts[2] == "0.0.0.0:0":
            return int(parts[4])
    return None


# ------------------------------------------------------------------ stop


def stop(pid_file=PID_FILE, port=PORT):
    running = running_demo(read_pids(pid_file))
    for _, pid, _ in running:
        kill(pid)
    pid_file.unlink(missing_ok=True)

    if running:
        print("已強制關閉：" + "、".join(f"{name}（PID {pid}）" for _, pid, name in running))
        return 0
    print("沒有正在執行的展示伺服器")
    if port_in_use(port):
        owner = port_owner(port)
        who = f"PID {owner}" if owner else "其他程式"
        print(f"注意：port {port} 還被 {who} 占用，請到工作管理員確認是什麼程式。")
    return 0


# ----------------------------------------------------------------- start


class TunnelOutput:
    """Reads cloudflared's output in the background: saves it to the log file,
    keeps the last lines for error messages and picks out the tunnel URL."""

    def __init__(self, process, log_path):
        self.url = None
        self.last_lines = collections.deque(maxlen=15)
        self.done = threading.Event()  # set once the URL is known or cloudflared ends
        threading.Thread(target=self._read, args=(process, log_path), daemon=True).start()

    def _read(self, process, log_path):
        with open(log_path, "w", encoding="utf-8") as log:
            for line in process.stdout:
                log.write(line)
                log.flush()
                self.last_lines.append(line.rstrip())
                if self.url is None:
                    self.url = find_tunnel_url(line)
                    if self.url:
                        self.done.set()
        self.done.set()


def wait_until_reachable(url, timeout=REACHABLE_TIMEOUT):
    deadline = time.monotonic() + timeout
    request = urllib.request.Request(url + "/login", headers={"User-Agent": "Mozilla/5.0 (share.py)"})
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status == 200:
                    print()
                    return True
        # URLError (name not in DNS yet), HTTPError (e.g. 530 while the tunnel
        # registers), timeouts, cut connections
        except (OSError, http.client.HTTPException):
            pass
        print(".", end="", flush=True)
        time.sleep(2)
    print()
    return False


def show(url):
    print(f"\n  {url}\n")
    code = qrcode.QRCode(border=2)
    code.add_data(url)
    code.make(fit=True)
    code.print_ascii(invert=True)  # light modules as blocks: reads well on a dark window
    print("\n手機掃 QR code 或打開上面的網址。範例帳號：demo / demo")
    print("⚠ 通道開著時，任何拿到網址的人都能連進來。")


def wait_for_stop(tunnel):
    def warn_if_tunnel_dies():
        tunnel.wait()
        # Ctrl+C reaches cloudflared too and may end it first; give the main
        # thread a moment to notice, so that case is not reported as a failure.
        time.sleep(1)
        if not stopping.is_set():
            print("\n⚠ 通道意外關閉了。按 Enter 關閉伺服器，再重新啟動。")

    stopping = threading.Event()
    threading.Thread(target=warn_if_tunnel_dies, daemon=True).start()
    print("按 Enter 或 Ctrl+C 關閉伺服器和通道。")
    try:
        input()
    except EOFError:
        # No keyboard (e.g. started in the background): run until the tunnel ends,
        # by Ctrl+C (which reaches cloudflared too) or `share.py stop`. Checking
        # isatty() is no help: on Windows it is True for the NUL device.
        tunnel.wait()
    finally:
        stopping.set()


def stop_tunnel(tunnel):
    if tunnel.poll() is None:
        tunnel.terminate()
        try:
            tunnel.wait(5)
        except subprocess.TimeoutExpired:
            tunnel.kill()
            tunnel.wait()


def start():
    cloudflared = find_cloudflared()
    if cloudflared is None:
        print(f"找不到 cloudflared。請先安裝：{INSTALL_HINT}")
        return 1
    if running_demo(read_pids(PID_FILE)):
        print("展示伺服器已經在執行，請先關閉它（或執行 stop_share.bat）")
        return 1
    if port_in_use(PORT):
        print(f"port {PORT} 已經被其他程式使用，無法啟動")
        return 1

    print("啟動展示伺服器（資料庫：instance/demo.db）…")
    app = create_app({"SQLALCHEMY_DATABASE_URI": DEMO_DATABASE})
    with app.app_context():
        if add_demo_data():
            print(ADDED_MESSAGE)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)  # keep the URL on screen
    server = make_server("127.0.0.1", PORT, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("開啟 Cloudflare 通道…")
    tunnel = subprocess.Popen(
        [cloudflared, "tunnel", "--url", f"http://127.0.0.1:{PORT}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    write_pids(PID_FILE, {"server": os.getpid(), "tunnel": tunnel.pid})
    output = TunnelOutput(tunnel, LOG_FILE)
    status = 0
    try:
        output.done.wait(URL_TIMEOUT)
        if output.url is None:
            print("無法開啟通道，cloudflared 的訊息：")
            print("\n".join(output.last_lines))
            print(f"完整紀錄在 {LOG_FILE}")
            status = 1
        else:
            print("確認網址可以連線（新網址通常要等 10 秒到 1 分鐘）", end="", flush=True)
            if not wait_until_reachable(output.url):
                print(f"⚠ {REACHABLE_TIMEOUT} 秒內還連不到這個網址，可以稍後再試，或關閉後重新啟動")
            show(output.url)
            wait_for_stop(tunnel)
    except KeyboardInterrupt:
        pass
    finally:
        # A second Ctrl+C must not cut the clean-up short.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        stop_tunnel(tunnel)
        server.shutdown()
        PID_FILE.unlink(missing_ok=True)
    print("已關閉伺服器和通道")
    return status


def main(argv):
    try:
        sys.stdout.reconfigure(errors="replace")  # never crash on a console that lacks a character
    except AttributeError:
        pass
    if argv == ["stop"]:
        return stop()
    if argv:
        print("用法：python share.py        啟動\n      python share.py stop   強制關閉")
        return 2
    return start()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
