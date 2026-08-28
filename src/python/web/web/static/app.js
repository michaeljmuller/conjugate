"use strict";

const el = (id) => document.getElementById(id);
const normalize = (s) => s.trim().toLowerCase().split(/\s+/).join(" ");

let lastFocused = null; // input to receive accent-bar insertions
let currentVerbId = null;
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
  buildAccentBar();
  applyInterface();

  const selTop = el("verb-select");
  const selBottom = el("verb-select-bottom");
  selTop.addEventListener("change", () => startVerb(selTop.value));
  selBottom.addEventListener("change", () => startVerb(selBottom.value));

  const verbs = await loadVerbs();
  if (verbs.length) await loadVerb(verbs[0].id);
  updateStickyHeight();
  window.addEventListener("resize", updateStickyHeight);
}

// (Re)fill both verb pickers from the server. Called at startup and again
// whenever a verb is added, so the new one appears without a reload.
async function loadVerbs() {
  const verbs = await api("/api/verbs");
  const options = verbs
    .map((v) => `<option value="${v.id}"></option>`)
    .join("");
  for (const id of ["verb-select", "verb-select-bottom"]) {
    const sel = el(id);
    const keep = sel.value;
    sel.innerHTML = options;
    // textContent: infinitives are model-generated, so never interpolated as HTML.
    [...sel.options].forEach((opt, i) => (opt.textContent = verbs[i].infinitive));
    if (keep) sel.value = keep;
  }
  return verbs;
}

function buildAccentBar() {
  el("accent-bar").innerHTML = lang.accents.map(
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

// The user's name is a dropdown: "Tense configuration" opens the settings
// panel, and "Sign out" sits last. Closes on outside click or Escape.
// Which commit is serving this page, from /healthz — the same answer curl gets,
// so the UI and a scripted check can never disagree. Quiet on failure: not
// knowing the version is not worth an error message in front of a drill.
async function showBuild() {
  const el_ = el("um-build");
  if (!el_) return;
  try {
    const res = await fetch("/healthz");
    if (!res.ok) return;
    const { version, committed } = await res.json();
    // A date is what a person reads; the hash is what they quote back.
    const when = committed ? new Date(committed) : null;
    el_.textContent = when && !isNaN(when)
      ? `${version} · ${when.toLocaleDateString(undefined, {
          year: "numeric", month: "short", day: "numeric",
        })}`
      : version;
    el_.title = committed || "";
  } catch (e) {
    /* leave it blank */
  }
}


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
    `<span class="um-who">` +
    `<span class="um-email"></span>` +
    `<span class="um-build" id="um-build"></span>` +
    `</span>` +
    `</div>` +
    `<button class="um-item" role="menuitem" id="menu-add-verb">Add a verb</button>` +
    `<button class="um-item" role="menuitem" id="menu-review">Example sentences</button>` +
    `<button class="um-item" role="menuitem" id="menu-tenses">Tense configuration</button>` +
    `<button class="um-item" role="menuitem" id="menu-interface">Interface</button>` +
    `<div class="um-divider" role="separator"></div>` +
    `<button class="um-item um-danger" role="menuitem" id="menu-logout">` +
    `<span class="um-arrow" aria-hidden="true">→</span> Sign out</button>` +
    `</div>`;
  // textContent: name/email are untrusted profile data.
  area.querySelector(".umb-name").textContent = name;
  area.querySelector(".um-email").textContent = email;
  showBuild();

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
  el("menu-add-verb").addEventListener("click", () => {
    setOpen(false);
    openAddVerb();
  });
  // Acts on the verb on screen — there is no other verb it could mean.
  el("menu-review").addEventListener("click", () => {
    setOpen(false);
    if (currentVerbId) openReview(currentVerbId);
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

// Take what the server says about the drilled language and the interface prefs.
// Everything language-specific — the name to show, which accented letters the
// bar offers — comes from here rather than being baked into the client.
function applySettings(data) {
  ui = data.interface;
  lang = {
    code: data.language,
    name: data.language_name,
    accents: data.accents || [],
    available: data.languages || [],
  };
}

function openInterface() {
  el("iface-accents").checked = ui.show_accents;
  el("iface-language").innerHTML = lang.available
    .map((l) => `<option value="${l.code}">${l.name}</option>`)
    .join("");
  el("iface-language").value = lang.code;
  // The "native names" option is labelled with the language it means.
  el("iface-native-label").textContent = lang.name;
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
  const language = el("iface-language").value;
  const switched = language !== lang.code;
  const data = await api("/api/settings", {
    method: "PUT",
    body: JSON.stringify({ language, interface: { labels, show_accents } }),
  });
  applySettings(data);
  // A different language means a different accent bar.
  buildAccentBar();
  applyInterface();
  closeInterface();

  if (switched) {
    // The verb list is per language, so the old selection is gone. Start on the
    // new language's first verb, or clear the drill if it has none yet.
    currentVerbId = null;
    const verbs = await loadVerbs();
    if (verbs.length) await loadVerb(verbs[0].id);
    else showEmptyLanguage();
  } else if (currentVerbId) {
    await loadVerb(currentVerbId); // relabel the drill in the new label language
  }
}

// A language with no verbs yet: clear the drill rather than leave the previous
// language's rows on screen.
function showEmptyLanguage() {
  rows = [];
  el("drill").innerHTML = "";
  // The banner names the verb being drilled, and there is no longer one.
  el("verb-indicator").classList.add("hidden");
  // textContent, not innerHTML: lang.name is server data, never markup.
  const note = document.createElement("p");
  note.className = "empty-language";
  note.textContent = `No ${lang.name} verbs yet — add one from the avatar menu.`;
  el("drill").appendChild(note);
  for (const id of ["verb-select", "verb-select-bottom"]) el(id).innerHTML = "";
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
  // the menu. Closing instead still drills the verb.
  addGoAction = () => {
    addOnClose = null;
    closeAddVerb();
    openReview(job.verb_id);
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
  input.addEventListener("blur", () => {
    div.classList.remove("focused");
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
  if (row.correct && !wasCorrect) showToast("Correct!"); // pop once, on the transition
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
  renderProgress(); // one fewer answered, and the footer hides again
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

  renderMistakes(complete);

  // Bring the freshly revealed controls into view (they're below the fold).
  if (justRevealed) footer.scrollIntoView({ behavior: "smooth", block: "end" });
}

// The end-of-drill review: every form that was missed first time, with the
// answer alongside what was actually typed. Same set the score counts, so a
// mistake forgiven as a typo drops out of both.
//
// Only rendered once the drill is complete — mid-drill it would be a running
// tally of failures next to the fields still being worked on.
function renderMistakes(complete) {
  const list = el("footer-mistakes");
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

// Leave a finished row: the next person, or the next tense block's first field
// when this was the section's last. No-op once every field is answered — the
// footer reveal wins there, and moving focus would scroll the field back into
// view over it.
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
