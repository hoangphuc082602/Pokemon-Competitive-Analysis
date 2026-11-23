import "./style.css";
import {
  DataError,
  filterRows,
  formNote,
  loadPairFile,
  loadTeamUsage,
  parseManifest,
  readFilters,
  speciesEntry,
  writeFilters,
  type Filters,
  type FormBasis,
  type Manifest,
  type Opponent,
  type PairDataset,
  type PairFile,
  type Partner,
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
const speciesSel = $<HTMLSelectElement>("species");
const detailContext = $<HTMLParagraphElement>("detail-context");
const detailBody = $<HTMLDivElement>("detail-body");
const partnerBody = document.querySelector<HTMLTableSectionElement>("#partners tbody")!;
const matchupBody = document.querySelector<HTMLTableSectionElement>("#matchups tbody")!;

const fmt = new Intl.NumberFormat("en");
const pct = (v: number, d = 1) => `${(100 * v).toFixed(d)}%`;
const pp = (v: number) => `${v >= 0 ? "+" : "−"}${Math.abs(100 * v).toFixed(1)} pp`;
const bandName = (b: string) => BAND_LABEL[b] ?? b;

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

function emptyRow(body: HTMLTableSectionElement, text: string, cols: number) {
  const tr = document.createElement("tr");
  const td = cell(text, "muted");
  td.colSpan = cols;
  tr.append(td);
  body.replaceChildren(tr);
}

// "observed" rows already say "(seen in battle)" in their label; the note stays in the tooltip.
const FORM_TAG: Record<FormBasis, string> = { listed: "", observed: "", unobserved: "never sent out",
  species_only: "species level" };

let filters: Filters;
let selectSpecies: (id: number) => void = () => {};

function speciesLink(text: string, id: number): HTMLAnchorElement {
  const a = document.createElement("a");
  a.textContent = text;
  a.href = writeFilters({ ...filters, species: id }) + "#detail";
  a.addEventListener("click", (e) => {
    e.preventDefault();
    selectSpecies(id);
  });
  return a;
}

function nameCell(r: UsageRow): HTMLTableCellElement {
  const td = document.createElement("td");
  td.append(speciesLink(r.label, r.species_id));
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
  if (!rows.length) emptyRow(tbody, query ? `No Pokémon matches “${query}”.` : "No form reaches the minimum sample size.", 8);
}

function setContext(data: TeamUsage) {
  context.textContent =
    `Population: completed ${data.regulation} battles, rating band “${bandName(data.rating_band)}” — ` +
    `${fmt.format(data.player_battles)} player-battles. Band baseline win rate ${pct(data.baseline_win_rate)}. ` +
    `${data.rows.length} forms with n ≥ ${data.min_n} shown (smaller samples hidden).`;
}

/** CSS class of a delta: coloured only when the 95% interval excludes the reference. */
const ciClass = (lo: number, hi: number, ref: number) => (lo > ref ? "up" : hi < ref ? "down" : "");
/** Matchup z is nominal (Bo3 games and one player's battles are not independent): |z| < 4 is noise (BR-12). */
const Z_NOISE = 4;
const zClass = (o: Opponent) => (o.z_vs_expected >= Z_NOISE ? "up" : o.z_vs_expected <= -Z_NOISE ? "down" : "");

function renderPartners(list: Partner[] | undefined, minN: number) {
  if (!list?.length) return emptyRow(partnerBody, `No partner pair reaches n ≥ ${minN} teams in this band.`, 7);
  partnerBody.replaceChildren(...list.map((p) => {
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    name.append(speciesLink(p.species, p.species_id));
    const base = p.win_rate - p.win_rate_delta;
    tr.append(
      name,
      cell(fmt.format(p.n), "num"),
      cell(pct(p.share), "num"),
      cell(p.lift.toFixed(2), "num"),
      cell(pct(p.win_rate), "num"),
      cell(`${pct(p.win_ci_low)}–${pct(p.win_ci_high)}`, "num muted"),
      cell(pp(p.win_rate_delta), `num ${ciClass(p.win_ci_low, p.win_ci_high, base)}`),
    );
    return tr;
  }));
}

function renderMatchups(list: Opponent[] | undefined, minN: number) {
  if (!list?.length) return emptyRow(matchupBody, `No matchup reaches n ≥ ${minN} battles in this band.`, 7);
  matchupBody.replaceChildren(...list.map((o) => {
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    name.append(speciesLink(o.species, o.species_id));
    tr.append(
      name,
      cell(fmt.format(o.n), "num"),
      cell(pct(o.win_rate), "num"),
      cell(`${pct(o.win_ci_low)}–${pct(o.win_ci_high)}`, "num muted"),
      cell(pct(o.expected_win_rate), "num"),
      cell(pp(o.win_rate_vs_expected), `num ${zClass(o)}`),
      cell(o.z_vs_expected.toFixed(1), `num ${zClass(o) || "muted"}`),
    );
    return tr;
  }));
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

  filters = readFilters(location.search, manifest);
  let current: TeamUsage | null = null;
  let pairs: { partners: PairFile | null; matchups: PairFile | null } = { partners: null, matchups: null };
  let token = 0;

  const sync = () => history.replaceState(null, "", writeFilters(filters) + location.hash);
  const tryLoad = (ds: PairDataset) =>
    loadPairFile(manifest, ds, filters.regulation, filters.band, fetchJson, BASE).catch((e: unknown) => {
      if (e instanceof DataError && e.code === "not-found") return null;   // not exported for this band
      throw e;
    });

  function renderDetail() {
    const seen = new Map<number, string>();
    for (const f of [pairs.partners, pairs.matchups]) for (const r of f?.rows ?? []) seen.set(r.species_id, r.species);
    const list = [...seen].sort((a, b) => a[1].localeCompare(b[1]));
    const id = filters.species;
    const name = id === null ? undefined : seen.get(id) ?? current?.rows.find((r) => r.species_id === id)?.species;
    speciesSel.replaceChildren(new Option("Choose a species…", ""),
      ...list.map(([sid, sname]) => new Option(sname, String(sid), false, sid === id)));
    if (id !== null && !seen.has(id)) speciesSel.add(new Option(`${name ?? `#${id}`} (no pair data)`, String(id), false, true));
    if (!pairs.partners && !pairs.matchups) {
      detailBody.hidden = true;
      detailContext.textContent = `No partner or matchup data exported for ${filters.regulation} / ${bandName(filters.band)}.`;
      return;
    }
    if (id === null) {
      detailBody.hidden = true;
      detailContext.textContent = "Choose a species, or click one in the table above.";
      return;
    }
    detailBody.hidden = false;
    detailContext.textContent =
      `${name ?? `Species #${id}`} — species level (all forms together), completed ${filters.regulation} battles, ` +
      `rating band “${bandName(filters.band)}”. Pairs with n < ${manifest.min_n} hidden; bands are never combined.`;
    const p = pairs.partners ? speciesEntry(pairs.partners, id) : undefined;
    const m = pairs.matchups ? speciesEntry(pairs.matchups, id) : undefined;
    if (pairs.partners) renderPartners(p?.partners, pairs.partners.min_n);
    else emptyRow(partnerBody, "Partners not exported for this band.", 7);
    if (pairs.matchups) renderMatchups(m?.opponents, pairs.matchups.min_n);
    else emptyRow(matchupBody, "Matchups not exported for this band.", 7);
  }

  selectSpecies = (id: number) => {
    filters = { ...filters, species: id };
    sync();
    if (current) renderTable(current, filters.query);   // links carry the selected species
    renderDetail();
    $("detail").scrollIntoView({ behavior: "smooth", block: "start" });
  };

  async function load() {
    const reg = manifest.regulations.find((r) => r.id === filters.regulation);
    options(regSel, manifest.regulations.map((r) => r.id), (v) => v, filters.regulation);
    options(bandSel, reg?.bands ?? [], bandName, filters.band);
    search.value = filters.query;
    sync();
    const mine = ++token;
    context.textContent = "Loading…";
    detailContext.textContent = "Loading…";
    const pairLoad = Promise.all([tryLoad("partners"), tryLoad("matchups")]);
    pairs = { partners: null, matchups: null };
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
    try {   // a broken partners / matchups file must not blank the usage table
      const [partners, matchups] = await pairLoad;
      if (mine !== token) return;
      pairs = { partners, matchups };
      renderDetail();
    } catch (e) {
      if (mine !== token) return;
      detailBody.hidden = true;
      detailContext.textContent = `Could not load partners / matchups: ${e instanceof Error ? e.message : String(e)}`;
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
  speciesSel.addEventListener("change", () => {
    filters = { ...filters, species: speciesSel.value ? Number(speciesSel.value) : null };
    sync();
    if (current) renderTable(current, filters.query);
    renderDetail();
  });
  await load();
  if (filters.species !== null && location.hash === "#detail") $("detail").scrollIntoView({ block: "start" });
}

void start();
