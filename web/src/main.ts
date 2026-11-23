import "./style.css";
import {
  DataError,
  filterRows,
  formNote,
  loadTeamUsage,
  parseManifest,
  readFilters,
  writeFilters,
  type Filters,
  type FormBasis,
  type Manifest,
  type TeamUsage,
  type UsageRow,
} from "./data";

const BASE = `${import.meta.env.BASE_URL}data/`;
const BAND_LABEL: Record<string, string> = {
  all: "All players",
  below_1200: "Below 1200",
  "1200_1399": "1200–1399",
  "1400_1499": "1400–1499",
  "1500_plus": "1500+",
  unknown: "Unrated",
};

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const regSel = $<HTMLSelectElement>("regulation");
const bandSel = $<HTMLSelectElement>("band");
const search = $<HTMLInputElement>("search");
const context = $<HTMLParagraphElement>("context");
const tbody = document.querySelector<HTMLTableSectionElement>("#usage tbody")!;

const fmt = new Intl.NumberFormat("en");
const pct = (v: number, d = 1) => `${(100 * v).toFixed(d)}%`;
const pp = (v: number) => `${v >= 0 ? "+" : "−"}${Math.abs(100 * v).toFixed(1)} pp`;

async function fetchJson(url: string): Promise<unknown> {
  const res = await fetch(url);
  if (!res.ok) throw new DataError("not-found", `${url}: HTTP ${res.status}`);
  return res.json();
}

function options(sel: HTMLSelectElement, values: string[], label: (v: string) => string, selected: string) {
  sel.replaceChildren(...values.map((v) => new Option(label(v), v, false, v === selected)));
}

function cell(text: string, cls?: string): HTMLTableCellElement {
  const td = document.createElement("td");
  td.textContent = text;
  if (cls) td.className = cls;
  return td;
}

// "observed" rows already say "(seen in battle)" in their label; the note stays in the tooltip.
const FORM_TAG: Record<FormBasis, string> = { listed: "", observed: "", unobserved: "never sent out",
  species_only: "species level" };

function nameCell(r: UsageRow): HTMLTableCellElement {
  const td = cell(r.label);
  const note = formNote(r);
  if (note) td.title = note;
  if (FORM_TAG[r.form_basis]) {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = FORM_TAG[r.form_basis];
    tag.title = note;
    td.append(" ", tag);
  }
  return td;
}

function renderTable(data: TeamUsage, query: string) {
  const rows = filterRows(data.rows, query);
  tbody.replaceChildren(...rows.map((r) => {
    const tr = document.createElement("tr");
    const rank = data.rows.indexOf(r) + 1;
    tr.append(
      cell(String(rank), "num muted"),
      nameCell(r),
      cell(fmt.format(r.n), "num"),
      cell(pct(r.usage_share), "num"),
      cell(pct(r.win_rate), "num"),
      cell(`${pct(r.win_ci_low)}–${pct(r.win_ci_high)}`, "num muted"),
      cell(pp(r.win_rate_delta), `num ${r.win_ci_low > data.baseline_win_rate ? "up" : r.win_ci_high < data.baseline_win_rate ? "down" : ""}`),
      cell(pct(r.lead_rate), "num"),
    );
    return tr;
  }));
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = cell(query ? `No Pokémon matches “${query}”.` : "No form reaches the minimum sample size.");
    td.colSpan = 8;
    tr.append(td);
    tbody.append(tr);
  }
}

function setContext(data: TeamUsage) {
  context.textContent =
    `Population: completed ${data.regulation} battles, rating band “${BAND_LABEL[data.rating_band] ?? data.rating_band}” — ` +
    `${fmt.format(data.player_battles)} player-battles. Band baseline win rate ${pct(data.baseline_win_rate)}. ` +
    `${data.rows.length} forms with n ≥ ${data.min_n} shown (smaller samples hidden).`;
}

async function start() {
  let manifest: Manifest;
  try {
    manifest = parseManifest(await fetchJson(`${BASE}manifest.json`));
  } catch (e) {
    $("dataset-size").textContent = "";
    context.textContent = e instanceof DataError && e.code === "schema-version"
      ? `Data error: ${e.message}`
      : "No data has been exported yet. Run: python -m python.analytics.export_web";
    return;
  }
  $("dataset-size").textContent =
    `Snapshot ${manifest.snapshot_date}: ${fmt.format(manifest.totals.battles)} completed VGC battles ` +
    `(${fmt.format(manifest.totals.player_battles)} player-battles) across ${manifest.regulations.length} regulations.`;

  let filters: Filters = readFilters(location.search, manifest);
  let current: TeamUsage | null = null;
  let token = 0;

  const sync = () => history.replaceState(null, "", writeFilters(filters) + location.hash);

  async function load() {
    const reg = manifest.regulations.find((r) => r.id === filters.regulation);
    options(regSel, manifest.regulations.map((r) => r.id), (v) => v, filters.regulation);
    options(bandSel, reg?.bands ?? [], (v) => BAND_LABEL[v] ?? v, filters.band);
    search.value = filters.query;
    sync();
    const mine = ++token;
    context.textContent = "Loading…";
    try {
      const data = await loadTeamUsage(manifest, filters.regulation, filters.band, fetchJson, BASE);
      if (mine !== token) return;
      current = data;
      setContext(data);
      renderTable(data, filters.query);
    } catch (e) {
      if (mine !== token) return;
      current = null;
      tbody.replaceChildren();
      context.textContent = `Could not load data: ${e instanceof Error ? e.message : String(e)}`;
    }
  }

  regSel.addEventListener("change", () => {
    filters = readFilters(writeFilters({ ...filters, regulation: regSel.value }), manifest);
    void load();
  });
  bandSel.addEventListener("change", () => {
    filters = { ...filters, band: bandSel.value };
    void load();
  });
  search.addEventListener("input", () => {
    filters = { ...filters, query: search.value };
    sync();
    if (current) renderTable(current, filters.query);
  });
  await load();
}

void start();
