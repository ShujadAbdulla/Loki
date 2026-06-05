window.LokiChat = {
  history: [],

  init(api) {
    const container = document.getElementById("page-chat");
    container.innerHTML = `
      <div class="chat-container">
        <div class="messages" id="messages"></div>
        <form class="chat-input-row" id="chat-form">
          <button type="button" class="attach-btn" id="attach-btn" title="Attach file path">+</button>
          <input type="text" id="input" placeholder="Ask Loki anything..." autocomplete="off" />
          <button type="submit" id="send-btn">Send</button>
        </form>
      </div>`;

    const form = document.getElementById("chat-form");
    const input = document.getElementById("input");
    const sendBtn = document.getElementById("send-btn");
    const messagesEl = document.getElementById("messages");

    document.getElementById("attach-btn").addEventListener("click", () => {
      const path = prompt("Enter file path from a watched folder:");
      if (path) input.value = (input.value ? input.value + " " : "") + path;
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      input.value = "";
      this.appendMessage("user", text);
      this.history.push({ role: "user", content: text });
      sendBtn.disabled = true;
      try {
        const res = await api("/chat", { method: "POST", body: JSON.stringify({ message: text, history: this.history }) });
        const meta = `route: ${res.route} · ${res.mode || "online"}`;
        this.appendMessage("assistant", res.reply, meta);
        this.history.push({ role: "assistant", content: res.reply });
        if (window.LokiApp) window.LokiApp.refreshApprovals();
      } catch (err) {
        this.appendMessage("assistant", `Error: ${err.message}`);
      } finally {
        sendBtn.disabled = false;
      }
    });

    api("/briefing").then((b) => {
      if (b.text) this.appendMessage("assistant", b.text, "startup briefing");
    }).catch(() => {});
  },

  appendMessage(role, content, meta = "") {
    const messagesEl = document.getElementById("messages");
    if (!messagesEl) return;
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    if (meta) {
      const m = document.createElement("div");
      m.className = "meta";
      m.textContent = meta;
      div.appendChild(m);
    }
    const body = document.createElement("div");
    body.innerHTML = this.linkify(content);
    div.appendChild(body);
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  },

  linkify(text) {
    const escaped = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return escaped.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  },
};
