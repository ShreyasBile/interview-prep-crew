// Agents: every agent, its tools, and how the system fits together.
(() => {
  const IPC = window.IPC;
  const { esc, icon } = IPC;

  const TOOL_ICON = { web_search: "search", news_search: "newspaper", read_webpage: "book" };

  const agentCard = (a, n, tools) => `
    <article class="card agent-detail ${a.kind}">
      <div class="ad-head"><span class="ad-ico">${a.icon}</span><div><span class="ad-no">${a.kind === "ats" ? "Resume crew" : `Agent ${n}`}</span><h3>${esc(a.role)}</h3></div></div>
      <p>${esc(a.summary)}</p>
      <dl>
        <div><dt>${icon("download")}Reads</dt><dd>${esc(a.reads)}</dd></div>
        <div><dt>${icon("upload")}Produces</dt><dd>${esc(a.produces)}</dd></div>
      </dl>
      <div class="ad-tools">${
        a.tools.length
          ? a.tools.map((t) => `<span class="chip mono" title="${esc((tools.find((x) => x.name === t) || {}).description || "")}">${icon(TOOL_ICON[t] || "zap")}${esc(t)}</span>`).join("")
          : `<span class="chip">${icon("cpu")}reasoning only</span>`
      }</div>
    </article>`;

  const node = (iconName, title, sub, chips = "") =>
    `<div class="arch-node"><span class="an-ico">${icon(iconName)}</span><b>${title}</b><span>${sub}</span>${chips ? `<div class="chips">${chips}</div>` : ""}</div>`;
  const link = (label) => `<div class="arch-link"><span>${label}</span><i></i></div>`;

  IPC.register("agents", {
    title: "Agents",
    subtitle: "Who does what, and how it fits together",

    async mount(root) {
      const config = (IPC.state.config = await IPC.api.get("/api/config"));
      const prep = config.agents.filter((a) => a.kind === "prep");
      const ats = config.agents.filter((a) => a.kind === "ats");
      const usedBy = (tool) => config.agents.filter((a) => a.tools.includes(tool)).map((a) => esc(a.role)).join(", ");
      const model = esc(config.model);

      root.innerHTML = `<div class="page">
        <section>
          <div class="section-head"><h3>Interview prep crew</h3><span class="muted">Runs in order; each agent receives the earlier outputs</span></div>
          <div class="flow flow-lg">${prep
            .map((a) => `<div class="flow-node"><span class="fn-ico">${a.icon}</span><b>${esc(a.role)}</b><span>${esc(a.produces)}</span></div>`)
            .join('<span class="flow-arrow">' + icon("chevron-right") + "</span>")}</div>
          <div class="grid two">${prep.map((a, i) => agentCard(a, i + 1, config.tools)).join("")}</div>
        </section>

        <section>
          <div class="section-head"><h3>Resume review</h3><span class="muted">Starts from the rule-based ATS score</span></div>
          <div class="grid two">${ats.map((a) => agentCard(a, 1, config.tools)).join("")}
            <article class="card agent-detail rules">
              <div class="ad-head"><span class="ad-ico">${icon("list-checks")}</span><div><span class="ad-no">Not an agent</span><h3>ATS scoring engine</h3></div></div>
              <p>Deterministic rules score the resume out of 100 in milliseconds, with no model call. Its findings are handed to the reviewer agent.</p>
              <dl><div><dt>${icon("list-checks")}Areas</dt><dd>Keywords 35 · Sections 15 · Contact 10 · Impact 15 · Formatting 15 · Language 10</dd></div></dl>
            </article></div>
        </section>

        <section class="card">
          <div class="card-head"><h3>Tools</h3></div>
          <div class="table-wrap"><table class="table"><thead><tr><th>Tool</th><th>What it does</th><th>Used by</th></tr></thead><tbody>
            ${config.tools.map((t) => `<tr><td><span class="chip mono">${icon(TOOL_ICON[t.name] || "zap")}${esc(t.name)}</span></td><td>${esc(t.description)}</td><td>${usedBy(t.name)}</td></tr>`).join("")}
          </tbody></table></div>
        </section>

        <section class="card">
          <div class="card-head"><h3>How it fits together</h3></div>
          <div class="arch">
            ${node("monitor", "Browser", "Dashboard, live agent view", '<span class="chip">HTML · JS</span>')}
            ${link("REST + live events")}
            ${node("server", "FastAPI server", "Runs, history, uploads", '<span class="chip">SSE</span>')}
            ${link("kickoff()")}
            ${node("bot", "CrewAI crew", "Agents, tasks, event bus", '<span class="chip">sequential</span>')}
            ${link("chat API")}
            ${node("cpu", "Language model", model, `<span class="chip ${config.live_ready ? "ok" : "bad"}">${esc(config.provider)}</span>`)}
            <div></div><div></div>
            ${node("database", "Run history", "JSON files on disk", '<span class="chip">no resumes</span>')}
            <div></div>
            ${node("globe", "Web tools", "Search, news, pages", '<span class="chip mono">DuckDuckGo</span>')}
            <div></div><div></div>
          </div>
        </section>
      </div>`;
    },
  });
})();
