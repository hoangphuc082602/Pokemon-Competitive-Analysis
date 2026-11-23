import "./style.css";
import {
  DataError,
  STAT_KEYS,
  baseStatTotal,
  chartPoints,
  formMaster,
  loadSpeciesForms,
  typeLabel,
  type FormMaster,
  pageList,
  paginate,
  regulationLabel,
  unratedNote,
  type ChartSeries,
  filterRows,
  formNote,
  loadPairFile,
  loadTeamUsage,
  loadTeraFile,
  loadTrendFile,
  parseManifest,
  readFilters,
  speciesEntry,
  teraEntry,
  writeFilters,
  type Filters,
  type FormBasis,
  type Manifest,
  type Opponent,
  type PairDataset,
  type PairFile,
  type Partner,
  type TeamUsage,
  type TeraFile,
  type TrendFile,
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
const unratedEl = $<HTMLParagraphElement>("unrated-note");
const tbody = document.querySelector<HTMLTableSectionElement>("#usage tbody")!;
const pagePrev = $<HTMLButtonElement>("page-prev");
const pageNext = $<HTMLButtonElement>("page-next");
const pageInfo = $<HTMLSpanElement>("page-info");
const pageNumbers = $<HTMLSpanElement>("page-numbers");
const speciesSel = $<HTMLSelectElement>("species");
const detailContext = $<HTMLParagraphElement>("detail-context");
const detailBody = $<HTMLDivElement>("detail-body");
const partnerBody = document.querySelector<HTMLTableSectionElement>("#partners tbody")!;
const matchupBody = document.querySelector<HTMLTableSectionElement>("#matchups tbody")!;
const trendContext = $<HTMLParagraphElement>("trend-context");
const trendChart = $<HTMLDivElement>("trend-chart");
const trendTail = $<HTMLParagraphElement>("trend-tail");
const trendBody = document.querySelector<HTMLTableSectionElement>("#trend-table tbody")!;
const teraContext = $<HTMLParagraphElement>("tera-context");
const teraBody = document.querySelector<HTMLTableSectionElement>("#tera tbody")!;

const fmt = new Intl.NumberFormat("en");
const pct = (v: number, d = 1) => `${(100 * v).toFixed(d)}%`;
const pp = (v: number) => `${v >= 0 ? "+" : "−"}${Math.abs(100 * v).toFixed(1)} pp`;
const bandName = (b: string) => BAND_LABEL[b] ?? b;
/** Regulation display label (dim_regulation.label from the manifest); set once the manifest is loaded. */
let regName: (id: string) => string = (id) => id;

/** Fill an element with text where the [text] pieces are highlighted (class `hl`, or the given class). */
type Piece = string | [string] | [string, string];
function rich(el: HTMLElement, pieces: Piece[]) {
  el.replaceChildren(...pieces.map((p) => {
    if (typeof p === "string") return p;
    return Object.assign(document.createElement("strong"), { className: p[1] ?? "hl", textContent: p[0] });
  }));
}

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

/** PokéAPI typing / base stats per poke_id (species_forms.json); empty until loaded. */
let forms = new Map<number, FormMaster>();
const STAT_LABEL: Record<(typeof STAT_KEYS)[number], string> = { hp: "HP", atk: "Atk", def: "Def", spatk: "SpA",
  spdef: "SpD", spe: "Spe" };

/** Typing and base stat total of the row's own form; unknown ("—") for a row without a form: nothing is guessed (BR-05). */
function formCells(r: UsageRow): HTMLTableCellElement[] {
  const f = formMaster(forms, r);
  const why = r.poke_id === null ? "Form unknown: no typing or base stats are guessed from the species"
    : "Not in the PokéAPI master data";
  const types = typeLabel(f);
  const bst = baseStatTotal(f);
  const t = cell(types ?? "—", types ? "" : "muted");
  const b = cell(bst === null ? "—" : String(bst), bst === null ? "num muted" : "num");
  if (!types) t.title = why;
  b.title = bst === null ? why : STAT_KEYS.map((k) => `${STAT_LABEL[k]} ${f![k]}`).join(" · ");
  return [t, b];
}

const PAGE_SIZE = 15;
/** Keep the address bar in step with the filters (page included), so a refresh shows the same view. */
const syncUrl = () => history.replaceState(null, "", writeFilters(filters) + location.hash);

function renderTable(data: TeamUsage, query: string) {
  const all = filterRows(data.rows, query);
  const pg = paginate(all, filters.page, PAGE_SIZE);
  if (pg.page !== filters.page) {      // a page past the end (e.g. from an old link) is clamped
    filters = { ...filters, page: pg.page };
    syncUrl();
  }
  pageInfo.replaceChildren();
  if (all.length) {
    const b = (t: string) => Object.assign(document.createElement("strong"), { textContent: t });
    pageInfo.append("Showing ", b(`${pg.from}–${pg.to}`), " of ", b(fmt.format(all.length)), " forms");
  }
  pagePrev.disabled = pg.page <= 1;
  pageNext.disabled = pg.page >= pg.pages;
  pageNumbers.replaceChildren(...(pg.pages > 1 ? pageList(pg.page, pg.pages) : []).map((p) => {
    if (p === "…") return Object.assign(document.createElement("span"), { className: "pager-gap", textContent: "…" });
    const btn = Object.assign(document.createElement("button"), { type: "button", className: "pager-num",
      textContent: String(p) });
    if (p === pg.page) btn.setAttribute("aria-current", "page");
    btn.addEventListener("click", () => {
      filters = { ...filters, page: p };
      syncUrl();
      renderTable(data, query);
    });
    return btn;
  }));
  const rows = pg.rows;
  tbody.replaceChildren(...rows.map((r) => {
    const tr = document.createElement("tr");
    const rank = data.rows.indexOf(r) + 1;
    tr.append(
      cell(String(rank), "num muted"),
      nameCell(r),
      ...formCells(r),
      cell(fmt.format(r.n), "num"),
      cell(pct(r.usage_share), "num"),
      cell(pct(r.win_rate), "num"),
      cell(`${pct(r.win_ci_low)}–${pct(r.win_ci_high)}`, "num muted"),
      cell(pp(r.win_rate_delta), `num ${r.win_ci_low > data.baseline_win_rate ? "up" : r.win_ci_high < data.baseline_win_rate ? "down" : ""}`),
      cell(pct(r.lead_rate), "num"),
    );
    return tr;
  }));
  if (!rows.length) emptyRow(tbody, query ? `No Pokémon matches “${query}”.` : "No form reaches the minimum sample size.", 10);
}

function setContext(data: TeamUsage) {
  rich(context, [
    "Population: completed ", [regName(data.regulation)], " battles, rating band “", [bandName(data.rating_band)], "” — ",
    [fmt.format(data.player_battles)], " player-battles. Band baseline win rate ", [pct(data.baseline_win_rate)], ". ",
    [String(data.rows.length)], " forms with n ≥ ", [String(data.min_n)], " shown (smaller samples hidden).",
  ]);
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
  const byWinRate = [...list].sort((a, b) => b.win_rate - a.win_rate);   // highest win rate first
  matchupBody.replaceChildren(...byWinRate.map((o) => {
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

const SVG = "http://www.w3.org/2000/svg";
function svg<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number>): SVGElementTagNameMap[K] {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  return el;
}

/** Line chart of monthly usage share: non-tail months on x, gaps where n < min_n, native tooltip per point.
 *  Months with few battles in this band stay charted, drawn hollow and named in the tooltip. */
function drawTrend(c: ChartSeries, band: string) {
  const { months, points } = c;
  const thin = new Set(c.thinMonths);
  const W = 640, H = 220, L = 48, R = 16, T = 12, B = 28;
  const top = Math.max(...points.map((p) => p.usage_share), 0.01);
  const step = top > 0.4 ? 0.1 : top > 0.2 ? 0.05 : top > 0.08 ? 0.02 : 0.01;
  const yMax = Math.ceil((top * 1.05) / step) * step;
  const x = (i: number) => L + (months.length > 1 ? (i * (W - L - R)) / (months.length - 1) : (W - L - R) / 2);
  const y = (v: number) => T + (1 - v / yMax) * (H - T - B);
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Monthly usage share; values in the table view below" });
  for (let v = 0; v <= yMax + 1e-9; v += step) {
    root.append(svg("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "grid" }));
    const t = svg("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end", class: "axis" });
    t.textContent = pct(v, 0);
    root.append(t);
  }
  // every k-th month plus the last; a regular label too close to the last is skipped so labels never overlap,
  // and the end labels are anchored inside the chart so they are not clipped
  const every = Math.ceil(months.length / 6);
  const last = months.length - 1;
  months.forEach((m, i) => {
    if (i !== last && (i % every || last - i < every)) return;
    const anchor = months.length === 1 ? "middle" : i === 0 ? "start" : i === last ? "end" : "middle";
    const t = svg("text", { x: x(i), y: H - 8, "text-anchor": anchor, class: "axis" });
    t.textContent = m;
    root.append(t);
  });
  const at = new Map(points.map((p) => [p.month, p]));
  let run: string[] = [];
  const flush = () => {
    if (run.length > 1) root.append(svg("polyline", { points: run.join(" "), class: "series" }));
    run = [];
  };
  months.forEach((m, i) => {
    const p = at.get(m);
    if (p) run.push(`${x(i)},${y(p.usage_share)}`);
    else flush();
  });
  flush();
  // HTML tooltip (native SVG <title> tooltips are slow and not shown on touch / keyboard focus)
  const plot = document.createElement("div");
  plot.className = "plot";
  const tip = document.createElement("div");
  tip.className = "tip";
  tip.hidden = true;
  tip.setAttribute("role", "status");
  const hide = () => { tip.hidden = true; };
  months.forEach((m, i) => {
    const p = at.get(m);
    if (!p) return;
    const battles = c.monthBattles[m];
    // [label, value, detail] rows; the value is the highlighted figure
    const rows: [string, string, string][] = [
      ["Usage", pct(p.usage_share), `${fmt.format(p.n)} of ${battles === undefined ? "?" : fmt.format(battles)} teams`],
      ["Win rate", pct(p.win_rate), `95% CI ${pct(p.win_ci_low)}–${pct(p.win_ci_high)}`],
      ["vs band", pp(p.win_rate_delta),
        c.monthBaseline[m] === undefined ? "" : `band baseline ${pct(c.monthBaseline[m])}`],
    ];
    const head = `${m} · ${band}`;
    const warn = thin.has(m) ? "Few battles in this band this month (< 5% of its busiest month): read with care." : "";
    const g = svg("g", { class: "pt", tabindex: 0,
      "aria-label": [head, ...rows.map((r) => r.join(" ")), warn].filter(Boolean).join("; ") });
    const el = (tag: string, cls: string, text = "") =>
      Object.assign(document.createElement(tag), { className: cls, textContent: text });
    const show = () => {
      tip.replaceChildren(el("div", "tip-head", head), ...rows.map(([label, value, detail]) => {
        const d = el("div", "tip-row");
        d.append(el("span", "tip-label", label), el("span", "tip-value", value), el("span", "tip-detail", detail));
        return d;
      }), ...(warn ? [el("div", "tip-warn", warn)] : []));
      tip.style.left = `${(100 * x(i)) / W}%`;
      tip.style.top = `${(100 * y(p.usage_share)) / H}%`;
      tip.dataset.align = x(i) < W * 0.25 ? "start" : x(i) > W * 0.75 ? "end" : "middle";
      tip.style.setProperty("--ty", y(p.usage_share) < H * 0.4 ? "12px" : "calc(-100% - 12px)");   // below high points
      tip.hidden = false;
    };
    g.addEventListener("pointerenter", show);
    g.addEventListener("focus", show);
    g.addEventListener("pointerleave", hide);
    g.addEventListener("blur", hide);
    g.append(svg("circle", { cx: x(i), cy: y(p.usage_share), r: 12, class: "hit" }),
      svg("circle", { cx: x(i), cy: y(p.usage_share), r: 4, class: thin.has(m) ? "dot thin" : "dot" }));
    root.append(g);
  });
  plot.append(root, tip);
  trendChart.replaceChildren(plot);
}

function renderTrend(file: TrendFile | null, id: number) {
  trendChart.replaceChildren();
  trendTail.textContent = "";
  if (!file) {
    trendContext.textContent = "Monthly usage not exported for this band.";
    trendBody.replaceChildren();
    return;
  }
  const c = chartPoints(file, id);
  trendContext.textContent = c.points.length
    ? `Share of teams per upload month, completed ${regName(file.regulation)} battles, rating band “${bandName(file.rating_band)}”; ${c.points.length} of ${c.months.length} months with n ≥ ${file.min_n} teams.`
    : `No month reaches n ≥ ${file.min_n} teams for this species in this band.`;
  if (c.points.length) drawTrend(c, bandName(file.rating_band));
  const notes: string[] = [];
  if (c.tailMonths.length) {
    notes.push(`Not charted: ${c.tailMonths.join(", ")} — tail month(s) with fewer than 5% of the busiest ` +
      `month's battles (the format is ending; a different, tiny population)` +
      (c.hiddenTailPoints ? `; ${c.hiddenTailPoints} value(s) of this species there are in the table view.` : "."));
  }
  const thinCharted = c.thinMonths.filter((mo) => c.points.some((p) => p.month === mo));
  if (thinCharted.length) {
    notes.push(`Hollow points (${thinCharted.join(", ")}): few battles in this band that month (< 5% of its busiest ` +
      `month); hover for the counts.`);
  }
  trendTail.textContent = notes.join(" ");
  const tail = new Set(c.tailMonths);
  const rows = (file.rows.find((r) => r.species_id === id)?.points ?? []).slice().sort((a, b) => a.month.localeCompare(b.month));
  trendBody.replaceChildren(...rows.map((p) => {
    const tr = document.createElement("tr");
    tr.append(cell(tail.has(p.month) ? `${p.month} (tail)` : p.month, tail.has(p.month) ? "muted" : undefined),
      cell(fmt.format(p.n), "num"), cell(pct(p.usage_share), "num"), cell(pct(p.win_rate), "num"),
      cell(`${pct(p.win_ci_low)}–${pct(p.win_ci_high)}`, "num muted"),
      cell(pp(p.win_rate_delta), `num ${ciClass(p.win_ci_low, p.win_ci_high, p.win_rate - p.win_rate_delta)}`));
    return tr;
  }));
  if (!rows.length) emptyRow(trendBody, `No month with n ≥ ${file.min_n} teams.`, 6);
}

function renderTera(file: TeraFile | null, id: number) {
  if (!file) {
    teraContext.textContent = "Tera not exported for this band.";
    return emptyRow(teraBody, "No data.", 3);
  }
  const t = teraEntry(file, id);
  if (!t) {
    teraContext.textContent = `Fewer than ${file.min_n} sent-out appearances in this band: Tera hidden.`;
    return emptyRow(teraBody, "No data.", 3);
  }
  const wr = (v: number | null, d: number | null) =>
    v === null ? `n < ${file.min_n}, hidden` : d === null ? pct(v) : `${pct(v)} (${pp(d)} vs band)`;
  const base = file.baseline_win_rate === null ? "" : ` Band baseline win rate ${pct(file.baseline_win_rate)}.`;
  teraContext.textContent =
    `${regName(file.regulation)}, rating band “${bandName(file.rating_band)}”: Terastallized in ${pct(t.tera_rate)} of ` +
    `${fmt.format(t.n)} sent-out appearances ` +
    `(95% CI ${pct(t.tera_rate_ci_low)}–${pct(t.tera_rate_ci_high)}; ${fmt.format(t.tera_events)} Tera events). ` +
    `Win rate with Tera ${wr(t.win_rate_tera, t.win_rate_tera_delta)}, ` +
    `without ${wr(t.win_rate_no_tera, t.win_rate_no_tera_delta)} — each against the band, not against each other ` +
    `(see note).${base}`;
  if (!t.types.length) return emptyRow(teraBody, `Type split hidden: fewer than ${file.min_n} Tera events.`, 3);
  teraBody.replaceChildren(...t.types.map((x) => {
    const tr = document.createElement("tr");
    tr.append(cell(x.tera_type), cell(fmt.format(x.events), "num"), cell(pct(x.type_share), "num"));
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

  regName = (id) => regulationLabel(manifest, id);
  try {
    forms = await loadSpeciesForms(manifest, fetchJson, BASE);
  } catch (e) {   // the usage table still works; typing and stats then show as unknown
    console.warn(`species_forms.json not loaded: ${e instanceof Error ? e.message : String(e)}`);
  }
  filters = readFilters(location.search, manifest);
  let current: TeamUsage | null = null;
  type Detail = { partners: PairFile | null; matchups: PairFile | null; trend: TrendFile | null; tera: TeraFile | null };
  const noDetail: Detail = { partners: null, matchups: null, trend: null, tera: null };
  let pairs: Detail = noDetail;
  let token = 0;

  const sync = syncUrl;
  const orNull = <T,>(p: Promise<T>) => p.catch((e: unknown) => {
    if (e instanceof DataError && e.code === "not-found") return null;   // not exported for this band
    throw e;
  });
  const tryLoad = (ds: PairDataset) => orNull(loadPairFile(manifest, ds, filters.regulation, filters.band, fetchJson, BASE));

  function renderDetail() {
    const seen = new Map<number, string>();
    for (const f of [pairs.partners, pairs.matchups, pairs.trend, pairs.tera]) {
      for (const r of f?.rows ?? []) seen.set(r.species_id, r.species);
    }
    const list = [...seen].sort((a, b) => a[1].localeCompare(b[1]));
    const id = filters.species;
    const name = id === null ? undefined : seen.get(id) ?? current?.rows.find((r) => r.species_id === id)?.species;
    speciesSel.replaceChildren(new Option("Choose a species…", ""),
      ...list.map(([sid, sname]) => new Option(sname, String(sid), false, sid === id)));
    if (id !== null && !seen.has(id)) speciesSel.add(new Option(`${name ?? `#${id}`} (no data)`, String(id), false, true));
    if (!pairs.partners && !pairs.matchups && !pairs.trend && !pairs.tera) {
      detailBody.hidden = true;
      detailContext.textContent = `No species detail exported for ${regName(filters.regulation)} /${bandName(filters.band)}.`;
      return;
    }
    if (id === null) {
      detailBody.hidden = true;
      detailContext.textContent = "Choose a species, or click one in the table above.";
      return;
    }
    detailBody.hidden = false;
    detailContext.textContent =
      `${name ?? `Species #${id}`} — species level (all forms together), completed ${regName(filters.regulation)} battles,` +
      `rating band “${bandName(filters.band)}”. Pairs with n < ${manifest.min_n} hidden; bands are never combined.`;
    const p = pairs.partners ? speciesEntry(pairs.partners, id) : undefined;
    const m = pairs.matchups ? speciesEntry(pairs.matchups, id) : undefined;
    if (pairs.partners) renderPartners(p?.partners, pairs.partners.min_n);
    else emptyRow(partnerBody, "Partners not exported for this band.", 7);
    if (pairs.matchups) renderMatchups(m?.opponents, pairs.matchups.min_n);
    else emptyRow(matchupBody, "Matchups not exported for this band.", 7);
    renderTrend(pairs.trend, id);
    renderTera(pairs.tera, id);
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
    options(regSel, manifest.regulations.map((r) => r.id), regName, filters.regulation);
    options(bandSel, reg?.bands ?? [], bandName, filters.band);
    search.value = filters.query;
    sync();
    const mine = ++token;
    context.textContent = "Loading…";
    const unrated = unratedNote(manifest, filters.regulation, filters.band);
    unratedEl.hidden = !unrated;
    if (unrated) {
      rich(unratedEl, [[pct(unrated.share), "notice-hl"], " of ", [unrated.regulation, "notice-hl"],
        " player-battles have no rating and are not in any rating band (they are counted in “All players”)."]);
    } else unratedEl.replaceChildren();
    detailContext.textContent = "Loading…";
    const pairLoad = Promise.all([tryLoad("partners"), tryLoad("matchups"),
      orNull(loadTrendFile(manifest, filters.regulation, filters.band, fetchJson, BASE)),
      orNull(loadTeraFile(manifest, filters.regulation, filters.band, fetchJson, BASE))]);
    pairs = noDetail;
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
      pageInfo.replaceChildren();
      pageNumbers.replaceChildren();
      pagePrev.disabled = pageNext.disabled = true;
      context.textContent = `Could not load data: ${e instanceof Error ? e.message : String(e)}`;
    }
    try {   // a broken partners / matchups file must not blank the usage table
      const [partners, matchups, trend, tera] = await pairLoad;
      if (mine !== token) return;
      pairs = { partners, matchups, trend, tera };
      renderDetail();
    } catch (e) {
      if (mine !== token) return;
      detailBody.hidden = true;
      detailContext.textContent = `Could not load species detail: ${e instanceof Error ? e.message : String(e)}`;
    }
  }

  regSel.addEventListener("change", () => {
    filters = readFilters(writeFilters({ ...filters, regulation: regSel.value, page: 1 }), manifest);
    void load();
  });
  bandSel.addEventListener("change", () => {
    filters = { ...filters, band: bandSel.value, page: 1 };
    void load();
  });
  search.addEventListener("input", () => {
    filters = { ...filters, query: search.value, page: 1 };
    sync();
    if (current) renderTable(current, filters.query);
  });
  const turnPage = (delta: number) => {
    if (!current) return;
    filters = { ...filters, page: filters.page + delta };
    sync();
    renderTable(current, filters.query);
  };
  pagePrev.addEventListener("click", () => turnPage(-1));
  pageNext.addEventListener("click", () => turnPage(1));
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
