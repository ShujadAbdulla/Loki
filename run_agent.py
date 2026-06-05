"""Loki launcher — starts FastAPI server + opens PyWebView native window."""

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def start_server():
    from backend.main import main
    main()


def main():
    from backend.config import load_config
    cfg = load_config()
    url = f"http://{cfg.server.host}:{cfg.server.port}/ui/"

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    import requests
    for _ in range(30):
        try:
            requests.get(f"http://{cfg.server.host}:{cfg.server.port}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)

    try:
        import webview
        window = webview.create_window(
            "Loki", url,
            width=1280, height=800,
            min_size=(900, 600),
            resizable=True,
        )
        webview.start(debug=os.getenv("LOKI_DEBUG", "").lower() in ("1", "true"))
    except ImportError:
        print(f"PyWebView not available. Opening browser at {url}")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
