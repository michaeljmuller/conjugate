"use strict";

const el = (id) => document.getElementById(id);
const normalize = (s) => s.trim().toLowerCase().split(/\s+/).join(" ");

// Accents folded away, for matching what was TYPED INTO THE VERB FILTER: "por"
// should find "pôr". Deliberately separate from normalize() above, which grading
// uses and which must stay accent-sensitive — a missing diacritic is wrong.
const fold = (s) => s.trim().toLowerCase().normalize("NFD").replace(/\p{Mn}/gu, "");

// A stray Enter right after the last answer would otherwise start the next verb
// before the results had been read; see finishDrill(). The switch dialog uses the
// same guard against the Return that opened it.
const ENTER_GUARD_MS = 400;

let lastFocused = null; // drill input to receive accent-bar insertions, and to
                        // go back to when the verb list is left mid-drill
let currentVerbId = null;
let verbOrder = [];     // the drilled language's verbs, in list order (regular
                        // first). The source for "the next verb" and for turning
                        // an id into an infinitive — never the DOM.
let pickerFocusedAt = 0; // when the list last took focus without being asked
let pickerHits = [];     // the verbs the list is currently showing, in row order
let highlightId = null;  // the highlighted verb, by id so it survives filtering
let drillFinished = false; // has this drill reached complete (and its finish —
                           // top of page, focus in the list — been set off)
let rows = [];          // MODEL: one entry per form, the single source of truth.
                        // The DOM is a projection of this — never read back for state.
let ui = { labels: "en", show_accents: false }; // interface prefs, loaded at init
let lang = { code: "", name: "", accents: [], available: [] }; // drilled language, loaded at init

// Tense/mood names come in both languages from the server; pick per interface pref.
const labelOf = (o) => (ui.labels === "native" && o.label_native) || o.label;
const moodOf = (o) => (ui.labels === "native" && o.mood_native) || o.mood;

// The mood is suppressed when the label already contains it (e.g. "Conditional"
// / conditional, "Past participle" / participle), so we never render
// "Conditional conditional".
const moodRedundant = (o) =>
  labelOf(o).toLowerCase().includes(moodOf(o).toLowerCase());

// The mood tag, as an HTML fragment for the tense heading.
function moodSpan(o, cls) {
  if (moodRedundant(o)) return "";
  return ` <span class="${cls}">${moodOf(o)}</span>`;
}

// The same heading as one plain string, for places that can't style a span.
// The mood is not decoration here: "Present", "Future" and "Past imperfect" each
// name both an indicative and a subjunctive tense, so a bare label is ambiguous.
const tenseText = (o) => (moodRedundant(o) ? labelOf(o) : `${labelOf(o)} ${moodOf(o)}`);

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

  wireControls();

  applySettings(await api("/api/settings"));
  buildLanguageMenu();
  buildAccentBar();
  applyInterface();

  showStart(await loadVerbs());
  updateStickyHeight();
  window.addEventListener("resize", updateStickyHeight);
}

// (Re)fill the verb list from the server. Called at startup and again whenever
// a verb is added, so the new one appears without a reload.
//
// Regular verbs lead. They are the models the irregular ones are departures
// from, so they are what you reach for first — and the split is the same one the
// add-a-verb confirmation reports, from the same `pattern` the server sends
// here. That order is also the order "the next verb" walks.
async function loadVerbs() {
  const verbs = await api("/api/verbs");
  verbOrder = [
    ...verbs.filter((v) => v.pattern),
    ...verbs.filter((v) => !v.pattern),
  ];
  el("verb-pick").disabled = !verbOrder.length;
  renderPickerList();
  return verbOrder;
}

// ---- The verb list ------------------------------------------------------
//
// Always on screen. The focus, when the list has it, is really in the filter
// box in its footer, which stays invisible until something is typed into it:
// the arrow keys move a highlight through the rows, Return starts the
// highlighted verb, and typing narrows the list. Nothing starts until Return
// or a click.

// The verb after the one on screen, wrapping at the end. With one verb in the
// language it is that verb, so Return runs it again.
function nextVerb() {
  if (!verbOrder.length || currentVerbId === null) return null;
  const i = verbOrder.findIndex((v) => v.id == currentVerbId);
  return verbOrder[(i + 1) % verbOrder.length];
}

// What the list shows for what has been typed: everything when the box is empty,
// otherwise every verb the text is a prefix of. Folded, so accents are a
// convenience rather than a requirement — "por" finds "pôr".
function filterVerbs(text) {
  const t = fold(text);
  if (!t) return verbOrder;
  return verbOrder.filter((v) => fold(v.infinitive).startsWith(t));
}

// Where the highlight lands once the list has been redrawn: on the verb the
// text names exactly (so "ser" means ser, not servir), else where it already
// was if that verb is still showing, else on the first row.
function highlightFor(text) {
  const t = fold(text);
  const exact = t && pickerHits.find((v) => fold(v.infinitive) === t);
  const kept = pickerHits.find((v) => v.id == highlightId);
  return (exact || kept || pickerHits[0])?.id ?? null;
}

// Give the list the focus with `id` highlighted and nothing typed. No scroll
// from the focus itself: the box is in the column's footer, and the page may be
// on its way back to the top.
function focusList(id) {
  const inp = el("verb-pick");
  if (inp.disabled) return;
  setFilter("");
  inp.focus({ preventScroll: true });
  highlightVerb(id);
}

function setFilter(text) {
  el("verb-pick").value = text;
  renderPickerList();
}

// A drill on screen that has not reached complete (see renderProgress). Read
// from the flag rather than worked out afresh, because completion depends on
// where the cursor was — and by the time this is asked it is in the list.
const drillUnfinished = () => rows.length > 0 && !drillFinished;

// The one way a verb starts from the list, whether by Return or a click. Part
// way through a drill it asks first, since a stray click on an always-visible
// list is easy; with nothing answered yet, or the drill done, there is nothing
// to ask about.
function chooseVerb(verb) {
  if (drillUnfinished() && rows.some((r) => r.graded)) openSwitch(verb);
  else startVerb(verb.id);
}

// ---- The switch dialog --------------------------------------------------

let switchTo = null;   // the verb the open dialog would start
let switchOpenedAt = 0;

function openSwitch(verb) {
  const dlg = el("switch-dialog");
  switchTo = verb;
  el("switch-text").textContent =
    verb.id == currentVerbId ? `Start ${verb.infinitive} over?` : `Switch to ${verb.infinitive}?`;
  switchOpenedAt = Date.now();
  dlg.showModal();
  el("switch-go").focus();
}

// Staying goes back to the field you left, even when the dialog was opened from
// the keyboard with the focus in the list. Done here rather than in a "close"
// listener: Chrome holds that event until the next paint, which a background
// tab never gets, and this runs after close() has put the focus back where the
// dialog found it, so the field wins.
function closeSwitch(go) {
  el("switch-dialog").close();
  if (go) startVerb(switchTo.id);
  else lastFocused?.focus();
}

// Return presses the focused button, which starts on Switch; Escape is Keep
// conjugating. Only a fresh Return counts: not a held one, and not one straight
// after the Return that opened the dialog.
function wireSwitch() {
  el("switch-go").addEventListener("click", () => closeSwitch(true));
  el("switch-stay").addEventListener("click", () => closeSwitch(false));
  el("switch-dialog").addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault(); // ours, not the dialog's own cancel
      closeSwitch(false);
    } else if (e.key === "Enter" && (e.repeat || Date.now() - switchOpenedAt < ENTER_GUARD_MS)) {
      e.preventDefault();
    }
  });
}

// ---- Drawing the verb list ----------------------------------------------

// Draw the list for whatever is typed. The Regular/Irregular headings are the
// split verbOrder already carries, and appear only when both kinds are showing:
// a heading over every row divides nothing. Row order follows pickerHits, which
// is what the arrow keys walk.
function renderPickerList() {
  const inp = el("verb-pick");
  const panel = el("verb-list");
  inp.classList.toggle("has-text", !!inp.value);
  pickerHits = filterVerbs(inp.value);
  panel.innerHTML = "";
  if (!pickerHits.length) {
    // Only a filter can empty the list; a language with no verbs says so in
    // the drill column instead.
    if (inp.value) {
      const none = document.createElement("div");
      none.className = "picker-none";
      none.textContent = "No such verb";
      panel.appendChild(none);
    }
  } else {
    const regular = pickerHits.filter((v) => v.pattern);
    const irregular = pickerHits.filter((v) => !v.pattern);
    const groups =
      regular.length && irregular.length
        ? [["Regular", regular], ["Irregular", irregular]]
        : [["", pickerHits]];
    for (const [label, verbs] of groups) {
      if (label) panel.appendChild(pickerHeading(label));
      for (const v of verbs) panel.appendChild(pickerRow(v));
    }
  }
  highlightVerb(highlightFor(inp.value));
}

function pickerHeading(text) {
  const head = document.createElement("div");
  head.className = "picker-group";
  head.textContent = text;
  return head;
}

// A row is a <div>, not a <button>: the box keeps the focus and the arrow keys
// move a highlight, so rows have no business in the tab order. `current` marks
// the verb on screen, which the dimming leaves alone. textContent —
// infinitives are model-generated.
function pickerRow(verb) {
  const row = document.createElement("div");
  row.className = "um-item picker-item";
  row.classList.toggle("current", verb.id == currentVerbId);
  row.id = `verb-row-${verb.id}`;
  row.setAttribute("role", "option");
  row.setAttribute("aria-selected", "false");
  row.dataset.id = verb.id;
  row.textContent = verb.infinitive;
  return row;
}

// Move the highlight onto a verb. Screen readers follow it through
// aria-activedescendant, since the focus itself never leaves the box. It shows
// only while the list has the focus (see styles.css), and scrolls into view
// only then: with the focus in the drill, a redraw has no business moving the
// page.
function highlightVerb(id) {
  const inp = el("verb-pick");
  highlightId = id;
  let active = null;
  for (const row of el("verb-list").querySelectorAll(".picker-item")) {
    const on = row.dataset.id == id;
    row.classList.toggle("active", on);
    row.setAttribute("aria-selected", String(on));
    if (on) active = row;
  }
  if (!active) return void inp.removeAttribute("aria-activedescendant");
  inp.setAttribute("aria-activedescendant", active.id);
  if (document.activeElement === inp) active.scrollIntoView({ block: "nearest" });
}

// One row up or down, clamped at the ends. The Regular/Irregular headings are
// not rows, so the walk steps over them.
function moveHighlight(delta) {
  if (!pickerHits.length) return;
  const i = pickerHits.findIndex((v) => v.id == highlightId);
  const to = i === -1 ? 0 : Math.min(Math.max(i + delta, 0), pickerHits.length - 1);
  highlightVerb(pickerHits[to].id);
}

// The list's keys. Return starts the highlighted verb; nothing else here starts
// a drill. Escape drops the filter and, part way through a drill, goes back to
// the field you left.
function pickerKey(e) {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    moveHighlight(e.key === "ArrowDown" ? 1 : -1);
    return;
  }
  if (e.key === "Escape") {
    // Some browsers clear an input on Escape themselves; the key is ours here.
    e.preventDefault();
    setFilter("");
    if (drillUnfinished() && lastFocused?.isConnected) lastFocused.focus();
    return;
  }
  if (e.key !== "Enter") return;
  e.preventDefault();
  // The Enter that answered the last field is consumed by the row it was typed
  // in, but a habitual second one lands here; see finishDrill().
  if (Date.now() - pickerFocusedAt < ENTER_GUARD_MS) return;
  const verb = pickerHits.find((v) => v.id == highlightId);
  if (verb) chooseVerb(verb);
}

// Cmd+K (Ctrl+K off the Mac), from anywhere: the list, with the highlight on
// the verb on screen, so Up and Down reach its neighbours and typing filters.
// Not over a dialog, which owns the keyboard while it is open.
function listShortcut(e) {
  if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey) return;
  if (e.key.toLowerCase() !== "k") return;
  if (el("switch-dialog").open || document.querySelector(".settings-panel:not(.hidden)")) return;
  e.preventDefault();
  focusList(currentVerbId ?? verbOrder[0]?.id);
}

// The bar's buttons, rebuilt whenever the drilled language changes. Only the
// buttons: the click handler is wired once in wireControls(), because it lives
// on the bar itself and re-adding it here would insert a character once per
// language switch made since the page loaded.
function buildAccentBar() {
  el("accent-bar").innerHTML = lang.accents.map(
    (c) => `<button type="button" data-ch="${c}">${c}</button>`
  ).join("");
}

function insertAccent(ch) {
  if (!ch || !lastFocused) return;
  const inp = lastFocused;
  const start = inp.selectionStart ?? inp.value.length;
  const end = inp.selectionEnd ?? inp.value.length;
  inp.value = inp.value.slice(0, start) + ch + inp.value.slice(end);
  inp.focus();
  const pos = start + ch.length;
  inp.setSelectionRange(pos, pos);
}

function wireControls() {
  el("accent-bar").addEventListener("click", (e) =>
    insertAccent(e.target.getAttribute("data-ch"))
  );
  el("verb-add").addEventListener("click", openAddVerb);
  const pick = el("verb-pick");
  pick.addEventListener("keydown", pickerKey);
  pick.addEventListener("input", renderPickerList);
  // A filter is for the moment you are in the list; leaving it (Tab, a click
  // elsewhere, a verb started) puts every verb back.
  pick.addEventListener("blur", () => {
    if (pick.value) setFilter("");
  });
  document.addEventListener("keydown", listShortcut);
  // Rows refuse the mousedown, so a click on one leaves the focus where it was:
  // in the drill, which is where the switch dialog's Escape goes back to.
  el("verb-list").addEventListener("mousedown", (e) => e.preventDefault());
  el("verb-list").addEventListener("click", (e) => {
    const row = e.target.closest(".picker-item");
    const verb = row && verbOrder.find((v) => v.id == row.dataset.id);
    if (verb) chooseVerb(verb);
  });
  wireSwitch();
  // Acts on the verb on screen — there is no other verb it could mean.
  el("verb-edit").addEventListener("click", () => openReview(currentVerbId));
  el("settings-save").addEventListener("click", saveSettings);
  el("settings-close").addEventListener("click", closeSettings);
  el("add-verb-go").addEventListener("click", () => addGoAction());
  el("add-verb-close").addEventListener("click", closeAddVerb);
  // The primary button means "rewrite" before there are proposals and "save"
  // after, so it dispatches on which state the card is showing.
  el("review-go").addEventListener("click", () =>
    reviewProposals.length ? saveReview() : submitReview()
  );
  el("review-close").addEventListener("click", closeReview);
  el("add-verb-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitAddVerb();
  });
}

// Which commit is serving this page, from /healthz — the same answer curl gets,
// so the UI and a scripted check can never disagree. Quiet on failure: not
// knowing the version is not worth an error message in front of a drill.
async function showBuild() {
  const box = el("um-build");
  if (!box) return;
  try {
    const res = await fetch("/healthz");
    if (!res.ok) return;
    const { version, committed } = await res.json();
    box.querySelector(".um-build-version").textContent = `Version ${version}`;
    // Date and time, in the reader's own locale and zone: "when did what I am
    // looking at get built" is the question this line answers.
    const when = committed ? new Date(committed) : null;
    box.querySelector(".um-build-when").textContent =
      when && !isNaN(when)
        ? when.toLocaleString(undefined, {
            year: "numeric", month: "short", day: "numeric",
            hour: "numeric", minute: "2-digit",
          })
        : "";
    box.title = committed || "";
  } catch (e) {
    /* leave it blank */
  }
}


// Both header dropdowns — the language picker and the user menu — open on their
// button and close on an outside click or Escape. Returns the open/close setter,
// so an item that should close the menu can say so.
function wireDropdown(btn, menu) {
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
  return setOpen;
}

// The avatar is a dropdown: the tense panel, the two interface preferences, the
// build line, and "Sign out" last.
function buildUserMenu(name, email) {
  const area = el("user-area");
  area.innerHTML =
    `<button class="menu-btn user-menu-btn" id="user-menu-btn" aria-haspopup="true" aria-expanded="false">` +
    `<img class="avatar" src="/static/user.png" alt="" />` +
    `<span class="umb-name"></span><span class="umb-caret" aria-hidden="true">▾</span>` +
    `</button>` +
    `<div class="menu-panel user-menu hidden" id="user-menu" role="menu">` +
    `<div class="um-header"><span class="um-email"></span></div>` +
    `<button class="um-item" role="menuitem" id="menu-tenses">` +
    `<span class="um-check"></span>Select tenses</button>` +
    // Checkable items rather than a panel: each is one setting, and a setting
    // that takes effect when you click it needs no Save button.
    `<button class="um-item" role="menuitemcheckbox" aria-checked="false" id="menu-labels">` +
    `<span class="um-check"></span>English tense labels</button>` +
    `<button class="um-item" role="menuitemcheckbox" aria-checked="false" id="menu-accents">` +
    `<span class="um-check"></span>Show accent buttons</button>` +
    `<div class="um-divider" role="separator"></div>` +
    `<div class="um-build" id="um-build">` +
    `<span class="um-build-version"></span>` +
    `<span class="um-build-when"></span>` +
    `</div>` +
    `<div class="um-divider" role="separator"></div>` +
    `<button class="um-item um-danger" role="menuitem" id="menu-logout">` +
    `<span class="um-arrow" aria-hidden="true">→</span> Sign out</button>` +
    `</div>`;
  // textContent: name/email are untrusted profile data.
  area.querySelector(".umb-name").textContent = name;
  area.querySelector(".um-email").textContent = email;
  showBuild();

  const setOpen = wireDropdown(el("user-menu-btn"), el("user-menu"));
  el("menu-tenses").addEventListener("click", () => {
    setOpen(false);
    openSettings();
  });
  // The toggles leave the menu open, so both can be flipped in one visit: the
  // stopPropagation is what keeps the click off the document handler above.
  el("menu-labels").addEventListener("click", (e) => {
    e.stopPropagation();
    setInterface({ labels: ui.labels === "en" ? "native" : "en" });
  });
  el("menu-accents").addEventListener("click", (e) => {
    e.stopPropagation();
    setInterface({ show_accents: !ui.show_accents });
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

// Take what the server says about the drilled language and the interface prefs.
// Everything language-specific — the name to show, which accented letters the
// bar offers — comes from here rather than being baked into the client.
function applySettings(data) {
  ui = data.interface;
  toastMs = data.toast_ms || toastMs;
  lang = {
    code: data.language,
    name: data.language_name,
    accents: data.accents || [],
    available: data.languages || [],
  };
}

// One interface preference, written and reflected at once. The menu item is the
// setting, so there is nothing to save.
async function setInterface(patch) {
  applySettings(
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ interface: patch }),
    })
  );
  applyInterface();
  // Tense headings are drawn through labelOf()/moodOf() at render time, so the
  // label language only reaches the drill by drawing it again.
  if (patch.labels !== undefined && currentVerbId) await loadVerb(currentVerbId);
}

// ---- The drilled language, in the header --------------------------------

// Each language's flag, drawn small: at 20px the arms of Portugal's armillary
// sphere are a smudge, so it is a disc, and Spain's coat of arms is left off.
// Inline rather than files under static/, which pyproject.toml's `static/*`
// package-data glob would not reach.
const FLAGS = {
  "pt-PT":
    `<svg class="flag" viewBox="0 0 30 20" aria-hidden="true">` +
    `<rect width="30" height="20" fill="#046a38"/>` +
    `<rect x="12" width="18" height="20" fill="#da291c"/>` +
    `<circle cx="12" cy="10" r="4.4" fill="#ffe900" stroke="#046a38" stroke-width="0.7"/>` +
    `<circle cx="12" cy="10" r="2.2" fill="#fff" stroke="#da291c" stroke-width="1.5"/></svg>`,
  es:
    `<svg class="flag" viewBox="0 0 30 20" aria-hidden="true">` +
    `<rect width="30" height="20" fill="#c60b1e"/>` +
    `<rect y="5" width="30" height="10" fill="#ffc400"/></svg>`,
  it:
    `<svg class="flag" viewBox="0 0 30 20" aria-hidden="true">` +
    `<rect width="10" height="20" fill="#009246"/>` +
    `<rect x="10" width="10" height="20" fill="#fff"/>` +
    `<rect x="20" width="10" height="20" fill="#ce2b37"/></svg>`,
};

// A button and a dropdown rather than a <select>: the options carry flags, and
// a <select> can only hold text.
function buildLanguageMenu() {
  const area = el("lang-area");
  area.innerHTML =
    `<button class="menu-btn lang-btn" id="lang-btn" aria-haspopup="true" aria-expanded="false"></button>` +
    `<div class="menu-panel lang-menu hidden" id="lang-menu" role="menu"></div>`;
  renderLanguageMenu();
  const setOpen = wireDropdown(el("lang-btn"), el("lang-menu"));
  el("lang-menu").addEventListener("click", (e) => {
    const item = e.target.closest(".lang-item");
    if (!item) return;
    setOpen(false);
    if (item.dataset.code !== lang.code) switchLanguage(item.dataset.code);
  });
}

// Button and list are both projections of `lang`, so one call relabels the
// header after a switch. Flags are our own constants and go in as markup; the
// names are server data and go in as text.
function renderLanguageMenu() {
  const btn = el("lang-btn");
  btn.innerHTML =
    `${FLAGS[lang.code] || ""}<span class="lang-name"></span>` +
    `<span class="umb-caret" aria-hidden="true">▾</span>`;
  btn.querySelector(".lang-name").textContent = lang.name;

  const menu = el("lang-menu");
  menu.innerHTML = "";
  for (const l of lang.available) {
    const item = document.createElement("button");
    item.className = "um-item lang-item";
    item.type = "button";
    item.setAttribute("role", "menuitemradio");
    item.setAttribute("aria-checked", String(l.code === lang.code));
    item.dataset.code = l.code;
    item.innerHTML = `${FLAGS[l.code] || ""}<span class="lang-name"></span>`;
    item.querySelector(".lang-name").textContent = l.name;
    menu.appendChild(item);
  }
}

// Drill a different language. Everything the drill is made of is per language —
// the verb list, the tense order, the accent bar — so this reloads the view
// rather than relabelling it.
async function switchLanguage(code) {
  applySettings(
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ language: code }),
    })
  );
  renderLanguageMenu();
  buildAccentBar();
  applyInterface();
  // The verb list is per language, so the old choice is gone — and a new
  // language is a new choice, not a different verb chosen for you.
  currentVerbId = null;
  showStart(await loadVerbs());
}

// Where the page opens, and where a language switch returns it: no verb chosen,
// an empty form, and the focus in the list on its first verb. Choosing the verb
// is the first move, so Return alone makes it.
function showStart(verbs) {
  showNoDrill(
    verbs.length
      ? "Pick a verb to start."
      : `No ${lang.name} verbs yet — use "Add a verb".`
  );
  focusList(verbs[0]?.id);
}

// Nothing to drill: either no verb has been chosen yet, or the language has none
// to choose. The clearing is the same apart from the note, so it is one
// function — the drill, the banner that names a verb (and carries the pencil
// that edits one), and the results of whatever was drilled before all go.
function showNoDrill(note) {
  rows = [];
  currentVerbId = null;
  el("drill").innerHTML = "";
  el("verb-indicator").classList.add("hidden");
  renderProgress(); // no rows: no results block, and the list undimmed
  renderPickerList(); // no verb on screen to mark
  // textContent, not innerHTML: lang.name is server data, never markup.
  const p = document.createElement("p");
  p.className = "drill-note";
  p.textContent = note;
  el("drill").appendChild(p);
}

// ---- Adding a verb ------------------------------------------------------

// The job payload from the server is the single source of truth while the panel
// is open, and renderJob() is a pure projection of it — the same discipline the
// drill uses for `rows`. Nothing is ever read back out of the DOM.
let addStream = null;  // live EventSource, if any
let addOnClose = null; // what to do once the panel closes (e.g. drill the new verb)
// What the panel's primary button does right now. Normally it submits the typed
// infinitive; while a question is on screen it answers yes to that question.
let addGoAction = () => submitAddVerb();

const STEP_GLYPH = { pending: "○", running: "◐", done: "✓", failed: "✗", skipped: "–" };

function openAddVerb() {
  closeAddStream();
  addOnClose = null;
  addGoAction = () => submitAddVerb();
  el("add-verb-form").classList.remove("hidden");
  el("add-verb-steps").classList.add("hidden");
  el("add-verb-notes").classList.add("hidden");
  el("add-verb-error").classList.add("hidden");
  el("add-verb-question").classList.add("hidden");
  el("add-verb-subject").textContent = "";
  el("add-verb-input").value = "";
  setAddButtons("Add", "Cancel");
  el("add-verb-panel").classList.remove("hidden");
  el("add-verb-input").focus();
}

function closeAddVerb() {
  closeAddStream();
  el("add-verb-panel").classList.add("hidden");
  const after = addOnClose;
  addOnClose = null;
  if (after) after();
}

function closeAddStream() {
  if (addStream) addStream.close();
  addStream = null;
}

// An empty `go` label hides the primary button — used while the job runs and
// once it has succeeded, when the only thing left to do is close.
function setAddButtons(go, close) {
  const btn = el("add-verb-go");
  btn.textContent = go;
  btn.classList.toggle("hidden", !go);
  el("add-verb-close").textContent = close;
}

function showAddError(message) {
  const err = el("add-verb-error");
  err.textContent = message;
  err.classList.remove("hidden");
}

// `force` waives the regular-verb question, and is how "Yes, add it" answers it.
async function submitAddVerb(force = false) {
  const infinitive = el("add-verb-input").value.trim();
  if (!infinitive) return;
  el("add-verb-error").classList.add("hidden");
  el("add-verb-question").classList.add("hidden");

  // Not via api(): a 400/409 here carries a message worth showing verbatim.
  let res;
  try {
    res = await fetch("/api/verbs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ infinitive, force }),
    });
  } catch (e) {
    return showAddError("Could not reach the server.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    return showAddError(body.detail || `Could not add that verb (${res.status}).`);
  }

  const job = await res.json();
  el("add-verb-form").classList.add("hidden");
  addGoAction = () => submitAddVerb();
  setAddButtons("", "Close");
  renderJob(job);
  followJob(job.job_id);
}

// Both jobs — adding a verb and rewriting its sentences — are watched the same
// way, so the reconnect logic below is written once and told which panel to
// report into. `ui` is {prefix, onFinish, onLost}; prefix names the element ids.
const ADD_PANEL = {
  prefix: "add-verb",
  onFinish: (job) => finishJob(job),
  onLost: (msg) => showAddError(msg),
};

// Watch the job over SSE, falling back to polling if the stream can't be held
// open (a proxy timeout, or a browser that suspended the tab).
function followJob(jobId, panel = ADD_PANEL) {
  closeAddStream();
  let polling = false;
  const source = new EventSource(`/api/verbs/jobs/${jobId}/stream`);
  addStream = source;

  source.onmessage = (e) => {
    const job = JSON.parse(e.data);
    renderJob(job, panel.prefix);
    if (job.status !== "running") {
      closeAddStream();
      panel.onFinish(job);
    }
  };
  source.onerror = () => {
    // Also fires when the server closes the stream after a finished job, which
    // onmessage has already handled — only fall back if it's still running.
    if (source !== addStream || polling) return;
    closeAddStream();
    polling = true;
    pollJob(jobId, panel);
  };
}

async function pollJob(jobId, panel = ADD_PANEL) {
  for (;;) {
    let job;
    try {
      job = await api(`/api/verbs/jobs/${jobId}`);
    } catch (e) {
      return panel.onLost("Lost track of that job — reload to see if it finished.");
    }
    if (!job) return;
    renderJob(job, panel.prefix);
    if (job.status !== "running") return panel.onFinish(job);
    await new Promise((r) => setTimeout(r, 1500));
  }
}

async function finishJob(job) {
  // The lookup succeeded and is reporting what it found before the expensive
  // half runs. Nothing has been written and no sentences drafted yet, so the
  // answer costs only a re-lookup.
  if (job.status === "needs_confirmation") {
    const question = el("add-verb-question");
    question.textContent = job.question;
    question.classList.remove("hidden");
    addGoAction = () => submitAddVerb(true);
    setAddButtons("Add it", "Cancel");
    return;
  }

  if (job.status === "failed") {
    // Keep the typed infinitive so a typo can be fixed and retried.
    el("add-verb-form").classList.remove("hidden");
    showAddError(job.error);
    setAddButtons("Try again", "Close");
    return;
  }

  await loadVerbs();
  addOnClose = () => startVerb(job.verb_id);
  // Sentences written by a model are worth a look before they become the only
  // prompt for a form, so the review panel is offered rather than hidden behind
  // the menu. Either way the drill ends up on the verb just added — reviewing
  // first used to leave it on the previous one, which read as the add having
  // silently failed. loadVerb rather than startVerb on this path: the review
  // panel is about to cover the drill, and focusing a field behind a modal
  // helps nobody.
  addGoAction = () => {
    addOnClose = () => {
      loadVerb(job.verb_id);
      openReview(job.verb_id);
    };
    closeAddVerb();
  };
  // Notes are things the user should actually read — a form the check corrected,
  // or a sentence that stayed weak. Hold the panel open for them either way now
  // that there is something to offer.
  setAddButtons("Review sentences", `Drill ${job.infinitive}`);
}

// ---- Reviewing a verb's example sentences -------------------------------
//
// One card, three states in sequence: the sentences with a comment box each,
// then the job's progress, then the proposals to accept or reject. Nothing is
// written until "Save accepted" — the server keeps the new sentences on the job
// and is sent back only the slots to keep.

let reviewVerbId = null;
let reviewProposals = [];   // what came back, in the order it is displayed
let reviewJobId = null;
// How to name a slot, built while listing the sentences. The proposals come
// back keyed by (tense, person) alone, and raw keys are not what the rest of the
// UI calls them — "Presente indicativo · eu", not "present_indicative · eu".
let reviewLabels = {};

async function openReview(verbId) {
  closeAddStream();
  reviewVerbId = verbId;
  reviewJobId = null;
  reviewProposals = [];
  reviewLabels = {};
  el("review-comment").value = "";
  el("review-error").classList.add("hidden");
  el("review-proposals").classList.add("hidden");
  el("review-steps").classList.add("hidden");
  el("review-notes").classList.add("hidden");
  el("review-compose").classList.remove("hidden");
  setReviewButtons("Rewrite", "Close");
  el("review-panel").classList.remove("hidden");

  const list = el("review-list");
  list.innerHTML = "";
  let data;
  try {
    data = await api(`/api/verbs/${verbId}/examples`);
  } catch (e) {
    return showReviewError("Could not load the sentences.");
  }
  if (!data) return;
  el("review-subject").textContent = data.infinitive;

  for (const block of data.blocks) {
    const h = document.createElement("h3");
    h.className = "review-tense";
    h.textContent = tenseText(block);
    list.appendChild(h);
    for (const row of block.rows) {
      reviewLabels[`${row.tense}/${row.person}`] = [tenseText(block), row.label]
        .filter(Boolean)
        .join(" · ");
      list.appendChild(reviewRow(row));
    }
  }
}

// One sentence, with somewhere to say what is wrong with it. textContent
// throughout: every string here is model-generated.
function reviewRow(row) {
  const div = document.createElement("div");
  div.className = "review-row";
  div.innerHTML =
    `<div class="rr-head"><span class="rr-person"></span><b class="rr-form"></b></div>` +
    `<div class="rr-en"></div><div class="rr-native"></div>` +
    `<input class="rr-comment" type="text" placeholder="what should change?" />`;
  div.querySelector(".rr-person").textContent = row.label;
  div.querySelector(".rr-form").textContent = row.form;
  div.querySelector(".rr-en").textContent = row.example_en || "(no sentence yet)";
  div.querySelector(".rr-native").textContent = row.example_native || "";
  div.dataset.tense = row.tense;
  div.dataset.person = row.person;
  return div;
}

function showReviewError(message) {
  const err = el("review-error");
  err.textContent = message;
  err.classList.remove("hidden");
}

// An empty `go` label hides the primary button, as in the add panel.
function setReviewButtons(go, close) {
  const btn = el("review-go");
  btn.textContent = go;
  btn.classList.toggle("hidden", !go);
  el("review-close").textContent = close;
}

const REVIEW_PANEL = {
  prefix: "review",
  onFinish: (job) => finishReview(job),
  onLost: (msg) => showReviewError(msg),
};

async function submitReview() {
  const comments = [...el("review-list").querySelectorAll(".review-row")]
    .map((row) => ({
      tense: row.dataset.tense,
      person: row.dataset.person,
      comment: row.querySelector(".rr-comment").value.trim(),
    }))
    .filter((c) => c.comment);
  const comment = el("review-comment").value.trim();
  if (!comments.length && !comment) {
    return showReviewError("Comment on a sentence, or on all of them.");
  }

  el("review-error").classList.add("hidden");
  let res;
  try {
    res = await fetch(`/api/verbs/${reviewVerbId}/examples/revise`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comments, comment }),
    });
  } catch (e) {
    return showReviewError("Could not reach the server.");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    return showReviewError(body.detail || `Could not start that (${res.status}).`);
  }

  const job = await res.json();
  reviewJobId = job.job_id;
  el("review-compose").classList.add("hidden");
  setReviewButtons("", "Close");
  renderJob(job, "review");
  followJob(job.job_id, REVIEW_PANEL);
}

function finishReview(job) {
  if (job.status === "failed") {
    el("review-compose").classList.remove("hidden");
    showReviewError(job.error);
    setReviewButtons("Try again", "Close");
    return;
  }
  reviewProposals = job.proposals || [];
  if (!reviewProposals.length) {
    // The job's own notes say why, when there is a why.
    showReviewError("Nothing to change — the sentences came back as they were.");
    el("review-compose").classList.remove("hidden");
    setReviewButtons("Try again", "Close");
    return;
  }
  renderProposals(); // which sets the buttons, from how many are accepted
}

// Each proposal is accepted or rejected on its own; the checkbox is the whole
// verdict, so there is no separate reject button to leave out of sync.
function renderProposals() {
  const box = el("review-proposals");
  box.innerHTML =
    `<div class="rp-head">` +
    `<span id="rp-count"></span>` +
    `<button class="btn ghost sm" type="button" id="rp-all">Accept all</button>` +
    `<button class="btn ghost sm" type="button" id="rp-none">Reject all</button>` +
    `</div>`;
  box.classList.remove("hidden");

  for (const [i, p] of reviewProposals.entries()) {
    const div = document.createElement("div");
    div.className = "rp-item";
    div.innerHTML =
      `<label class="rp-accept"><input type="checkbox" checked /> <span class="rp-where"></span></label>` +
      `<div class="rp-reason"></div>` +
      `<div class="rp-before"><s class="rp-before-en"></s><s class="rp-before-native"></s></div>` +
      `<div class="rp-after"><span class="rp-after-en"></span><b class="rp-after-native"></b></div>`;
    const where = reviewLabels[`${p.tense}/${p.person}`] || `${p.tense} · ${p.person}`;
    div.querySelector(".rp-where").textContent = `${where} — ${p.form}`;
    div.querySelector(".rp-reason").textContent = p.reason;
    div.querySelector(".rp-before-en").textContent = p.before_en;
    div.querySelector(".rp-before-native").textContent = p.before_native;
    div.querySelector(".rp-after-en").textContent = p.after_en;
    div.querySelector(".rp-after-native").textContent = p.after_native;
    div.querySelector("input").addEventListener("change", renderProposalCount);
    div.dataset.index = i;
    box.appendChild(div);
  }

  el("rp-all").addEventListener("click", () => setAllProposals(true));
  el("rp-none").addEventListener("click", () => setAllProposals(false));
  renderProposalCount();
}

function proposalBoxes() {
  return [...el("review-proposals").querySelectorAll(".rp-item input")];
}

function setAllProposals(on) {
  for (const box of proposalBoxes()) box.checked = on;
  renderProposalCount();
}

function renderProposalCount() {
  const accepted = proposalBoxes().filter((b) => b.checked).length;
  el("rp-count").textContent =
    `${accepted} of ${reviewProposals.length} change${reviewProposals.length === 1 ? "" : "s"} accepted`;
  // Nothing accepted is a valid answer, but "Save" would be a lie.
  setReviewButtons(accepted ? "Save accepted" : "", "Discard");
}

async function saveReview() {
  const accept = [...el("review-proposals").querySelectorAll(".rp-item")]
    .filter((d) => d.querySelector("input").checked)
    .map((d) => reviewProposals[Number(d.dataset.index)])
    .map((p) => ({ tense: p.tense, person: p.person }));

  let body;
  try {
    body = await api(`/api/verbs/${reviewVerbId}/examples/apply`, {
      method: "POST",
      body: JSON.stringify({ job_id: reviewJobId, accept }),
    });
  } catch (e) {
    return showReviewError("Could not save those changes.");
  }
  if (!body) return;
  closeReview();
  // The drill holds its own copy of every sentence, so it has to be reloaded
  // for the new ones to appear.
  if (reviewVerbId === currentVerbId) await loadVerb(currentVerbId);
  showToast(`Saved ${body.applied} sentence${body.applied === 1 ? "" : "s"}`);
}

function closeReview() {
  closeAddStream();
  el("review-panel").classList.add("hidden");
}


function renderJob(job, prefix = "add-verb") {
  // Name the verb in the heading: once the form is hidden the steps are the
  // only thing on screen, and none of them says what is being added.
  el(`${prefix}-subject`).textContent = job.infinitive;

  const list = el(`${prefix}-steps`);
  list.classList.remove("hidden");
  list.innerHTML = "";
  for (const step of job.steps) {
    const li = document.createElement("li");
    li.className = `job-step ${step.status}`;
    li.innerHTML =
      `<span class="js-glyph" aria-hidden="true"></span>` +
      `<span class="js-body">` +
      `<span class="js-label"></span><span class="js-detail"></span>` +
      `<span class="js-bar hidden"><i></i></span>` +
      `</span>`;
    li.querySelector(".js-glyph").textContent = STEP_GLYPH[step.status] || "○";
    li.querySelector(".js-label").textContent = step.label;
    // Details are server-composed and can quote model output: textContent only.
    li.querySelector(".js-detail").textContent = step.detail || "";
    if (step.total) {
      const bar = li.querySelector(".js-bar");
      bar.classList.remove("hidden");
      const pct = Math.round((100 * (step.done || 0)) / step.total);
      bar.querySelector("i").style.width = `${pct}%`;
    }
    list.appendChild(li);
  }

  const notes = el(`${prefix}-notes`);
  notes.innerHTML = "";
  notes.classList.toggle("hidden", !job.notes.length);
  for (const text of job.notes) {
    const li = document.createElement("li");
    li.textContent = text;
    notes.appendChild(li);
  }
}

// Reflect the current interface prefs in the DOM: show/hide the accent bar.
// The bar lives in the sticky header, so its height changes what the drill must
// scroll clear of — recompute the sticky offset whenever it toggles.
function applyInterface() {
  el("accent-bar").classList.toggle("hidden", !ui.show_accents);
  setCheck(el("menu-labels"), ui.labels === "en");
  setCheck(el("menu-accents"), ui.show_accents);
  updateStickyHeight();
}

function setCheck(item, on) {
  item.querySelector(".um-check").textContent = on ? "✓" : "";
  item.setAttribute("aria-checked", String(on));
}

// Keep drill sections from scrolling under the two pinned headers — the page's
// and the drill's banner below it: expose their live height as a CSS var that
// .tense-block uses for scroll-margin-top. The page header's own height is what
// everything else that sticks stops below. Also where the columns start on the
// page, which the verb column's height is cut to, so its footer is on screen.
function updateStickyHeight() {
  const top = document.querySelector(".topbar").offsetHeight;
  const h = el("sticky-header").offsetHeight;
  const root = document.documentElement.style;
  root.setProperty("--topbar-h", `${top}px`);
  root.setProperty("--sticky-h", `${top + h + 8}px`);
  root.setProperty("--col-top", `${el("app").offsetTop}px`);
}

async function loadVerb(verbId) {
  currentVerbId = verbId;
  const data = await api(`/api/verbs/${verbId}/forms`);
  renderDrill(data);
  renderPickerList(); // the list marks the verb being conjugated, as the banner names it
  updateVerbIndicator(verbId);
}

// Start (or restart) a verb fresh: reload it, jump to the top, and focus the
// first field. The list is the only way in — including back to the verb just
// finished, which is one Up away once the drill is done.
async function startVerb(verbId) {
  await loadVerb(verbId);
  rows[0]?.input.focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// Sticky banner naming the verb being drilled, so it stays visible on scroll.
function updateVerbIndicator(verbId) {
  const verb = verbOrder.find((v) => v.id == verbId);
  const label = verb ? verb.infinitive : "";
  el("verb-indicator").querySelector(".vi-verb").textContent = label;
  el("verb-indicator").classList.toggle("hidden", !label);
  // The banner is most of the pinned header's height, and it is hidden when the
  // page loads; measured then, a tense scrolled to the top lands behind it.
  updateStickyHeight();
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
      const row = makeRow(r, tenseText(block));
      wrap.appendChild(row.el);
      rows.push(row);
    }
    drill.appendChild(wrap);
  }
  renderProgress(); // fresh drill: "0 of Y"
}

// Build a row's DOM once and return its state object. All later changes go
// through the state + renderRow(); the element is never queried for truth.
function makeRow(data, tenseLabel) { // tenseLabel: the heading text, mood included
  const div = document.createElement("div");
  div.className = "row";
  div.innerHTML =
    `<div class="row-line">` +
    `<span class="person"></span>` +
    `<input type="text" autocomplete="off" autocapitalize="off" spellcheck="false" />` +
    `<span class="mark"></span>` +
    `</div>` +
    `<div class="row-example"></div>` +
    `<div class="row-example-pt"></div>` +
    `<div class="row-alts"></div>`;
  div.querySelector(".person").textContent = data.label;
  // English example is the always-visible prompt (textContent: model-generated).
  if (data.example_en)
    div.querySelector(".row-example").textContent = data.example_en;

  const input = div.querySelector("input");
  const row = {
    // immutable form data
    formId: data.form_id,
    answer: data.answer,
    // Where this row sits, so the end-of-drill summary can name it without
    // reading it back out of the DOM.
    tenseLabel,
    personLabel: data.label,
    // Other forms that are equally correct — Portuguese offers genuine
    // alternatives in some cells (oiço/ouço; the two past participles). The
    // server grades against the same list; this copy is what lets grading stay
    // local and synchronous.
    variants: data.variants || [],
    exampleNative: data.example_native || "",
    el: div,
    input,
    note: null, // the "missed it" note element, when present
    // mutable answer state
    graded: false,       // has been checked with a non-empty value
    correct: false,      // current value matches one of the accepted forms
    matched: null,       // which accepted form it matched, so alts can exclude it
    recorded: false,     // first attempt already sent to the server
    firstWrong: false,   // that first attempt was wrong (a mistake on record)
    typedWrong: "",      // what they first typed, for the resolved note
    attemptId: null,     // server id, to reclassify as a typo
    dismissedTypo: false,// "just a typo" clicked — no longer counts as a mistake
    attemptSeq: 0,       // bumped by clearError to abandon an in-flight record
  };

  input.addEventListener("focus", () => {
    lastFocused = input;
    div.classList.add("focused");
  });
  input.addEventListener("blur", (e) => {
    div.classList.remove("focused");
    // Stepping over to the verb list (Cmd+K, or the switch dialog a click on it
    // opens) is not answering: the field keeps what is in it, ungraded, for
    // when you come back.
    if (e.relatedTarget?.closest(".verb-col, #switch-dialog")) return;
    gradeRow(row);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      // Some browsers revert an input's value on Escape; the key is ours here.
      e.preventDefault();
      onEscape(row);
      return;
    }
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
    advanceFrom(row);
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
  // Any accepted form counts. Whichever one they typed is remembered so the
  // note afterwards can offer the ones they didn't.
  row.matched = accepted(row).find((f) => normalize(f) === normalize(text)) || null;
  row.correct = row.matched !== null;
  row.graded = true;

  // Record only the FIRST attempt per form — that's the honest score.
  if (!row.recorded) {
    row.recorded = true;
    recordAttempt(row, text);
  }

  renderRow(row);
  renderProgress();
  if (row.correct && !wasCorrect) showToast("Correct!", row.exampleNative); // pop once, on the transition
}

// Persist the first attempt in the background. The server also returns the
// authoritative verdict and an attempt id; if it was wrong, surface the "missed
// it" note (which needs that id for the "just a typo" reclassification). Grading
// and focus never wait on this — it runs after the row is already marked.
async function recordAttempt(row, text) {
  const seq = ++row.attemptSeq;
  let result;
  try {
    result = await api("/api/attempts", {
      method: "POST",
      body: JSON.stringify({ form_id: row.formId, submitted_text: text }),
    });
  } catch (e) {
    // Only reopen recording if this is still the attempt of record — clearError
    // has already reopened it otherwise, and may have a newer one in flight.
    if (row.attemptSeq === seq) row.recorded = false;
    console.error("recording attempt failed", e);
    return;
  }
  // Escape cleared the field while this was in flight. The answer it carries was
  // taken back, so forgive it on the server and leave the ungraded row alone —
  // marking it wrong now would restore the error the user just dismissed.
  if (row.attemptSeq !== seq) {
    if (!result.is_correct) forgiveAttempt(result.attempt_id);
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

// Reclassify a recorded attempt as a typo, so it stops counting against the
// score. The one server call behind both "just a typo" and Escape.
const forgiveAttempt = (attemptId) =>
  api(`/api/attempts/${attemptId}/verdict`, {
    method: "POST",
    body: JSON.stringify({ verdict: "typo" }),
  });

// ``advance`` is what the button does: the note it lives in is about to be
// removed from under the cursor, so focus has to go somewhere. Forgiving the
// previous field from the keyboard passes false — focus is already in the field
// after it, and advancing from the forgiven row would drag it backwards.
async function dismissTypo(row, { advance = true } = {}) {
  await forgiveAttempt(row.attemptId);
  row.dismissedTypo = true;
  renderRow(row);   // drops the note — and with it the button holding focus
  renderProgress(); // one fewer mistake on record
  if (advance) advanceFrom(row); // carry on where the keyboard left off
}

// Take back the grade on a field, leaving it as though it had never been
// answered — mark, note, mistake and all. Not the same as forgiving: a stray Tab
// grades whatever is half-typed, and that answer should not stand at all, so the
// next one becomes the attempt of record. Leave the field wrong again and the
// error comes straight back.
//
// The typed text stays put. You reached this field by mistyping in it, and
// finishing the word is the usual next move.
async function clearError(row) {
  const attemptId = row.attemptId;
  row.attemptSeq++; // abandons any record still in flight (see recordAttempt)
  row.graded = false;
  row.correct = false;
  row.matched = null;
  row.firstWrong = false;
  row.typedWrong = "";
  row.attemptId = null;
  row.dismissedTypo = false;
  row.recorded = false; // the next answer is the one that counts
  renderRow(row);
  renderProgress(); // one fewer answered, and the results block hides again
  if (attemptId) await forgiveAttempt(attemptId);
}

// A field currently showing an error, which Escape takes back.
const hasError = (row) => !!row && row.graded && !row.correct;

// A mistake still open to being forgiven: on record, not already forgiven, and
// carrying the server id the reclassification posts to. Returns the row so it
// composes as a lookup.
const forgivable = (row) =>
  row && row.firstWrong && !row.dismissedTypo && row.attemptId ? row : null;

// Escape, from a drill field. Two jobs, because a mistake you can still fix and
// one you have already moved past want opposite things:
//
//   - this field is wrong → take the grade back and let it be retyped. This is
//     the stray-Tab case, where the answer graded was never meant to be sent.
//   - this field is fine → forgive the mistake on the field just before it,
//     which is the one you tabbed off. Retrying is no longer on offer there, so
//     forgiving is all that is left, exactly as the button does.
//
// Exactly one field back, never a search for the nearest mistake: forgiving is a
// claim about what you just typed, and scanning further would let one keystroke
// rewrite a mistake made minutes ago somewhere off screen.
function onEscape(row) {
  if (hasError(row)) return void clearError(row);
  const previous = forgivable(rows[rows.indexOf(row) - 1]);
  if (previous) dismissTypo(previous, { advance: false });
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
    row.graded && row.exampleNative ? row.exampleNative : "";

  renderAlternatives(row);
  renderNote(row);
}

// Every form that counts as correct here, displayed one first.
function accepted(row) {
  return [row.answer, ...row.variants];
}

// Once answered, name the other forms that would also have been accepted —
// finding out `ouço` was fine too is the moment you learn it exists. Excludes
// whatever they actually typed, so it reads the same whichever one they chose,
// and stays silent when there's nothing to add (almost every row).
function renderAlternatives(row) {
  const el = row.el.querySelector(".row-alts");
  const others = row.graded
    ? accepted(row).filter((f) => normalize(f) !== normalize(row.matched || row.answer))
    : [];
  el.textContent = others.length ? `also correct: ${others.join(", ")}` : "";
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
      `<button class="typo-btn" type="button">just a typo</button>` +
      `<span class="esc-hint"></span>`;
    hint.querySelector(".typo-btn").addEventListener("click", () => dismissTypo(row));
    row.el.after(hint);
    row.note = hint;
  }
  row.note.classList.toggle("resolved", row.correct);
  // Escape retries a field that is still wrong; once it has been corrected the
  // key means something else entirely, so the hint goes away with the error.
  row.note.querySelector(".esc-hint").textContent = row.correct ? "" : "esc to retry";
  // Build with textContent so a user's typed value can't inject markup.
  const at = row.note.querySelector(".ans-text");
  at.textContent = row.correct ? "you typed: " : "answer: ";
  const b = document.createElement("b");
  b.textContent = row.correct ? row.typedWrong : row.answer;
  at.appendChild(b);
}

// The progress summary, derived purely from row state. Drives the sticky
// header readout always, and the results block once the drill is complete.
function renderProgress() {
  const total = rows.length;
  const filled = rows.filter((r) => r.graded).length;
  const mistakes = rows.filter((r) => r.firstWrong && !r.dismissedTypo).length;
  // Every field answered, and the cursor not in one still showing a wrong
  // answer. The row's rule is that you stay put until it is fixed, and the rest
  // of the drill being answered does not overrule it — otherwise the last field
  // is the one field you can leave wrong. Fixing it, or clicking away from it,
  // grades it again and brings completion back round.
  const complete = total > 0 && filled === total && !wrongRowFocused();
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

  // The verb list steps back until the drill is complete.
  el("app").classList.toggle("drilling", total > 0 && !complete);

  // The results block appears only once every field is answered.
  const results = el("results");
  results.classList.toggle("hidden", !complete);
  const summary = el("results-summary");
  summary.textContent = complete ? text : "";
  summary.classList.toggle("perfect", perfect);

  renderMistakes(complete);

  // The finish runs once per drill, the first time it is complete.
  // Un-answering a field (esc to retry) arms it again, so fixing a late mistake
  // still ends with the same jump to the top.
  if (!complete) drillFinished = false;
  else if (!drillFinished) {
    drillFinished = true;
    finishDrill();
  }
}

// Done: back to the top, where the results block is, with the focus in the verb
// list on the next verb. Deferred to the next turn of the
// event loop because renderProgress runs inside the last field's own blur or
// keydown handler, and taking focus out from under one is fragile. A timeout
// rather than requestAnimationFrame: rAF never fires in a tab that isn't being
// painted, and this has to happen whether or not the page is on screen.
function finishDrill() {
  setTimeout(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
    // The guard: the Enter that answered the last field is consumed by the row
    // it was typed in (see makeRow), but a habitual second Enter would land in
    // the list and skip past the results unread, so the list ignores one for a
    // moment after a focus it did not ask for.
    pickerFocusedAt = Date.now();
    focusList(nextVerb()?.id);
  }, 0);
}

// Is the cursor in a field that is currently answered wrong?
const wrongRowFocused = () =>
  rows.some((r) => r.input === document.activeElement && r.graded && !r.correct);

// The end-of-drill review: every form that was missed first time, with the
// answer alongside what was actually typed. Same set the score counts, so a
// mistake forgiven as a typo drops out of both.
//
// Only rendered once the drill is complete — mid-drill it would be a running
// tally of failures next to the fields still being worked on.
function renderMistakes(complete) {
  const list = el("results-mistakes");
  list.innerHTML = "";
  if (!complete) return;

  for (const row of rows.filter((r) => r.firstWrong && !r.dismissedTypo)) {
    const li = document.createElement("li");
    li.innerHTML =
      `<span class="fm-where"></span>` +
      `<b class="fm-answer"></b>` +
      `<span class="fm-typed">you typed <s></s></span>`;
    // textContent throughout: the answer is model-generated and the typed value
    // is whatever the user put in the box.
    li.querySelector(".fm-where").textContent = row.personLabel
      ? `${row.tenseLabel} · ${row.personLabel}`
      : row.tenseLabel;
    li.querySelector(".fm-answer").textContent = row.answer;
    li.querySelector(".fm-typed s").textContent = row.typedWrong;
    list.appendChild(li);
  }
}

// Brief fixed-position "Correct!" toast. Never focusable, so it doesn't
// interrupt typing; fades itself out shortly after appearing. An optional
// second line carries detail (the pt-PT sentence on a correct answer). How long
// it dwells is the server's TOAST_MS env var, delivered with the settings.
let toastMs = 2800;
let toastTimer = null;
function showToast(msg, detail) {
  const t = el("toast");
  t.textContent = "";
  const head = document.createElement("div");
  head.className = "toast-msg";
  head.textContent = msg;
  t.appendChild(head);
  if (detail) {
    const d = document.createElement("div");
    d.className = "toast-detail";
    d.textContent = detail; // model-generated: never innerHTML
    t.appendChild(d);
  }
  t.classList.toggle("has-detail", Boolean(detail));
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), toastMs);
}

// ---- Navigation helpers (view concerns: focus + scroll) -----------------

// Leave a finished row: the next person, or the next tense block's first field
// when this was the section's last. No-op once every field is answered — the
// finish takes focus to the verb list, and moving it into another
// field here would fight that.
function advanceFrom(row) {
  if (rows.every((r) => r.graded)) return;
  if (isLastInSection(row.input)) scrollToNextSection(row.el); // next tense to top
  else focusNextInput(row.input); // next person
}

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
