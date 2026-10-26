// History: every saved run, with filters, search, download and delete.
(() => {
  const IPC = window.IPC;
  const { $, $$, esc, icon } = IPC;

  IPC.register("history", {
    title: "History",
    subtitle: "Everything you have run, saved on this computer",

    async mount(root) {
      let runs = await IPC.api.get("/api/runs?limit=500");
      let kind = "all";
      let query = "";
      let confirming = null;
      let confirmTimer = null;

      root.innerHTML = `<div class="page">
        <div class="toolbar">
          <div class="seg" id="hFilter">
            <button type="button" data-k="all" class="active">All<em></em></button>
            <button type="button" data-k="prep">Interview preps<em></em></button>
            <button type="button" data-k="ats">Resume scans<em></em></button>
          </div>
          <div class="input-wrap search">${icon("search")}<input class="input" id="hSearch" placeholder="Search company, role or file" aria-label="Search history"></div>
        </div>
        <div class="run-list" id="hList"></div>
      </div>`;

      const counts = () => ({
        all: runs.length,
        prep: runs.filter((r) => r.kind === "prep").length,
        ats: runs.filter((r) => r.kind === "ats").length,
      });

      const item = (r) => {
        const ats = r.kind === "ats";
        const tags = [`<span class="chip ${ats ? "info" : "accent"}">${ats ? "Resume scan" : "Interview prep"}</span>`];
        if (!ats && r.inputs.has_resume) tags.push(`<span class="chip ok">${icon("user")}Resume</span>`);
        if (!ats && r.sources) tags.push(`<span class="chip">${icon("link")}${r.sources} sources</span>`);
        if (r.status !== "completed") tags.push(IPC.statusPill(r.status));
        const meta = [ats ? (r.score ? r.score.grade : "") : r.inputs.experience, IPC.shortModel(r.model), IPC.fmtDuration(r.duration), IPC.fmtDate(r.started_at)]
          .filter(Boolean).join(" · ");
        const sure = confirming === r.id;
        return `<article class="run-item" data-id="${r.id}">
          <a class="ri-icon ${ats ? "k-ats" : "k-prep"}" href="#/${r.kind}/${r.id}" tabindex="-1" aria-hidden="true">${icon(ats ? "file-check" : "target")}</a>
          <div class="ri-main"><h4><a href="#/${r.kind}/${r.id}">${esc(IPC.runTitle(r))}</a></h4><p>${esc(meta)}</p><div class="ri-tags">${tags.join("")}</div></div>
          ${r.score ? `<div class="ri-score"><span class="score-badge lg ${IPC.band(r.score.score)}">${r.score.score}</span><small>ATS</small></div>` : ""}
          <div class="ri-actions">
            <a class="btn sm" href="#/${r.kind}/${r.id}">Open</a>
            <a class="icon-btn" href="/api/runs/${r.id}/report.md" title="Download report" aria-label="Download report">${icon("download")}</a>
            <button type="button" class="icon-btn danger${sure ? " armed" : ""}" data-del="${r.id}" ${r.status === "running" ? "disabled" : ""} title="${sure ? "Click again to delete" : "Delete"}" aria-label="Delete">${icon("trash")}${sure ? "<span>Delete?</span>" : ""}</button>
          </div>
        </article>`;
      };

      const render = () => {
        const c = counts();
        $$("#hFilter button", root).forEach((b) => {
          b.classList.toggle("active", b.dataset.k === kind);
          $("em", b).textContent = c[b.dataset.k];
        });
        const q = query.trim().toLowerCase();
        const shown = runs.filter(
          (r) => (kind === "all" || r.kind === kind) && (!q || IPC.runTitle(r).toLowerCase().includes(q) || (r.inputs.company || "").toLowerCase().includes(q))
        );
        const list = $("#hList", root);
        if (!runs.length) {
          list.innerHTML = `<div class="card">${IPC.emptyState("history", "No history yet", "Interview preps and resume scans are saved here.",
            '<div class="empty-cta"><a class="btn primary sm" href="#/prep">Start interview prep</a><a class="btn sm" href="#/ats">Scan a resume</a></div>')}</div>`;
        } else if (!shown.length) {
          list.innerHTML = `<div class="card">${IPC.emptyState("search", "No matches", "Try another filter or search term.")}</div>`;
        } else {
          list.innerHTML = shown.map(item).join("");
        }
        $$("[data-del]", list).forEach((b) => b.addEventListener("click", () => remove(b.dataset.del)));
      };

      async function remove(id) {
        if (confirming !== id) {
          confirming = id;
          clearTimeout(confirmTimer);
          confirmTimer = setTimeout(() => {
            confirming = null;
            render();
          }, 3000);
          return render();
        }
        clearTimeout(confirmTimer);
        confirming = null;
        try {
          await IPC.api.del(`/api/runs/${id}`);
          runs = runs.filter((r) => r.id !== id);
          IPC.setHistoryCount(runs.length);
          IPC.toast("Deleted", "success");
        } catch (e) {
          IPC.toast(e.message, "error");
        }
        render();
      }

      $$("#hFilter button", root).forEach((b) =>
        b.addEventListener("click", () => {
          kind = b.dataset.k;
          render();
        })
      );
      $("#hSearch", root).addEventListener("input", (e) => {
        query = e.target.value;
        render();
      });
      this.cleanup = () => clearTimeout(confirmTimer);
      render();
    },

    unmount() {
      if (this.cleanup) this.cleanup();
    },
  });
})();
