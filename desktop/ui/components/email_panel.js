window.LokiEmails = {
  init(api) {
    this.api = api;
    const container = document.getElementById("page-emails");
    container.innerHTML = `
      <div style="margin-bottom:16px">
        <button id="connect-gmail" class="settings-section" style="display:inline;padding:8px 16px;cursor:pointer">Connect Gmail</button>
        <button id="connect-outlook" style="display:inline;padding:8px 16px;cursor:pointer;margin-left:8px">Connect Outlook</button>
        <button id="refresh-emails" style="display:inline;padding:8px 16px;cursor:pointer;margin-left:8px">Refresh</button>
      </div>
      <ul class="email-list" id="email-list"></ul>`;

    document.getElementById("connect-gmail").addEventListener("click", async () => {
      try {
        const r = await api("/gmail/auth");
        window.open(r.auth_url, "_blank");
      } catch (e) { alert(e.message); }
    });

    document.getElementById("connect-outlook").addEventListener("click", async () => {
      try {
        const r = await api("/outlook/auth");
        alert(`${r.message}\n\nCode: ${r.user_code}\n\nGo to: ${r.verification_uri}`);
        setTimeout(async () => {
          try {
            await api("/outlook/complete", { method: "POST" });
            alert("Outlook connected!");
            if (window.LokiApp) window.LokiApp.refreshHealth();
          } catch (e) { alert("Complete auth at microsoft.com/devicelogin first, then try again."); }
        }, 30000);
      } catch (e) { alert(e.message); }
    });

    document.getElementById("refresh-emails").addEventListener("click", () => this.refresh());
    this.refresh();
  },

  async refresh() {
    const list = document.getElementById("email-list");
    if (!list) return;
    let emails = [];
    try {
      const h = await this.api("/health");
      if (h.gmail) {
        const g = await this.api("/emails/gmail?n=15");
        emails = emails.concat(g.map((e) => ({ ...e, source: "Gmail" })));
      }
      if (h.outlook) {
        const o = await this.api("/emails/outlook?n=15");
        emails = emails.concat(o.map((e) => ({ ...e, source: "Outlook" })));
      }
    } catch {}
    if (!emails.length) {
      list.innerHTML = '<li class="empty-state">No emails. Connect Gmail or Outlook above.</li>';
      return;
    }
    list.innerHTML = emails.map((e) => `
      <li class="email-item">
        <div class="email-subject">${e.subject || "(no subject)"}</div>
        <div class="email-from">${e.source}: ${e.from}</div>
        <div class="email-snippet">${e.snippet || ""}</div>
      </li>`).join("");
  },
};
