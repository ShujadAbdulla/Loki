const API = window.location.origin;

const messagesEl = document.getElementById("messages");
const form = document.getElementById("chat-form");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send-btn");
const statusEl = document.getElementById("status");
const approvalsList = document.getElementById("approvals-list");
const tasksList = document.getElementById("tasks-list");
const webSearchToggle = document.getElementById("web-search-toggle");
const folderPath = document.getElementById("folder-path");
const addFolderBtn = document.getElementById("add-folder-btn");
const reindexBtn = document.getElementById("reindex-btn");

let history = [];

function linkify(text) {
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped.replace(
    /(https?:\/\/[^\s<]+)/g,
    '<a href="$1" target="_blank" rel="noopener">$1</a>'
  );
}

function appendMessage(role, content, meta = "") {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.innerHTML = meta ? `<div class="meta">${meta}</div>` : "";
  const body = document.createElement("div");
  body.innerHTML = linkify(content);
  div.appendChild(body);
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

async function refreshHealth() {
  try {
    const h = await api("/health");
    statusEl.textContent = `RAG: ${h.rag_stats?.chunk_count ?? 0} chunks · Groq: ${h.groq ? "on" : "off"} · Web: ${h.web_search ? "on" : "off"}`;
    statusEl.classList.add("ok");
  } catch {
    statusEl.textContent = "Offline — run .\\start.ps1 to wake Loki";
    statusEl.classList.remove("ok");
  }
}

async function refreshApprovals() {
  try {
    const items = await api("/approvals");
    approvalsList.innerHTML = "";
    if (!items.length) {
      approvalsList.innerHTML = "<li>None</li>";
      return;
    }
    for (const a of items) {
      const li = document.createElement("li");
      let preview = JSON.stringify(a.args);
      if (a.args?.content != null) {
        const c = String(a.args.content);
        const short = c.length > 80 ? c.slice(0, 80) + "…" : c;
        preview = `path: ${a.args.path}\ncontent: "${short}" (${a.args.content_len ?? c.length} bytes)`;
      } else if (a.args?.path) {
        const kind = a.args.kind ? ` (${a.args.kind})` : "";
        preview = `path: ${a.args.path}${kind}`;
      }
      li.innerHTML = `<strong>${a.tool}</strong> <span style="opacity:0.7">#${a.id}</span><br/><pre style="white-space:pre-wrap;margin:0.25rem 0">${preview}</pre>`;
      const actions = document.createElement("div");
      actions.className = "approval-actions";
      const ok = document.createElement("button");
      ok.className = "approve";
      ok.textContent = "Approve";
      ok.onclick = async () => {
        try {
          const res = await api(`/approve/${a.id}`, { method: "POST" });
          appendMessage("assistant", res.result || `Approved ${a.tool}`);
        } catch (err) {
          appendMessage("assistant", `Approve failed: ${err.message}`);
        }
        refreshApprovals();
      };
      const no = document.createElement("button");
      no.textContent = "Reject";
      no.onclick = async () => {
        await api(`/reject/${a.id}`, { method: "POST" });
        refreshApprovals();
      };
      actions.append(ok, no);
      li.appendChild(actions);
      approvalsList.appendChild(li);
    }
  } catch {
    approvalsList.innerHTML = "<li>—</li>";
  }
}

async function refreshTasks() {
  try {
    const items = await api("/tasks");
    tasksList.innerHTML = "";
    if (!items.length) {
      tasksList.innerHTML = "<li>None</li>";
      return;
    }
    for (const t of items.slice(0, 8)) {
      const li = document.createElement("li");
      li.textContent = `[${t.status}] ${t.goal.slice(0, 60)}`;
      tasksList.appendChild(li);
    }
  } catch {
    tasksList.innerHTML = "<li>—</li>";
  }
}

async function loadSettings() {
  try {
    const s = await api("/settings");
    webSearchToggle.checked = s.web_search_enabled;
    if (s.watched_paths?.length) {
      folderPath.placeholder = "Add another folder…";
      const hint = document.getElementById("watched-hint");
      if (hint) {
        hint.textContent = "Watching: " + s.watched_paths.join(", ");
      }
    }
  } catch {}
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  appendMessage("user", text);
  history.push({ role: "user", content: text });
  sendBtn.disabled = true;
  try {
    const res = await api("/chat", {
      method: "POST",
      body: JSON.stringify({ message: text, history }),
    });
    appendMessage("assistant", res.reply, `route: ${res.route}`);
    history.push({ role: "assistant", content: res.reply });
    refreshApprovals();
  } catch (err) {
    appendMessage("assistant", `Error: ${err.message}`);
  } finally {
    sendBtn.disabled = false;
    refreshTasks();
  }
});

webSearchToggle.addEventListener("change", async () => {
  await api("/settings", {
    method: "PUT",
    body: JSON.stringify({ web_search_enabled: webSearchToggle.checked }),
  });
});

addFolderBtn.addEventListener("click", async () => {
  const p = folderPath.value.trim();
  if (!p) {
    appendMessage("assistant", "Enter a folder path first (e.g. C:\\Users\\NXTWAVE\\Desktop\\testbyloki)");
    return;
  }
  try {
    const res = await api("/watched-paths", {
      method: "POST",
      body: JSON.stringify({ paths: [p] }),
    });
    folderPath.value = "";
    refreshHealth();
    if (res.added?.length) {
      let msg = `Added watched folder:\n${res.added.join("\n")}`;
      if (res.indexed_files != null) {
        msg += `\nIndexed ${res.indexed_files} file(s).`;
      }
      if (res.errors?.length) {
        msg += `\n\nNote:\n${res.errors.join("\n")}`;
      }
      appendMessage("assistant", msg);
    } else {
      appendMessage("assistant", res.errors?.join("\n") || "No folder was added.");
    }
  } catch (err) {
    appendMessage("assistant", `Could not add folder: ${err.message}`);
  }
});

reindexBtn.addEventListener("click", async () => {
  const r = await api("/index", { method: "POST" });
  let msg = `Indexed ${r.indexed_files} text documents (${r.stats.chunk_count} chunks).`;
  if (r.skipped_non_text) msg += ` Skipped ${r.skipped_non_text} video/audio/image files.`;
  if (r.note) msg += `\n${r.note}`;
  appendMessage("assistant", msg);
  refreshHealth();
});

refreshHealth();
refreshApprovals();
refreshTasks();
loadSettings();
setInterval(refreshHealth, 15000);
setInterval(refreshApprovals, 5000);
