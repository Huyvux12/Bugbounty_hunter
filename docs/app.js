const LABELS = {
  hackerone: "HackerOne",
  bugcrowd: "Bugcrowd",
  intigriti: "Intigriti",
  yeswehack: "YesWeHack",
  federacy: "Federacy",
  hackenproof: "HackenProof",
};
const ORDER = ["hackerone", "bugcrowd", "intigriti", "yeswehack", "federacy", "hackenproof"];

const state = { tab: "recommended", q: "", platform: "", feeds: null, programs: [] };

async function load() {
  const [feeds, programs] = await Promise.all([
    fetch("data/feeds.json").then((r) => r.json()),
    fetch("data/programs.min.json").then((r) => r.json()),
  ]);
  state.feeds = feeds;
  state.programs = programs.programs || [];
  const counts = feeds.counts || countBy(state.programs);
  const parts = ORDER.filter((p) => counts[p])
    .map((p) => `${LABELS[p] || p} ${counts[p]}`)
    .concat(Object.keys(counts).filter((p) => !ORDER.includes(p)).map((p) => `${p} ${counts[p]}`));
  document.getElementById("meta").textContent =
    `Cập nhật ${feeds.generated_at || programs.generated_at || ""} · ${state.programs.length} program` +
    (parts.length ? ` · ${parts.join(" · ")}` : "");
  renderChips();
  render();
}

function countBy(rows) {
  const counts = {};
  for (const p of rows) counts[p.platform] = (counts[p.platform] || 0) + 1;
  return counts;
}

function platformIds() {
  const present = new Set(state.programs.map((p) => p.platform));
  return ORDER.filter((p) => present.has(p)).concat([...present].filter((p) => !ORDER.includes(p)).sort());
}

function chipCount(platform) {
  if (state.tab === "recommended") {
    const grouped = (state.feeds && state.feeds.recommended_by_platform) || {};
    if (grouped[platform]) return grouped[platform].length;
  }
  const rows = tabRows();
  return rows.filter((p) => p.platform === platform).length;
}

function renderChips() {
  const root = document.getElementById("platforms");
  root.innerHTML = "";
  const all = document.createElement("button");
  all.type = "button";
  all.textContent = "Tất cả";
  all.className = state.platform ? "" : "active";
  all.addEventListener("click", () => {
    state.platform = "";
    renderChips();
    render();
  });
  root.appendChild(all);
  for (const platform of platformIds()) {
    const n = chipCount(platform);
    if (!n && state.tab !== "all") continue;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = `${LABELS[platform] || platform} (${n})`;
    btn.className = state.platform === platform ? "active" : "";
    btn.addEventListener("click", () => {
      state.platform = platform;
      renderChips();
      render();
    });
    root.appendChild(btn);
  }
}

function tabRows() {
  if (state.tab === "all") return state.programs;
  if (state.tab === "recommended" && state.platform) {
    const grouped = (state.feeds && state.feeds.recommended_by_platform) || {};
    const ids = new Set((grouped[state.platform] || []).map((c) => c.id));
    if (ids.size) return state.programs.filter((p) => ids.has(p.id));
  }
  const ids = new Set(((state.feeds && state.feeds[state.tab]) || []).map((c) => c.id));
  return state.programs.filter((p) => ids.has(p.id));
}

function currentRows() {
  return tabRows().filter((p) => !state.platform || p.platform === state.platform);
}

function render() {
  const q = state.q.toLowerCase();
  const rows = currentRows().filter((p) => {
    if (!q) return true;
    const blob = `${p.name} ${p.handle} ${p.id} ${(p.in_scope || []).map((a) => a.identifier).join(" ")}`.toLowerCase();
    return blob.includes(q);
  });
  const root = document.getElementById("list");
  root.innerHTML = "";
  if (!rows.length) {
    root.innerHTML = '<p class="empty">Không có program khớp bộ lọc.</p>';
    return;
  }
  for (const p of rows) {
    const el = document.createElement("article");
    el.className = "card";
    el.innerHTML = `<h2>${escapeHtml(p.name)} <span class="score">${escapeHtml(p.easy_score ?? "")}</span></h2>
      <p>${escapeHtml(LABELS[p.platform] || p.platform)} · ${p.offers_bounty ? "bounty" : "VDP"} · ${p.concrete_count || 0} host/repo · ${escapeHtml((p.reasons || []).slice(0, 3).join(", "))}</p>`;
    el.addEventListener("click", () => show(p));
    root.appendChild(el);
  }
}

function show(p) {
  document.getElementById("d-title").textContent = p.name;
  document.getElementById("d-meta").innerHTML = `<a href="${escapeHtml(p.url)}" target="_blank" rel="noreferrer">${escapeHtml(p.url)}</a>`;
  document.getElementById("d-reasons").textContent = (p.reasons || []).join(" · ");
  fillAssets("d-in", p.in_scope || []);
  fillAssets("d-out", p.out_of_scope || []);
  document.getElementById("detail").showModal();
}

function fillAssets(id, assets) {
  const ul = document.getElementById(id);
  ul.innerHTML = "";
  if (!assets.length) {
    ul.innerHTML = "<li>Không có</li>";
    return;
  }
  for (const a of assets) {
    const li = document.createElement("li");
    li.innerHTML = `${escapeHtml(a.identifier)} <span class="kind">${escapeHtml(a.kind || a.asset_type || "")}</span>`;
    ul.appendChild(li);
  }
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[ch]);
}

document.querySelectorAll(".tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.tab = btn.dataset.tab;
    renderChips();
    render();
  });
});
document.getElementById("q").addEventListener("input", (e) => {
  state.q = e.target.value;
  render();
});
document.getElementById("close").addEventListener("click", () => document.getElementById("detail").close());

load().catch(() => {
  document.getElementById("meta").textContent = "Chưa có data/feeds.json — chạy feed-bot trước.";
});
