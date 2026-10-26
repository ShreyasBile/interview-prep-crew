// Minimal, dependency-free Markdown -> HTML for agent outputs.
// Everything is HTML-escaped first, so model output can never inject markup.
(function () {
  const escapeHtml = (s) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  function inline(text) {
    let s = escapeHtml(text);
    const codes = [];
    s = s.replace(/`([^`]+)`/g, (_, c) => {
      codes.push(c);
      return `\u0000${codes.length - 1}\u0000`;
    });
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    s = s.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>');
    s = s.replace(/\[Resume\]/g, '<span class="tag">From your resume</span>');
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/__([^_]+)__/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>").replace(/(^|\s)_([^_]+)_(?=\s|$|[.,;:])/g, "$1<em>$2</em>");
    return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[Number(i)]}</code>`);
  }

  // Small models sometimes wrap the whole answer in ```markdown fences or leak <think> blocks.
  function clean(md) {
    let s = (md || "").replace(/<think>[\s\S]*?<\/think>/gi, "").trim();
    const fenced = s.match(/^```(?:markdown|md)?\s*\n([\s\S]*?)\n```\s*$/i);
    if (fenced) s = fenced[1];
    return s;
  }

  function isTableSep(line) {
    return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/.test(line);
  }
  const cells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => inline(c.trim()));

  function render(md) {
    const lines = clean(md).replace(/\r\n?/g, "\n").split("\n");
    const out = [];
    let para = [];
    let list = null; // {tag, items: [{html, sub: []}]}

    const flushPara = () => {
      if (para.length) out.push(`<p>${para.map(inline).join("<br>")}</p>`);
      para = [];
    };
    const flushList = () => {
      if (!list) return;
      const items = list.items
        .map((it) => {
          const sub = it.sub.length ? `<ul>${it.sub.map((x) => `<li>${x}</li>`).join("")}</ul>` : "";
          return `<li>${it.html}${sub}</li>`;
        })
        .join("");
      out.push(`<${list.tag}>${items}</${list.tag}>`);
      list = null;
    };
    const flush = () => {
      flushPara();
      flushList();
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      let m;
      if (/^\s*```/.test(line)) {
        flush();
        const code = [];
        while (++i < lines.length && !/^\s*```/.test(lines[i])) code.push(lines[i]);
        out.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
      } else if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
        flush();
        const level = Math.min(m[1].length + 1, 6); // page already has an h1/h2
        out.push(`<h${level}>${inline(m[2].replace(/#+\s*$/, ""))}</h${level}>`);
      } else if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(line)) {
        flush();
        out.push("<hr>");
      } else if (line.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
        flush();
        const head = cells(line);
        const rows = [];
        i++;
        while (i + 1 < lines.length && lines[i + 1].includes("|") && lines[i + 1].trim()) rows.push(cells(lines[++i]));
        out.push(
          `<div class="table-wrap"><table><thead><tr>${head.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>` +
            rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("") +
            "</tbody></table></div>"
        );
      } else if ((m = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/))) {
        flushPara();
        const nested = m[1].replace(/\t/g, "  ").length >= 2 && list;
        const tag = /\d/.test(m[2]) ? "ol" : "ul";
        if (nested) {
          list.items[list.items.length - 1].sub.push(inline(m[3]));
        } else {
          if (list && list.tag !== tag) flushList();
          if (!list) list = { tag, items: [] };
          list.items.push({ html: inline(m[3]), sub: [] });
        }
      } else if ((m = line.match(/^>\s?(.*)$/))) {
        flush();
        out.push(`<blockquote>${inline(m[1])}</blockquote>`);
      } else if (!line.trim()) {
        flush();
      } else if (list && /^\s{2,}\S/.test(line)) {
        list.items[list.items.length - 1].html += " " + inline(line.trim());
      } else {
        flushList();
        para.push(line.trim());
      }
    }
    flush();
    return out.join("\n");
  }

  window.MD = { render, clean, escapeHtml };
})();
