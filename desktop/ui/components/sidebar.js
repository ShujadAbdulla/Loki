window.LokiSidebar = {
  init(onNavigate) {
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.addEventListener("click", (e) => {
        e.preventDefault();
        const page = item.dataset.page;
        document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
        item.classList.add("active");
        document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
        const el = document.getElementById(`page-${page}`);
        if (el) el.classList.add("active");
        const titles = { chat: "Chat", dashboard: "Dashboard", files: "Files", emails: "Emails", downloads: "Generated Docs", settings: "Settings" };
        document.getElementById("page-title").textContent = titles[page] || page;
        if (onNavigate) onNavigate(page);
      });
    });
  },

  updateConnections(health) {
    const set = (id, connected) => {
      const el = document.getElementById(id);
      if (el) el.classList.toggle("connected", !!connected);
    };
    set("gmail-badge", health.gmail);
    set("outlook-badge", health.outlook);
    set("wa-badge", health.whatsapp);
  },

    updateMode(health) {
    const dot = document.getElementById("loki-status");
    const label = document.getElementById("mode-label");
    const banner = document.getElementById("offline-banner");
    const main = document.getElementById("main-content");
    const mode = health.mode || "online";
    const pref = health.llm_preference || "auto";
    const isOffline = mode === "offline";
    dot.classList.toggle("offline", isOffline);
    if (isOffline) {
      label.textContent = pref === "offline" ? "Offline (local)" : "Offline (fallback)";
      banner.style.display = "block";
      banner.textContent = pref === "offline"
        ? "Offline Mode — using local AI (Ollama). Switch to Online in Settings for faster responses."
        : "Groq unavailable — using local AI fallback (responses may be slower). Check Settings or your API key.";
      main.classList.add("has-banner");
    } else if (mode === "unavailable") {
      label.textContent = "No API key";
      banner.style.display = "block";
      banner.textContent = "Add GROQ_API_KEY to .env for online mode, or set AI Mode to Offline in Settings.";
      main.classList.add("has-banner");
      dot.classList.add("offline");
    } else {
      label.textContent = pref === "auto" ? "Online (Groq)" : "Online";
      banner.style.display = "none";
      main.classList.remove("has-banner");
    }
  },
};
