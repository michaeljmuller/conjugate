"use strict";

const ACCENTS = ["á", "â", "ã", "à", "é", "ê", "í", "ó", "ô", "õ", "ú", "ç"];

const el = (id) => document.getElementById(id);
const normalize = (s) => s.trim().toLowerCase().split(/\s+/).join(" ");

let lastFocused = null; // input to receive accent-bar insertions
let currentVerbId = null;
let rows = [];          // MODEL: one entry per form, the single source of truth.
                        // The DOM is a projection of this — never read back for state.
let ui = { labels: "en", show_accents: false }; // interface prefs, loaded at init

// Tense/mood names come in both languages from the server; pick per interface pref.
const labelOf = (o) => (ui.labels === "pt" && o.label_pt) || o.label;
const moodOf = (o) => (ui.labels === "pt" && o.mood_pt) || o.mood;

// The mood tag, as an HTML fragment — but suppressed when the label already
// contains it (e.g. "Conditional" / conditional, "Past participle" / participle),
// so we never render "Conditional conditional".
function moodSpan(o, cls) {
  const mood = moodOf(o);
  if (labelOf(o).toLowerCase().includes(mood.toLowerCase())) return "";
  return ` <span class="${cls}">${mood}</span>`;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.status === 204 ? null : res.json();
}

async function init() {
  const me = await api("/api/me");
  if (!me) {
    el("signed-out").classList.remove("hidden");
    return;
  }
  el("app").classList.remove("hidden");
  buildUserMenu(me.name || me.email, me.email);

  buildAccentBar();
  wireControls();

  ui = (await api("/api/settings")).interface;
  applyInterface();

  const verbs = await api("/api/verbs");
  const options = verbs
    .map((v) => `<option value="${v.id}">${v.infinitive}</option>`)
    .join("");
  const selTop = el("verb-select");
  const selBottom = el("verb-select-bottom");
  selTop.innerHTML = options;
  selBottom.innerHTML = options;
  selTop.addEventListener("change", () => startVerb(selTop.value));
  selBottom.addEventListener("change", () => startVerb(selBottom.value));

  if (verbs.length) await loadVerb(verbs[0].id);
  updateStickyHeight();
  window.addEventListener("resize", updateStickyHeight);
}

function buildAccentBar() {
  el("accent-bar").innerHTML = ACCENTS.map(
    (c) => `<button type="button" data-ch="${c}">${c}</button>`
  ).join("");
  el("accent-bar").addEventListener("click", (e) => {
    const ch = e.target.getAttribute("data-ch");
    if (!ch || !lastFocused) return;
    const inp = lastFocused;
    const start = inp.selectionStart ?? inp.value.length;
    const end = inp.selectionEnd ?? inp.value.length;
    inp.value = inp.value.slice(0, start) + ch + inp.value.slice(end);
    inp.focus();
    const pos = start + ch.length;
    inp.setSelectionRange(pos, pos);
  });
}

function wireControls() {
  el("again").addEventListener("click", () => startVerb(currentVerbId));
  el("settings-save").addEventListener("click", saveSettings);
  el("settings-close").addEventListener("click", closeSettings);
  el("interface-save").addEventListener("click", saveInterface);
  el("interface-close").addEventListener("click", closeInterface);
}

// The user's name is a dropdown: "Tense configuration" opens the settings
// panel, and "Sign out" sits last. Closes on outside click or Escape.
function buildUserMenu(name, email) {
  const area = el("user-area");
  area.innerHTML =
    `<button class="user-menu-btn" id="user-menu-btn" aria-haspopup="true" aria-expanded="false">` +
    `<img class="avatar" src="/static/user.png" alt="" />` +
    `<span class="umb-name"></span><span class="umb-caret" aria-hidden="true">▾</span>` +
    `</button>` +
    `<div class="user-menu hidden" id="user-menu" role="menu">` +
    `<div class="um-header">` +
    `<img class="avatar avatar-lg" src="/static/user.png" alt="" />` +
    `<span class="um-email"></span>` +
    `</div>` +
    `<button class="um-item" role="menuitem" id="menu-tenses">Tense configuration</button>` +
    `<button class="um-item" role="menuitem" id="menu-interface">Interface</button>` +
    `<div class="um-divider" role="separator"></div>` +
    `<button class="um-item um-danger" role="menuitem" id="menu-logout">` +
    `<span class="um-arrow" aria-hidden="true">→</span> Sign out</button>` +
    `</div>`;
  // textContent: name/email are untrusted profile data.
  area.querySelector(".umb-name").textContent = name;
  area.querySelector(".um-email").textContent = email;

  const btn = el("user-menu-btn");
  const menu = el("user-menu");
  const setOpen = (open) => {
    menu.classList.toggle("hidden", !open);
    btn.setAttribute("aria-expanded", String(open));
  };
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    setOpen(menu.classList.contains("hidden"));
  });
  document.addEventListener("click", () => setOpen(false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") setOpen(false);
  });
  el("menu-tenses").addEventListener("click", () => {
    setOpen(false);
    openSettings();
  });
  el("menu-interface").addEventListener("click", () => {
    setOpen(false);
    openInterface();
  });
  el("menu-logout").addEventListener("click", async () => {
    await api("/auth/logout", { method: "POST" });
    location.reload();
  });
}

// ---- Settings: which tenses to drill, and in what order -----------------

async function openSettings() {
  const data = await api("/api/settings");
  renderTensePrefs(data.tenses);
  el("settings-error").classList.add("hidden");
  el("settings-panel").classList.remove("hidden");
}

function closeSettings() {
  el("settings-panel").classList.add("hidden");
}

// One row per tense: an enable checkbox plus a drag handle for reordering.
// Labels come from the server (trusted constants), so innerHTML is safe here.
function renderTensePrefs(tenses) {
  const ul = el("tense-prefs");
  ul.innerHTML = "";
  for (const t of tenses) {
    const li = document.createElement("li");
    li.className = "tense-pref";
    li.dataset.key = t.key;
    li.draggable = true;
    li.innerHTML =
      `<span class="tp-grip" aria-hidden="true">⣿</span>` +
      `<label class="tp-toggle">` +
      `<input type="checkbox" ${t.enabled ? "checked" : ""} />` +
      `<span class="tp-name">${labelOf(t)}${moodSpan(t, "tp-mood")}</span>` +
      `</label>`;
    ul.appendChild(li);
  }
  wireDragReorder(ul);
}

// HTML5 drag-and-drop reordering. On dragover we splice the dragged row in
// before/after the row under the cursor based on which half it's over.
function wireDragReorder(ul) {
  let dragged = null;
  ul.addEventListener("dragstart", (e) => {
    dragged = e.target.closest(".tense-pref");
    if (!dragged) return;
    dragged.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
  });
  ul.addEventListener("dragend", () => {
    dragged?.classList.remove("dragging");
    dragged = null;
  });
  ul.addEventListener("dragover", (e) => {
    if (!dragged) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    const over = e.target.closest(".tense-pref");
    if (!over || over === dragged) return;
    const rect = over.getBoundingClientRect();
    const after = e.clientY > rect.top + rect.height / 2;
    ul.insertBefore(dragged, after ? over.nextElementSibling : over);
  });
}

async function saveSettings() {
  const tenses = [...el("tense-prefs").querySelectorAll(".tense-pref")].map((li) => ({
    key: li.dataset.key,
    enabled: li.querySelector("input[type=checkbox]").checked,
  }));
  if (!tenses.some((t) => t.enabled)) {
    const err = el("settings-error");
    err.textContent = "Enable at least one tense.";
    err.classList.remove("hidden");
    return;
  }
  await api("/api/settings", { method: "PUT", body: JSON.stringify({ tenses }) });
  closeSettings();
  if (currentVerbId) await loadVerb(currentVerbId); // re-render with new order/selection
}

// ---- Interface settings: label language + accent-button visibility ------

function openInterface() {
  el("iface-accents").checked = ui.show_accents;
  for (const r of document.getElementsByName("iface-labels"))
    r.checked = r.value === ui.labels;
  el("interface-panel").classList.remove("hidden");
}

function closeInterface() {
  el("interface-panel").classList.add("hidden");
}

async function saveInterface() {
  const labels =
    [...document.getElementsByName("iface-labels")].find((r) => r.checked)?.value || "en";
  const show_accents = el("iface-accents").checked;
  const data = await api("/api/settings", {
    method: "PUT",
    body: JSON.stringify({ interface: { labels, show_accents } }),
  });
  ui = data.interface;
  applyInterface();
  closeInterface();
  if (currentVerbId) await loadVerb(currentVerbId); // relabel the drill in the new language
}

// Reflect the current interface prefs in the DOM: show/hide the accent bar.
// The bar lives in the sticky header, so its height changes what the drill must
// scroll clear of — recompute the sticky offset whenever it toggles.
function applyInterface() {
  el("accent-bar").classList.toggle("hidden", !ui.show_accents);
  updateStickyHeight();
}

// Keep drill sections from scrolling under the sticky header: expose its live
// height as a CSS var that .tense-block uses for scroll-margin-top.
function updateStickyHeight() {
  const h = el("sticky-header").offsetHeight;
  document.documentElement.style.setProperty("--sticky-h", `${h + 8}px`);
}

async function loadVerb(verbId) {
  currentVerbId = verbId;
  const data = await api(`/api/verbs/${verbId}/forms`);
  renderDrill(data);
  el("verb-select").value = verbId;
  el("verb-select-bottom").value = verbId;
  updateVerbIndicator(verbId);
}

// Start (or restart) a verb fresh: reload it, jump to the top, and focus the
// first field. Used by "conjugate again" and both verb pickers.
async function startVerb(verbId) {
  await loadVerb(verbId);
  rows[0]?.input.focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// Sticky banner naming the verb being drilled, so it stays visible on scroll.
function updateVerbIndicator(verbId) {
  const sel = el("verb-select");
  const opt = [...sel.options].find((o) => o.value == verbId);
  const label = opt ? opt.text : "";
  el("verb-indicator").querySelector(".vi-verb").textContent = label;
  el("verb-indicator").classList.toggle("hidden", !label);
}

// ---- Model construction -------------------------------------------------

function renderDrill(data) {
  const drill = el("drill");
  drill.innerHTML = "";
  rows = [];
  for (const block of data.blocks) {
    const wrap = document.createElement("div");
    wrap.className = "tense-block";
    wrap.innerHTML = `<h3>${labelOf(block)}${moodSpan(block, "mood")}</h3>`;
    for (const r of block.rows) {
      const row = makeRow(r);
      wrap.appendChild(row.el);
      rows.push(row);
    }
    drill.appendChild(wrap);
  }
  renderProgress(); // fresh drill: "0 of Y"
}

// Build a row's DOM once and return its state object. All later changes go
// through the state + renderRow(); the element is never queried for truth.
function makeRow(data) {
  const div = document.createElement("div");
  div.className = "row";
  div.innerHTML =
    `<div class="row-line">` +
    `<span class="person"></span>` +
    `<input type="text" autocomplete="off" autocapitalize="off" spellcheck="false" />` +
    `<span class="mark"></span>` +
    `</div>` +
    `<div class="row-example"></div>` +
    `<div class="row-example-pt"></div>`;
  div.querySelector(".person").textContent = data.label;
  // English example is the always-visible prompt (textContent: model-generated).
  if (data.example_en)
    div.querySelector(".row-example").textContent = data.example_en;

  const input = div.querySelector("input");
  const row = {
    // immutable form data
    formId: data.form_id,
    answer: data.answer,
    examplePt: data.example_pt || "",
    el: div,
    input,
    note: null, // the "missed it" note element, when present
    // mutable answer state
    graded: false,       // has been checked with a non-empty value
    correct: false,      // current value matches the answer
    recorded: false,     // first attempt already sent to the server
    firstWrong: false,   // that first attempt was wrong (a mistake on record)
    typedWrong: "",      // what they first typed, for the resolved note
    attemptId: null,     // server id, to reclassify as a typo
    dismissedTypo: false,// "just a typo" clicked — no longer counts as a mistake
  };

  input.addEventListener("focus", () => {
    lastFocused = input;
    div.classList.add("focused");
  });
  input.addEventListener("blur", () => {
    div.classList.remove("focused");
    gradeRow(row);
  });
  input.addEventListener("keydown", (e) => {
    const isTab = e.key === "Tab" && !e.shiftKey;
    if (!isTab && e.key !== "Enter") return;

    // Empty field: don't trap it — let Tab skip ahead (Enter is a no-op here).
    if (!input.value.trim()) return;

    // Grade first and control movement ourselves, so focus can't leave a wrong
    // answer via the browser's default Tab — you stay put to fix it. Grading is
    // synchronous (a local string compare), so focus moves this same tick: there
    // is no network gap in which the next keystroke could land in this field.
    e.preventDefault();
    gradeRow(row);
    if (!row.correct) return; // wrong: keep focus on this field
    // Drill just finished: let the footer reveal/scroll win — don't navigate
    // focus (which would scroll the field back into view over the footer).
    if (rows.every((r) => r.graded)) return;
    if (isLastInSection(input)) scrollToNextSection(div); // next tense to top
    else focusNextInput(input); // next person
  });
  return row;
}

// ---- State transitions --------------------------------------------------

// Grade a row against the answer. This is synchronous and local — the server's
// grading is byte-for-byte the same normalization, so we never wait on it to
// decide correctness or to move focus. The first attempt is persisted in the
// background (recordAttempt), which is all the server round-trip is for.
function gradeRow(row) {
  const text = row.input.value.trim();
  if (!text) return;

  const wasCorrect = row.graded && row.correct;
  row.correct = normalize(text) === normalize(row.answer);
  row.graded = true;

  // Record only the FIRST attempt per form — that's the honest score.
  if (!row.recorded) {
    row.recorded = true;
    recordAttempt(row, text);
  }

  renderRow(row);
  renderProgress();
  if (row.correct && !wasCorrect) showToast("Correct!"); // pop once, on the transition
}

// Persist the first attempt in the background. The server also returns the
// authoritative verdict and an attempt id; if it was wrong, surface the "missed
// it" note (which needs that id for the "just a typo" reclassification). Grading
// and focus never wait on this — it runs after the row is already marked.
async function recordAttempt(row, text) {
  let result;
  try {
    result = await api("/api/attempts", {
      method: "POST",
      body: JSON.stringify({ form_id: row.formId, submitted_text: text }),
    });
  } catch (e) {
    row.recorded = false; // let a later grade (blur/re-tab) retry the record
    console.error("recording attempt failed", e);
    return;
  }
  if (!result.is_correct) {
    row.firstWrong = true;
    row.attemptId = result.attempt_id;
    row.typedWrong = text;
    renderRow(row);   // reveal the note now that the id exists
    renderProgress(); // and count the mistake
  }
}

async function dismissTypo(row) {
  await api(`/api/attempts/${row.attemptId}/verdict`, {
    method: "POST",
    body: JSON.stringify({ verdict: "typo" }),
  });
  row.dismissedTypo = true;
  renderRow(row);   // drops the note
  renderProgress(); // one fewer mistake on record
}

// ---- Projections: model -> DOM -----------------------------------------

// Everything visible about a single row derives from its state here.
function renderRow(row) {
  const div = row.el;

  div.classList.toggle("correct", row.graded && row.correct);
  div.classList.toggle("wrong", row.graded && !row.correct);
  div.querySelector(".mark").textContent = row.graded
    ? row.correct ? "✓" : "✗"
    : "";

  // pt-PT example holds the answer word, so it's shown only once answered.
  div.querySelector(".row-example-pt").textContent =
    row.graded && row.examplePt ? row.examplePt : "";

  renderNote(row);
}

// The "missed it first try" note exists iff a first wrong attempt stands
// unforgiven. Text depends on whether the field has since been corrected.
function renderNote(row) {
  const show = row.firstWrong && !row.dismissedTypo;
  if (!show) {
    row.note?.remove();
    row.note = null;
    return;
  }
  if (!row.note) {
    const hint = document.createElement("div");
    hint.className = "answer";
    hint.innerHTML =
      `<span class="ans-text"></span> ` +
      `<button class="typo-btn" type="button">just a typo</button>`;
    hint.querySelector(".typo-btn").addEventListener("click", () => dismissTypo(row));
    row.el.after(hint);
    row.note = hint;
  }
  row.note.classList.toggle("resolved", row.correct);
  // Build with textContent so a user's typed value can't inject markup.
  const at = row.note.querySelector(".ans-text");
  at.textContent = row.correct ? "you typed: " : "answer: ";
  const b = document.createElement("b");
  b.textContent = row.correct ? row.typedWrong : row.answer;
  at.appendChild(b);
}

// The progress summary, derived purely from row state. Drives the sticky
// header readout always, and the footer summary once the drill is complete.
function renderProgress() {
  const total = rows.length;
  const filled = rows.filter((r) => r.graded).length;
  const mistakes = rows.filter((r) => r.firstWrong && !r.dismissedTypo).length;
  const complete = total > 0 && filled === total;
  const perfect = complete && mistakes === 0;

  let text = "";
  if (total) {
    text = perfect ? "Perfect!" : `${filled} of ${total}`;
    if (!perfect && mistakes > 0)
      text += ` (${mistakes} mistake${mistakes === 1 ? "" : "s"})`;
  }

  const header = el("verb-indicator").querySelector(".vi-progress");
  header.textContent = text;
  header.classList.toggle("perfect", perfect);

  // Footer (summary + next-verb controls) appears only once all fields are answered.
  const footer = el("footer-controls");
  const justRevealed = complete && footer.classList.contains("hidden");
  footer.classList.toggle("hidden", !complete);
  const summary = el("footer-summary");
  summary.textContent = complete ? text : "";
  summary.classList.toggle("perfect", perfect);

  // Bring the freshly revealed controls into view (they're below the fold).
  if (justRevealed) footer.scrollIntoView({ behavior: "smooth", block: "end" });
}

// Brief fixed-position "Correct!" toast. Never focusable, so it doesn't
// interrupt typing; fades itself out shortly after appearing.
let toastTimer = null;
function showToast(msg) {
  const t = el("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 700);
}

// ---- Navigation helpers (view concerns: focus + scroll) -----------------

function focusNextInput(input) {
  const inputs = rows.map((r) => r.input);
  const next = inputs[inputs.indexOf(input) + 1];
  if (next) next.focus();
}

// Is this the last person input within its tense section?
function isLastInSection(input) {
  const inSection = [...input.closest(".tense-block").querySelectorAll(".row input")];
  return input === inSection[inSection.length - 1];
}

// Scroll the next tense block's heading to the top and move focus into its
// first person input. No-op on the final section.
function scrollToNextSection(rowEl) {
  const next = rowEl.closest(".tense-block").nextElementSibling;
  if (next && next.classList.contains("tense-block")) {
    next.scrollIntoView({ behavior: "smooth", block: "start" });
    next.querySelector(".row input")?.focus({ preventScroll: true });
  }
}

init().catch((err) => {
  console.error(err);
  document.body.insertAdjacentHTML(
    "beforeend",
    `<pre style="color:#e03131;padding:1rem">${err.message}</pre>`
  );
});
