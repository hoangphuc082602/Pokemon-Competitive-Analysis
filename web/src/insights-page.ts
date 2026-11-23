import "./style.css";
import {
  DataError,
  loadPairFile,
  loadTeamUsage,
  loadTeraFile,
  parseManifest,
  regulationLabel,
  speciesEntry,
  type Manifest,
  type PairFile,
  type Partner,
  type TeamUsage,
  type TeraFile,
  type TeraRow,
} from "./data";
import {
  aboveBaselineByHalf,
  bandShift,
  overviewLink,
  popularityPoints,
  teraSummary,
  textOn,
  typeColor,
  type PopularityPoint,
  type ShiftRow,
} from "./insights";

const BASE = `${import.meta.env.BASE_URL}data/`;
const REG = "gen9vgc2026regf";      // the largest recent Scarlet/Violet regulation with all four views
const MIN_TEAMS = 2000;             // same threshold as the EDA report's band shift and popularity sections
const DONDOZO = 977, TATSUGIRI = 978, PELIPPER = 279, ARCHALUDON = 1018;

/** Figures quoted from documents/EDA_FINDINGS.md (species level); not recomputable from the web export. */
const EDA = {
  popularity: { species: 204, rho: 0.61, min: 0.48, max: 0.65 },                 // section 4, first table
  byBand: { species: 68, below_1200: 0.31, "1200_1399": 0.11, "1400_1499": 0.25, "1500_plus": 0.37 },  // section 4
  tera: { min: 0.196, max: 0.214, regulations: 7, medianTopType: 0.57 },         // section 5 (median: Reg F 2026)
  urshifuShift: 0.099,                                                            // section 3, Reg F 2026
};

const fmt = new Intl.NumberFormat("en");
const pct = (v: number, d = 1) => `${(100 * v).toFixed(d)}%`;
const pp = (v: number) => `${v >= 0 ? "+" : "−"}${Math.abs(100 * v).toFixed(1)} pp`;
const signed = (v: number) => `${v >= 0 ? "" : "−"}${Math.abs(v).toFixed(2)}`;

// ---- DOM helpers -------------------------------------------------------------------------------------------
type Src = "export" | "eda";
type Piece = string | Node;
const el = <K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", ...kids: Piece[]) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  e.append(...kids);
  return e;
};
/** A highlighted figure with its source badge. */
const fig = (text: string, src: Src = "export") => {
  const s = el("strong", "hl", text);
  s.title = src === "export" ? "Computed from the exported data (Meta Overview)" : "Quoted from the generated EDA report";
  return src === "eda" ? el("span", "", s, el("sup", "src", "EDA")) : s;
};
const link = (text: string, href: string) => Object.assign(el("a", "", text), { href });

const SVG = "http://www.w3.org/2000/svg";
function svg<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number>, text?: string) {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  if (text !== undefined) e.textContent = text;
  return e;
}
const tip = (node: SVGElement, text: string) => { node.append(svg("title", {}, text)); return node; };
function chartBox(root: SVGSVGElement): HTMLDivElement {
  const box = el("div", "chart");
  box.append(root);
  return box;
}

interface Card {
  id: string;
  title: string;
  // every finding states these five (BR: population, regulation, band, n, baseline)
  population: Piece[];
  regulation: string;
  band: Piece[];
  n: Piece[];
  baseline: Piece[];
  chart: HTMLElement;
  how: string;
  fact: Piece[];
  calc: Piece[];
  interp: Piece[];
  caution?: Piece[];
  links: [string, string][];
}

function card(c: Card): HTMLElement {
  const sec = el("section", "insight");
  sec.id = c.id;
  sec.setAttribute("aria-labelledby", `${c.id}-title`);
  const h = el("h2", "", c.title);
  h.id = `${c.id}-title`;
  const meta = el("dl", "meta");
  const rows: [string, Piece[]][] = [["Population", c.population], ["Regulation", [c.regulation]], ["Rating band", c.band],
    ["n", c.n], ["Baseline", c.baseline]];
  for (const [k, v] of rows) meta.append(el("dt", "", k), el("dd", "", ...v));
  const block = (label: string, kids: Piece[], cls = "") => el("p", `part ${cls}`, el("strong", "part-label", label), " ", ...kids);
  const links = el("p", "deep-links", ...c.links.flatMap(([t, href], i) => [i ? " · " : "", link(`${t} →`, href)]));
  sec.append(h, meta, c.chart, el("p", "note", el("strong", "", "How to read: "), c.how),
    block("Fact.", c.fact), block("Calculation.", c.calc), block("Interpretation.", c.interp),
    ...(c.caution ? [block("Caution.", c.caution, "caution")] : []), links);
  return sec;
}

// ---- charts ------------------------------------------------------------------------------------------------
/** Dumbbell: usage of each form in the lower band (hollow) and the higher band (filled). */
function dumbbell(rows: ShiftRow[], lowName: string, highName: string): HTMLDivElement {
  const W = 640, L = 96, R = 52, T = 22, rowH = 20, B = 18;
  const H = T + rows.length * rowH + B;
  const top = Math.max(...rows.flatMap((r) => [r.low, r.high]), 0.1);
  const xMax = Math.ceil(top * 10) / 10;
  const x = (v: number) => L + (v / xMax) * (W - L - R);
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": `Usage share ${lowName} and ${highName}: ` +
      rows.map((r) => `${r.label} ${pct(r.low)} to ${pct(r.high)}`).join("; ") });
  for (let v = 0; v <= xMax + 1e-9; v += 0.1) {
    root.append(svg("line", { x1: x(v), x2: x(v), y1: T - 6, y2: H - B, class: "grid" }),
      svg("text", { x: x(v), y: H - 6, "text-anchor": "middle", class: "axis" }, pct(v, 0)));
  }
  root.append(svg("circle", { cx: L, cy: 8, r: 4, class: "dot low" }),
    svg("text", { x: L + 8, y: 11, class: "axis" }, lowName),
    svg("circle", { cx: L + 100, cy: 8, r: 4, class: "dot" }),
    svg("text", { x: L + 108, y: 11, class: "axis" }, highName));
  rows.forEach((r, i) => {
    const y = T + i * rowH + rowH / 2;
    const g = svg("g", {});
    g.append(svg("text", { x: 4, y: y + 3, "text-anchor": "start", class: "label" }, r.label),
      svg("line", { x1: x(r.low), x2: x(r.high), y1: y, y2: y, class: "stem" }),
      svg("circle", { cx: x(r.low), cy: y, r: 4, class: "dot low" }),
      svg("circle", { cx: x(r.high), cy: y, r: 4, class: "dot" }),
      svg("text", { x: W - 4, y: y + 3, "text-anchor": "end", class: `value ${r.shift >= 0 ? "up" : "down"}` }, pp(r.shift)));
    root.append(tip(g, `${r.label}: ${pct(r.low)} of ${lowName} teams (n ${fmt.format(r.nLow)}), ` +
      `${pct(r.high)} of ${highName} teams (n ${fmt.format(r.nHigh)})`));
  });
  return chartBox(root);
}

/** Horizontal bars of lift, with a line at 1 (chance) and the win rate vs band at the right. */
function liftBars(list: Partner[]): HTMLDivElement {
  const W = 640, L = 90, R = 64, T = 18, rowH = 20, B = 18;
  const H = T + list.length * rowH + B;
  const max = Math.max(...list.map((p) => p.lift), 2);
  const x = (v: number) => L + (v / max) * (W - L - R);
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Lift of each partner: " + list.map((p) => `${p.species} ${p.lift.toFixed(1)}`).join("; ") });
  root.append(svg("text", { x: W - 4, y: 10, "text-anchor": "end", class: "axis" }, "win rate vs band"),
    svg("line", { x1: x(1), x2: x(1), y1: T - 4, y2: H - B, class: "ref" }),
    svg("text", { x: x(1) + 3, y: H - 6, class: "axis" }, "1 = chance"));
  list.forEach((p, i) => {
    const y = T + i * rowH;
    const g = svg("g", {});
    const cls = p.win_ci_low > p.win_rate - p.win_rate_delta ? "up" : p.win_ci_high < p.win_rate - p.win_rate_delta ? "down" : "muted";
    g.append(svg("text", { x: L - 10, y: y + rowH / 2 + 3, "text-anchor": "end", class: "label" }, p.species),
      svg("rect", { x: L, y: y + 6, width: Math.max(1, x(p.lift) - L), height: rowH - 12, class: "bar" }),
      svg("text", { x: x(p.lift) + 6, y: y + rowH / 2 + 3, class: "value" }, `${p.lift.toFixed(1)}×`),
      svg("text", { x: W - 4, y: y + rowH / 2 + 3, "text-anchor": "end", class: `value ${cls}` }, pp(p.win_rate_delta)));
    root.append(tip(g, `${p.species}: on ${fmt.format(p.n)} teams together, lift ${p.lift.toFixed(2)}, ` +
      `win rate ${pct(p.win_rate)} (95% CI ${pct(p.win_ci_low)}–${pct(p.win_ci_high)})`));
  });
  return chartBox(root);
}

/** One stacked bar per species: its three most used Tera types and the rest. */
function teraStack(rows: TeraRow[]): HTMLDivElement {
  const W = 640, L = 90, R = 8, T = 6, rowH = 22, B = 6;
  const H = T + rows.length * rowH + B;
  const x = (v: number) => L + v * (W - L - R);
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Share of each species' Tera events by type: " + rows.map((r) =>
      `${r.species} ${r.types.slice(0, 3).map((t) => `${t.tera_type} ${pct(t.type_share, 0)}`).join(", ")}`).join("; ") });
  const seen = new Set<string>();
  rows.forEach((r, i) => {
    const y = T + i * rowH;
    root.append(svg("text", { x: L - 10, y: y + rowH / 2 + 3, "text-anchor": "end", class: "label" }, r.species));
    const parts = r.types.slice(0, 3).map((t) => [t.tera_type, t.type_share] as const);
    const rest = 1 - parts.reduce((s, [, v]) => s + v, 0);
    let at = 0;
    [...parts, ["other", Math.max(0, rest)] as const].forEach(([name, share]) => {
      if (share <= 0) return;
      const g = svg("g", {});
      const color = typeColor(name);
      if (color) seen.add(name);
      g.append(svg("rect", { x: x(at), y: y + 5, width: x(at + share) - x(at), height: rowH - 10,
        class: color ? "seg" : "seg seg3", ...(color ? { style: `fill: ${color}` } : {}) }));
      if (share >= 0.09) {
        g.append(svg("text", { x: x(at) + 6, y: y + rowH / 2 + 3, class: "seg-label",
          ...(color ? { style: `fill: ${textOn(color)}` } : {}) }, `${name} ${pct(share, 0)}`));
      }
      root.append(tip(g, `${r.species}: ${name} ${pct(share)} of ${fmt.format(r.tera_events)} Tera events`));
      at += share;
    });
  });
  const box = chartBox(root);
  const legend = el("div", "legend");
  for (const name of [...seen, "other"]) {
    const sw = el("span", "swatch");
    const color = typeColor(name);
    if (color) sw.style.background = color;
    legend.append(el("span", "legend-item", sw, name === "other" ? "other types" : name));
  }
  box.prepend(legend);
  return box;
}

/** Usage (log scale) against win rate minus the band baseline, one dot per form. */
function scatter(points: PopularityPoint[]): HTMLDivElement {
  const W = 640, H = 300, L = 40, R = 12, T = 10, B = 26;
  const lx = points.map((p) => Math.log10(p.usage));
  const x0 = Math.floor(Math.min(...lx)), x1 = Math.ceil(Math.max(...lx));
  const yAbs = Math.max(0.02, Math.ceil(Math.max(...points.map((p) => Math.abs(p.delta))) * 100) / 100);
  const x = (u: number) => L + ((Math.log10(u) - x0) / (x1 - x0)) * (W - L - R);
  const y = (d: number) => T + (1 - (d + yAbs) / (2 * yAbs)) * (H - T - B);
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": `Usage against win rate minus the band baseline for ${points.length} forms` });
  for (let e = x0; e <= x1; e++) {
    const u = 10 ** e;
    root.append(svg("line", { x1: x(u), x2: x(u), y1: T, y2: H - B, class: "grid" }),
      svg("text", { x: x(u), y: H - 13, "text-anchor": "middle", class: "axis" }, pct(u, e < -2 ? 1 : 0)));
  }
  const step = yAbs > 0.05 ? 0.02 : 0.01;
  for (let d = -Math.floor(yAbs / step) * step; d <= yAbs + 1e-9; d += step) {
    root.append(svg("line", { x1: L, x2: W - R, y1: y(d), y2: y(d), class: Math.abs(d) < 1e-9 ? "ref" : "grid" }),
      svg("text", { x: L - 6, y: y(d) + 3, "text-anchor": "end", class: "axis" }, Math.abs(d) < 1e-9 ? "0" : pp(d)));
  }
  root.append(svg("text", { x: (L + W - R) / 2, y: H - 3, "text-anchor": "middle", class: "axis" },
    "usage share (log scale)"),
    svg("text", { x: W - R, y: y(0) - 5, "text-anchor": "end", class: "axis" }, "band baseline"));
  for (const p of points) {
    root.append(tip(svg("circle", { cx: x(p.usage), cy: y(p.delta), r: 3.5, class: `dot ${p.delta > 0 ? "" : "low"}` }),
      `${p.label}: usage ${pct(p.usage)} (n ${fmt.format(p.n)}), win rate ${pp(p.delta)} vs band`));
  }
  return chartBox(root);
}

// ---- insights ----------------------------------------------------------------------------------------------
async function fetchJson(url: string): Promise<unknown> {
  const res = await fetch(url);
  if (!res.ok) throw new DataError("not-found", `${url}: HTTP ${res.status}`);
  return res.json();
}

const ALL_PLAYERS: Piece[] = ["All players (rated and unrated; no band is summed)"];
const pbCount = (d: TeamUsage): Piece[] => [fig(fmt.format(d.player_battles)), " player-battles"];
const regBaseline = (d: TeamUsage): Piece[] =>
  ["win rate of all teams in the regulation and band: ", fig(pct(d.baseline_win_rate))];
const names = (xs: ShiftRow[]) => xs.map((r) => r.label).join(", ");

function shiftCard(reg: string, low: TeamUsage, high: TeamUsage): HTMLElement {
  const rows = bandShift(low, high, MIN_TEAMS);
  const drops = rows.slice(0, 4);
  const rises = rows.slice(-4).reverse();      // largest rise first
  const shown = rows.length > 8 ? [...drops, ...[...rises].reverse()] : rows;
  const say = (r: ShiftRow): Piece[] => [`${r.label} (`, fig(pct(r.low)), " → ", fig(pct(r.high)), ", ", fig(pp(r.shift)), ")"];
  const list = (xs: ShiftRow[]) => xs.flatMap((r, i) => [i ? (i === xs.length - 1 ? " and " : ", ") : "", ...say(r)]);
  return card({
    id: "band-shift",
    title: "1. Players rated 1500+ bring different Pokémon from players below 1200",
    population: ["completed battles, unit = player-battle (one team in one battle)"],
    regulation: reg,
    band: ["below 1200 (", ...pbCount(low), ") against 1500+ (", ...pbCount(high), "), each measured against its own teams"],
    n: [fig(String(rows.length)), ` forms with at least ${fmt.format(MIN_TEAMS)} teams in both bands`],
    baseline: ["usage is a share of each band's own teams; band baseline win rates ", fig(pct(low.baseline_win_rate)),
      " below 1200 and ", fig(pct(high.baseline_win_rate)), " at 1500+ (not used in this comparison)"],
    chart: dumbbell(shown, "below 1200", "1500+"),
    how: "one row per form; the hollow dot is its share of teams below 1200, the filled dot its share at 1500+. " +
      "The four largest falls and the four largest rises are shown; the value on the right is the difference. " +
      "The two values of a row are in the two Overview links below (one per band).",
    fact: ["the forms that gain most at 1500+ are ", ...list(rises.slice(0, 3)),
      ". The forms that lose most are ", ...list(drops.slice(0, 3)), "."],
    calc: ["usage = teams with the form ÷ player-battles of the band; the difference is in percentage points. Only " +
      "species with exactly one form, listed at team preview, are compared: forms are never summed, so masked or " +
      "multi-form species (Urshifu, Ogerpon, Tatsugiri…) are left out. The EDA report counts them at species level " +
      "(e.g. Urshifu ", fig(pp(EDA.urshifuShift), "eda"), ")."],
    interp: [`at high rating, usage moves away from ${names(drops.slice(0, 2))} and toward ${names(rises.slice(0, 2))}. ` +
      "This describes what the players who upload replays bring at each rating, not why they bring it, and not that " +
      "a pick makes a player stronger."],
    links: [["Open “below 1200” in Meta Overview", overviewLink(REG, "below_1200")],
      ["Open “1500+” in Meta Overview", overviewLink(REG, "1500_plus")]],
  });
}

function partnerCard(reg: string, all: TeamUsage, partners: PairFile): HTMLElement {
  const dondozo = speciesEntry(partners, DONDOZO)?.partners ?? [];
  const top = [...dondozo].sort((a, b) => b.n - a.n).slice(0, 8);
  const tats = dondozo.find((p) => p.species_id === TATSUGIRI);
  const rain = speciesEntry(partners, PELIPPER)?.partners?.find((p) => p.species_id === ARCHALUDON);
  const own = all.rows.filter((r) => r.species_id === DONDOZO);
  const teams = own.length === 1 && own[0].form_basis === "listed" ? own[0].n : null;   // one listed form: no summing
  return card({
    id: "lift",
    title: "2. Lift finds team archetypes; it does not say which pairs win",
    population: ["completed battles, unit = player-battle; species level (partners are counted per species)"],
    regulation: reg,
    band: ALL_PLAYERS,
    n: [...(teams === null ? [] : [fig(fmt.format(teams)), " Dondozo teams; "]), "pairs shown with n ≥ ",
      fig(String(partners.min_n)), " teams together"],
    baseline: regBaseline(all),
    chart: top.length ? liftBars(top) : el("p", "muted", "Dondozo's partners are not in this export."),
    how: "Dondozo's eight most frequent partners. The bar is the lift (how many times more often the two are on " +
      "the same team than if teams were random); the right column is the win rate of teams with both, minus the baseline " +
      "(coloured only when the 95% interval excludes it).",
    fact: tats ? ["Dondozo and Tatsugiri are on ", fig(fmt.format(tats.n)), " teams together, a lift of ",
      fig(tats.lift.toFixed(1)), "; those teams win ", fig(pct(tats.win_rate)), " (", fig(pp(tats.win_rate_delta)),
      " vs the baseline).", ...(rain ? [" Pelipper and Archaludon also have a high lift (", fig(rain.lift.toFixed(1)),
      ", ", fig(fmt.format(rain.n)), " teams), yet their teams win ", fig(pp(rain.win_rate_delta)), " vs the baseline."] : [])]
      : ["Dondozo and Tatsugiri are not in this export."],
    calc: ["lift = P(both on a team) ÷ (P(A) × P(B)); win rate vs baseline = win rate of teams with both − the " +
      "baseline. The two numbers are computed separately and say different things."],
    interp: ["high lift picks out known archetypes (the Dondozo + Tatsugiri Commander pair, a rain setter and its " +
      "partner): it is co-occurrence, not synergy. A pair's win rate also mixes in the other four Pokémon and who " +
      "plays the team, so even a pair above the baseline is not shown to work better together."],
    links: [["Dondozo's partners in Meta Overview", overviewLink(REG, "all", DONDOZO)],
      ["Pelipper's partners", overviewLink(REG, "all", PELIPPER)]],
  });
}

function teraCard(reg: string, tera: TeraFile): HTMLElement {
  const s = teraSummary(tera, 5);
  const byTop = [...s.top].sort((a, b) => b.types[0].type_share - a.types[0].type_share);
  const most = byTop[0], least = byTop[byTop.length - 1];
  return card({
    id: "tera",
    title: "3. About one sent-out Pokémon in five Terastallizes; the type is only partly predictable",
    population: ["completed battles; unit = a species sent out in a player-battle"],
    regulation: reg,
    band: ALL_PLAYERS,
    n: [fig(fmt.format(s.appearances)), " sent-out appearances of ", fig(String(s.species)),
      ` species (each with n ≥ ${tera.min_n}); `, fig(fmt.format(s.events)), " Tera events"],
    baseline: ["no win-rate comparison here. Reference: Tera per sent-out appearance in the ",
      `${EDA.tera.regulations} regulations with Tera is `, fig(`${pct(EDA.tera.min)}–${pct(EDA.tera.max)}`, "eda")],
    chart: teraStack(s.top),
    how: "the five species with the most Tera events; each bar splits that species' Tera events by type (three most " +
      "used types, then the rest). Each species' split is in its Overview detail (links below).",
    fact: [fig(pct(s.rate)), " of sent-out appearances Terastallize. ",
      ...(most && least ? [`Among these five, ${most.species} uses ${most.types[0].tera_type} in `,
        fig(pct(most.types[0].type_share)), ` of its Tera events, while ${least.species}'s most used type `,
        `(${least.types[0].tera_type}) takes only `, fig(pct(least.types[0].type_share)), "."] : [])],
    calc: ["rate = Σ Tera events ÷ Σ sent-out appearances over the exported species (pooled, not a mean of rates); " +
      "type share = Tera events of that type ÷ the species' Tera events."],
    interp: ["the species narrows down the Tera type but often does not settle it: over the species with at least " +
      "5,000 Tera events, the most used type takes a median of ", fig(pct(EDA.tera.medianTopType), "eda"),
      " of a species' Tera events in this regulation."],
    caution: ["win rates with and without Tera are not compared here: a Pokémon must still be on the field to " +
      "Terastallize, so the games without Tera include early faints (survivorship), and players choose when to Tera."],
    links: s.top.map((r): [string, string] => [`${r.species}'s Tera`, overviewLink(REG, "all", r.species_id)]),
  });
}

function popularityCard(reg: string, all: TeamUsage): HTMLElement {
  const pts = popularityPoints(all, MIN_TEAMS);
  const half = aboveBaselineByHalf(pts);
  const b = EDA.byBand;
  return card({
    id: "popularity",
    title: "4. Popular Pokémon win more often in every rating band; rating does not explain it",
    population: ["completed battles, unit = player-battle"],
    regulation: reg,
    band: [...ALL_PLAYERS, " for the chart; each rating band separately (its own baseline) for the band correlations"],
    n: ["chart: ", fig(String(pts.length)), ` forms with at least ${fmt.format(MIN_TEAMS)} teams (`, ...pbCount(all),
      "); correlations: ", fig(String(EDA.popularity.species), "eda"), " species (all players) and ",
      fig(String(b.species), "eda"), " species (per band)"],
    baseline: regBaseline(all),
    chart: scatter(pts),
    how: "one dot per form: how often it is brought (left to right, log scale) against how its teams do compared " +
      "with the baseline (filled dots above it). Hover a dot for its name and n.",
    fact: ["in the more used half of these forms ", fig(`${half.upper.above} of ${half.upper.of}`),
      " win above the baseline; in the less used half ", fig(`${half.lower.above} of ${half.lower.of}`),
      ". At species level the rank correlation between usage and win rate vs baseline is ", fig(String(EDA.popularity.rho), "eda"),
      " (", fig(`${EDA.popularity.min}–${EDA.popularity.max}`, "eda"),
      " in the seven Scarlet/Violet regulations). Inside each rating band, against that band's baseline, it is ",
      fig(signed(b.below_1200), "eda"), " below 1200, ", fig(signed(b["1200_1399"]), "eda"),
      " at 1200–1399, ", fig(signed(b["1400_1499"]), "eda"), " at 1400–1499 and ", fig(signed(b["1500_plus"]), "eda"), " at 1500+."],
    calc: ["Spearman rank correlation (EDA report, species level: species with ≥ 2,000 teams; the band view uses the " +
      "species with ≥ 500 teams at 1500+ so every band counts the same species). The half split is over the forms in " +
      "the chart, by usage share. The correlations are not shown in the Overview; its tables hold the usage and " +
      "win rate of each form in each band."],
    interp: ["popularity and win rate move together at every rating, so the link is not just strong players " +
      "picking popular Pokémon. Most of it comes from rarely used Pokémon winning less; whether they are weaker or less " +
      "well played, the data cannot separate. This is correlation, not cause: bringing a popular Pokémon is not shown " +
      "to raise anyone's win rate."],
    links: [["Open the table in Meta Overview", overviewLink(REG, "all")],
      ["1500+ only", overviewLink(REG, "1500_plus")]],
  });
}

async function start() {
  const status = document.getElementById("status")!;
  const main = document.getElementById("insights")!;
  let manifest: Manifest;
  try {
    manifest = parseManifest(await fetchJson(`${BASE}manifest.json`));
    const reg = regulationLabel(manifest, REG);
    const [low, high, all, partners, tera] = await Promise.all([
      loadTeamUsage(manifest, REG, "below_1200", fetchJson, BASE),
      loadTeamUsage(manifest, REG, "1500_plus", fetchJson, BASE),
      loadTeamUsage(manifest, REG, "all", fetchJson, BASE),
      loadPairFile(manifest, "partners", REG, "all", fetchJson, BASE),
      loadTeraFile(manifest, REG, "all", fetchJson, BASE),
    ]);
    document.getElementById("reg-name")!.textContent = reg;
    document.getElementById("snapshot")!.textContent = `Data snapshot ${manifest.snapshot_date}.`;
    main.replaceChildren(shiftCard(reg, low, high), partnerCard(reg, all, partners), teraCard(reg, tera),
      popularityCard(reg, all));
    status.textContent = "";
    status.hidden = true;
  } catch (e) {
    status.textContent = `Could not load the insights data: ${e instanceof Error ? e.message : String(e)}`;
  }
}

void start();
