window.LokiFiles = {
  init(api) {
    this.api = api;
    const container = document.getElementById("page-files");
    container.innerHTML = `
      <div class="settings-section">
        <h3>Watched Folders</h3>
        <ul id="files-folders" style="list-style:none;font-size:14px"></ul>
      </div>
      <div class="settings-section">
        <h3>Quick Actions</h3>
        <button id="files-reindex">Re-index all documents</button>
        <p style="font-size:12px;color:var(--text-muted);margin-top:8px">
          Text files (PDF, DOCX, TXT) are indexed automatically. Use Chat to process media files.
        </p>
      </div>`;
    document.getElementById("files-reindex").addEventListener("click", async () => {
      const r = await api("/index", { method: "POST" });
      alert(`Indexed ${r.indexed_files} files`);
      if (window.LokiApp) window.LokiApp.refreshHealth();
    });
    this.refresh();
  },

  async refresh() {
    const list = document.getElementById("files-folders");
    if (!list) return;
    try {
      const s = await this.api("/settings");
      if (!s.watched_paths?.length) {
        list.innerHTML = "<li>No folders watched. Add one in Settings.</li>";
        return;
      }
      list.innerHTML = s.watched_paths.map((p) => `<li style="padding:6px 0;border-bottom:1px solid var(--border)">${p}</li>`).join("");
    } catch {
      list.innerHTML = "<li>Could not load folders</li>";
    }
  },
};
