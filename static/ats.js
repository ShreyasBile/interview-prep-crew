// Resume ATS: rule-based score (instant) plus an AI review agent (streamed).
(() => {
  const IPC = window.IPC;
  const { $, $$, esc, icon } = IPC;

  const CHECKED = [
    ["Keyword match", 35, "Terms from the job description that appear in your resume"],
    ["Sections", 15, "Education, skills, experience or projects, summary"],
    ["Contact info", 10, "Email, phone, LinkedIn or GitHub"],
    ["Impact", 15, "Bullets that start with a verb and include numbers"],
    ["Formatting", 15, "Length, dates, consistent bullets, no walls of text"],
    ["Language", 10, "Weak phrases such as “responsible for”, first-person pronouns"],
  ];

  const TEMPLATE = `
    <div class="page split-page">
      <aside class="card form-card">
        <div class="card-head"><h3>Resume scan</h3></div>
        <form id="aForm" autocomplete="off" novalidate>
          <div id="aResumeSlot"></div>
          <div class="field"><label for="aRole">Target role <span class="muted">optional</span></label>
            <div class="input-wrap">${icon("user")}<input class="input" id="aRole" name="role" maxlength="80" placeholder="Backend Engineer"></div></div>
          <details class="fold" id="aJdFold"><summary>${icon("file-text")}<span>Job description</span><em>for keyword match</em>${icon("chevron-down", "chev")}</summary>
            <textarea class="textarea" name="job_description" rows="6" maxlength="6000" aria-label="Job description"></textarea></details>
          <label class="switch"><input type="checkbox" name="review" checked>
            <span class="track"></span><span class="switch-text"><b>AI review</b><small>An agent rewrites weak bullets</small></span></label>
          <button class="btn primary block" type="submit" id="aScan"><span class="btn-ico">${icon("file-check")}</span><span class="btn-label">Scan resume</span></button>
          <p class="hint" id="aHint" role="status"></p>
        </form>
      </aside>
      <section class="stack" id="aResults"></section>
    </div>`;

  const emptyResults = () => `
    <div class="card ats-intro">
      <div class="intro-gauge"><svg class="gauge ghost" viewBox="0 0 140 140" aria-hidden="true"><circle class="g-track" cx="70" cy="70" r="58"/><text x="70" y="78" class="g-num" text-anchor="middle">--</text></svg></div>
      <div class="intro-text"><h3>Your score appears here</h3><p>Upload a PDF, DOCX or TXT, or paste your resume. The ATS score is instant and works without a model.</p></div>
    </div>
    <div class="card">
      <div class="card-head"><h3>What is scored</h3><span class="muted">100 points</span></div>
      <div class="criteria">${CHECKED.map(([name, pts, text]) => `<div class="criterion"><b>${pts}</b><div><h4>${name}</h4><p>${text}</p></div></div>`).join("")}</div>
    </div>`;

  const scoreCards = (run) => {
    const s = run.score;
    const who = run.inputs.filename || "Pasted resume";
    return `
      <div class="card score-hero">
        <div class="gauge-wrap">${IPC.gauge(s.score)}</div>
        <div class="score-info">
          <div class="grade-row"><span class="grade ${IPC.band(s.score)}">${s.grade}</span><span class="muted">${esc(who)}${run.inputs.role ? ` · ${esc(run.inputs.role)}` : ""}</span></div>
          <div class="tiles">${IPC.statTiles(s.stats)}</div>
          <div class="score-actions"><a class="btn sm" href="/api/runs/${run.id}/report.md">${icon("download")}Download report</a></div>
        </div>
      </div>
      <div class="card"><div class="card-head"><h3>Score breakdown</h3></div><div class="areas">${IPC.areaList(s.areas)}</div></div>
      <div class="card"><div class="card-head"><h3>Keywords</h3></div>${IPC.keywordBlock(s)}</div>
      <div id="aReviewSlot"></div>`;
  };

  const reviewCard = () => `
    <div class="card review-card">
      <div class="card-head"><h3>${icon("sparkles")} AI review</h3><span class="clock" id="aClock"></span></div>
      <div class="banner" id="aBanner" hidden></div>
      <div class="pipeline" id="aPipeline"></div>
      <article class="markdown review-body" id="aReviewBody" hidden></article>
      <details class="fold" id="aActivity"><summary>${icon("activity")}<span>Agent activity</span>${icon("chevron-down", "chev")}</summary>
        <div class="timeline" id="aTimeline"></div></details>
    </div>`;

  const note = (iconName, text) => `<div class="card note-card">${icon(iconName)}<p>${esc(text)}</p></div>`;

  IPC.register("ats", {
    title: "Resume ATS",
    subtitle: "Score your resume and get an AI review",
    viewer: null,

    async mount(root, runId) {
      const config = IPC.state.config || (IPC.state.config = await IPC.api.get("/api/config"));
      const agent = config.agents.filter((a) => a.kind === "ats");
      const draft = IPC.draft;
      root.innerHTML = TEMPLATE;
      const form = $("#aForm", root);
      const results = $("#aResults", root);
      const hint = $("#aHint", root);
      const scanBtn = $("#aScan", root);
      const resume = IPC.resumeField({ optional: false, rows: 9 });
      $("#aResumeSlot", root).appendChild(resume.el);

      form.role.value = draft.role;
      form.job_description.value = draft.job_description;
      $("#aJdFold", root).open = !!draft.job_description;
      resume.setText(draft.resume.text, draft.resume.filename);
      form.addEventListener("input", () => {
        draft.role = form.role.value;
        draft.job_description = form.job_description.value;
      });
      resume.onChange((r) => (draft.resume = { text: r.text, filename: r.filename }));
      if (!config.live_ready) {
        form.review.checked = false;
        form.review.disabled = true;
        $(".switch-text small", root).textContent = "Model not configured; the score still works";
      }

      let busy = false;
      const setBusy = (on) => {
        busy = on;
        scanBtn.disabled = on;
        $(".btn-label", scanBtn).textContent = on ? "Reviewing…" : "Scan resume";
        $(".btn-ico", scanBtn).innerHTML = on ? '<span class="spinner"></span>' : icon("file-check");
      };

      const showRun = (run, skipped = null) => {
        this.destroyViewer();
        results.innerHTML = scoreCards(run);
        IPC.animateGauges(results);
        const slot = $("#aReviewSlot", results);
        const hasReview = run.status === "running" || run.event_count > 2;
        if (!hasReview) {
          slot.innerHTML = skipped
            ? note("info", `AI review skipped: ${skipped}`)
            : note("sparkles", "AI review was off for this scan. Turn it on to get prioritised fixes and bullet rewrites.");
          return;
        }
        slot.innerHTML = reviewCard();
        const banner = $("#aBanner", results);
        const body = $("#aReviewBody", results);
        const setBanner = (html, kind = "") => {
          banner.className = `banner ${kind}`;
          banner.innerHTML = html;
          banner.hidden = false;
        };
        this.viewer = new IPC.RunViewer({
          pipeline: $("#aPipeline", results),
          timeline: $("#aTimeline", results),
          clock: $("#aClock", results),
          onEvent: (ev) => {
            if (ev.type === "run_started") setBanner(`<span class="spinner"></span><span>Reviewing with ${esc(IPC.shortModel(ev.model))}…</span>`);
            if (ev.type === "task_completed") {
              body.innerHTML = MD.render(ev.output);
              body.hidden = false;
            }
            if (ev.type === "run_completed") {
              setBanner(`${icon("check")}<span>AI review ready in ${IPC.fmtDuration(ev.duration)}</span>`, "done");
              setBusy(false);
              if (IPC.state.activeRun && IPC.state.activeRun.id === run.id) IPC.setActiveRun(null);
              IPC.refreshCounts();
              if (run.status === "running") IPC.toast("AI review is ready", "success"); // not when replaying history
            }
            if (ev.type === "run_failed" || ev.type === "connection_lost") {
              setBanner(`${icon("alert")}<span>${ev.type === "run_failed" ? `Review failed: ${esc(ev.error)}` : "Lost connection to this run."}</span>`, "error");
              setBusy(false);
              if (IPC.state.activeRun && IPC.state.activeRun.id === run.id) IPC.setActiveRun(null);
            }
          },
        });
        this.viewer.setAgents(agent);
        if (run.status === "running") {
          setBusy(true);
          $("#aActivity", results).open = true;
          IPC.setActiveRun({ id: run.id, kind: "ats", label: "Resume review running" });
        }
        this.viewer.open(run);
      };

      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (busy) return;
        hint.className = "hint";
        hint.textContent = "";
        const text = resume.getText();
        if (text.split(/\s+/).filter(Boolean).length < 40) {
          resume.setError("Paste or upload your resume first (at least 40 words).");
          resume.focus();
          return;
        }
        resume.setError("");
        setBusy(true);
        try {
          const run = await IPC.api.post("/api/ats", {
            resume: text,
            job_description: form.job_description.value.trim(),
            role: form.role.value.trim(),
            filename: resume.getFilename(),
            review: form.review.checked,
          });
          history.replaceState(null, "", `#/ats/${run.id}`);
          if (run.status !== "running") setBusy(false);
          showRun(run, run.review_skipped);
          IPC.refreshCounts();
        } catch (err) {
          setBusy(false);
          hint.className = "hint error";
          hint.textContent = err.message;
        }
      });

      results.innerHTML = emptyResults();
      const id = runId || (IPC.state.activeRun && IPC.state.activeRun.kind === "ats" ? IPC.state.activeRun.id : null);
      if (id) {
        try {
          const run = await IPC.api.get(`/api/runs/${id}`);
          if (run.kind === "prep") return IPC.navigate(`#/prep/${id}`);
          showRun(run);
        } catch (err) {
          history.replaceState(null, "", "#/ats");
          IPC.toast(err.message, "error");
        }
      }
    },

    destroyViewer() {
      if (this.viewer) this.viewer.destroy();
      this.viewer = null;
    },
    unmount() {
      this.destroyViewer();
    },
  });
})();
