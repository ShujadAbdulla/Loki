window.LokiLogPanel = {
  entries: [],
  filter: "ALL",
  debugMode: false,

  init(api) {
    const panel = document.getElementById("log-panel");
    panel.innerHTML = `
      <div class="log-header">
        <strong>Activity Log</strong>
        <div>
          <label style="font-size:12px;margin-right:8px"><input type="checkbox" id="debug-toggle" /> Debug</label>
          <button id="log-close" style="border:none;background:none;cursor:pointer;font-size:18px">x</button>
        </div>
      </div>
      <div class="log-filters" id="log-filters"></div>
      <div class="log-timeline" id="log-timeline"></div>`;

    const cats = ["ALL", "FILE", "EMAIL", "AI_ACTION", "DOCUMENT", "ERROR"];
    const filtersEl = document.getElementById("log-filters");
    cats.forEach((cat) => {
      const tab = document.createElement("button");
      tab.className = `filter-tab${cat === "ALL" ? " active" : ""}`;
      tab.textContent = cat;
      tab.onclick = () => {
        this.filter = cat;
        filtersEl.querySelectorAll(".filter-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        this.render();
      };
      filtersEl.appendChild(tab);
    });

    document.getElementById("debug-toggle").addEventListener("change", (e) => {
      this.debugMode = e.target.checked;
      this.render();
    });

    document.getElementById("log-fab-btn").addEventListener("click", () => this.open());
    document.getElementById("log-close").addEventListener("click", () => this.close());
    document.getElementById("log-overlay").addEventListener("click", () => this.close());

    api("/audit?n=100").then((items) => {
      this.entries = items.reverse();
      this.render();
    }).catch(() => {});

    try {
      const es = new EventSource(`${window.location.origin}/audit/stream`);
      es.onmessage = (e) => {
        try {
          const entry = JSON.parse(e.data);
          this.entries.unshift(entry);
          if (this.entries.length > 200) this.entries.pop();
          this.render();
          const badge = document.getElementById("log-badge");
          if (badge && !document.getElementById("log-panel").classList.contains("open")) {
            badge.style.display = "inline";
            badge.textContent = String((parseInt(badge.textContent) || 0) + 1);
          }
        } catch {}
      };
    } catch {}
  },

  open() {
    document.getElementById("log-panel").classList.add("open");
    document.getElementById("log-overlay").style.display = "block";
    const badge = document.getElementById("log-badge");
    if (badge) { badge.style.display = "none"; badge.textContent = "0"; }
  },

  close() {
    document.getElementById("log-panel").classList.remove("open");
    document.getElementById("log-overlay").style.display = "none";
  },

  render() {
    const timeline = document.getElementById("log-timeline");
    if (!timeline) return;
    const filtered = this.filter === "ALL" ? this.entries : this.entries.filter((e) => e.category === this.filter);
    timeline.innerHTML = filtered.map((e) => {
      const ts = e.ts ? new Date(e.ts).toLocaleTimeString() : "";
      const undoBtn = e.category === "FILE" && e.id ? `<button onclick="LokiLogPanel.undo('${e.id}')" style="font-size:11px;margin-top:4px">Undo</button>` : "";
      const debug = this.debugMode ? `<pre style="font-size:11px;margin-top:4px;opacity:0.7">${JSON.stringify(e.detail, null, 2)}</pre>` : "";
      return `<div class="log-entry"><span class="log-cat">${e.category || ""}</span><span class="log-ts">${ts}</span><div>${e.action}</div>${debug}${undoBtn}</div>`;
    }).join("") || '<div class="empty-state">No activity yet</div>';
  },

  async undo(id) {
    try {
      await fetch(`${window.location.origin}/undo/${id}`, { method: "POST" });
      alert("Undone!");
    } catch (e) {
      alert("Undo failed: " + e.message);
    }
  },
};
