// Core runtime: helpers, API client, toasts, theme, router. Everything hangs off window.IPC.
(() => {
  const IPC = (window.IPC = window.IPC || {});

  IPC.$ = (sel, root = document) => root.querySelector(sel);
  IPC.$$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  IPC.esc = (s) => MD.escapeHtml(String(s ?? ""));
  IPC.icon = (name, cls = "") => `<svg class="icon ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

  IPC.fmtDuration = (sec) => {
    sec = Math.max(0, Math.round(sec));
    return sec < 60 ? `${sec}s` : `${Math.floor(sec / 60)}m ${String(sec % 60).padStart(2, "0")}s`;
  };
  IPC.fmtDate = (ts) =>
    new Date(ts * 1000).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  IPC.timeAgo = (ts) => {
    const sec = Date.now() / 1000 - ts;
    if (sec < 60) return "just now";
    if (sec < 3600) return `${Math.floor(sec / 60)} min ago`;
    if (sec < 86400) return `${Math.floor(sec / 3600)} h ago`;
    return IPC.fmtDate(ts);
  };
  IPC.shortModel = (model) => (model || "").replace(/^[a-z_]+\//, "");

  // Form values shared between views, in memory only (a resume is never written to storage).
  IPC.draft = { company: "", role: "", experience: "Fresher / intern", job_description: "", resume: { text: "", filename: "" } };
  IPC.state = { config: null, stats: null, activeRun: null };

  // ---------- API ----------
  async function request(method, url, body, raw = false) {
    const init = { method };
    if (body !== undefined) {
      init.body = raw ? body : JSON.stringify(body);
      if (!raw) init.headers = { "Content-Type": "application/json" };
    }
    let res;
    try {
      res = await fetch(url, init);
    } catch {
      throw new Error("Could not reach the server. Is it still running?");
    }
    if (res.status === 204) return null;
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const detail = data && data.detail;
      throw new Error(Array.isArray(detail) ? detail.map((d) => d.msg).join("; ") : detail || `Request failed (${res.status})`);
    }
    return data;
  }
  IPC.api = {
    get: (url) => request("GET", url),
    post: (url, body) => request("POST", url, body),
    postRaw: (url, body) => request("POST", url, body, true),
    del: (url) => request("DELETE", url),
  };

  // ---------- toasts ----------
  IPC.toast = (message, kind = "info") => {
    const host = IPC.$("#toasts");
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.innerHTML = `${IPC.icon(kind === "error" ? "alert" : kind === "success" ? "check" : "info")}<span>${IPC.esc(message)}</span>`;
    host.appendChild(el);
    setTimeout(() => el.classList.add("out"), 3800);
    setTimeout(() => el.remove(), 4300);
  };

  // ---------- theme ----------
  const dark = () =>
    document.documentElement.dataset.theme === "dark" ||
    (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  function paintThemeButton() {
    IPC.$("#themeBtn").innerHTML = IPC.icon(dark() ? "sun" : "moon");
  }
  IPC.initTheme = () => {
    paintThemeButton();
    IPC.$("#themeBtn").addEventListener("click", () => {
      const next = dark() ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try {
        localStorage.setItem("ipc-theme", next);
      } catch {}
      paintThemeButton();
    });
  };

  // ---------- live run indicator ----------
  IPC.setActiveRun = (run) => {
    IPC.state.activeRun = run;
    const pill = IPC.$("#livePill");
    pill.hidden = !run;
    if (run) {
      IPC.$("#liveText").textContent = run.label;
      pill.href = `#/${run.kind}/${run.id}`;
    }
  };

  // ---------- history counter in the sidebar ----------
  IPC.setHistoryCount = (n) => {
    const el = IPC.$("#navCount");
    el.hidden = !n;
    el.textContent = n;
  };
  IPC.refreshStats = async () => {
    IPC.state.stats = await IPC.api.get("/api/stats");
    return IPC.state.stats;
  };
  IPC.refreshCounts = async () => {
    try {
      const runs = await IPC.api.get("/api/runs?limit=500");
      IPC.setHistoryCount(runs.length);
      const running = runs.find((r) => r.status === "running");
      if (running && !IPC.state.activeRun) {
        IPC.setActiveRun({ id: running.id, kind: running.kind, label: running.kind === "ats" ? "Resume review running" : "Interview prep running" });
      } else if (!running && IPC.state.activeRun) {
        IPC.setActiveRun(null);
      }
    } catch {}
  };

  // ---------- router ----------
  IPC.views = {};
  IPC.register = (name, view) => (IPC.views[name] = view);
  let current = null;
  let token = 0;

  IPC.navigate = (hash) => {
    if (location.hash === hash) show();
    else location.hash = hash;
  };

  async function show() {
    const [name = "dashboard", param] = location.hash.replace(/^#\/?/, "").split("/");
    const view = IPC.views[name] || IPC.views.dashboard;
    const mine = ++token;
    if (current && current.unmount) current.unmount();
    current = null;
    const root = IPC.$("#view");
    root.innerHTML = "";
    window.scrollTo(0, 0);
    IPC.$("#pageTitle").textContent = view.title;
    IPC.$("#pageSub").textContent = view.subtitle || "";
    document.title = `${view.title} · Interview Prep Crew`;
    const route = IPC.views[name] ? name : "dashboard";
    IPC.$$(".nav a").forEach((a) => {
      const on = a.dataset.route === route;
      a.classList.toggle("active", on);
      if (on) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    current = view;
    try {
      await view.mount(root, param);
    } catch (err) {
      if (mine === token) root.innerHTML = `<div class="page"><div class="card"><div class="empty">${IPC.icon("alert")}<h4>Something went wrong</h4><p>${IPC.esc(err.message)}</p></div></div></div>`;
    }
  }

  IPC.startRouter = () => {
    window.addEventListener("hashchange", show);
    return show();
  };
})();
