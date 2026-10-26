// Shared UI components used by several views.
(() => {
  const IPC = window.IPC;
  const { $, $$, esc, icon } = IPC;

  IPC.emptyState = (iconName, title, text = "", extra = "") =>
    `<div class="empty">${icon(iconName)}<h4>${esc(title)}</h4>${text ? `<p>${esc(text)}</p>` : ""}${extra}</div>`;

  const STATUS_LABEL = { completed: "Completed", running: "Running", failed: "Failed" };
  IPC.statusPill = (status) => `<span class="pill ${status}">${STATUS_LABEL[status] || esc(status)}</span>`;

  IPC.band = (score) => (score >= 80 ? "excellent" : score >= 65 ? "good" : score >= 50 ? "fair" : "weak");

  // ---------- resume field: paste text or upload a PDF / DOCX / TXT ----------
  IPC.resumeField = ({ label = "Resume", optional = true, rows = 7, placeholder = "Paste your resume text, or drop a PDF, DOCX or TXT file here" } = {}) => {
    const el = document.createElement("div");
    el.className = "field resume-field";
    el.innerHTML = `
      <label>${esc(label)} ${optional ? '<span class="muted">optional</span>' : ""}</label>
      <div class="dropzone">
        <textarea class="textarea" rows="${rows}" maxlength="12000" placeholder="${esc(placeholder)}" aria-label="${esc(label)}"></textarea>
        <div class="dz-bar">
          <button type="button" class="btn sm ghost upload-btn">${icon("upload")}<span>Upload file</span></button>
          <span class="dz-file" hidden>${icon("file-text")}<b class="dz-name"></b><button type="button" class="dz-clear" aria-label="Remove file">${icon("x")}</button></span>
          <span class="dz-count">0 words</span>
        </div>
        <input type="file" accept=".pdf,.docx,.txt,.md" hidden>
      </div>
      <p class="field-error" role="alert" hidden></p>`;
    const zone = $(".dropzone", el);
    const ta = $("textarea", el);
    const input = $("input[type=file]", el);
    const err = $(".field-error", el);
    const button = $(".upload-btn", el);
    const listeners = [];
    let filename = "";

    const words = () => (ta.value.match(/\S+/g) || []).length;
    const paint = () => {
      $(".dz-count", el).textContent = `${words()} words`;
      $(".dz-file", el).hidden = !filename;
      $(".dz-name", el).textContent = filename;
    };
    const changed = () => {
      paint();
      listeners.forEach((fn) => fn({ text: ta.value.trim(), filename }));
    };
    const showError = (message) => {
      err.hidden = !message;
      err.textContent = message || "";
    };

    async function upload(file) {
      showError("");
      if (file.size > 5 * 1024 * 1024) return showError("The file is larger than 5 MB.");
      button.disabled = true;
      button.querySelector("span").textContent = "Reading…";
      try {
        const data = await IPC.api.postRaw(`/api/resume/parse?filename=${encodeURIComponent(file.name)}`, file);
        ta.value = data.text;
        filename = file.name;
        changed();
      } catch (e) {
        showError(e.message);
      } finally {
        button.disabled = false;
        button.querySelector("span").textContent = "Upload file";
        input.value = "";
      }
    }

    button.addEventListener("click", () => input.click());
    input.addEventListener("change", () => input.files[0] && upload(input.files[0]));
    ta.addEventListener("input", () => {
      showError("");
      changed();
    });
    $(".dz-clear", el).addEventListener("click", () => {
      ta.value = "";
      filename = "";
      changed();
    });
    ["dragenter", "dragover"].forEach((t) =>
      zone.addEventListener(t, (e) => {
        e.preventDefault();
        zone.classList.add("drag");
      })
    );
    ["dragleave", "drop"].forEach((t) => zone.addEventListener(t, () => zone.classList.remove("drag")));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      const file = e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) upload(file);
    });

    paint();
    return {
      el,
      getText: () => ta.value.trim(),
      getFilename: () => filename,
      setText(text, name = "") {
        ta.value = text || "";
        filename = name || "";
        paint();
      },
      onChange: (fn) => listeners.push(fn),
      setError: showError,
      focus: () => ta.focus(),
    };
  };

  // ---------- ATS score ----------
  IPC.gauge = (score) => {
    const r = 58;
    const c = +(2 * Math.PI * r).toFixed(1);
    const target = +(c * (1 - score / 100)).toFixed(1);
    return `<svg class="gauge ${IPC.band(score)}" viewBox="0 0 140 140" role="img" aria-label="ATS score ${score} out of 100">
      <circle class="g-track" cx="70" cy="70" r="${r}"/>
      <circle class="g-fill" cx="70" cy="70" r="${r}" transform="rotate(-90 70 70)" stroke-dasharray="${c}" stroke-dashoffset="${c}" data-target="${target}"/>
      <text x="70" y="72" class="g-num" text-anchor="middle">${score}</text>
      <text x="70" y="92" class="g-of" text-anchor="middle">out of 100</text>
    </svg>`;
  };
  IPC.animateGauges = (root) =>
    requestAnimationFrame(() =>
      requestAnimationFrame(() => $$(".g-fill", root).forEach((c) => (c.style.strokeDashoffset = c.dataset.target)))
    );

  IPC.areaList = (areas) =>
    areas
      .map((a) => {
        const pct = a.max ? Math.round((100 * a.score) / a.max) : 0;
        const tone = pct >= 75 ? "ok" : pct >= 45 ? "warn" : "bad";
        const checks = a.checks
          .map(
            (c) => `<li class="chk ${c.status}">${icon(c.status === "pass" ? "check" : c.status === "warn" ? "alert" : "x")}
              <div><b>${esc(c.title)}</b>${c.detail ? `<span>${esc(c.detail)}</span>` : ""}</div></li>`
          )
          .join("");
        return `<details class="area" ${tone === "ok" ? "" : "open"}>
          <summary><span class="a-label">${esc(a.label)}</span><span class="a-score">${a.score}<small> / ${a.max}</small></span>
            <span class="bar ${tone}"><i style="width:${pct}%"></i></span>${icon("chevron-down", "chev")}</summary>
          <ul class="checks">${checks}</ul></details>`;
      })
      .join("");

  IPC.keywordBlock = (score) => {
    const k = score.keywords;
    const chips = (list, cls) => list.map((t) => `<span class="chip ${cls}">${esc(t)}</span>`).join("");
    if (score.has_job_description && (k.matched.length || k.missing.length)) {
      return `<div class="kw-group"><h5>${icon("check")} Found in your resume <em>${k.matched.length}</em></h5><div class="chips">${chips(k.matched, "ok") || '<span class="muted">None</span>'}</div></div>
              <div class="kw-group"><h5>${icon("x")} Missing <em>${k.missing.length}</em></h5><div class="chips">${chips(k.missing, "bad") || '<span class="muted">Nothing missing</span>'}</div></div>`;
    }
    return `<div class="kw-group"><h5>${icon("sparkles")} Skills detected <em>${k.skills_found.length}</em></h5>
      <div class="chips">${chips(k.skills_found, "info") || '<span class="muted">No known skills found</span>'}</div>
      <p class="hint">Add a job description to score keyword match.</p></div>`;
  };

  IPC.statTiles = (stats) => {
    const pct = stats.bullets ? Math.round((100 * stats.quantified) / stats.bullets) : 0;
    const tile = (value, label) => `<div class="tile"><b>${value}</b><span>${label}</span></div>`;
    return [
      tile(stats.words, "words"),
      tile(stats.bullets, "bullets"),
      tile(`${pct}%`, "with numbers"),
      tile(stats.skills, "skills found"),
    ].join("");
  };

  // ---------- small charts ----------
  IPC.sparkline = (points, { width = 280, height = 84 } = {}) => {
    if (!points.length) return "";
    const pad = 8;
    const xs = (i) => (points.length === 1 ? width / 2 : pad + (i * (width - 2 * pad)) / (points.length - 1));
    const ys = (v) => height - pad - ((height - 2 * pad) * v) / 100;
    const line = points.map((p, i) => `${xs(i).toFixed(1)},${ys(p).toFixed(1)}`).join(" ");
    const area = `${pad},${height - pad} ${line} ${xs(points.length - 1).toFixed(1)},${height - pad}`;
    const dots = points.map((p, i) => `<circle cx="${xs(i).toFixed(1)}" cy="${ys(p).toFixed(1)}" r="${i === points.length - 1 ? 4 : 2.5}"/>`).join("");
    return `<svg class="spark" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Score trend">
      <defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="currentColor" stop-opacity=".25"/><stop offset="1" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs>
      <polygon points="${area}" fill="url(#sg)"/><polyline points="${line}" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>${dots}</svg>`;
  };

  // ---------- sources ----------
  IPC.sourceList = (sources, byKey = {}) => {
    if (!sources.length) return IPC.emptyState("link", "No sources yet", "Pages the research agents read will be listed here.");
    return `<ul class="sources">${sources
      .map((s) => {
        let host = s.url;
        try {
          host = new URL(s.url).hostname.replace(/^www\./, "");
        } catch {}
        const agent = byKey[s.agent];
        return `<li><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">
          <span class="src-ico">${icon(s.tool === "news_search" ? "newspaper" : s.tool === "read_webpage" ? "book" : "globe")}</span>
          <span class="src-main"><b>${esc(s.title)}</b><span>${esc(host)}${agent ? ` · found by ${esc(agent.role)}` : ""}</span></span>
          ${icon("external", "src-go")}</a></li>`;
      })
      .join("")}</ul>`;
  };

  // run title used in lists and the live pill
  IPC.runTitle = (run) =>
    run.kind === "ats"
      ? `Resume scan: ${run.inputs.filename || run.inputs.role || "pasted resume"}`
      : `${run.inputs.role} at ${run.inputs.company}`;
})();
