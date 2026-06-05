"""System tray entry for Loki."""

import sys
import webbrowser
from pathlib import Path


def create_tray():
    try:
        import pystray
        from PIL import Image, ImageDraw

        icon_path = Path(__file__).parent / "desktop" / "ui" / "assets" / "loki-tray.ico"
        if icon_path.exists():
            img = Image.open(icon_path)
        else:
            img = Image.new("RGB", (64, 64), "#0D1B2A")
            draw = ImageDraw.Draw(img)
            draw.text((20, 20), "L", fill="#2E86DE")

        def on_open(icon, item):
            webbrowser.open("http://127.0.0.1:8787/ui/")

        def on_exit(icon, item):
            icon.stop()
            sys.exit(0)

        menu = pystray.Menu(
            pystray.MenuItem("Open Loki", on_open, default=True),
            pystray.MenuItem("Exit", on_exit),
        )
        icon = pystray.Icon("Loki", img, "Loki", menu)
        icon.run()
    except ImportError:
        print("pystray/Pillow not installed. Run: pip install pystray Pillow")


if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: __import__("run_agent").main(), daemon=True).start()
    create_tray()
