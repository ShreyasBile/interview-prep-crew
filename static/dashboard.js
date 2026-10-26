// Dashboard: overview, quick actions, recent activity, ATS trend and system status.
(() => {
  const IPC = window.IPC;
  const { esc, icon } = IPC;

  const stat = (iconName, tone, value, label, sub) => `
    <div class="card stat">
      <div class="stat-ico ${tone}">${icon(iconName)}</div>
      <div class="stat-body"><b>${value}</b><span>${label}</span><small>${sub}</small></div>
    </div>`;

  const scoreBadge = (run) =>
    run.score ? `<span class="score-badge ${IPC.band(run.score.score)}">${run.score.score}</span>` : IPC.statusPill(run.status);

  function recentItem(run) {
    const ats = run.kind === "ats";
    const meta = ats
      ? `${run.score ? run.score.grade : "Scanned"} · ${IPC.timeAgo(run.started_at)}`
      : `${run.inputs.experience} · ${IPC.timeAgo(run.started_at)}`;
    return `<a class="recent-item" href="#/${run.kind}/${run.id}">
      <span class="ri-icon ${ats ? "k-ats" : "k-prep"}">${icon(ats ? "file-check" : "target")}</span>
      <span class="ri-main"><b>${esc(IPC.runTitle(run))}</b><span>${esc(meta)}</span></span>
      <span class="ri-end">${scoreBadge(run)}</span></a>`;
  }

  function trendCard(stats) {
    if (!stats.scans) {
      return `<div class="card trend">
        <div class="card-head"><h3>Resume ATS score</h3></div>
        <div class="trend-empty">
          <svg class="gauge ghost" viewBox="0 0 140 140" aria-hidden="true"><circle class="g-track" cx="70" cy="70" r="58"/><text x="70" y="78" class="g-num" text-anchor="middle">--</text></svg>
          ${IPC.emptyState("file-check", "No scans yet", "Scan a resume to track its ATS score here.", '<a class="btn sm primary" href="#/ats">Scan a resume</a>')}
        </div></div>`;
    }
    const last = stats.score_trend[stats.score_trend.length - 1];
    return `<div class="card trend">
      <div class="card-head"><h3>Resume ATS score</h3><a class="link" href="#/history">All scans ${icon("chevron-right")}</a></div>
      <div class="trend-body">
        <div class="trend-gauge">${IPC.gauge(last.score)}<span class="muted">Latest scan</span></div>
        <div class="trend-side">
          <div class="spark-wrap ${IPC.band(last.score)}">${IPC.sparkline(stats.score_trend.map((t) => t.score))}</div>
          <div class="trend-nums"><div><b>${stats.best_score}</b><span>best</span></div><div><b>${stats.avg_score}</b><span>average</span></div><div><b>${stats.scans}</b><span>scans</span></div></div>
        </div>
      </div></div>`;
  }

  function crewCard(config) {
    const prep = config.agents.filter((a) => a.kind === "prep");
    const ats = config.agents.filter((a) => a.kind === "ats");
    const node = (a) => `<div class="flow-node"><span class="fn-ico">${a.icon}</span><b>${esc(a.role)}</b><span>${esc(a.produces)}</span>
      <div class="chips">${a.tools.map((t) => `<span class="chip mono">${esc(t)}</span>`).join("") || '<span class="chip">reasoning</span>'}</div></div>`;
    return `<div class="card">
      <div class="card-head"><h3>The crew</h3><a class="link" href="#/agents">Details ${icon("chevron-right")}</a></div>
      <div class="flow">${prep.map(node).join('<span class="flow-arrow">' + icon("chevron-right") + "</span>")}</div>
      <div class="flow flow-ats">${ats.map(node).join("")}<span class="flow-note">${icon("zap")} Reviews your resume after the rule-based ATS score</span></div>
    </div>`;
  }

  const FEATURES = [
    ["globe", "Live web research", "Search and news with source links for every claim"],
    ["compass", "Role analysis", "Skills, interview rounds and what interviewers look for"],
    ["user", "Personalised questions", "Probes the projects and skills on your own resume"],
    ["graduation", "Answer coaching", "STAR outlines, tips and a 5-day preparation plan"],
    ["list-checks", "ATS scoring", "Six scored areas in seconds, no AI call needed"],
    ["shield", "Private by design", "Resumes are sent to the model but never saved to disk"],
  ];

  function systemCard(config, stats) {
    const row = (iconName, label, value, ok) => `<div class="sys-row"><span class="sys-ico">${icon(iconName)}</span><span class="sys-label">${label}</span>
      <span class="sys-val ${ok === undefined ? "" : ok ? "ok" : "bad"}">${ok === undefined ? "" : '<i class="dot"></i>'}${value}</span></div>`;
    return `<div class="card">
      <div class="card-head"><h3>System</h3></div>
      <div class="sys">
        ${row("cpu", "Language model", esc(config.model), config.live_ready)}
        ${row("globe", "Web search", "DuckDuckGo", true)}
        ${row("database", "Saved runs", `${config.saved_runs} on this computer`)}
        ${row("clock", "Average prep time", stats.avg_prep_seconds ? IPC.fmtDuration(stats.avg_prep_seconds) : "No runs yet")}
        ${row("layers", "Version", esc(config.version))}
      </div>
      ${config.live_ready ? "" : `<p class="hint error">${esc(config.live_reason)}</p>`}
    </div>`;
  }

  IPC.register("dashboard", {
    title: "Dashboard",
    subtitle: "Your interview preparation at a glance",
    async mount(root) {
      root.innerHTML = `<div class="page"><div class="card skeleton-card"></div></div>`;
      const [stats, runs, config] = await Promise.all([IPC.refreshStats(), IPC.api.get("/api/runs?limit=6"), IPC.api.get("/api/config")]);
      IPC.state.config = config;
      const prepAgents = config.agents.filter((a) => a.kind === "prep");
      root.innerHTML = `<div class="page dashboard">
        <section class="hero">
          <div class="hero-text">
            <span class="hero-badge">${icon("sparkles")} Multi-agent AI crew</span>
            <h2>Walk into every interview prepared</h2>
            <p>Four specialist agents research the company, decode the role, predict your questions and coach your answers. Your resume gets an ATS score and an AI review.</p>
            <div class="hero-cta">
              <a class="btn light" href="#/prep">${icon("play")} Start interview prep</a>
              <a class="btn glass" href="#/ats">${icon("file-check")} Scan my resume</a>
            </div>
          </div>
          <div class="hero-art" aria-hidden="true">
            ${prepAgents.map((a, i) => `<div class="art-card" style="--i:${i}"><span>${a.icon}</span><b>${esc(a.role)}</b><i></i></div>`).join("")}
          </div>
        </section>

        <section class="stats">
          ${stat("target", "indigo", stats.preps, "Interview preps", `${stats.preps * 10} questions generated`)}
          ${stat("file-check", "green", stats.scans, "Resume scans", stats.avg_score !== null ? `Average score ${stats.avg_score}` : "No scans yet")}
          ${stat("activity", "amber", stats.agent_steps, "Agent steps", `${stats.tool_calls} tool calls`)}
          ${stat("link", "blue", stats.sources, "Sources cited", "Links behind every brief")}
        </section>

        <section class="grid two">
          <a class="card action-card prep" href="#/prep">
            <div class="ac-ico">${icon("target")}</div>
            <div><h3>Interview prep</h3><p>Company brief, role analysis, 10 likely questions and coached answers.</p></div>
            <span class="go">${icon("chevron-right")}</span>
          </a>
          <a class="card action-card ats" href="#/ats">
            <div class="ac-ico">${icon("file-check")}</div>
            <div><h3>Resume ATS scorer</h3><p>Score out of 100 across six areas, with an AI review that rewrites weak bullets.</p></div>
            <span class="go">${icon("chevron-right")}</span>
          </a>
        </section>

        <section class="grid main-side">
          <div class="card">
            <div class="card-head"><h3>Recent activity</h3><a class="link" href="#/history">View all ${icon("chevron-right")}</a></div>
            ${runs.length
              ? `<div class="recent">${runs.map(recentItem).join("")}</div>`
              : IPC.emptyState("history", "Nothing here yet", "Runs you complete show up here.", '<a class="btn sm primary" href="#/prep">Start your first prep</a>')}
          </div>
          ${trendCard(stats)}
        </section>

        ${crewCard(config)}

        <section class="features">
          ${FEATURES.map(([i, t, d]) => `<div class="feature"><span class="f-ico">${icon(i)}</span><h4>${t}</h4><p>${d}</p></div>`).join("")}
        </section>

        ${systemCard(config, stats)}
      </div>`;
      IPC.animateGauges(root);
      IPC.setHistoryCount(config.saved_runs);
    },
  });
})();
