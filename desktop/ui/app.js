const API = window.location.origin;

window.LokiApp = {
  async api(path, options = {}) {
    const res = await fetch(`${API}${path}`, {
      headers: { "Content-Type": "application/json", ...options.headers },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    return res.json();
  },

  async refreshHealth() {
    try {
      const h = await this.api("/health");
      LokiSidebar.updateConnections(h);
      LokiSidebar.updateMode(h);
    } catch {
      LokiSidebar.updateMode({ mode: "offline", llm_preference: "auto" });
    }
  },

  async refreshApprovals() {
    const list = document.getElementById("approvals-list");
    if (!list) return;
    try {
      const items = await this.api("/approvals");
      if (!items.length) { list.innerHTML = "<li>None</li>"; return; }
      list.innerHTML = items.map((a) => {
        const preview = a.args?.path || JSON.stringify(a.args).slice(0, 60);
        return `<li style="margin-bottom:8px;padding:8px;background:var(--bg);border-radius:4px">
          <strong>${a.tool}</strong> #${a.id}<br/><small>${preview}</small><br/>
          <button onclick="LokiApp.approve('${a.id}')" style="margin-top:4px;padding:4px 8px;background:var(--success);color:white;border:none;border-radius:4px;cursor:pointer">Approve</button>
          <button onclick="LokiApp.reject('${a.id}')" style="margin-top:4px;padding:4px 8px;border:none;border-radius:4px;cursor:pointer">Reject</button>
        </li>`;
      }).join("");
    } catch { list.innerHTML = "<li>—</li>"; }
  },

  async approve(id) {
    try {
      const res = await this.api(`/approve/${id}`, { method: "POST" });
      if (LokiChat) LokiChat.appendMessage("assistant", res.result || "Approved");
      this.refreshApprovals();
    } catch (e) { alert(e.message); }
  },

  async reject(id) {
    await this.api(`/reject/${id}`, { method: "POST" });
    this.refreshApprovals();
  },

  onNavigate(page) {
    if (page === "dashboard" && LokiDashboard) LokiDashboard.refresh();
    if (page === "downloads" && LokiDownloads) LokiDownloads.refresh();
    if (page === "emails" && LokiEmails) LokiEmails.refresh();
    if (page === "settings" && LokiSettings) LokiSettings.load();
    if (page === "files" && LokiFiles) LokiFiles.refresh();
  },

  init() {
    const api = this.api.bind(this);
    LokiSidebar.init((page) => this.onNavigate(page));
    LokiChat.init(api);
    LokiLogPanel.init(api);
    LokiDownloads.init(api);
    LokiEmails.init(api);
    LokiSettings.init(api);
    LokiDashboard.init(api);
    if (window.LokiFiles) LokiFiles.init(api);
    this.refreshHealth();
    this.refreshApprovals();
    setInterval(() => this.refreshHealth(), 30000);

    document.getElementById("global-search").addEventListener("keydown", async (e) => {
      if (e.key === "Enter") {
        const q = e.target.value.trim();
        if (!q) return;
        LokiSidebar.init(() => {});
        document.querySelector('[data-page="chat"]').click();
        if (LokiChat) {
          const input = document.getElementById("input");
          if (input) { input.value = `Search: ${q}`; document.getElementById("chat-form").dispatchEvent(new Event("submit")); }
        }
      }
    });

    const params = new URLSearchParams(window.location.search);
    if (params.get("gmail") === "connected") {
      alert("Gmail connected successfully!");
      this.refreshHealth();
    }
  },
};

document.addEventListener("DOMContentLoaded", () => LokiApp.init());
