const LABELS = {
  hackerone: "HackerOne",
  bugcrowd: "Bugcrowd",
  intigriti: "Intigriti",
  yeswehack: "YesWeHack",
  "self-host": "Self-host",
};
const REWARD_LABELS = {
  cash: "Tiền thưởng",
  crypto: "Crypto",
  swag: "Swag",
  hall_of_fame: "Hall of fame",
  none: "VDP",
  unknown: "Chưa rõ thưởng",
};
const ORDER = ["hackerone", "bugcrowd", "intigriti", "yeswehack", "self-host"];
const TITLES = {
  recommended: "Đề xuất cho bạn",
  easy: "Dễ tiếp cận",
  new: "Mới cập nhật",
  all: "Tất cả chương trình",
  saved: "Bộ sưu tập của bạn",
};
const STORE_KEY = "bbh-saved-v1";
const MAX_IMPORT_BYTES = 2 * 1024 * 1024;
let recoveryRaw = null,
  storageWarning = "",
  toastTimer,
  searchTimer,
  pendingImport = null,
  historyRequest = null;
const state = {
  tab: "recommended",
  q: "",
  platform: "",
  kind: "",
  reward: "",
  minb: "",
  currency: "",
  sort: "rank",
  history: null,
  feeds: null,
  programs: [],
  saved: loadSaved(),
  openId: "",
  visible: 50,
  searchIndex: new Map(),
  base: "",
  snapshotId: "",
  details: new Map(),
  loading: false,
};
const $ = (id) => document.getElementById(id);

function normalizeSaved(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw))
    throw new Error("Bản sao phải là một object JSON.");
  const items = Object.hasOwn(raw, "version")
    ? raw.version === 1
      ? raw.items
      : null
    : raw;
  if (
    !items ||
    typeof items !== "object" ||
    Array.isArray(items) ||
    Object.keys(items).length > 5000
  )
    throw new Error("Định dạng bản sao không được hỗ trợ hoặc quá 5.000 mục.");
  const result = {};
  for (const [id, entry] of Object.entries(items)) {
    if (
      !id ||
      id.length > 300 ||
      ["__proto__", "constructor", "prototype"].includes(id) ||
      !entry ||
      typeof entry !== "object" ||
      Array.isArray(entry)
    )
      throw new Error("Mục đã lưu không hợp lệ.");
    if (
      entry.note !== undefined &&
      (typeof entry.note !== "string" || entry.note.length > 20000)
    )
      throw new Error("Ghi chú phải là văn bản, tối đa 20.000 ký tự.");
    const clean = { note: entry.note || "" };
    if (
      typeof entry.saved_at === "string" &&
      entry.saved_at.length < 50 &&
      Number.isFinite(Date.parse(entry.saved_at))
    )
      clean.saved_at = entry.saved_at;
    if (
      entry.program &&
      typeof entry.program === "object" &&
      !Array.isArray(entry.program)
    ) {
      clean.program = {};
      for (const key of ["id", "name", "platform", "handle", "url"])
        if (typeof entry.program[key] === "string")
          clean.program[key] = entry.program[key].slice(0, 1000);
      clean.program.id = id;
    }
    result[id] = clean;
  }
  return result;
}
function loadSaved() {
  let raw = null;
  try {
    raw = localStorage.getItem(STORE_KEY);
    const saved = normalizeSaved(JSON.parse(raw || "{}"));
    recoveryRaw = null;
    storageWarning = "";
    return saved;
  } catch {
    recoveryRaw = raw;
    storageWarning =
      "Không đọc được bản lưu trên thiết bị. Bản gốc sẽ được giữ riêng trước khi lưu thay đổi mới.";
    return {};
  }
}
function persistSaved() {
  try {
    if (recoveryRaw !== null) {
      localStorage.setItem(STORE_KEY + ".recovery", recoveryRaw);
      recoveryRaw = null;
    }
    localStorage.setItem(STORE_KEY, JSON.stringify(state.saved));
    storageWarning = "";
    $("storage-status").textContent = "";
    return true;
  } catch {
    storageWarning =
      "Chưa lưu được trên thiết bị (bộ nhớ đầy hoặc bị chặn). Ghi chú còn trong phiên này; hãy xuất bản sao trước khi đóng trang.";
    $("storage-status").textContent = storageWarning;
    return false;
  }
}
function notify(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    $("toast").hidden = true;
  }, 4500);
}
function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
}
function safeHttpUrl(value) {
  try {
    const u = new URL(value);
    return ["https:", "http:"].includes(u.protocol) && !!u.hostname;
  } catch {
    return false;
  }
}
function formatDate(value) {
  const d = new Date(value);
  return value && Number.isFinite(+d)
    ? new Intl.DateTimeFormat("vi-VN", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(d)
    : "Chưa rõ";
}
function countBy(rows) {
  const counts = {};
  for (const p of rows) counts[p.platform] = (counts[p.platform] || 0) + 1;
  return counts;
}
function kindsOf(p) {
  return p.scope_kinds?.length
    ? p.scope_kinds
    : [...new Set((p.in_scope || []).map((a) => a.kind).filter(Boolean))];
}
function rewardsOf(p) {
  return p.reward_types?.length
    ? p.reward_types
    : p.offers_bounty
      ? ["cash"]
      : ["unknown"];
}
function rewardText(p) {
  const n = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 4 });
  if (Number.isFinite(p.max_bounty))
    return `Tối đa ${n.format(p.max_bounty)} ${p.currency || ""}`.trim();
  if (Number.isFinite(p.min_bounty))
    return `Từ ${n.format(p.min_bounty)} ${p.currency || ""}`.trim();
  return rewardsOf(p)
    .map((r) => REWARD_LABELS[r] || r)
    .join(" · ");
}
async function readJson(url, cache = "no-cache") {
  const response = await fetch(url, {
    cache,
    signal: AbortSignal.timeout(20000),
  });
  if (!response.ok) {
    const error = new Error(
      `Không đọc được dữ liệu (HTTP ${response.status}).`,
    );
    error.status = response.status;
    throw error;
  }
  return response.json();
}
async function readSnapshot() {
  let manifest;
  try {
    manifest = await readJson("data/manifest.json");
  } catch (error) {
    if (error.status !== 404) throw error;
  }
  if (manifest) {
    if (
      manifest.schema_version !== 1 ||
      !/^[a-f0-9]{24}$/.test(manifest.snapshot_id) ||
      manifest.base !== `data/snapshots/${manifest.snapshot_id}/`
    )
      throw new Error("Phiên bản snapshot không hợp lệ.");
    const [feeds, programs] = await Promise.all([
      readJson(manifest.base + "feeds.json", "force-cache"),
      readJson(manifest.base + "index.json", "force-cache"),
    ]);
    if (
      [feeds, programs].some(
        (x) => x.schema_version !== 1 || x.snapshot_id !== manifest.snapshot_id,
      ) ||
      !Array.isArray(programs.programs)
    )
      throw new Error("Snapshot chưa nhất quán. Hãy thử tải lại.");
    return {
      feeds,
      programs,
      base: manifest.base,
      snapshotId: manifest.snapshot_id,
    };
  }
  for (let i = 0; i < 2; i++) {
    const [feeds, programs] = await Promise.all([
      readJson("data/feeds.json"),
      readJson("data/programs.min.json"),
    ]);
    if (feeds.generated_at === programs.generated_at)
      return { feeds, programs, base: "data/", snapshotId: "" };
  }
  throw new Error("Dữ liệu đang cập nhật. Hãy thử tải lại.");
}
async function load() {
  if (state.loading) return;
  state.loading = true;
  $("load-error").hidden = true;
  $("list").setAttribute("aria-busy", "true");
  $("retry").disabled = true;
  try {
    const loaded = await readSnapshot();
    Object.assign(state, {
      feeds: loaded.feeds,
      programs: loaded.programs.programs || [],
      base: loaded.base,
      snapshotId: loaded.snapshotId,
      history: null,
      details: new Map(),
    });
    historyRequest = null;
    state.searchIndex = new Map(
      state.programs.map((p) => [
        p.id,
        `${p.name} ${p.handle} ${p.id} ${p.summary_vi || p.summary || p.summary_excerpt || ""} ${p.search_text || ""} ${(p.in_scope || []).map((a) => a.identifier).join(" ")}`.toLocaleLowerCase(
          "vi",
        ),
      ]),
    );
    $("meta").textContent = `Cập nhật ${formatDate(state.feeds.generated_at)}`;
    $("stat-total").textContent = state.programs.length.toLocaleString("vi-VN");
    $("stat-easy").textContent = state.programs
      .filter(
        (p) =>
          !p.stale &&
          ["open", "live", "active", ""].includes(p.status || "") &&
          p.concrete_count > 0 &&
          p.easy_score >= 50,
      )
      .length.toLocaleString("vi-VN");
    renderHealth();
    populateCurrencies();
    readUrl();
    syncControls();
    renderChips();
    render();
    if (state.openId) {
      const p = allSavedRows().find((p) => p.id === state.openId);
      if (p) await show(p, false);
      else notify("Program trong liên kết không còn trong snapshot.");
    }
  } catch (error) {
    $("error-text").textContent =
      "Không tải được chương trình. " + error.message;
    $("load-error").hidden = false;
    if (!state.feeds) {
      $("list").innerHTML = "";
      $("list-status").textContent = "Chưa có dữ liệu để hiển thị.";
    }
  } finally {
    state.loading = false;
    $("list").setAttribute("aria-busy", "false");
    $("retry").disabled = false;
  }
}
function allSavedRows() {
  const rows = [...state.programs],
    present = new Set(rows.map((p) => p.id));
  for (const [id, entry] of Object.entries(state.saved))
    if (!present.has(id))
      rows.push({
        ...entry.program,
        id,
        name: entry.program?.name || id,
        platform: entry.program?.platform || id.split(":")[0],
        unavailable: true,
        stale: true,
      });
  return rows;
}
function programsInFeedOrder(cards) {
  const byId = new Map(state.programs.map((p) => [p.id, p]));
  return (cards || []).map((c) => byId.get(c.id)).filter(Boolean);
}
function tabRows() {
  if (state.tab === "saved")
    return allSavedRows().filter((p) => state.saved[p.id]);
  if (state.tab === "all") return state.programs;
  if (state.tab === "recommended" && state.platform) {
    const grouped = state.feeds?.recommended_by_platform || {};
    if (grouped[state.platform])
      return programsInFeedOrder(grouped[state.platform]);
  }
  return programsInFeedOrder(state.feeds?.[state.tab]);
}
function platformIds() {
  const present = new Set(
    (state.tab === "saved"
      ? allSavedRows().filter((p) => state.saved[p.id])
      : state.programs
    ).map((p) => p.platform),
  );
  return ORDER.filter((p) => present.has(p)).concat(
    [...present].filter((p) => !ORDER.includes(p)).sort(),
  );
}
function chipCount(platform) {
  if (
    state.tab === "recommended" &&
    state.feeds?.recommended_by_platform?.[platform]
  )
    return state.feeds.recommended_by_platform[platform].length;
  return (
    state.tab === "saved"
      ? allSavedRows().filter((p) => state.saved[p.id])
      : tabRows()
  ).filter((p) => p.platform === platform).length;
}
function renderChips() {
  const root = $("platforms");
  root.innerHTML = "";
  for (const platform of ["", ...platformIds()]) {
    const n = platform ? chipCount(platform) : null;
    if (platform && !n && state.tab !== "all") continue;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = platform
      ? `${LABELS[platform] || platform} (${n})`
      : "Tất cả nền tảng";
    btn.className = state.platform === platform ? "active" : "";
    btn.setAttribute("aria-pressed", String(state.platform === platform));
    btn.addEventListener("click", () => {
      state.platform = platform;
      changed();
    });
    root.appendChild(btn);
  }
}
function currentRows() {
  return tabRows().filter((p) => {
    if (state.platform && p.platform !== state.platform) return false;
    if (state.kind && !kindsOf(p).includes(state.kind)) return false;
    if (state.reward && !rewardsOf(p).includes(state.reward)) return false;
    if (state.currency && (p.currency || "").toUpperCase() !== state.currency)
      return false;
    if (
      state.minb !== "" &&
      Number(state.minb) > 0 &&
      (!state.currency ||
        !Number.isFinite(p.max_bounty) ||
        p.max_bounty < Number(state.minb))
    )
      return false;
    return true;
  });
}
function resetList() {
  state.visible = 50;
  render();
}
function render() {
  const q = state.q.trim().toLocaleLowerCase("vi");
  let rows = currentRows().filter(
    (p) =>
      !q ||
      (
        state.searchIndex.get(p.id) ||
        `${p.name} ${p.handle || ""} ${p.id} ${p.summary_vi || p.summary || ""} ${(p.in_scope || []).map((a) => a.identifier).join(" ")}`.toLocaleLowerCase(
          "vi",
        )
      ).includes(q) ||
      String(state.saved[p.id]?.note || "")
        .toLocaleLowerCase("vi")
        .includes(q),
  );
  if (state.sort === "name")
    rows.sort((a, b) => (a.name || "").localeCompare(b.name || "", "vi"));
  if (state.sort === "score")
    rows.sort((a, b) => (b.easy_score || 0) - (a.easy_score || 0));
  if (state.sort === "updated")
    rows.sort((a, b) => (b.last_seen || "").localeCompare(a.last_seen || ""));
  if (state.sort === "bounty" && state.currency)
    rows.sort((a, b) => (b.max_bounty ?? -1) - (a.max_bounty ?? -1));
  const root = $("list");
  root.innerHTML = "";
  $("list-status").textContent =
    `Hiển thị ${Math.min(rows.length, state.visible)}/${rows.length} program khớp bộ lọc.`;
  $("section-title").textContent = TITLES[state.tab];
  const filters = [
    state.q,
    state.platform,
    state.kind,
    state.reward,
    state.currency,
    state.minb,
  ].filter(Boolean).length;
  $("active-filters").textContent = filters
    ? `${filters} bộ lọc đang áp dụng`
    : "";
  updateSavedCount();
  if (!rows.length) {
    const box = document.createElement("div");
    box.className = "empty";
    box.innerHTML =
      state.tab === "saved" && !Object.keys(state.saved).length
        ? "<strong>Những mục tiêu đáng để quay lại.</strong><p>Lưu program hoặc viết ghi chú để bắt đầu bộ sưu tập của bạn.</p>"
        : "<strong>Chưa có program phù hợp.</strong><p>Thử tên khác hoặc mở rộng bộ lọc.</p>";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "Xóa bộ lọc";
    btn.addEventListener("click", resetFilters);
    box.appendChild(btn);
    root.appendChild(box);
    return;
  }
  for (const p of rows.slice(0, state.visible)) {
    const el = document.createElement("article");
    el.className = "card";
    el.dataset.programId = p.id;
    el.tabIndex = -1;
    el.setAttribute("aria-label", `Xem ${p.name}`);
    const icon = (LABELS[p.platform] || p.platform || "?")
      .slice(0, 2)
      .toUpperCase();
    const tags = [
      ...kindsOf(p)
        .slice(0, 3)
        .map((k) => `<span class="tag">${escapeHtml(k)}</span>`),
      `<span class="tag">${p.concrete_count || 0} asset cụ thể</span>`,
    ];
    const summary = p.unavailable
      ? "Không còn trong feed hiện tại. Ghi chú của bạn vẫn được giữ lại."
      : p.summary_excerpt ||
        p.summary_vi ||
        p.summary ||
        (p.reasons || []).slice(0, 2).join(" · ") ||
        "Đọc policy gốc để tìm hiểu chương trình.";
    el.innerHTML = `<div class="platform-icon" data-platform="${escapeHtml(p.platform)}" aria-hidden="true">${escapeHtml(icon)}</div><div class="card-main"><h2><button class="open-program" type="button" aria-label="Xem ${escapeHtml(p.name)}">${escapeHtml(p.name)}</button></h2><span class="card-platform">${escapeHtml(LABELS[p.platform] || p.platform)}</span><p class="card-summary">${escapeHtml(summary)}</p><div class="card-tags">${tags.join("")}</div>${p.stale ? `<p class="stale">${p.unavailable ? "Đã rời feed" : "Dữ liệu cũ · " + escapeHtml(formatDate(p.last_seen))}</p>` : ""}</div><div class="card-right"><div class="card-reward">${escapeHtml(rewardText(p))}<small>${p.currency ? "Theo đơn vị nguồn công bố" : "Chi tiết trong policy gốc"}</small></div><div class="card-bottom"><span class="score" title="Điểm heuristic dựa trên metadata, không phải xác suất tìm lỗi">Tiếp cận ${p.easy_score ?? "—"}/100</span></div></div>`;
    const star = document.createElement("button");
    star.className = "bookmark";
    star.type = "button";
    star.textContent = state.saved[p.id] ? "★" : "☆";
    star.setAttribute(
      "aria-label",
      `${state.saved[p.id] ? "Bỏ lưu" : "Lưu"} ${p.name}`,
    );
    star.setAttribute("aria-pressed", String(!!state.saved[p.id]));
    star.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleSaved(p);
      [...root.querySelectorAll(".bookmark")]
        .find((b) => b.closest(".card")?.dataset.programId === p.id)
        ?.focus();
    });
    // Separate button semantics from the article: keyboard activation on a child
    // must not also activate the detail panel.
    el.querySelector?.(".card-bottom")?.appendChild(star);
    el.addEventListener("click", () => show(p));
    el.addEventListener("keydown", (e) => {
      if (e.target !== el) return;
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
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
      const first = state.visible;
      state.visible += 50;
      render();
      $("list").querySelectorAll?.(".card")[first]?.focus();
    });
    root.appendChild(more);
  }
}
function savedEntry(p, note = "") {
  const program = {};
  for (const k of ["id", "name", "platform", "handle", "url"])
    if (typeof p[k] === "string") program[k] = p[k];
  return { note, saved_at: new Date().toISOString(), program };
}
function updateSavedCount() {
  const count = Object.keys(state.saved).length;
  $("saved-count").textContent = count;
  $("stat-saved").textContent = count;
}
function syncSaveButton() {
  $("save").textContent = state.saved[state.openId]
    ? "Bỏ lưu chương trình"
    : "Lưu chương trình";
  $("save").setAttribute("aria-pressed", String(!!state.saved[state.openId]));
}
function toggleSaved(p) {
  if (state.saved[p.id]) {
    if (
      state.saved[p.id].note &&
      typeof window !== "undefined" &&
      !window.confirm("Bỏ lưu sẽ xóa ghi chú của program này. Tiếp tục?")
    )
      return;
    delete state.saved[p.id];
  } else
    state.saved[p.id] = savedEntry(
      p,
      p.id === state.openId ? $("d-note").value : "",
    );
  const ok = persistSaved();
  syncSaveButton();
  renderChips();
  render();
  notify(ok ? "Đã cập nhật bộ sưu tập." : storageWarning);
}
function openProgram() {
  return allSavedRows().find((p) => p.id === state.openId);
}
async function detailFor(p) {
  if (!p.detail_bucket || p.unavailable) return p;
  const bucket = p.detail_bucket;
  if (!state.details.has(bucket)) {
    const promise = readJson(
      state.base + `details/${bucket}.json`,
      "force-cache",
    )
      .then((data) => {
        if (data.schema_version !== 1 || data.snapshot_id !== state.snapshotId)
          throw new Error("Chi tiết thuộc snapshot khác.");
        return data.programs;
      })
      .catch((error) => {
        state.details.delete(bucket);
        throw error;
      });
    state.details.set(bucket, promise);
  }
  const programs = await state.details.get(bucket);
  if (!programs[p.id]) throw new Error("Chưa có chi tiết cho program này.");
  return programs[p.id];
}
async function show(p, updateUrl = true) {
  state.openId = p.id;
  $("detail").dataset.programId = p.id;
  if (updateUrl) writeUrl();
  $("d-title").textContent = p.name;
  $("d-platform").textContent = LABELS[p.platform] || p.platform;
  $("d-note").value = state.saved[p.id]?.note || "";
  $("note-status").textContent = storageWarning;
  syncSaveButton();
  $("d-in").innerHTML = "";
  $("d-out").innerHTML = "";
  $("retry-detail").hidden = true;
  $("copy-assets").disabled = true;
  paintDetail(p);
  if (!$("detail").open) $("detail").showModal();
  showHistory(p.id);
  if (p.detail_bucket) {
    $("d-in").textContent = "Đang tải scope…";
    $("d-out").textContent = "Đang tải scope…";
  }
  try {
    const full = await detailFor(p);
    if (state.openId !== p.id) return;
    paintDetail(full);
    $("copy-assets").disabled = !(full.in_scope || []).length;
    $("copy-assets").dataset.assets = JSON.stringify(
      (full.in_scope || []).map((a) => a.identifier),
    );
  } catch {
    if (state.openId !== p.id) return;
    $("d-in").textContent =
      "Chưa tải được scope. Hãy thử lại hoặc đọc policy gốc.";
    $("d-out").textContent = "Chưa tải được scope.";
    if (state.openId === p.id) $("retry-detail").hidden = false;
  }
}
function paintDetail(p) {
  const meta = $("d-meta");
  meta.innerHTML = "";
  const url = p.policy_url || p.url;
  if (safeHttpUrl(url)) {
    const a = document.createElement("a");
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = "Đọc policy gốc ↗";
    meta.appendChild(a);
  } else meta.textContent = "Chưa có liên kết policy hợp lệ.";
  $("d-reward").textContent = rewardText(p);
  $("d-contact").textContent = p.contact ? `Liên hệ: ${p.contact}` : "";
  $("d-summary").textContent = p.unavailable
    ? "Program không còn trong feed. Bạn vẫn có thể đọc, sửa và xuất ghi chú."
    : p.summary_vi ||
      p.summary ||
      p.summary_excerpt ||
      "Chưa có mô tả từ nguồn tổng hợp. Hãy đọc policy gốc.";
  $("d-reasons").textContent = [
    ...(p.reasons || []),
    p.stale
      ? "Dữ liệu cũ · " + formatDate(p.last_seen)
      : "Điểm tiếp cận là heuristic từ metadata, không phải xác suất tìm được lỗi.",
  ].join(" · ");
  fillAssets("d-in", p.in_scope || [], p.platform === "self-host");
  fillAssets("d-out", p.out_of_scope || [], p.platform === "self-host");
}
function fillAssets(id, assets, fromDirectory = false) {
  const root = $(id);
  root.innerHTML = "";
  if (!assets.length) {
    const li = document.createElement("li");
    li.textContent = fromDirectory
      ? "Nguồn tổng hợp chưa cung cấp scope; hãy kiểm tra policy gốc."
      : "Chưa có dữ liệu scope.";
    root.appendChild(li);
    return;
  }
  for (const a of assets) {
    const li = document.createElement("li");
    li.innerHTML = `${escapeHtml(a.identifier)}<span class="kind">${escapeHtml(a.kind || a.asset_type || "")}${a.eligible_for_bounty === false ? " · Không nhận bounty" : ""}${a.eligible_for_submission === false ? " · Không nhận báo cáo" : ""}</span>`;
    root.appendChild(li);
  }
}
function populateCurrencies() {
  const root = $("currency");
  root.innerHTML = '<option value="">Tất cả đơn vị</option>';
  for (const currency of [
    ...new Set(
      state.programs
        .map((p) => (p.currency || "").toUpperCase())
        .filter(Boolean),
    ),
  ].sort()) {
    const o = document.createElement("option");
    o.value = currency;
    o.textContent = currency;
    root.appendChild(o);
  }
}
function syncControls() {
  for (const key of ["q", "kind", "reward", "currency", "minb", "sort"])
    $(key).value = state[key];
  $("minb").disabled = !state.currency;
  document.querySelectorAll(".tabs button").forEach((btn) => {
    btn.classList.toggle("active", state.tab === btn.dataset.tab);
    btn.setAttribute("aria-pressed", String(state.tab === btn.dataset.tab));
  });
}
function writeUrl(replace = false) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  for (const k of [
    "tab",
    "q",
    "platform",
    "kind",
    "reward",
    "currency",
    "minb",
    "sort",
  ]) {
    if (state[k] && state[k] !== { tab: "recommended", sort: "rank" }[k])
      url.searchParams.set(k, state[k]);
    else url.searchParams.delete(k);
  }
  if (state.openId) url.searchParams.set("program", state.openId);
  else url.searchParams.delete("program");
  if (url.href !== window.location.href)
    window.history[replace ? "replaceState" : "pushState"]({}, "", url);
}
function readUrl() {
  if (typeof window === "undefined") return;
  const p = new URL(window.location.href).searchParams;
  state.tab = Object.hasOwn(TITLES, p.get("tab"))
    ? p.get("tab")
    : "recommended";
  state.q = (p.get("q") || "").slice(0, 300);
  state.platform = (p.get("platform") || "").slice(0, 100);
  for (const k of ["kind", "reward", "currency"]) {
    const raw = p.get(k) || "";
    state[k] = [...$(k).options].some((o) => o.value === raw) ? raw : "";
  }
  state.minb =
    state.currency &&
    p.get("minb") !== null &&
    Number.isFinite(Number(p.get("minb"))) &&
    Number(p.get("minb")) >= 0
      ? p.get("minb")
      : "";
  state.sort = ["rank", "name", "score", "updated", "bounty"].includes(
    p.get("sort"),
  )
    ? p.get("sort")
    : "rank";
  state.openId = (p.get("program") || "").slice(0, 300);
}
function changed() {
  syncControls();
  writeUrl();
  renderChips();
  resetList();
}
function resetFilters() {
  Object.assign(state, {
    q: "",
    platform: "",
    kind: "",
    reward: "",
    minb: "",
    currency: "",
    sort: "rank",
  });
  changed();
}
function filterDrawer(open) {
  $("filter-panel").classList.toggle("open", open);
  document.body.classList.toggle("filters-open", open);
  $("filter-toggle").setAttribute("aria-expanded", String(open));
  if (open) {
    $("filter-panel").setAttribute("role", "dialog");
    $("filter-panel").setAttribute("aria-modal", "true");
    $("filter-panel").setAttribute("aria-label", "Bộ lọc chương trình");
    $("filter-close").focus();
  } else {
    for (const a of ["role", "aria-modal", "aria-label"])
      $("filter-panel").removeAttribute(a);
    $("filter-toggle").focus();
  }
}
function renderHealth() {
  const q = state.feeds.quality || {},
    sources = (state.feeds.source_status || []).filter(
      (s) => s.platform !== "llm",
    );
  const ok = sources.filter((s) => s.ok).length;
  $("stat-sources").textContent = `${ok}/${sources.length}`;
  $("stat-health").textContent =
    ok === sources.length ? "Nguồn đang đầy đủ" : "Có nguồn cần kiểm tra";
  document.querySelector(".health-dot").style.background =
    ok === sources.length ? "var(--green)" : "var(--orange)";
  $("quality").textContent =
    `Dữ liệu cũ: ${q.stale_count ?? "chưa rõ"} · Bản ghi lỗi: ${q.rejected_count ?? "chưa rõ"} · Nguồn chưa đầy đủ: ${q.incomplete_sources ?? "chưa rõ"} · Thông báo chờ: ${q.pending_notifications ?? "chưa rõ"}`;
  const ai = q.llm || {};
  $("ai-status").textContent = ai.configured
    ? `AI self-host: ${ai.ok || 0} đã xử lý · ${ai.skipped || 0} chờ · ${ai.error || 0} lỗi.`
    : "Mô tả hiển thị từ nguồn tổng hợp; AI bổ sung chưa bật.";
  $("source-status").innerHTML = "";
  for (const source of sources) {
    const li = document.createElement("li");
    li.textContent = `${LABELS[source.platform] || source.platform}: ${source.ok ? "Đầy đủ" : source.state === "partial" ? "Tải thiếu" : "Lỗi"} · ${source.count || 0} program · giữ ${source.retained_count || 0} bản cũ · thành công gần nhất ${formatDate(source.last_success_at)}`;
    if (source.error) li.textContent += ` · ${source.error}`;
    $("source-status").appendChild(li);
  }
  $("history-download").href = state.base + "history.json";
}
async function loadHistory() {
  if (state.history) return state.history;
  if (!historyRequest) {
    const base = state.base,
      snapshot = state.snapshotId;
    historyRequest = readJson(
      base + "history.json",
      snapshot ? "force-cache" : "no-cache",
    )
      .then((data) => {
        if (snapshot && data.snapshot_id !== snapshot)
          throw new Error("Lịch sử thuộc snapshot khác.");
        if (base !== state.base) throw new Error("Snapshot đã thay đổi.");
        state.history = data.events || [];
        return state.history;
      })
      .finally(() => {
        historyRequest = null;
      });
  }
  return historyRequest;
}
const FIELD_LABELS = {
  status: "Trạng thái",
  offers_bounty: "Có thưởng",
  min_bounty: "Thưởng thấp nhất",
  max_bounty: "Thưởng cao nhất",
  currency: "Đơn vị",
  reward_types: "Loại thưởng",
  policy_url: "Policy",
  contact: "Liên hệ",
};
function historyText(event) {
  const kinds = {
    added: "Program mới",
    removed: "Ngừng xuất hiện",
    scope_changes: "Scope đổi",
    program_changes: "Thông tin đổi",
  };
  const lines = [
    `${formatDate(event.at)} · ${event.name} · ${kinds[event.kind] || event.kind}`,
  ];
  const value = (v) =>
    v == null ? "chưa rõ" : Array.isArray(v) ? v.join(", ") : String(v);
  for (const [key, c] of Object.entries(event.fields || {}))
    lines.push(
      `${FIELD_LABELS[key] || key}: ${value(c.before)} → ${value(c.after)}`,
    );
  for (const [scope, c] of Object.entries(event.scopes || {})) {
    const label = scope === "in_scope" ? "Trong scope" : "Ngoài scope";
    if (c.added?.length) lines.push(`${label} thêm: ${c.added.join(", ")}`);
    if (c.removed?.length) lines.push(`${label} bỏ: ${c.removed.join(", ")}`);
    for (const item of c.updated || []) {
      const edits = Object.keys(item.after).filter(
        (k) => JSON.stringify(item.before[k]) !== JSON.stringify(item.after[k]),
      );
      const labels = {
        eligible_for_submission: "Nhận báo cáo",
        eligible_for_bounty: "Nhận thưởng",
        kind: "Loại asset",
        asset_type: "Loại nguồn",
      };
      lines.push(
        `${item.identifier}: ` +
          edits
            .map(
              (k) =>
                `${labels[k] || k} ${value(item.before[k])} → ${value(item.after[k])}`,
            )
            .join("; "),
      );
    }
  }
  return lines.join("\n");
}
function renderHistory(id, events) {
  const root = $(id);
  root.innerHTML = "";
  for (const e of events.slice(-100).reverse()) {
    const li = document.createElement("li");
    li.textContent = historyText(e);
    root.appendChild(li);
  }
}
async function showHistory(id) {
  $("d-history").innerHTML = "";
  $("d-history-status").textContent = "Đang tải lịch sử…";
  try {
    const events = (await loadHistory()).filter((e) => e.id === id);
    if (state.openId !== id) return;
    $("d-history-status").textContent = events.length
      ? `${events.length} thay đổi · hiển thị tối đa 100 mục gần nhất.`
      : "Chưa có thay đổi được ghi nhận.";
    renderHistory("d-history", events);
  } catch {
    if (state.openId === id)
      $("d-history-status").textContent =
        "Chưa tải được lịch sử. Bấm thử tải chi tiết lại.";
    $("retry-detail").hidden = false;
  }
}
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    notify("Đã sao chép.");
  } catch {
    notify(
      "Không truy cập được clipboard. Hãy chọn và sao chép nội dung trực tiếp.",
    );
  }
}

// Bind once; rendering never replaces the note field or import controls.
document.querySelectorAll(".tabs button").forEach((btn) =>
  btn.addEventListener("click", () => {
    state.tab = btn.dataset.tab;
    state.platform = "";
    changed();
  }),
);
$("q").addEventListener("input", (e) => {
  state.q = e.target.value.slice(0, 300);
  clearTimeout(searchTimer);
  searchTimer = setTimeout(changed, 180);
});
for (const key of ["kind", "reward", "currency", "sort"])
  $(key).addEventListener("change", (e) => {
    state[key] = e.target.value;
    if (key === "currency" && !state.currency) {
      state.minb = "";
      if (state.sort === "bounty") state.sort = "rank";
    }
    if (key === "sort" && state.sort === "bounty" && !state.currency) {
      state.sort = "rank";
      notify("Chọn đơn vị thưởng trước khi sắp xếp theo mức thưởng.");
    }
    changed();
  });
$("minb").addEventListener("input", (e) => {
  state.minb = e.target.value;
  changed();
});
$("reset").addEventListener("click", resetFilters);
$("retry").addEventListener("click", load);
$("filter-toggle").addEventListener("click", () =>
  filterDrawer(!$("filter-panel").classList.contains("open")),
);
$("filter-close").addEventListener("click", () => filterDrawer(false));
$("filter-panel").addEventListener("keydown", (e) => {
  if (!$("filter-panel").classList.contains("open")) return;
  if (e.key === "Escape") {
    filterDrawer(false);
    return;
  }
  if (e.key === "Tab") {
    const controls = [
      ...$("filter-panel").querySelectorAll("button,select,input"),
    ].filter((c) => !c.disabled);
    const first = controls[0],
      last = controls.at(-1);
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }
});
$("close").addEventListener("click", () => $("detail").close());
$("detail").addEventListener("close", () => {
  const id = state.openId || $("detail").dataset.programId;
  state.openId = "";
  writeUrl();
  [...document.querySelectorAll("#list article")]
    .find((el) => el.dataset.programId === id)
    ?.querySelector(".open-program")
    ?.focus();
});
$("save").addEventListener("click", () => {
  const p = openProgram();
  if (p) toggleSaved(p);
});
$("d-note").addEventListener("input", (e) => {
  const p = openProgram();
  if (!p) return;
  state.saved[p.id] = {
    ...(state.saved[p.id] || savedEntry(p)),
    note: e.target.value.slice(0, 20000),
  };
  const ok = persistSaved();
  $("note-status").textContent = ok ? "Đã lưu trên thiết bị." : storageWarning;
  syncSaveButton();
  renderChips();
  render();
});
$("share").addEventListener("click", () => copyText(window.location.href));
$("copy-assets").addEventListener("click", () =>
  copyText(JSON.parse($("copy-assets").dataset.assets || "[]").join("\n")),
);
$("retry-detail").addEventListener("click", () => {
  const p = openProgram();
  if (p) show(p, false);
});
$("export").addEventListener("click", () => {
  const blob = new Blob(
    [
      JSON.stringify(
        {
          version: 1,
          exported_at: new Date().toISOString(),
          items: state.saved,
        },
        null,
        2,
      ),
    ],
    { type: "application/json" },
  );
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "scopeboard-saved.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});
$("import").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  try {
    if (file.size > MAX_IMPORT_BYTES)
      throw new Error("File quá lớn (tối đa 2 MB).");
    const parsed = normalizeSaved(JSON.parse(await file.text()));
    if (Object.keys({ ...state.saved, ...parsed }).length > 5000)
      throw new Error("Bộ sưu tập sau khi gộp vượt 5.000 mục.");
    pendingImport = parsed;
    const duplicate = Object.keys(parsed).filter(
      (id) => state.saved[id],
    ).length;
    $("import-summary").textContent =
      `${Object.keys(parsed).length} mục hợp lệ · ${duplicate} mục trùng.`;
    $("import-dialog").showModal();
  } catch (error) {
    notify("Không nhập được: " + error.message);
  } finally {
    e.target.value = "";
  }
});
$("confirm-import").addEventListener("click", () => {
  if (!pendingImport) return;
  state.saved = { ...state.saved, ...pendingImport };
  pendingImport = null;
  const ok = persistSaved();
  $("import-dialog").close();
  renderChips();
  render();
  if (state.openId) {
    $("d-note").value = state.saved[state.openId]?.note || "";
    syncSaveButton();
  }
  notify(ok ? "Đã gộp bản sao lưu." : storageWarning);
});
$("cancel-import").addEventListener("click", () => {
  pendingImport = null;
  $("import-dialog").close();
});
$("load-history").addEventListener("click", async () => {
  const status = $("history-status");
  status.textContent = "Đang tải lịch sử…";
  try {
    const events = await loadHistory();
    renderHistory("recent-history", events);
    status.textContent = `${events.length} thay đổi · hiển thị tối đa 100 mục gần nhất.`;
  } catch {
    status.textContent = "Không tải được lịch sử. Bấm để thử lại.";
  }
});
document
  .querySelector("form.filters")
  .addEventListener("submit", (e) => e.preventDefault());
if (typeof window !== "undefined") {
  window.addEventListener("popstate", () => {
    const old = state.openId;
    readUrl();
    syncControls();
    renderChips();
    resetList();
    if (state.openId) {
      const p = allSavedRows().find((p) => p.id === state.openId);
      if (p) show(p, false);
    } else if (old) $("detail").close();
  });
  window.addEventListener("storage", (event) => {
    if (event.key !== STORE_KEY) return;
    state.saved = loadSaved();
    $("storage-status").textContent = storageWarning;
    renderChips();
    render();
    if (state.openId) {
      $("d-note").value = state.saved[state.openId]?.note || "";
      syncSaveButton();
    }
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth > 760 && $("filter-panel").classList.contains("open"))
      filterDrawer(false);
  });
}
$("storage-status").textContent = storageWarning;
load();
