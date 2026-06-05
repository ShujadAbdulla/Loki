# Loki v2

A Windows desktop personal AI assistant that runs locally on your machine. Indexes documents (RAG), processes media, generates files, integrates with Gmail/Outlook, and accepts remote commands via email or Telegram.

## Features (v2)

- **Professional UI** — dark sidebar, dashboard, chat, emails, downloads, settings
- **Hybrid media pipeline** — MarkItDown → vision fallback (Moondream) + Whisper for audio
- **Online/offline LLM** — Groq primary, Phi-3 Mini via Ollama fallback (automatic)
- **File generation** — DOCX, PDF, PPTX, XLSX
- **Gmail & Outlook OAuth2** — read/send email (tokens in OS keychain)
- **WhatsApp Web** — read-only Phase 1 via Selenium
- **Activity Log** — live SSE stream, filters, undo (30s window)
- **Download Center** — all generated files in one place
- **Morning briefing** — catch-up summary on startup
- **PyWebView native window** + system tray support
- **Windows installer** — PyInstaller + NSIS scripts included

## Quick start

### 1. Install dependencies

```powershell
cd C:\Users\munna\OneDrive\Desktop\agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure API keys

Copy `.env.example` to `.env` and set:

```
GROQ_API_KEY=your_key
TAVILY_API_KEY=your_key          # optional
GOOGLE_CLIENT_ID=...             # optional, for Gmail
GOOGLE_CLIENT_SECRET=...
MICROSOFT_CLIENT_ID=...          # optional, for Outlook
```

### 3. Install Ollama (for offline fallback)

```powershell
# Download from https://ollama.com
ollama pull phi3:mini
ollama pull moondream
```

### 4. Run

```powershell
python run_agent.py
```

Opens native window (PyWebView) or browser fallback at `http://127.0.0.1:8787/ui/`

**System tray:**
```powershell
python run_tray.py
```

## Project layout

```
agent/
├── backend/
│   ├── agent/          # Orchestrator, router, model_router
│   ├── media/          # Hybrid media pipeline
│   ├── generators/     # DOCX/PDF/PPTX/XLSX
│   ├── communication/  # Gmail, Outlook, WhatsApp
│   ├── automations/    # YAML workflows + startup briefing
│   ├── rag/            # ChromaDB indexing
│   ├── security/       # Audit, approvals, undo
│   └── tools/          # LangChain tools
├── desktop/ui/         # Professional web UI + components
├── config/             # default.yaml
├── run_agent.py        # PyWebView launcher
├── run_tray.py         # System tray
├── build.py            # PyInstaller build
└── installer.nsi       # NSIS installer script
```

## Security

- API listens on **127.0.0.1 only**
- File access limited to **watched folders**
- Write/delete/move require **approval** in UI
- OAuth tokens stored in **OS keychain** (never plaintext)
- Actions logged to `%LOCALAPPDATA%\PersonalAgent\audit.jsonl`

## Build installer

```powershell
python build.py
# Then compile installer.nsi with NSIS
```
