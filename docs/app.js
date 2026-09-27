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
  currency: "",
  history: null,
  feeds: null,
  programs: [],
  saved: loadSaved(),
  openId: "",
  visible: 50,
  searchIndex: new Map(),
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
  let feeds, programs;
  for (let attempt = 0; attempt < 2; attempt++) {
    [feeds, programs] = await Promise.all([readJson("data/feeds.json"), readJson("data/programs.min.json")]);
    if (feeds.generated_at === programs.generated_at) break;
    if (attempt === 1) throw new Error("Dữ liệu đang cập nhật, vui lòng tải lại trang.");
  }
  state.feeds = feeds;
  state.programs = programs.programs || [];
  state.searchIndex = new Map(state.programs.map(p => [p.id,
    `${p.name} ${p.handle} ${p.id} ${p.summary_vi || p.summary || ""} ${(p.in_scope || []).map(a => a.identifier).join(" ")}`.toLowerCase()]));
  const counts = feeds.counts || countBy(state.programs);
  const parts = ORDER.filter((p) => counts[p])
    .map((p) => `${LABELS[p] || p} ${counts[p]}`)
    .concat(Object.keys(counts).filter((p) => !ORDER.includes(p)).map((p) => `${p} ${counts[p]}`));
  document.getElementById("meta").textContent =
    `Cập nhật ${feeds.generated_at || programs.generated_at || ""} · ${state.programs.length} program` +
    (parts.length ? ` · ${parts.join(" · ")}` : "");
  renderHealth();
  populateCurrencies();
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
    resetList();
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
      resetList();
    });
    root.appendChild(btn);
  }
}

function programsInFeedOrder(cards) {
  const byId = new Map(state.programs.map((p) => [p.id, p]));
  return (cards || []).map((card) => byId.get(card.id)).filter(Boolean);
}

function tabRows() {
  if (state.tab === "saved") return state.programs.filter((p) => state.saved[p.id]);
  if (state.tab === "all") return state.programs;
  if (state.tab === "recommended" && state.platform) {
    const grouped = (state.feeds && state.feeds.recommended_by_platform) || {};
    if (grouped[state.platform]) return programsInFeedOrder(grouped[state.platform]);
  }
  return programsInFeedOrder(state.feeds && state.feeds[state.tab]);
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
    if (state.currency && (p.currency || "").toUpperCase() !== state.currency) return false;
    if (state.minb !== "" && Number(state.minb) > 0) {
      if (!state.currency || !Number.isFinite(p.max_bounty) || p.max_bounty < Number(state.minb)) return false;
    }
    return true;
  });
}

function resetList() {
  state.visible = 50;
  render();
}

function render() {
  const q = state.q.toLowerCase();
  const rows = currentRows().filter((p) => {
    if (!q) return true;
    const blob = state.searchIndex.get(p.id) ||
      `${p.name} ${p.handle} ${p.id} ${p.summary_vi || p.summary || ""} ${(p.in_scope || []).map((a) => a.identifier).join(" ")}`.toLowerCase();
    return blob.includes(q);
  });
  const root = document.getElementById("list");
  root.innerHTML = "";
  document.getElementById("list-status").textContent = `Hiển thị ${Math.min(rows.length, state.visible)}/${rows.length} program khớp bộ lọc.`;
  if (!rows.length) {
    root.innerHTML = '<p class="empty">Không có program khớp bộ lọc.</p>';
    return;
  }
  for (const p of rows.slice(0, state.visible)) {
    const el = document.createElement("article");
    el.className = "card";
    el.tabIndex = 0;
    el.dataset.programId = p.id;
    el.setAttribute("role", "button");
    el.setAttribute("aria-label", `Xem ${p.name}`);
    const star = state.saved[p.id] ? "★" : "";
    const reward = rewardsOf(p).map((r) => REWARD_LABELS[r] || r).join(", ");
    el.innerHTML = `<h2>${escapeHtml(p.name)} <span class="score">Điểm dễ ${escapeHtml(p.easy_score ?? "")}/100</span> <span class="star">${star}</span></h2>
      <p>${escapeHtml(LABELS[p.platform] || p.platform)} · ${escapeHtml(reward)} · ${p.concrete_count || 0} host/repo · ${escapeHtml((p.reasons || []).slice(0, 3).join(", "))}</p>`;
    if (p.stale) {
      const badge = document.createElement("p");
      badge.className = "stale";
      badge.textContent = "Dữ liệu cũ · " + (p.last_seen || "chưa rõ thời điểm xác nhận");
      el.appendChild(badge);
    }
    el.addEventListener("click", () => show(p));
    el.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        show(p);
      }
    });
    root.appendChild(el);
  }
  if (state.visible < rows.length) {
    const more = document.createElement("button");
    more.type = "button";
    more.className = "more";
    more.textContent = `Xem thêm ${Math.min(50, rows.length - state.visible)} mục`;
    more.addEventListener("click", () => {
      const firstNew = state.visible;
      state.visible += 50;
      render();
      root.querySelectorAll?.(".card")[firstNew]?.focus?.();
    });
    root.appendChild(more);
  }
}

function show(p) {
  state.openId = p.id;
  document.getElementById("d-title").textContent = p.name;
  const policy = p.policy_url || p.url;
  const meta = document.getElementById("d-meta");
  meta.innerHTML = "";
  if (safeHttpUrl(p.url)) {
    const link = document.createElement("a");
    link.href = p.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = p.url;
    meta.appendChild(link);
  } else meta.textContent = "Link policy không hợp lệ.";
  const bits = [
    rewardsOf(p).map((r) => REWARD_LABELS[r] || r).join(", "),
    p.min_bounty != null || p.max_bounty != null
      ? `${p.min_bounty ?? "?"}–${p.max_bounty ?? "?"} ${p.currency || ""}`.trim()
      : "",
    kindsOf(p).join(", "),
    p.stale ? `Dữ liệu cũ · xác nhận lần cuối: ${p.last_seen || "chưa rõ"}` : "",
  ].filter(Boolean);
  document.getElementById("d-reward").textContent = bits.join(" · ");
  const contact = p.contact ? `Liên hệ: ${p.contact}` : "";
  const extra = policy && policy !== p.url ? `Policy: ${policy}` : "";
  document.getElementById("d-contact").textContent = [contact, extra].filter(Boolean).join(" · ");
  document.getElementById("d-summary").textContent = p.summary_vi ||
    (p.summary ? `Mô tả từ nguồn (chưa dịch): ${p.summary}` : "Chưa có mô tả trong nguồn tổng hợp. Hãy đọc policy gốc.");
  document.getElementById("d-reasons").textContent = (p.reasons || []).join(" · ");
  document.getElementById("d-note").value = (state.saved[p.id] && state.saved[p.id].note) || "";
  document.getElementById("save").textContent = state.saved[p.id] ? "Bỏ lưu" : "Lưu";
  fillAssets("d-in", p.in_scope || [], p.platform === "self-host");
  fillAssets("d-out", p.out_of_scope || [], p.platform === "self-host");
  document.getElementById("detail").showModal();
  showHistory(p.id);

}

function fillAssets(id, assets, fromDirectory = false) {
  const ul = document.getElementById(id);
  ul.innerHTML = "";
  if (!assets.length) {
    const li = document.createElement("li");
    li.textContent = fromDirectory ? "Nguồn tổng hợp chưa cung cấp scope; hãy kiểm tra policy gốc." : "Chưa có dữ liệu scope.";
    ul.appendChild(li);
    return;
  }
  for (const a of assets) {
    const li = document.createElement("li");
    li.innerHTML = `${escapeHtml(a.identifier)} <span class="kind">${escapeHtml(a.kind || a.asset_type || "")}</span>`;
    ul.appendChild(li);
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[ch]);
}

function safeHttpUrl(value) {
  try {
    const url = new URL(value);
    return (url.protocol === "https:" || url.protocol === "http:") && !!url.hostname;
  } catch { return false; }
}

function openProgram() {
  return state.programs.find((p) => p.id === state.openId);
}

document.querySelectorAll(".tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.tab = btn.dataset.tab;
    state.platform = "";
    renderChips();
    resetList();
  });
});
document.getElementById("q").addEventListener("input", (e) => {
  state.q = e.target.value;
  resetList();
});
document.getElementById("kind").addEventListener("change", (e) => {
  state.kind = e.target.value;
  resetList();
});
document.getElementById("reward").addEventListener("change", (e) => {
  state.reward = e.target.value;
  resetList();
});
document.getElementById("minb").addEventListener("input", (e) => {
  state.minb = e.target.value;
  resetList();
});
document.getElementById("close").addEventListener("click", () => document.getElementById("detail").close());
document.getElementById("detail").addEventListener("close", () => {
  [...document.querySelectorAll("#list article")].find(el => el.dataset.programId === state.openId)?.focus();
});
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
      resetList();
    }
  } catch {
    document.getElementById("meta").textContent = "Import JSON không hợp lệ.";
  }
  e.target.value = "";
});

load().catch((error) => {
  document.getElementById("meta").textContent = "Không tải được dữ liệu. " + error.message;
});


async function readJson(url) {
  const response = await fetch(url, { cache: "no-cache" });
  if (!response.ok) throw new Error("Không đọc được " + url);
  return response.json();
}

function populateCurrencies() {
  const root = document.getElementById("currency");
  root.innerHTML = '<option value="">Tất cả</option>';
  const currencies = new Set(["USD", ...state.programs.map(p => (p.currency || "").toUpperCase()).filter(Boolean)]);
  for (const currency of [...currencies].sort()) {
    const option = document.createElement("option");
    option.value = currency;
    option.textContent = currency;
    root.appendChild(option);
  }
  root.value = state.currency;
}

document.getElementById("currency").addEventListener("change", (event) => {
  state.currency = event.target.value;
  const input = document.getElementById("minb");
  input.disabled = !state.currency;
  if (!state.currency) { state.minb = ""; input.value = ""; }
  resetList();
});
document.querySelector("form.filters").addEventListener("submit", event => event.preventDefault());

function renderHealth() {
  const q = state.feeds.quality || {};
  document.getElementById("quality").textContent =
    `Dữ liệu cũ: ${q.stale_count || 0} · Bản ghi lỗi: ${q.rejected_count || 0} · Bỏ qua: ${q.skipped_count || 0} · Nguồn chưa đầy đủ: ${q.incomplete_sources || 0} · Thông báo chờ: ${q.pending_notifications || 0}`;
  const ai = q.llm || {};
  document.getElementById("ai-status").textContent = ai.configured
    ? `AI self-host: ${ai.ok || 0} đã xử lý · ${ai.skipped || 0} chờ · ${ai.error || 0} lỗi · lần này ${ai.used_this_run || 0}.`
    : "AI self-host: chưa cấu hình URL; dữ liệu chưa được AI bổ sung.";
  const root = document.getElementById("source-status");
  root.innerHTML = "";
  for (const source of state.feeds.source_status || []) {
    const li = document.createElement("li");
    const status = source.ok ? "Đầy đủ" : source.state === "partial" ? "Tải thiếu" : "Lỗi";
    li.textContent = `${LABELS[source.platform] || source.platform}: ${status} · ${source.count || 0} program · giữ dữ liệu cũ: ${source.retained_count || 0}` +
      (source.last_success_at ? ` · thành công gần nhất: ${source.last_success_at}` : "");
    if (source.error) li.textContent += ` · lý do: ${source.error}`;
    if (source.normalized_count > source.count)
      li.textContent += ` · gộp ${source.normalized_count - source.count} ID trùng`;
    const merge = (source.sources || []).find(s => s.source === "merge");
    if (merge) li.textContent += ` · đã gộp ${merge.deduplicated || 0} bản ghi trùng`;
    const limit = (source.sources || []).find(s => s.truncated);
    if (limit) li.textContent += ` · giới hạn đã bỏ qua ${limit.truncated} program`;
    const failures = (source.sources || []).filter(s => !s.ok).map(s => s.source);
    if (failures.length) li.textContent += " · nguồn con/slug lỗi: " + failures.join(", ");
    root.appendChild(li);
  }
}

let historyRequest = null;
async function loadHistory() {
  if (state.history) return state.history;
  if (!historyRequest) {
    historyRequest = readJson("data/history.json").then(data => {
      state.history = data.events || [];
      return state.history;
    }).finally(() => { historyRequest = null; });
  }
  return historyRequest;
}

const FIELD_LABELS = {status:"Trạng thái", offers_bounty:"Có thưởng", min_bounty:"Thưởng thấp nhất", max_bounty:"Thưởng cao nhất", currency:"Đơn vị", reward_types:"Loại thưởng", policy_url:"Policy", contact:"Liên hệ"};
function historyText(event) {
  const kinds = {added:"Program mới", removed:"Ngừng xuất hiện", scope_changes:"Scope đổi", program_changes:"Thông tin đổi"};
  const lines = [`${event.at} · ${event.name} · ${kinds[event.kind] || event.kind}`];
  const value = v => v === null || v === undefined ? "chưa rõ" : Array.isArray(v) ? v.join(", ") : String(v);
  for (const [key, change] of Object.entries(event.fields || {})) {
    lines.push(`${FIELD_LABELS[key] || key}: ${value(change.before)} → ${value(change.after)}`);
  }
  for (const [scope, change] of Object.entries(event.scopes || {})) {
    const label = scope === "in_scope" ? "Trong scope" : "Ngoài scope";
    if (change.added.length) lines.push(`${label} thêm: ${change.added.join(", ")}`);
    if (change.removed.length) lines.push(`${label} bỏ: ${change.removed.join(", ")}`);
    for (const item of change.updated) {
      const edits = Object.keys(item.after).filter(k => item.before[k] !== item.after[k]);
      const labels = {eligible_for_submission:"Nhận báo cáo", eligible_for_bounty:"Nhận thưởng", kind:"Loại asset", asset_type:"Loại nguồn"};
      lines.push(`${item.identifier}: ` + edits.map(k => `${labels[k] || k} ${value(item.before[k])} → ${value(item.after[k])}`).join("; "));
    }
  }
  return lines.join("\n");
}
function renderHistory(rootId, events) {
  const root = document.getElementById(rootId);
  root.innerHTML = "";
  for (const event of events.slice(-100).reverse()) {
    const li = document.createElement("li");
    li.textContent = historyText(event);
    root.appendChild(li);
  }
}
async function showHistory(id) {
  document.getElementById("d-history").innerHTML = "";
  document.getElementById("d-history-status").textContent = "Đang tải lịch sử…";
  try {
    const events = (await loadHistory()).filter(e => e.id === id);
    if (state.openId !== id) return;
    document.getElementById("d-history-status").textContent = events.length ? `${events.length} thay đổi · hiển thị tối đa 100 mục gần nhất.` : "Chưa có thay đổi được ghi nhận.";
    renderHistory("d-history", events);
  } catch {
    if (state.openId === id) document.getElementById("d-history-status").textContent = "Chưa tải được lịch sử. Đóng và mở lại để thử lại.";
  }
}
document.getElementById("load-history").addEventListener("click", async () => {
  const status = document.getElementById("history-status");
  status.textContent = "Đang tải lịch sử…";
  try {
    const events = await loadHistory();
    renderHistory("recent-history", events);
    status.textContent = `${events.length} thay đổi · hiển thị tối đa 100 mục gần nhất.`;
  } catch { status.textContent = "Không tải được lịch sử. Bấm để thử lại."; }
});
