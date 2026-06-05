"""Build Loki into a standalone Windows executable."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

subprocess.run([
    sys.executable, "-m", "PyInstaller",
    "--name=Loki",
    "--onedir",
    "--windowed",
    f"--icon={ROOT / 'desktop' / 'ui' / 'assets' / 'loki-tray.ico'}" if (ROOT / "desktop" / "ui" / "assets" / "loki-tray.ico").exists() else "--name=Loki",
    f"--add-data={ROOT / 'desktop'}{';' if sys.platform == 'win32' else ':'}desktop",
    f"--add-data={ROOT / 'config'}{';' if sys.platform == 'win32' else ':'}config",
    "--hidden-import=chromadb",
    "--hidden-import=langchain_groq",
    "--hidden-import=langchain_ollama",
    "--hidden-import=faster_whisper",
    "--hidden-import=uvicorn.logging",
    "--hidden-import=uvicorn.loops",
    "--hidden-import=uvicorn.loops.auto",
    "--hidden-import=uvicorn.protocols",
    "--hidden-import=uvicorn.protocols.http",
    "--hidden-import=uvicorn.protocols.http.auto",
    "--hidden-import=uvicorn.protocols.websockets",
    "--hidden-import=uvicorn.protocols.websockets.auto",
    "--hidden-import=uvicorn.lifespan",
    "--hidden-import=uvicorn.lifespan.on",
    str(ROOT / "run_agent.py"),
], check=True, cwd=str(ROOT))

print("Build complete. Find Loki in dist/Loki/")
