// RunViewer: streams one run's events and draws the agent cards and the activity feed.
// Views create one with their own containers and react to events through onEvent.
(() => {
  const IPC = window.IPC;
  const { $, esc, icon, fmtDuration } = IPC;

  const TOOL_ICON = { web_search: "search", news_search: "newspaper", read_webpage: "book" };
  const PILL = { waiting: "Queued", thinking: "Thinking", tool: "Tool", done: "Done", error: "Error" };
  const toolIcon = (tool) => TOOL_ICON[tool] || "zap";
  const toolArg = (args) => (args ? args.query || args.url || args.input || Object.values(args).join(", ") : "");
  const tokenCount = (u) => (u ? u.total_tokens || (u.prompt_tokens || u.input_tokens || 0) + (u.completion_tokens || u.output_tokens || 0) : 0);

  class RunViewer {
    /** o: { pipeline, timeline, filter, clock, onEvent(ev), onSelect(key) } */
    constructor(o) {
      this.o = o;
      this.agents = [];
      this.byKey = {};
      this._reset();
      this.timer = setInterval(() => this._tick(), 250);
      o.timeline.addEventListener("scroll", () => {
        // moving above the last auto-scroll position means the person scrolled up to read
        const t = o.timeline;
        if (t.scrollTop + 5 < this.autoTop) this.follow = false;
        else if (t.scrollHeight - t.scrollTop - t.clientHeight < 60) this.follow = true;
      });
    }

    destroy() {
      this.close();
      clearInterval(this.timer);
    }

    close() {
      if (this.es) this.es.close();
      this.es = null;
    }

    _reset() {
      this.close();
      Object.assign(this, {
        stats: {}, calls: new Map(), openTools: {}, cutOff: {}, lastSeq: 0, startedAt: null, finishedAt: null,
        evTime: 0, live: false, follow: true, autoTop: 0, runId: null, filterKey: "all",
      });
      this.o.timeline.innerHTML = "";
    }

    setAgents(agents) {
      this.agents = agents.map((a, i) => ({ ...a, index: i }));
      this.byKey = Object.fromEntries(this.agents.map((a) => [a.key, a]));
      this.stats = Object.fromEntries(this.agents.map((a) => [a.key, { status: "waiting", llm: 0, tool: 0, start: null, end: null }]));
      this._renderPipeline();
      this._renderFilter();
      this._renderClock();
    }

    open(run) {
      const agents = this.agents;
      this._reset();
      this.runId = run.id;
      this.live = run.status === "running";
      this.setAgents(agents);
      this.es = new EventSource(`/api/runs/${run.id}/events`);
      this.es.onmessage = (msg) => {
        const ev = JSON.parse(msg.data);
        if (ev.seq <= this.lastSeq) return;
        this.lastSeq = ev.seq;
        this._handle(ev);
      };
      // EventSource retries dropped connections itself; it only gives up (CLOSED) when the
      // server no longer knows the run, e.g. after a server restart.
      this.es.onerror = () => {
        if (!this.es || this.es.readyState !== EventSource.CLOSED || this.finishedAt) return;
        this.finishedAt = Date.now();
        this._finish();
        this.o.onEvent({ type: "connection_lost" });
      };
    }

    // ---------- rendering ----------
    _renderPipeline() {
      const p = this.o.pipeline;
      p.dataset.count = this.agents.length;
      p.innerHTML = this.agents
        .map((a, i) => {
          const chips = a.tools.length
            ? a.tools.map((t) => `<span class="chip mono">${icon(toolIcon(t))}${esc(t)}</span>`).join("")
            : `<span class="chip">${icon("cpu")}reasoning only</span>`;
          return `<div class="agent-card" data-agent="${a.key}" data-status="waiting" tabindex="0" role="button" title="${esc(a.summary)}" aria-label="Show activity of ${esc(a.role)}">
            <div class="ac-top"><span class="ac-no">${i + 1}</span><span class="pill">${PILL.waiting}</span></div>
            <div class="ac-icon" aria-hidden="true">${a.icon}</div>
            <h4>${esc(a.role)}</h4>
            <p class="ac-out">${esc(a.produces)}</p>
            <div class="chips">${chips}</div>
            <div class="now">–</div>
            <div class="ac-stats">
              <span title="LLM calls">${icon("cpu")}<b data-stat="llm">0</b></span>
              <span title="Tool calls">${icon("zap")}<b data-stat="tool">0</b></span>
              <span title="Time">${icon("clock")}<b data-stat="time">–</b></span>
            </div></div>`;
        })
        .join("");
      p.querySelectorAll(".agent-card").forEach((card) => {
        const pick = () => this.select(card.dataset.agent);
        card.addEventListener("click", pick);
        card.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            pick();
          }
        });
      });
    }

    _renderFilter() {
      const f = this.o.filter;
      if (!f) return;
      f.innerHTML =
        `<button type="button" data-filter="all" class="active">All</button>` +
        this.agents.map((a) => `<button type="button" data-filter="${a.key}">${a.icon} ${esc(a.role)}</button>`).join("");
      f.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => this._setFilter(b.dataset.filter)));
      this.filterKey = "all";
    }

    _setFilter(key) {
      this.filterKey = key;
      if (this.o.filter) this.o.filter.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.filter === key));
      this.o.pipeline.querySelectorAll(".agent-card").forEach((c) => c.classList.toggle("selected", c.dataset.agent === key));
      this.o.timeline.querySelectorAll(".entry").forEach((e) => e.classList.toggle("is-hidden", key !== "all" && e.dataset.agent !== key));
      this.follow = true;
      this._autoscroll();
    }

    select(key) {
      this._setFilter(this.filterKey === key ? "all" : key);
      if (this.o.onSelect) this.o.onSelect(key);
    }

    _renderClock() {
      if (!this.o.clock) return;
      if (!this.startedAt) this.o.clock.textContent = "";
      else this.o.clock.textContent = fmtDuration(((this.finishedAt || Date.now()) - this.startedAt) / 1000);
    }

    _renderTime(key) {
      const s = this.stats[key];
      const card = $(`.agent-card[data-agent="${key}"]`, this.o.pipeline);
      if (!s || !s.start || !card) return;
      $('[data-stat="time"]', card).textContent = fmtDuration(((s.end || this.finishedAt || Date.now()) - s.start) / 1000);
    }

    _setStatus(agent, status, now) {
      const s = this.stats[agent];
      const card = $(`.agent-card[data-agent="${agent}"]`, this.o.pipeline);
      if (!s || !card) return;
      if (s.status === "done" && status !== "done") return; // late events never undo "done"
      s.status = status;
      card.dataset.status = status;
      $(".pill", card).textContent = PILL[status];
      if (now) $(".now", card).textContent = now;
      $('[data-stat="llm"]', card).textContent = s.llm;
      $('[data-stat="tool"]', card).textContent = s.tool;
    }

    _tick() {
      if (!this.live || this.finishedAt || !this.startedAt) return;
      this._renderClock();
      Object.keys(this.stats).forEach((k) => this._renderTime(k));
      // models can take a while before the first token: show that the call is alive
      for (const call of this.calls.values()) {
        if (call.done || call.stream.textContent) continue;
        const waited = fmtDuration((Date.now() - call.start) / 1000);
        call.note.textContent = `waiting for the model · ${waited}`;
        if (this.stats[call.agent] && this.stats[call.agent].status === "thinking") {
          $(`.agent-card[data-agent="${call.agent}"] .now`, this.o.pipeline).textContent = `Thinking · call ${call.n} · ${waited}`;
        }
      }
    }

    _finish() {
      this.close();
      Object.keys(this.stats).forEach((k) => this._renderTime(k));
      this._renderClock();
    }

    _elapsed() {
      return this.startedAt ? `+${(((this.evTime || Date.now()) - this.startedAt) / 1000).toFixed(1)}s` : "";
    }

    _addEntry(agent, kind, iconName, titleHtml, bodyHtml = "") {
      const a = this.byKey[agent] || { role: agent, icon: "" };
      const entry = document.createElement("div");
      entry.className = `entry k-${kind}${this.filterKey !== "all" && this.filterKey !== agent ? " is-hidden" : ""}`;
      entry.dataset.agent = agent;
      entry.innerHTML = `<div class="e-icon" aria-hidden="true">${icon(iconName)}</div><div class="e-body">
        <div class="e-head"><span class="e-agent">${a.icon} ${esc(a.role)}</span><span class="e-title">${titleHtml}</span>
        <span class="e-time">${this._elapsed()}</span></div>${bodyHtml}</div>`;
      this.o.timeline.appendChild(entry);
      this._autoscroll();
      return entry;
    }

    _autoscroll() {
      if (!this.follow) return;
      this.o.timeline.scrollTop = this.o.timeline.scrollHeight;
      this.autoTop = this.o.timeline.scrollTop;
    }

    _call(callId, agent) {
      let call = this.calls.get(callId);
      if (call) return call;
      const n = this.stats[agent] ? this.stats[agent].llm || 1 : 1;
      const entry = this._addEntry(agent, "llm", "sparkles", `LLM call ${n}`,
        `<details class="more" hidden><summary>Model reasoning</summary><pre class="think"></pre></details>
         <div class="stream live"></div><div class="e-note"></div>`);
      call = {
        entry, agent, n, start: this.evTime || Date.now(), done: false,
        stream: $(".stream", entry), think: $(".think", entry), thinkBox: $("details", entry), note: $(".e-note", entry),
      };
      this.calls.set(callId, call);
      return call;
    }

    // ---------- events ----------
    _handle(ev) {
      this.evTime = ev.ts ? ev.ts * 1000 : Date.now(); // server time, so a replayed log keeps its real timings
      const fn = this[`on_${ev.type}`];
      if (fn) fn.call(this, ev);
      this.o.onEvent(ev);
    }

    on_run_started(ev) {
      this.startedAt = this.evTime;
      if (ev.agents && ev.agents.length) this.setAgents(ev.agents);
    }

    on_agent_started(ev) {
      const s = this.stats[ev.agent];
      s.start = this.evTime;
      this._setStatus(ev.agent, "thinking", "Starting…");
      this._addEntry(ev.agent, "start", "play", "Started",
        `<details class="more"><summary>Task prompt</summary><pre>${esc(ev.task_prompt)}</pre></details>`);
    }

    on_llm_started(ev) {
      const s = this.stats[ev.agent];
      s.llm += 1;
      this._setStatus(ev.agent, "thinking", `Thinking · call ${s.llm}`);
      this._call(ev.call_id, ev.agent);
    }

    on_llm_chunk(ev) {
      const call = this._call(ev.call_id, ev.agent);
      call.stream.textContent += ev.text;
      call.stream.scrollTop = call.stream.scrollHeight;
      this._setStatus(ev.agent, "thinking", `Writing: ${call.stream.textContent.slice(-90).replace(/\s+/g, " ")}`);
      this._autoscroll();
    }

    on_llm_thinking(ev) {
      const call = this._call(ev.call_id, ev.agent);
      call.thinkBox.hidden = false;
      call.think.textContent += ev.text;
      this._setStatus(ev.agent, "thinking", "Reasoning…");
    }

    on_llm_completed(ev) {
      const call = this._call(ev.call_id, ev.agent);
      call.done = true;
      call.stream.classList.remove("live");
      if (!call.stream.textContent && ev.text) call.stream.textContent = ev.text;
      const tokens = tokenCount(ev.usage);
      call.note.textContent = (ev.wants_tool ? "→ tool call" : "→ answer") + (tokens ? ` · ${tokens} tokens` : "");
      if (ev.cut_off) {
        call.note.textContent = "Reply was cut off before the model finished";
        call.entry.classList.add("k-warn");
        this.cutOff[ev.agent] = true;
      }
    }

    on_llm_failed(ev) {
      const call = this._call(ev.call_id, ev.agent);
      call.done = true;
      call.stream.classList.remove("live");
      call.note.textContent = `LLM call failed: ${ev.error}`;
    }

    on_tool_started(ev) {
      this.stats[ev.agent].tool += 1;
      const arg = toolArg(ev.args);
      this._setStatus(ev.agent, "tool", `${ev.tool}: ${arg}`);
      const entry = this._addEntry(ev.agent, "tool", toolIcon(ev.tool), `<code>${esc(ev.tool)}</code>`,
        `<div class="args">${esc(arg)}</div><div class="e-note"><span class="spinner"></span> running…</div>`);
      entry.dataset.tool = ev.tool;
      entry.dataset.arg = arg;
      (this.openTools[ev.agent] ||= []).push(entry);
    }

    on_tool_finished(ev) {
      // agents can run several searches at once: match on tool and query, then on tool alone
      const queue = this.openTools[ev.agent] || [];
      const arg = toolArg(ev.args);
      let idx = queue.findIndex((e) => e.dataset.tool === ev.tool && e.dataset.arg === arg);
      if (idx < 0) idx = queue.findIndex((e) => e.dataset.tool === ev.tool);
      let entry = idx >= 0 ? queue.splice(idx, 1)[0] : null;
      if (!entry) {
        entry = this._addEntry(ev.agent, "tool", toolIcon(ev.tool), `<code>${esc(ev.tool)}</code>`,
          `<div class="args">${esc(arg)}</div><div class="e-note"></div>`);
      }
      const results = (ev.output.match(/^\d+\. /gm) || []).length;
      $(".e-note", entry).innerHTML = `${icon("check")} ${results ? `${results} results` : "done"}${ev.from_cache ? " (cached)" : ""}`;
      $(".e-body", entry).insertAdjacentHTML("beforeend", `<details class="more"><summary>Output</summary><pre>${esc(ev.output)}</pre></details>`);
      this._setStatus(ev.agent, "thinking", "Reading results…");
    }

    on_tool_error(ev) {
      this._addEntry(ev.agent, "error", "alert", `Tool <code>${esc(ev.tool)}</code> failed`, `<div class="e-note">${esc(ev.error)}</div>`);
      const queue = this.openTools[ev.agent] || [];
      const idx = queue.findIndex((e) => e.dataset.tool === ev.tool);
      if (idx >= 0) $(".e-note", queue.splice(idx, 1)[0]).textContent = "failed";
    }

    on_agent_error(ev) {
      this._setStatus(ev.agent, "error", "Failed");
      this._addEntry(ev.agent, "error", "alert", "Agent error", `<div class="e-note">${esc(ev.error)}</div>`);
    }

    on_task_failed(ev) {
      this.on_agent_error(ev);
    }

    on_task_completed(ev) {
      const s = this.stats[ev.agent];
      s.end = this.evTime;
      this._renderTime(ev.agent);
      const a = this.byKey[ev.agent];
      const next = this.agents[a.index + 1];
      const handoff = next ? `→ ${next.role}` : "Report ready";
      this._setStatus(ev.agent, "done", this.cutOff[ev.agent] ? `Incomplete output · ${handoff}` : handoff);
      const words = ev.output.split(/\s+/).filter(Boolean).length;
      this._addEntry(ev.agent, "done", "check", "Completed", `<div class="e-note">${esc(a.report_title)} · ${words} words</div>`);
      if (next) {
        $(`.agent-card[data-agent="${ev.agent}"]`, this.o.pipeline).classList.add("handed");
        this._addEntry(next.key, "handoff", "chevron-right", `Handoff from ${esc(a.role)}`);
      }
    }

    on_run_completed() {
      this.finishedAt = this.evTime;
      this._finish();
    }

    on_run_failed() {
      this.finishedAt = this.evTime;
      for (const [key, s] of Object.entries(this.stats)) {
        if (s.status === "thinking" || s.status === "tool") this._setStatus(key, "error", "Stopped");
      }
      this._finish();
    }
  }

  IPC.RunViewer = RunViewer;
})();
