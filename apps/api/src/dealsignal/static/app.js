/* DealSignal UI.
   Two rules shape this file: a score never appears without its reasons, and a
   failure is always shown in words rather than an empty table. */



const form = document.getElementById("buybox-form");
const statusLine = document.getElementById("form-status");
const resultsBody = document.getElementById("results-body");
const resultsMeta = document.getElementById("results-meta");
const button = document.getElementById("search-button");
const detail = document.getElementById("detail");
const detailBody = document.getElementById("detail-body");

/* Industries and regions are defined once, in the API, and fetched here. */
function fillOptions(select, options) {
  select.innerHTML = options
    .map((option) => `<option value="${option.key}">${escapeHtml(option.label)}</option>`)
    .join("");
}

const metaReady = fetch("/meta")
  .then((response) => response.json())
  .then((meta) => {
    fillOptions(document.getElementById("industry"), meta.industries);
    fillOptions(document.getElementById("seed-industry"), meta.industries);
    fillOptions(document.getElementById("seed-region"), meta.regions);
    return meta;
  });

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
}

/* The mode changes what a good result means, so the words around the form change too. */
const MODE_COPY = {
  acquisition: {
    hint: "What you are looking to buy. Saved once, reused for every search.",
    button: "Find companies to buy",
    tagline: "Businesses worth buying, ranked, with the reasons shown.",
    name: "HVAC, Dallas",
  },
  sales: {
    hint: "Who you want to sell to. Saved once, reused for every search.",
    button: "Find prospects",
    tagline: "Companies likely to buy from you, ranked, with the reasons shown.",
    name: "HVAC prospects, Dallas",
  },
};

function applyMode(mode) {
  const copy = MODE_COPY[mode];
  document.getElementById("mode-hint").textContent = copy.hint;
  document.getElementById("search-button").textContent = copy.button;
  document.querySelector(".tagline").textContent = copy.tagline;
  const nameField = form.elements.namedItem("name");
  if (Object.values(MODE_COPY).some((entry) => entry.name === nameField.value)) {
    nameField.value = copy.name;  // only replace our own default, never the user's text
  }
}

form.querySelectorAll('input[name="mode"]').forEach((radio) => {
  radio.addEventListener("change", () => applyMode(radio.value));
});
applyMode("acquisition");

/** Every API call goes through here, so an error always reaches the user. */
async function callApi(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = body?.error?.message ?? `Request failed (${response.status}).`;
    throw new Error(message);
  }
  return body;
}

function setStatus(message, isError = false) {
  statusLine.textContent = message;
  statusLine.classList.toggle("error", isError);
}

function numberOrNull(value) {
  const parsed = Number(value);
  return value === "" || Number.isNaN(parsed) ? null : parsed;
}

/* ---------- Saved Buy Boxes ---------- */

const savedSelect = document.getElementById("saved-buybox");
let savedBuyBoxes = new Map();
let formEdited = false;

/** The picker is a convenience: if the list fails to load, the form still works. */
async function loadSavedBuyBoxes(selectedId = "") {
  try {
    const boxes = await callApi("/buy-boxes");
    savedBuyBoxes = new Map(boxes.map((box) => [box.id, box]));
    savedSelect.innerHTML = `<option value="">New Buy Box</option>` + boxes.map((box) =>
      `<option value="${box.id}">${escapeHtml(box.name)}${box.mode === "sales" ? " (sell to)" : ""}</option>`
    ).join("");
    savedSelect.value = selectedId;
  } catch {
    savedSelect.value = "";
  }
}

function fillForm(box) {
  form.querySelector(`input[name="mode"][value="${box.mode}"]`).checked = true;
  applyMode(box.mode);
  form.elements.namedItem("name").value = box.name;
  form.elements.namedItem("industry").value = box.industries[0] ?? "";
  form.elements.namedItem("country").value = box.countries[0] ?? "US";
  form.elements.namedItem("city").value = box.city ?? "";
  for (const key of ["revenue_min", "revenue_max", "employees_min", "employees_max"]) {
    form.elements.namedItem(key).value = box[key] ?? "";
  }
}

savedSelect.addEventListener("change", async () => {
  const box = savedBuyBoxes.get(savedSelect.value);
  if (!box) return;
  await metaReady;  // the industry options must exist before one can be selected
  fillForm(box);
  formEdited = false;
  await runSearch(box.id);
});

/* Changing the criteria makes a new Buy Box; the saved one is left as it was. */
form.addEventListener("input", () => { formEdited = true; });

async function runSearch(buyBoxId) {
  button.disabled = true;
  setStatus("Scoring companies…");
  try {
    const search = await callApi(`/buy-boxes/${buyBoxId}/search`, { method: "POST" });
    renderResults(search);
    showExportLinks(buyBoxId, search.results.length);
    latestSearch = search;
    document.getElementById("results-toggle").hidden = search.results.length === 0;
    if (currentResultsView() === "map") drawMap(search);
    setStatus(`Scored ${search.results.length} companies.`);
  } catch (error) {
    setStatus(error.message, true);
    resultsBody.innerHTML = `<p class="empty">The search did not finish, so nothing is shown.</p>`;
    resultsMeta.textContent = "";
  } finally {
    button.disabled = false;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (savedSelect.value && !formEdited) {
    await runSearch(savedSelect.value);
    return;
  }

  const data = new FormData(form);
  button.disabled = true;
  setStatus("Saving the Buy Box…");
  let buyBox;
  try {
    buyBox = await callApi("/buy-boxes", {
      method: "POST",
      body: JSON.stringify({
        name: data.get("name"),
        mode: data.get("mode"),
        industries: [data.get("industry")],
        countries: [data.get("country")],
        city: data.get("city") || null,
        revenue_min: numberOrNull(data.get("revenue_min")),
        revenue_max: numberOrNull(data.get("revenue_max")),
        employees_min: numberOrNull(data.get("employees_min")),
        employees_max: numberOrNull(data.get("employees_max")),
      }),
    });
  } catch (error) {
    setStatus(error.message, true);
    button.disabled = false;
    return;
  }
  formEdited = false;
  await loadSavedBuyBoxes(buyBox.id);
  await runSearch(buyBox.id);
});

loadSavedBuyBoxes();

/** Export is offered only when there is something to export. */
function showExportLinks(buyBoxId, resultCount) {
  const links = document.getElementById("export-links");
  links.hidden = resultCount === 0;
  document.getElementById("export-csv").href = `/buy-boxes/${buyBoxId}/export?format=csv`;
  document.getElementById("export-xlsx").href = `/buy-boxes/${buyBoxId}/export?format=xlsx`;
}

function renderResults(search) {
  const withheld = search.withheld
    ? ` · ${search.withheld} withheld as do-not-contact`
    : "";
  resultsMeta.textContent =
    `${search.considered} companies considered · ${search.high_confidence} with high confidence${withheld}`;

  if (!search.results.length) {
    resultsBody.innerHTML =
      `<p class="empty">No stored companies match this Buy Box yet. Seed a region first.</p>`;
    return;
  }

  const rows = search.results.map((row, index) => {
    const reasons = row.reasons.slice(0, 3).map((reason) =>
      `<span class="chip ${reason.points === 0 ? "zero" : ""}">${escapeHtml(reason.reason)}</span>`
    ).join("");

    return `
      <tr data-company="${row.company_id}" tabindex="0">
        <td class="rank">${index + 1}</td>
        <td>
          <div class="name">${escapeHtml(row.name)}</div>
          <div class="sub">${row.score === null
            ? "not enough data yet, enrich to score"
            : row.missing_signals.length
              ? `${row.missing_signals.length} of ${row.total_signals} signals unknown`
              : "all signals known"}</div>
        </td>
        <td class="score-cell">
          ${row.score === null
            ? `<div class="score-value unknown">--</div>`
            : `<div class="score-value">${row.score.toFixed(0)}</div>
               <div class="bar"><span style="width:${row.score}%"></span></div>`}
        </td>
        <td><span class="pill ${row.confidence_label}">${row.confidence_label}</span></td>
        <td><div class="reasons">${reasons}</div></td>
      </tr>`;
  }).join("");

  resultsBody.innerHTML = `
    <table>
      <thead>
        <tr><th>#</th><th>Company</th><th>Score</th><th>Confidence</th><th>Why</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;

  resultsBody.querySelectorAll("tr[data-company]").forEach((row) => {
    row.addEventListener("click", () => showDetail(row.dataset.company));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter") showDetail(row.dataset.company);
    });
  });
}

function field(label, value, note = null) {
  const shown = value === null || value === undefined || value === ""
    ? `<span class="unknown">not on record</span>`
    : escapeHtml(value);
  const noteHtml = note ? `<div class="evidence">${escapeHtml(note)}</div>` : "";
  return `<dt>${label}</dt><dd>${shown}${noteHtml}</dd>`;
}

/* Stored field names, in words. Anything not listed shows its raw name. */
const FIELD_LABELS = {
  display_name: "Name",
  domain: "Website",
  phone_e164: "Phone",
  street: "Street",
  city: "City",
  postal_code: "Postcode",
  category: "Category",
  founded_year: "Founded",
  employee_count: "Employees",
  employee_band: "Staff band",
  revenue_estimate: "Revenue",
  domain_registered_year: "Domain registered",
  website_last_updated_year: "Website updated",
  has_recurring_revenue: "Recurring revenue",
  sells_to_businesses: "Sells to businesses",
  mentions_family_ownership: "Family owned",
  is_part_of_group: "Part of a group",
  location_count: "Locations",
};

const CHECK_LABELS = {
  domain_age: "Domain age",
  registry: "Company register",
  website: "Website",
};

function money(amount) {
  return amount >= 1e6 ? `$${(amount / 1e6).toFixed(1)}M` : `$${Math.round(amount / 1e3)}k`;
}

function displayValue(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "object" && "low" in value && "high" in value) {
    return `${money(value.low)} to ${money(value.high)}`;
  }
  return String(value);
}

function shortDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function revenueField(company) {
  if (company.revenue_low === null || company.revenue_high === null) {
    return field("Revenue", null);
  }
  const range = `${money(company.revenue_low)} to ${money(company.revenue_high)} (our estimate)`;
  return field("Revenue", range, company.revenue_method);
}

function staffField(company) {
  if (company.employee_count !== null) return field("Employees", company.employee_count);
  if (company.employee_band) return field("Employees", `${company.employee_band} (register band)`);
  return field("Employees", null);
}

function peopleSection(people) {
  if (!people.length) return `<p class="unknown">No owners or directors on record.</p>`;
  const rows = people.map((person) => {
    const details = [
      person.role,
      person.is_owner && !person.is_company ? "owner" : null,
      person.is_company ? "holding company" : null,
      person.birth_year ? `born ${person.birth_year}` : null,
      person.appointed_year ? `since ${person.appointed_year}` : null,
    ].filter(Boolean).join(" · ");
    return `<li><strong>${escapeHtml(person.name)}</strong>
      <span class="sub">${escapeHtml(details)} · ${escapeHtml(person.source)}</span></li>`;
  }).join("");
  return `<ul class="plain-list">${rows}</ul>`;
}

function checksSection(checks) {
  if (!checks.length) {
    return `<p class="unknown">No lookups recorded for this company yet. Start them from Load &amp; enrich.</p>`;
  }
  const rows = checks.map((check) => `
    <li><span class="pill ${check.succeeded ? "high" : "low"}">${check.succeeded ? "found" : "not found"}</span>
      <strong>${escapeHtml(CHECK_LABELS[check.task] ?? check.task)}</strong>
      <span class="sub">${shortDate(check.attempted_at)}</span>
      <div class="sub">${escapeHtml(check.message)}</div></li>`).join("");
  return `<ul class="plain-list">${rows}</ul>`;
}

function provenanceSection(entries) {
  if (!entries.length) return `<dd class="unknown">No sources recorded yet.</dd>`;
  return entries.map((entry) => `
    <dt>${escapeHtml(FIELD_LABELS[entry.field] ?? entry.field)}</dt>
    <dd>${escapeHtml(displayValue(entry.value))}
      <span class="sub">· ${escapeHtml(entry.source)} · confidence ${entry.confidence.toFixed(2)}</span>
      ${entry.evidence ? `<div class="evidence">${escapeHtml(entry.evidence)}</div>` : ""}</dd>`
  ).join("");
}

async function showDetail(companyId) {
  detail.hidden = false;
  detailBody.innerHTML = `<p class="empty">Loading…</p>`;

  try {
    const company = await callApi(`/companies/${companyId}`);
    detailBody.innerHTML = `
      <h3>${escapeHtml(company.name)}</h3>
      <div class="panel-actions">
        <button id="add-to-pipeline" data-company="${company.id}">Add to pipeline</button>
        <button id="draft-outreach" class="secondary" data-company="${company.id}">Draft outreach</button>
        <button id="never-contact" class="secondary" data-company="${company.id}">Never contact</button>
      </div>
      <p id="panel-result" class="sub" role="status"></p>
      <div id="draft-output"></div>
      <p class="sub">${escapeHtml([company.city, company.region, company.country].filter(Boolean).join(", "))}</p>
      ${company.summary ? `<p>${escapeHtml(company.summary)}</p>` : ""}
      <dl>
        ${field("Website", company.domain)}
        ${field("Phone", company.phone)}
        ${field("Industry", company.industry_label)}
        ${field("Founded", company.founded_year)}
        ${field("Domain registered", company.domain_registered_year)}
        ${staffField(company)}
        ${revenueField(company)}
        ${company.part_of_group ? field("Part of a group", "yes") : ""}
      </dl>
      <p class="section-title">Owners and directors</p>
      ${peopleSection(company.people)}
      <p class="section-title">What we checked</p>
      ${checksSection(company.checks)}
      <p class="section-title">Where each field came from</p>
      <dl>${provenanceSection(company.provenance)}</dl>`;
  } catch (error) {
    detailBody.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`;
  }
}

document.getElementById("detail-close").addEventListener("click", () => {
  detail.hidden = true;
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") detail.hidden = true;
});

/* ---------- Tabs ---------- */

const views = {
  search: { tab: document.getElementById("tab-search"), panel: document.getElementById("view-search") },
  pipeline: { tab: document.getElementById("tab-pipeline"), panel: document.getElementById("view-pipeline") },
  data: { tab: document.getElementById("tab-data"), panel: document.getElementById("view-data") },
  review: { tab: document.getElementById("tab-review"), panel: document.getElementById("view-review") },
};

function showView(name) {
  for (const [key, view] of Object.entries(views)) {
    const active = key === name;
    view.tab.setAttribute("aria-selected", String(active));
    view.panel.hidden = !active;
  }
  if (name === "review") loadDuplicates();
  if (name === "pipeline") loadPipeline();
}

views.search.tab.addEventListener("click", () => showView("search"));
views.review.tab.addEventListener("click", () => showView("review"));
views.pipeline.tab.addEventListener("click", () => showView("pipeline"));
views.data.tab.addEventListener("click", () => showView("data"));

/* ---------- Duplicate review ---------- */

const reviewBody = document.getElementById("review-body");
const reviewStatus = document.getElementById("review-status");
const reviewCount = document.getElementById("review-count");

function setReviewCount(count) {
  reviewCount.hidden = count === 0;
  reviewCount.textContent = String(count);
}

/** A field on one side, highlighted when both sides agree. */
function comparedField(label, value, otherValue) {
  const known = value !== null && value !== undefined && value !== "";
  const matches = known && value === otherValue;
  const shown = known ? escapeHtml(value) : `<span class="unknown">not on record</span>`;
  return `<dt>${label}</dt><dd class="${matches ? "match" : ""}">${shown}</dd>`;
}

function renderSide(side, other) {
  return `
    <div class="side">
      <h4>${escapeHtml(side.name)}</h4>
      <dl>
        ${comparedField("Website", side.domain, other.domain)}
        ${comparedField("Phone", side.phone, other.phone)}
        ${comparedField("Address", side.address, other.address)}
        ${comparedField("Founded", side.founded_year, other.founded_year)}
      </dl>
    </div>`;
}

function renderPair(pair) {
  return `
    <article class="pair" data-pair="${pair.id}">
      <div class="pair-meta">
        <span class="similarity">Similarity <strong>${Math.round(pair.similarity * 100)}%</strong></span>
        <span class="pair-reason">${escapeHtml(pair.reason ?? "")}</span>
      </div>
      <div class="sides">
        ${renderSide(pair.left, pair.right)}
        ${renderSide(pair.right, pair.left)}
      </div>
      <div class="pair-actions">
        <button data-action="merge" data-keep="a" title="Keep ${escapeHtml(pair.left.name)}">Same business, keep left</button>
        <button data-action="merge" data-keep="b" title="Keep ${escapeHtml(pair.right.name)}">Same business, keep right</button>
        <button data-action="reject" class="secondary">Different, keep both</button>
      </div>
      <p class="pair-outcome" role="status"></p>
    </article>`;
}

async function loadDuplicates() {
  reviewStatus.textContent = "";
  reviewStatus.classList.remove("error");
  try {
    const pairs = await callApi("/duplicates");
    setReviewCount(pairs.length);
    reviewBody.innerHTML = pairs.length
      ? pairs.map(renderPair).join("")
      : `<p class="empty">Nothing to review. Every uncertain match has been decided.</p>`;
  } catch (error) {
    reviewBody.innerHTML = "";
    reviewStatus.textContent = error.message;
    reviewStatus.classList.add("error");
  }
}

/** One handler for both decisions, so the success and failure paths cannot drift apart. */
reviewBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;

  const card = button.closest(".pair");
  const outcome = card.querySelector(".pair-outcome");
  const buttons = card.querySelectorAll("button");
  const action = button.dataset.action;

  buttons.forEach((each) => { each.disabled = true; });
  outcome.textContent = action === "merge" ? "Merging…" : "Saving…";
  outcome.classList.remove("error");

  try {
    const keep = action === "merge" ? `?keep=${button.dataset.keep}` : "";
    const result = await callApi(`/duplicates/${card.dataset.pair}/${action}${keep}`, { method: "POST" });
    outcome.textContent = result.message;
    card.classList.add("resolved");
    setReviewCount(Math.max(0, Number(reviewCount.textContent || 0) - 1));
  } catch (error) {
    // The decision was not saved, so the buttons come back for another try.
    outcome.textContent = `${error.message} Nothing was changed.`;
    outcome.classList.add("error");
    buttons.forEach((each) => { each.disabled = false; });
  }
});

/* Show how many pairs are waiting as soon as the page opens. */
callApi("/duplicates")
  .then((pairs) => setReviewCount(pairs.length))
  .catch(() => setReviewCount(0));

/* ---------- Pipeline ---------- */

const STAGE_LABELS = {
  new: "New", contacted: "Contacted", replied: "Replied",
  meeting: "Meeting", offer: "Offer", won: "Won", lost: "Lost",
};

const pipelineBoard = document.getElementById("pipeline-board");
const pipelineStatus = document.getElementById("pipeline-status");
const pipelineCount = document.getElementById("pipeline-count");

function setPipelineCount(count) {
  pipelineCount.hidden = count === 0;
  pipelineCount.textContent = String(count);
}

function renderCard(card, stages) {
  const options = stages
    .map((stage) => `<option value="${stage}" ${stage === card.stage ? "selected" : ""}>${STAGE_LABELS[stage]}</option>`)
    .join("");
  const contact = [card.phone, card.domain].filter(Boolean).map(escapeHtml).join(" · ");
  return `
    <article class="card" data-card="${card.id}">
      <h4>${escapeHtml(card.name)}</h4>
      <p class="sub">${escapeHtml([card.city, card.country].filter(Boolean).join(", "))}</p>
      ${contact ? `<p class="sub">${contact}</p>` : `<p class="sub unknown">no contact details on record</p>`}
      <div class="card-row">
        <select data-field="stage" aria-label="Stage">${options}</select>
        <button class="remove" data-remove aria-label="Remove from pipeline">Remove</button>
      </div>
      <label class="sub">Follow up on
        <input type="date" data-field="next_action_on" value="${card.next_action_on ?? ""}">
      </label>
      <textarea data-field="notes" placeholder="Notes" aria-label="Notes">${escapeHtml(card.notes ?? "")}</textarea>
      <span class="saved" role="status"></span>
    </article>`;
}

function renderBoard(board) {
  setPipelineCount(board.cards.length);
  pipelineBoard.innerHTML = board.stages.map((stage) => {
    const cards = board.cards.filter((card) => card.stage === stage);
    return `
      <section class="column ${stage}" data-stage="${stage}">
        <h3><span>${STAGE_LABELS[stage]}</span><span>${cards.length}</span></h3>
        ${cards.length
          ? cards.map((card) => renderCard(card, board.stages)).join("")
          : `<p class="empty">Nothing here yet.</p>`}
      </section>`;
  }).join("");
}

async function loadPipeline() {
  pipelineStatus.textContent = "";
  pipelineStatus.classList.remove("error");
  try {
    renderBoard(await callApi("/pipeline"));
  } catch (error) {
    pipelineBoard.innerHTML = "";
    pipelineStatus.textContent = error.message;
    pipelineStatus.classList.add("error");
  }
}

/** Save one field, and say so, or say plainly that it was not saved. */
async function saveCardField(card, payload) {
  const saved = card.querySelector(".saved");
  saved.classList.remove("error");
  saved.textContent = "Saving…";
  try {
    await callApi(`/pipeline/${card.dataset.card}`, { method: "PATCH", body: JSON.stringify(payload) });
    saved.textContent = "Saved";
    return true;
  } catch (error) {
    saved.textContent = `Not saved: ${error.message}`;
    saved.classList.add("error");
    return false;
  }
}

pipelineBoard.addEventListener("change", async (event) => {
  const field = event.target.dataset.field;
  const card = event.target.closest(".card");
  if (!field || !card || field === "notes") return;

  if (field === "stage") {
    if (await saveCardField(card, { stage: event.target.value })) loadPipeline();
  } else if (field === "next_action_on") {
    const value = event.target.value;
    await saveCardField(card, value ? { next_action_on: value } : { clear_next_action: true });
  }
});

/* Notes save when the box loses focus, not on every keystroke. */
pipelineBoard.addEventListener("focusout", (event) => {
  if (event.target.dataset.field !== "notes") return;
  const card = event.target.closest(".card");
  saveCardField(card, { notes: event.target.value });
});

pipelineBoard.addEventListener("click", async (event) => {
  if (!event.target.matches("[data-remove]")) return;
  const card = event.target.closest(".card");
  try {
    await callApi(`/pipeline/${card.dataset.card}`, { method: "DELETE" });
    loadPipeline();
  } catch (error) {
    const saved = card.querySelector(".saved");
    saved.textContent = `Not removed: ${error.message}`;
    saved.classList.add("error");
  }
});

/* The panel's button is created per company, so listen on the panel itself. */
detailBody.addEventListener("click", async (event) => {
  if (event.target.id !== "add-to-pipeline") return;
  const result = document.getElementById("panel-result");
  event.target.disabled = true;
  result.textContent = "Adding…";
  try {
    const response = await fetch("/pipeline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_id: event.target.dataset.company }),
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(body?.error?.message ?? `Request failed (${response.status}).`);
    result.textContent = response.status === 201 ? "Added to the pipeline." : "Already on the pipeline.";
    callApi("/pipeline").then((board) => setPipelineCount(board.cards.length)).catch(() => {});
  } catch (error) {
    result.textContent = error.message;
    event.target.disabled = false;
  }
});

callApi("/pipeline")
  .then((board) => setPipelineCount(board.cards.length))
  .catch(() => setPipelineCount(0));

/* ---------- Map view ---------- */

const STRONG_SCORE = 70;
const FAIR_SCORE = 40;
// OpenFreeMap needs no API key. CARTO's basemaps started requiring one and watermark
// every tile without it, which is not something to discover in a demo.
const MAP_STYLE = "https://tiles.openfreemap.org/styles/dark";

let latestSearch = null;
let resultsMap = null;
let mapMarkers = [];

function currentResultsView() {
  return document.querySelector('input[name="results-view"]:checked')?.value ?? "table";
}

function scoreBand(score) {
  if (score === null || score === undefined) return "unknown-dot";
  if (score >= STRONG_SCORE) return "strong";
  if (score >= FAIR_SCORE) return "fair";
  return "weak";
}

function createMap() {
  if (typeof maplibregl === "undefined") return null;
  return new maplibregl.Map({
    container: "results-map",
    style: MAP_STYLE,
    center: [-96.8, 32.8],
    zoom: 8,
  });
}

/** Plot every company that has a location, and say how many do not. */
function drawMap(search) {
  const note = document.getElementById("map-note");
  resultsMap ??= createMap();
  if (!resultsMap) {
    note.textContent = "The map could not load. It needs an internet connection for the map library and tiles.";
    return;
  }

  mapMarkers.forEach((marker) => marker.remove());
  mapMarkers = [];

  const placed = search.results.filter((row) => row.latitude !== null && row.longitude !== null);
  const unplaced = search.results.length - placed.length;
  note.textContent = unplaced
    ? `${placed.length} companies shown. ${unplaced} have no location on record, so they are not on the map.`
    : `${placed.length} companies shown.`;

  if (!placed.length) return;

  const bounds = new maplibregl.LngLatBounds();
  for (const row of placed) {
    const element = document.createElement("button");
    element.className = `map-marker ${scoreBand(row.score)}`;
    element.setAttribute("aria-label", `${row.name}, score ${row.score ?? "unknown"}`);
    element.addEventListener("click", () => showDetail(row.company_id));

    const popup = new maplibregl.Popup({ offset: 10, closeButton: false }).setHTML(
      `<strong>${escapeHtml(row.name)}</strong><br>${row.score === null ? "Not enough data yet" : `Score ${row.score.toFixed(0)}`}`
    );
    const marker = new maplibregl.Marker({ element })
      .setLngLat([row.longitude, row.latitude])
      .setPopup(popup)
      .addTo(resultsMap);
    element.addEventListener("mouseenter", () => marker.togglePopup());
    element.addEventListener("mouseleave", () => marker.togglePopup());

    mapMarkers.push(marker);
    bounds.extend([row.longitude, row.latitude]);
  }
  resultsMap.fitBounds(bounds, { padding: 40, maxZoom: 13, duration: 0 });
}

document.querySelectorAll('input[name="results-view"]').forEach((radio) => {
  radio.addEventListener("change", () => {
    const showMap = radio.value === "map";
    document.getElementById("results-body").hidden = showMap;
    document.getElementById("results-map-wrap").hidden = !showMap;
    if (showMap && latestSearch) {
      drawMap(latestSearch);
      resultsMap?.resize();  // the container was hidden when the map was created
    }
  });
});

/* ---------- Load & enrich (background jobs) ---------- */

const JOB_TITLES = {
  seed_region: "Load companies",
  lookup_registry: "Company register",
  check_domain_age: "Domain age",
  read_websites: "Read websites",
};
const JOB_ENDPOINTS = {
  seed: "/jobs/seed",
  registry: "/jobs/registry",
  "domain-age": "/jobs/domain-age",
  websites: "/jobs/websites",
};
const POLL_MS = 2000;
const STORAGE_KEY = "dealsignal.jobs";
const FINISHED = new Set(["complete", "failed", "not_found"]);

const jobList = document.getElementById("job-list");
const dataCount = document.getElementById("data-count");
const jobs = new Map();  // id -> latest state

function rememberJobs() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...jobs.keys()].slice(-20)));
  } catch { /* storage may be unavailable; the list still works for this visit */ }
}

function recalledJobIds() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function jobSummary(state) {
  if (state.status === "failed") return `Stopped with an error: ${state.error}`;
  if (state.status === "not_found") return "This job is no longer known. Results are kept for 24 hours.";
  if (state.status !== "complete") return state.status === "queued" ? "Waiting for the worker…" : "Working…";
  const result = state.result ?? {};
  if (!result.attempted) return "Nothing needed doing.";
  return `${result.succeeded} of ${result.attempted} succeeded.`;
}

function renderJobs() {
  const running = [...jobs.values()].filter((state) => !FINISHED.has(state.status)).length;
  dataCount.hidden = running === 0;
  dataCount.textContent = String(running);

  if (!jobs.size) {
    jobList.innerHTML = `<p class="empty">Nothing started yet.</p>`;
    return;
  }
  jobList.innerHTML = [...jobs.values()].reverse().map((state) => {
    const result = state.result ?? {};
    const failures = result.failures ?? [];
    return `
      <article class="job">
        <div class="job-head">
          <span class="job-title">${escapeHtml(JOB_TITLES[state.kind] ?? state.kind ?? "Job")}</span>
          <span class="job-status ${state.status}">${state.status.replace("_", " ")}</span>
        </div>
        <p class="job-summary">${escapeHtml(jobSummary(state))}</p>
        ${result.note ? `<p class="job-note">${escapeHtml(result.note)}</p>` : ""}
        ${failures.length ? `
          <details>
            <summary>${failures.length} could not be done, and why</summary>
            <ul>${failures.map((failure) => `<li><strong>${escapeHtml(failure.company)}</strong>: ${escapeHtml(failure.reason)}</li>`).join("")}</ul>
          </details>` : ""}
      </article>`;
  }).join("");
}

async function pollJob(id) {
  try {
    const state = await callApi(`/jobs/${id}`);
    const previous = jobs.get(id) ?? {};
    jobs.set(id, { ...state, kind: state.kind ?? previous.kind });
    renderJobs();
    if (!FINISHED.has(state.status)) setTimeout(() => pollJob(id), POLL_MS);
  } catch (error) {
    jobs.set(id, { id, kind: jobs.get(id)?.kind, status: "failed", error: error.message });
    renderJobs();
  }
}

document.querySelectorAll("form[data-job]").forEach((jobForm) => {
  jobForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = jobForm.querySelector("button");
    const payload = Object.fromEntries(new FormData(jobForm));
    payload.limit = Number(payload.limit);

    button.disabled = true;
    try {
      const started = await callApi(JOB_ENDPOINTS[jobForm.dataset.job], {
        method: "POST",
        body: JSON.stringify(payload),
      });
      jobs.set(started.id, started);
      rememberJobs();
      renderJobs();
      pollJob(started.id);
    } catch (error) {
      const failedId = `local-${Date.now()}`;
      jobs.set(failedId, { id: failedId, kind: null, status: "failed", error: error.message });
      renderJobs();
    } finally {
      button.disabled = false;
    }
  });
});

/* Pick up jobs started earlier, so a reload does not lose a running job. */
for (const id of recalledJobIds()) {
  jobs.set(id, { id, kind: null, status: "queued" });
  pollJob(id);
}
renderJobs();

/* ---------- Outreach drafts and do-not-contact ---------- */

const SENDER_KEY = "dealsignal.sender";

function savedSender() {
  try {
    return JSON.parse(localStorage.getItem(SENDER_KEY) ?? "null");
  } catch {
    return null;
  }
}

/** Asked once, then remembered: nobody wants to retype who they are per company. */
function askForSender() {
  const existing = savedSender();
  if (existing) return existing;

  const name = prompt("Your name, as the message should sign off:");
  if (!name) return null;
  const background = prompt(
    "One or two lines about you and what you are looking for. This goes to the model, not to the company."
  );
  if (!background) return null;

  const sender = { name, background };
  try {
    localStorage.setItem(SENDER_KEY, JSON.stringify(sender));
  } catch { /* fine: it will ask again next time */ }
  return sender;
}

function renderDraft(draft) {
  const facts = draft.facts_used.map((fact) => `<li>${escapeHtml(fact)}</li>`).join("");
  return `
    <article class="draft">
      <p class="section-title">Draft for ${escapeHtml(draft.company_name)}</p>
      <label class="sub">Subject<input id="draft-subject" value="${escapeHtml(draft.subject)}"></label>
      <label class="sub">Message<textarea id="draft-body" rows="9">${escapeHtml(draft.body)}</textarea></label>
      <p class="sub">Follow-up if there is no reply: ${escapeHtml(draft.follow_up)}</p>
      <details open>
        <summary>What this was written from (${draft.facts_used.length})</summary>
        <ul>${facts}</ul>
      </details>
      <button id="copy-draft" class="secondary">Copy message</button>
      <span id="copy-result" class="sub" role="status"></span>
    </article>`;
}

detailBody.addEventListener("click", async (event) => {
  const target = event.target;
  const result = document.getElementById("panel-result");
  const output = document.getElementById("draft-output");

  if (target.id === "draft-outreach") {
    const sender = askForSender();
    if (!sender) return;
    target.disabled = true;
    result.textContent = "Writing a draft…";
    output.innerHTML = "";
    try {
      const draft = await callApi("/outreach/drafts", {
        method: "POST",
        body: JSON.stringify({
          company_id: target.dataset.company,
          buy_box_id: latestSearch?.buy_box_id ?? null,
          sender,
        }),
      });
      result.textContent = "";
      output.innerHTML = renderDraft(draft);
    } catch (error) {
      result.textContent = error.message;
    } finally {
      target.disabled = false;
    }
  }

  if (target.id === "never-contact") {
    const reason = prompt("Why should this company never be contacted? (optional)") ?? "";
    target.disabled = true;
    try {
      await callApi("/suppression", {
        method: "POST",
        body: JSON.stringify({
          kind: "company",
          value: target.dataset.company,
          reason: reason || null,
        }),
      });
      result.textContent = "Added to the do-not-contact list. It will be left out of searches, exports and drafts.";
      output.innerHTML = "";
    } catch (error) {
      result.textContent = error.message;
      target.disabled = false;
    }
  }

  if (target.id === "copy-draft") {
    const text = `${document.getElementById("draft-subject").value}\n\n${document.getElementById("draft-body").value}`;
    try {
      await navigator.clipboard.writeText(text);
      document.getElementById("copy-result").textContent = "Copied.";
    } catch {
      document.getElementById("copy-result").textContent = "Could not copy; select the text instead.";
    }
  }
});
