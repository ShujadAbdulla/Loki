window.LokiDashboard = {
  init(api) {
    this.api = api;
    const container = document.getElementById("page-dashboard");
    container.innerHTML = `<div class="dashboard-grid" id="dashboard-grid"></div>`;
    this.refresh();
  },

  async refresh() {
    const grid = document.getElementById("dashboard-grid");
    if (!grid) return;
    try {
      const h = await this.api("/health");
      const downloads = await this.api("/downloads").catch(() => []);
      grid.innerHTML = `
        <div class="stat-card"><div class="stat-value">${h.rag_stats?.chunk_count ?? 0}</div><div class="stat-label">RAG Chunks</div></div>
        <div class="stat-card"><div class="stat-value">${h.watched_paths?.length ?? 0}</div><div class="stat-label">Watched Folders</div></div>
        <div class="stat-card"><div class="stat-value">${downloads.length}</div><div class="stat-label">Generated Files</div></div>
        <div class="stat-card"><div class="stat-value" style="text-transform:capitalize">${h.mode || "online"}</div><div class="stat-label">AI Mode</div></div>
        <div class="stat-card"><div class="stat-value">${h.gmail ? "Yes" : "No"}</div><div class="stat-label">Gmail Connected</div></div>
        <div class="stat-card"><div class="stat-value">${h.outlook ? "Yes" : "No"}</div><div class="stat-label">Outlook Connected</div></div>`;
    } catch {
      grid.innerHTML = '<div class="empty-state">Could not load dashboard</div>';
    }
  },
};
