window.LokiSettings = {
  init(api) {
    this.api = api;
    const container = document.getElementById("page-settings");
    container.innerHTML = `
      <div class="settings-section">
        <h3>AI Mode</h3>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:12px">
          Online uses Groq (fast). Offline uses local Ollama (slow on CPU). Auto prefers Groq and falls back only if a request fails.
        </p>
        <div id="llm-mode-status" style="font-size:13px;margin-bottom:12px"></div>
        <label style="display:block;margin-bottom:8px">
          <input type="radio" name="llm-mode" value="auto" /> Auto — Groq online, local fallback
        </label>
        <label style="display:block;margin-bottom:8px">
          <input type="radio" name="llm-mode" value="online" /> Online — Groq only (fastest)
        </label>
        <label style="display:block;margin-bottom:8px">
          <input type="radio" name="llm-mode" value="offline" /> Offline — Local Ollama only
        </label>
      </div>
      <div class="settings-section">
        <h3>Web Search</h3>
        <label><input type="checkbox" id="web-search-toggle" /> Enable Tavily web search</label>
      </div>
      <div class="settings-section">
        <h3>Watched Folders</h3>
        <p id="watched-hint" style="font-size:13px;color:var(--text-muted);margin-bottom:8px"></p>
        <input type="text" id="folder-path" placeholder="C:\\Users\\You\\Documents" />
        <button id="add-folder-btn">Add folder</button>
        <button id="reindex-btn">Re-index documents</button>
      </div>
      <div class="settings-section">
        <h3>WhatsApp (read-only)</h3>
        <button id="wa-connect-btn">Connect WhatsApp Web</button>
        <p style="font-size:12px;color:var(--text-muted);margin-top:8px">Opens Chrome for QR scan. Session persists.</p>
      </div>
      <div class="settings-section">
        <h3>Pending Approvals</h3>
        <ul id="approvals-list" style="list-style:none;font-size:13px"></ul>
      </div>`;

    document.querySelectorAll('input[name="llm-mode"]').forEach((radio) => {
      radio.addEventListener("change", async (e) => {
        if (!e.target.checked) return;
        await api("/settings", { method: "PUT", body: JSON.stringify({ llm_mode: e.target.value }) });
        if (window.LokiApp) window.LokiApp.refreshHealth();
        this.load();
      });
    });

    document.getElementById("web-search-toggle").addEventListener("change", async (e) => {
      await api("/settings", { method: "PUT", body: JSON.stringify({ web_search_enabled: e.target.checked }) });
    });

    document.getElementById("add-folder-btn").addEventListener("click", async () => {
      const p = document.getElementById("folder-path").value.trim();
      if (!p) return alert("Enter a folder path");
      try {
        const res = await api("/watched-paths", { method: "POST", body: JSON.stringify({ paths: [p] }) });
        document.getElementById("folder-path").value = "";
        if (res.added?.length) {
          alert(`Added: ${res.added.join(", ")}\nIndexed ${res.indexed_files} files.`);
          this.load();
          if (window.LokiApp) window.LokiApp.refreshHealth();
        } else {
          alert(res.errors?.join("\n") || "No folder added");
        }
      } catch (e) { alert(e.message); }
    });

    document.getElementById("reindex-btn").addEventListener("click", async () => {
      const r = await api("/index", { method: "POST" });
      alert(`Indexed ${r.indexed_files} files (${r.stats.chunk_count} chunks)`);
      if (window.LokiApp) window.LokiApp.refreshHealth();
    });

    document.getElementById("wa-connect-btn").addEventListener("click", async () => {
      const r = await api("/whatsapp/connect", { method: "POST" });
      alert(r.message);
    });

    this.load();
    if (window.LokiApp) {
      setInterval(() => window.LokiApp.refreshApprovals(), 5000);
    }
  },

  async load() {
    try {
      const s = await this.api("/settings");
      const mode = s.llm_mode || "auto";
      const radio = document.querySelector(`input[name="llm-mode"][value="${mode}"]`);
      if (radio) radio.checked = true;
      const statusEl = document.getElementById("llm-mode-status");
      if (statusEl) {
        const groq = s.groq_configured ? "Groq API key configured" : "Groq API key missing — add GROQ_API_KEY to .env";
        statusEl.innerHTML = `<strong>Active:</strong> ${s.mode || "unknown"} · ${groq}`;
      }
      document.getElementById("web-search-toggle").checked = s.web_search_enabled;
      if (s.watched_paths?.length) {
        document.getElementById("watched-hint").textContent = "Watching: " + s.watched_paths.join(", ");
      }
    } catch {}
  },
};
