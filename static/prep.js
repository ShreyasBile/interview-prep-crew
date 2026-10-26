// Interview prep: the form, the four-agent crew, and its Activity / Prep pack / Sources tabs.
(() => {
  const IPC = window.IPC;
  const { $, $$, esc, icon } = IPC;

  const TEMPLATE = (experienceOptions) => `
    <div class="page split-page">
      <aside class="card form-card">
        <div class="card-head"><h3>New interview prep</h3></div>
        <form id="prepForm" autocomplete="off" novalidate>
          <div class="field"><label for="pCompany">Company</label>
            <div class="input-wrap">${icon("building")}<input class="input" id="pCompany" name="company" maxlength="80" placeholder="Infosys" required></div></div>
          <div class="field"><label for="pRole">Role</label>
            <div class="input-wrap">${icon("user")}<input class="input" id="pRole" name="role" maxlength="80" placeholder="Software Engineer" required></div></div>
          <div class="field"><label for="pExp">Experience</label>
            <select class="select" id="pExp" name="experience">${experienceOptions}</select></div>
          <details class="fold" id="pJdFold"><summary>${icon("file-text")}<span>Job description</span><em>optional</em>${icon("chevron-down", "chev")}</summary>
            <textarea class="textarea" name="job_description" rows="5" maxlength="4000" aria-label="Job description"></textarea></details>
          <div id="pResumeSlot"></div>
          <button class="btn primary block" type="submit" id="pRun"><span class="btn-ico">${icon("play")}</span><span class="btn-label">Run crew</span></button>
          <p class="hint" id="pHint" role="status"></p>
        </form>
      </aside>

      <section class="stack">
        <div class="card crew-card">
          <div class="card-head"><h3>Crew</h3><span class="clock" id="pClock"></span></div>
          <div class="banner" id="pBanner" hidden></div>
          <div class="pipeline" id="pPipeline"></div>
        </div>

        <div class="card results-card">
          <div class="tabs pane-tabs" role="tablist">
            <button type="button" role="tab" data-pane="activity" class="active">${icon("activity")}Activity</button>
            <button type="button" role="tab" data-pane="pack">${icon("file-text")}Prep pack<i class="dotmark" hidden></i></button>
            <button type="button" role="tab" data-pane="sources">${icon("link")}Sources<em class="count" id="pSrcCount">0</em></button>
            <span class="spacer"></span>
            <a class="btn sm" id="pDownload" hidden>${icon("download")}Download</a>
          </div>

          <div class="pane active" data-pane="activity">
            <div class="activity-head"><div class="seg" id="pFilter" aria-label="Filter by agent"></div></div>
            <div class="timeline" id="pTimeline"><p class="empty-line">No activity yet.</p></div>
          </div>

          <div class="pane" data-pane="pack">
            <div class="pack-meta" id="pMeta"></div>
            <div class="tabs sub-tabs" id="pPackTabs" role="tablist"></div>
            <article class="markdown" id="pPackBody">${IPC.emptyState("file-text", "No report yet", "Each agent's output appears here as soon as it finishes.")}</article>
          </div>

          <div class="pane" data-pane="sources" id="pSources">${IPC.sourceList([])}</div>
        </div>
      </section>
    </div>`;

  IPC.register("prep", {
    title: "Interview prep",
    subtitle: "Four agents research, question and coach",
    viewer: null,

    async mount(root, runId) {
      const config = IPC.state.config || (IPC.state.config = await IPC.api.get("/api/config"));
      const agents = config.agents.filter((a) => a.kind === "prep");
      const draft = IPC.draft;
      root.innerHTML = TEMPLATE(config.experience_levels.map((x) => `<option>${esc(x)}</option>`).join(""));

      const form = $("#prepForm", root);
      const hint = $("#pHint", root);
      const runBtn = $("#pRun", root);
      const banner = $("#pBanner", root);
      const resume = IPC.resumeField({ rows: 6 });
      $("#pResumeSlot", root).appendChild(resume.el);

      // restore what was typed earlier (shared with the Resume ATS page)
      form.company.value = draft.company;
      form.role.value = draft.role;
      form.experience.value = draft.experience;
      form.job_description.value = draft.job_description;
      $("#pJdFold", root).open = !!draft.job_description;
      resume.setText(draft.resume.text, draft.resume.filename);
      form.addEventListener("input", () => {
        draft.company = form.company.value;
        draft.role = form.role.value;
        draft.experience = form.experience.value;
        draft.job_description = form.job_description.value;
      });
      resume.onChange((r) => (draft.resume = { text: r.text, filename: r.filename }));

      let report = {};
      let sources = [];
      let currentRun = null;
      let packTab = null;
      let packPinned = false;
      let busy = false;

      // ----- panes -----
      const showPane = (name) => {
        $$(".pane", root).forEach((p) => p.classList.toggle("active", p.dataset.pane === name));
        $$(".pane-tabs [data-pane]", root).forEach((b) => b.classList.toggle("active", b.dataset.pane === name));
        if (name === "pack") $(".dotmark", root).hidden = true;
      };
      $$(".pane-tabs [data-pane]", root).forEach((b) => b.addEventListener("click", () => showPane(b.dataset.pane)));

      const renderSources = () => {
        $("#pSources", root).innerHTML = IPC.sourceList(sources, this.viewer.byKey);
        $("#pSrcCount", root).textContent = sources.length;
      };

      const renderPackTabs = () => {
        $("#pPackTabs", root).innerHTML = agents
          .map((a) => `<button type="button" role="tab" class="tab${a.key === packTab ? " active" : ""}" data-tab="${a.key}" ${report[a.key] ? "" : "disabled"}>${a.icon} ${esc(a.report_title)}</button>`)
          .join("");
        $$("#pPackTabs .tab", root).forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab, true)));
      };
      const showTab = (key, pinned = false) => {
        if (!report[key]) return;
        packTab = key;
        if (pinned) packPinned = true;
        renderPackTabs();
        $("#pPackBody", root).innerHTML = MD.render(report[key]);
      };
      const resetPack = () => {
        report = {};
        sources = [];
        packTab = null;
        packPinned = false;
        renderPackTabs();
        renderSources();
        $("#pPackBody", root).innerHTML = IPC.emptyState("file-text", "No report yet", "Each agent's output appears here as soon as it finishes.");
        $("#pMeta", root).innerHTML = "";
        $("#pDownload", root).hidden = true;
        $(".dotmark", root).hidden = true;
        banner.hidden = true;
      };

      const setBanner = (html, kind = "") => {
        banner.className = `banner ${kind}`;
        banner.innerHTML = html;
        banner.hidden = false;
      };
      const setBusy = (on) => {
        busy = on;
        runBtn.disabled = on || !config.live_ready;
        $(".btn-label", runBtn).textContent = on ? "Running…" : "Run crew";
        $(".btn-ico", runBtn).innerHTML = on ? '<span class="spinner"></span>' : icon("play");
      };
      const finishRun = (runId_) => {
        setBusy(false);
        if (IPC.state.activeRun && IPC.state.activeRun.id === runId_) IPC.setActiveRun(null);
        IPC.refreshCounts();
      };

      // ----- the viewer -----
      this.viewer = new IPC.RunViewer({
        pipeline: $("#pPipeline", root),
        timeline: $("#pTimeline", root),
        filter: $("#pFilter", root),
        clock: $("#pClock", root),
        onSelect: () => showPane("activity"),
        onEvent: (ev) => {
          switch (ev.type) {
            case "run_started": {
              const { company, role, experience } = ev.inputs;
              form.company.value = draft.company = company;
              form.role.value = draft.role = role;
              form.experience.value = draft.experience = experience;
              setBanner(`${icon("target")}<span>${esc(role)} at ${esc(company)} · ${esc(experience)} · ${esc(IPC.shortModel(ev.model))}</span>`);
              $("#pMeta", root).innerHTML = ev.inputs.has_resume
                ? `<span class="chip ok">${icon("user")}Personalised with your resume · ${ev.inputs.resume_words} words</span>`
                : "";
              break;
            }
            case "tool_finished":
              for (const s of ev.sources || []) if (!sources.some((x) => x.url === s.url)) sources.push({ ...s, agent: ev.agent, tool: ev.tool });
              renderSources();
              break;
            case "task_completed":
              report[ev.agent] = ev.output;
              if (!packPinned || !packTab) showTab(ev.agent);
              else renderPackTabs();
              if (!$(".pane[data-pane=pack]", root).classList.contains("active")) $(".dotmark", root).hidden = false;
              break;
            case "run_completed": {
              report = { ...report, ...ev.report };
              sources = ev.sources || sources;
              renderSources();
              if (!packTab) showTab(agents[0].key);
              else renderPackTabs();
              const warn = ev.warnings && ev.warnings.length;
              setBanner(
                warn
                  ? `${icon("alert")}<span>Completed in ${IPC.fmtDuration(ev.duration)}, but ${ev.warnings.map(esc).join(" ")}</span>`
                  : `${icon("check")}<span>Completed in ${IPC.fmtDuration(ev.duration)}</span>`,
                warn ? "warn" : "done"
              );
              const dl = $("#pDownload", root);
              dl.href = `/api/runs/${currentRun.id}/report.md`;
              dl.hidden = false;
              showPane("pack");
              finishRun(currentRun.id);
              if (currentRun.status === "running") IPC.toast("Interview prep is ready", "success"); // not when replaying history
              break;
            }
            case "run_failed":
              setBanner(`${icon("alert")}<span>Run failed: ${esc(ev.error)}</span>`, "error");
              finishRun(currentRun.id);
              break;
            case "connection_lost":
              setBanner(`${icon("alert")}<span>Lost connection to this run. The server may have restarted.</span>`, "error");
              finishRun(currentRun.id);
              break;
          }
        },
      });
      this.viewer.setAgents(agents);

      const open = (run) => {
        currentRun = run;
        resetPack();
        history.replaceState(null, "", `#/prep/${run.id}`); // a reload reconnects to this run
        if (run.status === "running") {
          setBusy(true);
          IPC.setActiveRun({ id: run.id, kind: "prep", label: "Interview prep running" });
          showPane("activity");
        }
        this.viewer.open(run);
      };

      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (busy) return;
        hint.className = "hint";
        hint.textContent = "";
        const data = {
          company: form.company.value.trim(),
          role: form.role.value.trim(),
          experience: form.experience.value,
          job_description: form.job_description.value.trim(),
          resume: resume.getText(),
        };
        if (!data.company || !data.role) {
          hint.className = "hint error";
          hint.textContent = "Company and role are required.";
          (data.company ? form.role : form.company).focus();
          return;
        }
        setBusy(true);
        try {
          open(await IPC.api.post("/api/runs", data));
        } catch (err) {
          hint.className = "hint error";
          hint.textContent = err.message;
          setBusy(false);
        }
      });

      if (!config.live_ready) {
        runBtn.disabled = true;
        hint.className = "hint error";
        hint.textContent = config.live_reason;
      }

      // re-attach to a run from the URL, or to the one in progress
      const id = runId || (IPC.state.activeRun && IPC.state.activeRun.kind === "prep" ? IPC.state.activeRun.id : null);
      if (id) {
        try {
          const run = await IPC.api.get(`/api/runs/${id}`);
          if (run.kind === "ats") return IPC.navigate(`#/ats/${id}`);
          open(run);
        } catch (err) {
          history.replaceState(null, "", "#/prep");
          IPC.toast(err.message, "error");
        }
      }
    },

    unmount() {
      if (this.viewer) this.viewer.destroy();
      this.viewer = null;
    },
  });
})();
