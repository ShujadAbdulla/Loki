# Loki

A Windows desktop personal assistant named **Loki** (mischievous, clever — your local agent) that runs on your machine. It indexes your documents (RAG), searches the web (Tavily), performs file operations in approved folders, and accepts remote commands via email or Telegram.

## Features

- **Chat UI** — browser-based panel at `http://127.0.0.1:8787/ui/`
- **Local RAG** — watches folders, indexes PDF/DOCX/TXT/MD, answers with `[local: path]` citations
- **Web search** — Tavily integration with `[web: url]` citations
- **File tools** — read, write, move, delete (with approval for destructive ops)
- **Remote control** — `TASK:`, `APPROVE:`, `REJECT:` via email or Telegram
- **Automations** — YAML workflows in `config/default.yaml`

## Quick start

### 1. Install dependencies

```powershell
cd C:\Users\NXTWAVE\Desktop\agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure API keys

Copy `.env.example` to `.env` and set:

```env
GROQ_API_KEY=your_key
TAVILY_API_KEY=your_key   # optional, for web search
```

### 3. Run

```powershell
python run_agent.py
```

Opens the chat UI in your browser. The API only binds to `127.0.0.1`.

### 4. Add a watched folder

In the UI sidebar, enter a path like `C:\Users\You\Documents` and click **Add folder**. Click **Re-index documents** to index existing files.

## Remote commands

### Telegram

1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Set in `.env`:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_CHAT_IDS=123456789
```

3. Enable in user config (`%LOCALAPPDATA%\PersonalAgent\config.yaml`):

```yaml
telegram:
  enabled: true
```

4. Message your bot:

```
TASK: Summarize my latest report and save summary to Desktop
APPROVE: abc12345
```

### Email

Set `EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `IMAP_HOST`, `SMTP_HOST` in `.env` and add allowed senders in settings.

## Project layout

```
agent/
├── backend/          # FastAPI + LangGraph agent
├── desktop/ui/       # Chat web UI
├── config/           # Default YAML config
├── run_agent.py      # Launcher
└── app.py            # Legacy career copilot (optional)
```

## Security

- API listens on **localhost only**
- File access limited to **watched folders** you approve
- Write/delete/move require **approval** in the UI
- Actions logged to `%LOCALAPPDATA%\PersonalAgent\audit.jsonl`

## Legacy career copilot

The original Gradio app is still at `app.py`:

```powershell
python app.py
```

## Tauri native app (future)

The `desktop/` folder currently ships a web UI served by FastAPI. A Tauri wrapper can be added later for a system-tray installable `.msi`.
