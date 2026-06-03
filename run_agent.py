#!/usr/bin/env python3
"""Launch Loki backend and open the chat UI in your browser."""

import os
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

if __name__ == "__main__":
    from backend.config import load_config

    cfg = load_config()
    url = f"http://{cfg.server.host}:{cfg.server.port}/ui/"
    print(f"Starting Loki at {url}")
    webbrowser.open(url)
    from backend.main import main

    main()
