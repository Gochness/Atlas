"use strict";

/*
 * Atlas Workspace v0.1
 *
 * Statische Ansicht des Atlas-Repositoryzustands. Liest ausschliesslich
 * ueber die GitHub API (unauthentifiziert). Kein Backend, keine
 * Schreibfunktion, keine externen Frameworks.
 *
 * Bewusste Design-Entscheidung: Die Submission-YAML- und Artefakt-Markdown-
 * Parser unten sind KEINE Allzweck-Parser, sondern eng auf das feste
 * Schema aus THE WORKSHOPS/platform/validator/validator.py bzw.
 * materialization_service.py zugeschnitten. Ein vollstaendiger YAML-Parser
 * wuerde eine externe Library erfordern, was der Vorgabe widerspricht.
 */

const REPO = "Gochness/Atlas";
const API = `https://api.github.com/repos/${REPO}`;
const BRANCH = "master";

const SUBMISSIONS_DIR = "THE WORKSHOPS/platform/submissions";
const ARTIFACTS_DIR = "THE LIBRARY/artifacts";
const PLATFORM_STATUS_PATH = "THE NORTH STAR/PLATFORM_STATUS.md";
const PROJECT_STATE_PATH = "THE NORTH STAR/PROJECT_STATE.md";
const SESSION_PATH = "THE NORTH STAR/SESSION.md";

// ---------------------------------------------------------------------------
// HTML escaping (Repository-Inhalte sind nicht vertrauenswuerdig genug fuer
// direktes innerHTML - jede Submission koennte beliebigen Text enthalten)
// ---------------------------------------------------------------------------

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function truncate(str, n) {
  if (!str) return "";
  return str.length > n ? str.slice(0, n).trim() + "…" : str;
}

// ---------------------------------------------------------------------------
// GitHub API Zugriff
// ---------------------------------------------------------------------------

function encodePath(path) {
  return path.split("/").map(encodeURIComponent).join("/");
}

function b64DecodeUnicode(b64) {
  const clean = b64.replace(/\n/g, "");
  const binary = atob(clean);
  const percentEncoded = binary
    .split("")
    .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
    .join("");
  return decodeURIComponent(percentEncoded);
}

// Repository-Dateien enthalten teils ein UTF-8-BOM (bricht "^submission:"-
// Regex) und CRLF-Zeilenenden (bricht "\n\n"-Regex in parseArtifactMarkdown).
// Einmal zentral normalisieren statt in jedem Parser einzeln.
function normalizeText(str) {
  return str.replace(/^\uFEFF/, "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
}

async function ghJson(url) {
  const res = await fetch(url, {
    headers: { Accept: "application/vnd.github+json" },
  });
  if (!res.ok) {
    if (res.status === 403) {
      throw new Error("GitHub API Rate-Limit erreicht (403). Bitte spaeter erneut versuchen.");
    }
    throw new Error(`GitHub API Fehler: HTTP ${res.status}`);
  }
  return res.json();
}

async function fetchFileText(path) {
  const json = await ghJson(`${API}/contents/${encodePath(path)}?ref=${BRANCH}`);
  return normalizeText(b64DecodeUnicode(json.content));
}

async function fetchDir(path) {
  return ghJson(`${API}/contents/${encodePath(path)}?ref=${BRANCH}`);
}

async function fetchRawByUrl(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Rohdatei-Fehler: HTTP ${res.status}`);
  return normalizeText(await res.text());
}

async function fetchCommits() {
  return ghJson(`${API}/commits?sha=${BRANCH}&per_page=10`);
}

async function fetchPulls() {
  return ghJson(`${API}/pulls?state=all&per_page=100`);
}

// ---------------------------------------------------------------------------
// Markdown-Hilfsparser (handgeschrieben, kein Framework)
// ---------------------------------------------------------------------------

function parseTableSections(md) {
  const lines = md.split("\n");
  const sections = [];
  let current = null;
  for (const line of lines) {
    if (/^##\s+/.test(line)) {
      current = { title: line.replace(/^##\s+/, "").trim(), rows: [] };
      sections.push(current);
      continue;
    }
    if (current && line.trim().startsWith("|")) {
      const cells = line
        .split("|")
        .slice(1, -1)
        .map((c) => c.trim());
      if (cells.length === 0) continue;
      if (cells.every((c) => /^:?-+:?$/.test(c))) continue; // Trennzeile
      current.rows.push(cells);
    }
  }
  return sections.filter((s) => s.rows.length > 0);
}

function extractSummaryFraction(md) {
  const m = md.match(/(\d+)\s*\/\s*(\d+)\s*components complete/i);
  return m ? `${m[1]} / ${m[2]}` : "unbekannt";
}

function allHeadingSections(md) {
  const lines = md.split("\n");
  const idxs = [];
  lines.forEach((l, i) => {
    if (/^##\s+/.test(l)) idxs.push(i);
  });
  return idxs.map((idx, k) => {
    const end = idxs[k + 1] ?? lines.length;
    return {
      heading: lines[idx].replace(/^##\s+/, "").trim(),
      body: lines.slice(idx + 1, end).join("\n").trim(),
    };
  });
}

function findSectionByHeading(md, regex) {
  const sections = allHeadingSections(md);
  return sections.find((s) => regex.test(s.heading)) || null;
}

function findLastRelevantSection(md, preferRegex) {
  const sections = allHeadingSections(md);
  if (sections.length === 0) return null;
  for (let i = sections.length - 1; i >= 0; i--) {
    if (preferRegex.test(sections[i].heading) || preferRegex.test(sections[i].body)) {
      return sections[i];
    }
  }
  return sections[sections.length - 1];
}

// ---------------------------------------------------------------------------
// Submission-YAML Parser (auf das feste Schema zugeschnitten)
// ---------------------------------------------------------------------------

function parseSubmissionYaml(text) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const result = { submission: {}, candidate: {} };
  let mode = null;
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (/^submission:\s*$/.test(line)) {
      mode = "submission";
      i++;
      continue;
    }
    if (/^candidate:\s*$/.test(line)) {
      mode = "candidate";
      i++;
      continue;
    }

    const kv = mode && line.match(/^ {2}([a-zA-Z_]+):[ ]?(.*)$/);
    if (kv) {
      const key = kv[1];
      const rest = kv[2].trim();

      if (rest === ">") {
        i++;
        const buf = [];
        while (i < lines.length && (lines[i].trim() === "" || /^ {4,}/.test(lines[i]))) {
          buf.push(lines[i].trim());
          i++;
        }
        result[mode][key] = buf.join(" ").replace(/\s+/g, " ").trim();
        continue;
      }

      if (rest === "") {
        i++;
        const list = [];
        while (i < lines.length && /^ {4}-\s*(.+)$/.test(lines[i])) {
          list.push(lines[i].match(/^ {4}-\s*(.+)$/)[1].trim());
          i++;
        }
        result[mode][key] = list.length ? list : null;
        continue;
      }

      result[mode][key] = rest === "null" ? null : rest;
      i++;
      continue;
    }

    i++;
  }

  return result;
}

// ---------------------------------------------------------------------------
// Artefakt-Markdown Parser (auf materialization_service.py Ausgabeformat zugeschnitten)
// ---------------------------------------------------------------------------

function parseArtifactMarkdown(text) {
  const refMatch = text.match(/^#\s*(\S+)/m);
  const srcMatch = text.match(/\*\*Materialisiert aus:\*\*\s*(\S+)/);
  const dateMatch = text.match(/\*\*Materialisiert am:\*\*\s*(\S+)/);

  function section(name) {
    const re = new RegExp(`## ${name}\\n\\n([\\s\\S]*?)(\\n## |$)`);
    const m = text.match(re);
    return m ? m[1].trim() : "";
  }

  return {
    ref: refMatch ? refMatch[1] : "?",
    sourceSubmission: srcMatch ? srcMatch[1] : "?",
    date: dateMatch ? dateMatch[1] : "?",
    claim: section("Behauptung"),
  };
}

function artifactType(ref) {
  if (ref.startsWith("ART-")) return "ART";
  if (ref.startsWith("JUDG-")) return "JUDG";
  if (ref.startsWith("CONT-")) return "CONT";
  return "?";
}

// ---------------------------------------------------------------------------
// Status-Ableitung fuer Submissions
// ---------------------------------------------------------------------------

function deriveSubmissionStatus(submissionId, proposedRef, pulls, artifactRefs) {
  const pr = pulls.find((p) => p.head && p.head.ref === `submission/${submissionId}`);
  const materialized = proposedRef ? artifactRefs.has(proposedRef) : false;

  if (!pr) {
    return materialized
      ? { label: "Materialisiert", cls: "ok" }
      : { label: "Kein Pull Request gefunden", cls: "warn" };
  }
  if (pr.state === "open") {
    return { label: "Offen – wartet auf Review", cls: "pending", pr };
  }
  if (pr.merged_at) {
    return materialized
      ? { label: "Materialisiert", cls: "ok", pr }
      : { label: "Gemerged, nicht materialisiert", cls: "info", pr };
  }
  return { label: "Abgelehnt / geschlossen", cls: "bad", pr };
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function renderError(containerId, err) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `<div class="error-box">Daten aktuell nicht abrufbar: ${escapeHtml(err.message)}</div>`;
}

function renderStatusSection(md) {
  const fraction = extractSummaryFraction(md);
  document.getElementById("status-badge").textContent = fraction;

  const sections = parseTableSections(md);
  const container = document.getElementById("status-tables");
  container.innerHTML = "";

  for (const section of sections) {
    if (section.title.toLowerCase() === "summary") continue;
    const [header, ...rows] = section.rows;
    const table = document.createElement("table");
    table.className = "status-table";
    const caption = document.createElement("caption");
    caption.textContent = section.title;
    table.appendChild(caption);

    const thead = document.createElement("thead");
    thead.innerHTML = `<tr>${header.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr>`;
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    tbody.innerHTML = rows
      .map((r) => `<tr>${r.map((c) => `<td>${escapeHtml(c)}</td>`).join("")}</tr>`)
      .join("");
    table.appendChild(tbody);

    container.appendChild(table);
  }
}

function renderNextStep(projectStateMd, sessionMd) {
  const projectSection = findSectionByHeading(projectStateMd, /next step/i);
  document.getElementById("next-step-project").innerHTML = projectSection
    ? `<pre>${escapeHtml(projectSection.body)}</pre>`
    : `<p class="claim-snippet">Kein "Next Step"-Abschnitt gefunden.</p>`;

  const sessionSection = findLastRelevantSection(sessionMd, /next action/i);
  document.getElementById("next-step-session").innerHTML = sessionSection
    ? `<h4 style="margin:0 0 6px 0;">${escapeHtml(sessionSection.heading)}</h4><pre>${escapeHtml(
        truncate(sessionSection.body, 1200)
      )}</pre>`
    : `<p class="claim-snippet">Kein Abschnitt gefunden.</p>`;
}

async function renderSubmissions(pulls, artifactRefs) {
  const dirEntries = await fetchDir(SUBMISSIONS_DIR);
  const yamlEntries = dirEntries.filter((e) => e.type === "file" && e.name.endsWith(".yaml") && e.name !== "example-submission.yaml");

  const items = await Promise.all(
    yamlEntries
      .sort((a, b) => a.name.localeCompare(b.name))
      .map(async (entry) => {
        try {
          const text = await fetchRawByUrl(entry.download_url);
          const parsed = parseSubmissionYaml(text);
          const sub = parsed.submission;
          const cand = parsed.candidate;
          const status = deriveSubmissionStatus(sub.id, cand.proposed_ref, pulls, artifactRefs);
          return { sub, cand, status };
        } catch (err) {
          return { error: err, name: entry.name };
        }
      })
  );

  const html = items
    .map((item) => {
      if (item.error) {
        return `<div class="list-item"><div class="error-box">${escapeHtml(item.name)}: ${escapeHtml(item.error.message)}</div></div>`;
      }
      const { sub, cand, status } = item;
      const prLink = status.pr
        ? `<a href="${escapeHtml(status.pr.html_url)}" target="_blank" rel="noopener">PR #${status.pr.number}</a>`
        : "";
      return `
        <li class="list-item">
          <div class="list-item-head">
            <span class="ref">${escapeHtml(sub.id)} → ${escapeHtml(cand.proposed_ref || "?")}</span>
            <span class="badge ${status.cls}">${escapeHtml(status.label)}</span>
          </div>
          <p class="claim-snippet">Typ: ${escapeHtml(sub.type)} &middot; Ziel: ${escapeHtml(
        Array.isArray(sub.target) ? sub.target.join(", ") : sub.target || "–"
      )} ${prLink ? "&middot; " + prLink : ""}</p>
          <p class="claim-snippet">${escapeHtml(truncate(cand.claim, 220))}</p>
        </li>`;
    })
    .join("");

  document.getElementById("submissions-list").innerHTML = `<ul class="plain-list">${html}</ul>`;
}

async function renderArtifacts() {
  const dirEntries = await fetchDir(ARTIFACTS_DIR);
  const mdEntries = dirEntries.filter((e) => e.type === "file" && e.name.endsWith(".md"));

  const items = await Promise.all(
    mdEntries
      .sort((a, b) => a.name.localeCompare(b.name))
      .map(async (entry) => {
        try {
          const text = await fetchRawByUrl(entry.download_url);
          return parseArtifactMarkdown(text);
        } catch (err) {
          return { error: err, name: entry.name };
        }
      })
  );

  const html = items
    .map((item) => {
      if (item.error) {
        return `<li class="list-item"><div class="error-box">${escapeHtml(item.name)}: ${escapeHtml(item.error.message)}</div></li>`;
      }
      return `
        <li class="list-item">
          <div class="list-item-head">
            <span class="ref">${escapeHtml(item.ref)}</span>
            <span class="badge info">${escapeHtml(artifactType(item.ref))}</span>
          </div>
          <p class="claim-snippet">Aus ${escapeHtml(item.sourceSubmission)} &middot; ${escapeHtml(item.date)}</p>
          <p class="claim-snippet">${escapeHtml(truncate(item.claim, 220))}</p>
        </li>`;
    })
    .join("");

  document.getElementById("artifacts-list").innerHTML = `<ul class="plain-list">${html}</ul>`;

  return new Set(items.filter((i) => !i.error).map((i) => i.ref));
}

function renderCommits(commits) {
  const html = commits
    .map((c) => {
      const sha = c.sha.slice(0, 7);
      const message = (c.commit.message || "").split("\n")[0];
      const author = c.commit.author ? c.commit.author.name : "?";
      const date = c.commit.author ? c.commit.author.date.slice(0, 10) : "?";
      return `
        <div class="commit-row">
          <span class="commit-sha"><a href="${escapeHtml(c.html_url)}" target="_blank" rel="noopener">${escapeHtml(sha)}</a></span>
          <span>${escapeHtml(message)}</span>
          <span class="claim-snippet">&mdash; ${escapeHtml(author)}, ${escapeHtml(date)}</span>
        </div>`;
    })
    .join("");

  document.getElementById("commits-list").innerHTML = html || "<p>Keine Commits gefunden.</p>";
}

// ---------------------------------------------------------------------------
// Orchestrierung
// ---------------------------------------------------------------------------

async function loadStatusSection() {
  try {
    const md = await fetchFileText(PLATFORM_STATUS_PATH);
    renderStatusSection(md);
  } catch (err) {
    renderError("status-tables", err);
    document.getElementById("status-badge").textContent = "?";
  }
}

async function loadNextStepSection() {
  try {
    const [projectMd, sessionMd] = await Promise.all([
      fetchFileText(PROJECT_STATE_PATH),
      fetchFileText(SESSION_PATH),
    ]);
    renderNextStep(projectMd, sessionMd);
  } catch (err) {
    renderError("next-step-project", err);
    renderError("next-step-session", err);
  }
}

async function loadSubmissionsAndArtifacts() {
  let artifactRefs = new Set();
  try {
    artifactRefs = await renderArtifacts();
  } catch (err) {
    renderError("artifacts-list", err);
  }

  try {
    const pulls = await fetchPulls();
    await renderSubmissions(pulls, artifactRefs);
  } catch (err) {
    renderError("submissions-list", err);
  }
}

async function loadCommitsSection() {
  try {
    const commits = await fetchCommits();
    renderCommits(commits);
  } catch (err) {
    renderError("commits-list", err);
  }
}

async function loadAll() {
  const btn = document.getElementById("refresh-btn");
  btn.disabled = true;

  await Promise.all([
    loadStatusSection(),
    loadNextStepSection(),
    loadSubmissionsAndArtifacts(),
    loadCommitsSection(),
  ]);

  document.getElementById("last-updated").textContent =
    "Zuletzt geladen: " + new Date().toLocaleString("de-DE");
  btn.disabled = false;
}

document.getElementById("refresh-btn").addEventListener("click", loadAll);

loadAll();
