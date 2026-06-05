window.LokiDownloads = {
  init(api) {
    this.api = api;
    const container = document.getElementById("page-downloads");
    container.innerHTML = `<div class="downloads-grid" id="downloads-grid"></div>`;
    this.refresh();
    setInterval(() => this.refresh(), 30000);
  },

  async refresh() {
    const grid = document.getElementById("downloads-grid");
    if (!grid) return;
    try {
      const files = await this.api("/downloads");
      if (!files.length) {
        grid.innerHTML = '<div class="empty-state">No generated files yet. Ask Loki to create a document.</div>';
        return;
      }
      const icons = { docx: "D", pdf: "P", pptx: "S", xlsx: "X" };
      grid.innerHTML = files.map((f) => {
        const size = f.size > 1048576 ? (f.size / 1048576).toFixed(1) + " MB" : Math.round(f.size / 1024) + " KB";
        const date = new Date(f.modified * 1000).toLocaleString();
        return `<div class="file-card">
          <div class="file-icon">${icons[f.type] || "F"}</div>
          <div class="file-name">${f.name}</div>
          <div class="file-meta">${size} · ${date}</div>
          <div class="file-actions">
            <button onclick="LokiDownloads.open('${f.path.replace(/\\/g, "\\\\")}')">Open</button>
          </div>
        </div>`;
      }).join("");
    } catch {
      grid.innerHTML = '<div class="empty-state">Could not load downloads</div>';
    }
  },

  open(path) {
    if (window.LokiChat) {
      LokiChat.appendMessage("user", `Open file: ${path}`);
    }
  },
};
