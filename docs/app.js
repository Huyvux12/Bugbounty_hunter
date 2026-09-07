const LABELS = {
  hackerone: "HackerOne",
  bugcrowd: "Bugcrowd",
  intigriti: "Intigriti",
  yeswehack: "YesWeHack",
  federacy: "Federacy",
  hackenproof: "HackenProof",
  "self-host": "Self-host",
};
const REWARD_LABELS = {
  cash: "tiền",
  crypto: "crypto",
  swag: "swag",
  hall_of_fame: "hall of fame",
  none: "VDP",
  unknown: "chưa rõ",
};
const ORDER = ["hackerone", "bugcrowd", "intigriti", "yeswehack", "federacy", "hackenproof", "self-host"];
const STORE_KEY = "bbh-saved-v1";

const state = {
  tab: "recommended",
  q: "",
  platform: "",
  kind: "",
  reward: "",
  minb: "",
  feeds: null,
  programs: [],
  saved: loadSaved(),
  openId: "",
};

function loadSaved() {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY) || "{}") || {};
  } catch {
    return {};
  }
}

function persistSaved() {
  localStorage.setItem(STORE_KEY, JSON.stringify(state.saved));
}

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
  if (state.tab === "saved") {
    return state.programs.filter((p) => state.saved[p.id] && p.platform === platform).length;
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
  if (state.tab === "saved") return state.programs.filter((p) => state.saved[p.id]);
  if (state.tab === "all") return state.programs;
  if (state.tab === "recommended" && state.platform) {
    const grouped = (state.feeds && state.feeds.recommended_by_platform) || {};
    const ids = new Set((grouped[state.platform] || []).map((c) => c.id));
    if (ids.size) return state.programs.filter((p) => ids.has(p.id));
  }
  const ids = new Set(((state.feeds && state.feeds[state.tab]) || []).map((c) => c.id));
  return state.programs.filter((p) => ids.has(p.id));
}

function kindsOf(p) {
  if (p.scope_kinds && p.scope_kinds.length) return p.scope_kinds;
  return (p.in_scope || []).map((a) => a.kind).filter(Boolean);
}

function rewardsOf(p) {
  if (p.reward_types && p.reward_types.length) return p.reward_types;
  return p.offers_bounty ? ["cash"] : ["unknown"];
}

function currentRows() {
  return tabRows().filter((p) => {
    if (state.platform && p.platform !== state.platform) return false;
    if (state.kind && !kindsOf(p).includes(state.kind)) return false;
    if (state.reward && !rewardsOf(p).includes(state.reward)) return false;
    if (state.minb !== "" && Number(state.minb) > 0) {
      const max = p.max_bounty == null ? p.min_bounty : p.max_bounty;
      if (max == null || Number(max) < Number(state.minb)) return false;
    }
    return true;
  });
}

function render() {
  const q = state.q.toLowerCase();
  const rows = currentRows().filter((p) => {
    if (!q) return true;
    const blob = `${p.name} ${p.handle} ${p.id} ${p.summary_vi || ""} ${(p.in_scope || []).map((a) => a.identifier).join(" ")}`.toLowerCase();
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
    const star = state.saved[p.id] ? "★" : "";
    const reward = rewardsOf(p).map((r) => REWARD_LABELS[r] || r).join(", ");
    el.innerHTML = `<h2>${escapeHtml(p.name)} <span class="score">${escapeHtml(p.easy_score ?? "")}</span> <span class="star">${star}</span></h2>
      <p>${escapeHtml(LABELS[p.platform] || p.platform)} · ${escapeHtml(reward)} · ${p.concrete_count || 0} host/repo · ${escapeHtml((p.reasons || []).slice(0, 3).join(", "))}</p>`;
    el.addEventListener("click", () => show(p));
    root.appendChild(el);
  }
}

function show(p) {
  state.openId = p.id;
  document.getElementById("d-title").textContent = p.name;
  const policy = p.policy_url || p.url;
  document.getElementById("d-meta").innerHTML = `<a href="${escapeHtml(p.url)}" target="_blank" rel="noreferrer">${escapeHtml(p.url)}</a>`;
  const bits = [
    rewardsOf(p).map((r) => REWARD_LABELS[r] || r).join(", "),
    p.min_bounty != null || p.max_bounty != null
      ? `${p.min_bounty ?? "?"}–${p.max_bounty ?? "?"} ${p.currency || ""}`.trim()
      : "",
    kindsOf(p).join(", "),
  ].filter(Boolean);
  document.getElementById("d-reward").textContent = bits.join(" · ");
  const contact = p.contact ? `Liên hệ: ${p.contact}` : "";
  const extra = policy && policy !== p.url ? `Policy: ${policy}` : "";
  document.getElementById("d-contact").textContent = [contact, extra].filter(Boolean).join(" · ");
  document.getElementById("d-summary").textContent = p.summary_vi || "";
  document.getElementById("d-reasons").textContent = (p.reasons || []).join(" · ");
  document.getElementById("d-note").value = (state.saved[p.id] && state.saved[p.id].note) || "";
  document.getElementById("save").textContent = state.saved[p.id] ? "Bỏ lưu" : "Lưu";
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

function openProgram() {
  return state.programs.find((p) => p.id === state.openId);
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
document.getElementById("kind").addEventListener("change", (e) => {
  state.kind = e.target.value;
  render();
});
document.getElementById("reward").addEventListener("change", (e) => {
  state.reward = e.target.value;
  render();
});
document.getElementById("minb").addEventListener("input", (e) => {
  state.minb = e.target.value;
  render();
});
document.getElementById("close").addEventListener("click", () => document.getElementById("detail").close());
document.getElementById("save").addEventListener("click", () => {
  const p = openProgram();
  if (!p) return;
  if (state.saved[p.id]) delete state.saved[p.id];
  else state.saved[p.id] = { note: document.getElementById("d-note").value, saved_at: new Date().toISOString() };
  persistSaved();
  document.getElementById("save").textContent = state.saved[p.id] ? "Bỏ lưu" : "Lưu";
  renderChips();
  render();
});
document.getElementById("d-note").addEventListener("input", (e) => {
  const p = openProgram();
  if (!p) return;
  if (!state.saved[p.id]) state.saved[p.id] = { saved_at: new Date().toISOString() };
  state.saved[p.id].note = e.target.value;
  persistSaved();
  document.getElementById("save").textContent = "Bỏ lưu";
});
document.getElementById("export").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(state.saved, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "bugbounty-saved.json";
  a.click();
  URL.revokeObjectURL(a.href);
});
document.getElementById("import").addEventListener("change", async (e) => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  try {
    const parsed = JSON.parse(await file.text());
    if (parsed && typeof parsed === "object") {
      state.saved = { ...state.saved, ...parsed };
      persistSaved();
      renderChips();
      render();
    }
  } catch {
    document.getElementById("meta").textContent = "Import JSON không hợp lệ.";
  }
  e.target.value = "";
});

load().catch(() => {
  document.getElementById("meta").textContent = "Chưa có data/feeds.json — chạy feed-bot trước.";
});
