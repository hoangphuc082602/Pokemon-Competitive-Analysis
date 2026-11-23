import { describe, expect, it } from "vitest";
import {
  DataError,
  SCHEMA_VERSION,
  filterRows,
  chartPoints,
  formNote,
  loadPairFile,
  loadTeamUsage,
  loadTeraFile,
  loadTrendFile,
  paginate,
  parseManifest,
  speciesEntry,
  teraEntry,
  readFilters,
  selectFile,
  writeFilters,
  type Manifest,
  type UsageRow,
} from "./data";

const manifest = (over: Record<string, unknown> = {}) => ({
  schema_version: SCHEMA_VERSION,
  snapshot_date: "2026-11-01",
  min_n: 100,
  population: "completed VGC battles",
  totals: { battles: 500, player_battles: 1000 },
  regulations: [
    { id: "regA", battles: 500, player_battles: 1000, bands: ["all", "1500_plus"] },
    { id: "regB", battles: null, player_battles: null, bands: ["all"] },
  ],
  bands: ["all", "1500_plus"],
  datasets: {
    team_usage: [
      { regulation: "regA", rating_band: "all", path: "team_usage/regA__all.json", rows: 2, bytes: 10 },
      { regulation: "regA", rating_band: "1500_plus", path: "team_usage/regA__1500_plus.json", rows: 1, bytes: 10 },
      { regulation: "regB", rating_band: "all", path: "team_usage/regB__all.json", rows: 1, bytes: 10 },
    ],
    partners: [
      { regulation: "regA", rating_band: "all", path: "partners/regA__all.json", rows: 1, bytes: 10 },
      { regulation: "regA", rating_band: "1500_plus", path: "partners/regA__1500_plus.json", rows: 1, bytes: 10 },
    ],
    matchups: [{ regulation: "regA", rating_band: "1500_plus", path: "matchups/regA__1500_plus.json", rows: 1, bytes: 10 }],
    trend: [{ regulation: "regA", rating_band: "1500_plus", path: "trend/regA__1500_plus.json", rows: 1, bytes: 10 }],
    tera: [{ regulation: "regA", rating_band: "1500_plus", path: "tera/regA__1500_plus.json", rows: 1, bytes: 10 }],
  },
  ...over,
});

const row = (species: string, n: number, form: Partial<UsageRow> = {}) => ({
  species_id: n, species, poke_id: n, form: species.toLowerCase(), form_basis: "listed" as const, label: species,
  ...form, n, usage_share: 0.1, win_rate: 0.5, win_ci_low: 0.4, win_ci_high: 0.6,
  win_rate_delta: 0, lead_rate: 0.2,
});

describe("parseManifest", () => {
  it("accepts the current schema version", () => {
    expect(parseManifest(manifest()).regulations.map((r) => r.id)).toEqual(["regA", "regB"]);
  });

  it("rejects a different schema version with a typed error", () => {
    expect(() => parseManifest(manifest({ schema_version: SCHEMA_VERSION + 1 }))).toThrow(DataError);
    expect(() => parseManifest(manifest({ schema_version: 0 })))
      .toThrow(expect.objectContaining({ code: "schema-version" }));
  });

  it("rejects a v1 (species-level) export", () => {
    expect(() => parseManifest(manifest({ schema_version: 1 })))
      .toThrow(expect.objectContaining({ code: "schema-version" }));
  });

  it("rejects something that is not a manifest", () => {
    expect(() => parseManifest({ hello: 1 })).toThrow(DataError);
    expect(() => parseManifest(null)).toThrow(DataError);
  });
});

describe("selectFile", () => {
  const m = parseManifest(manifest()) as Manifest;

  it("returns the single file of the chosen regulation and band", () => {
    expect(selectFile(m, "regA", "1500_plus")?.path).toBe("team_usage/regA__1500_plus.json");
    expect(selectFile(m, "regA", "all")?.path).toBe("team_usage/regA__all.json");
  });

  it("never falls back to another band or combines bands when the band is missing", () => {
    expect(selectFile(m, "regB", "1500_plus")).toBeUndefined();
  });
});

describe("loadTeamUsage", () => {
  const m = parseManifest(manifest()) as Manifest;
  const fetchJson = (body: unknown) => async (_url: string) => body;

  it("loads exactly one band's rows", async () => {
    const urls: string[] = [];
    const f = async (url: string) => {
      urls.push(url);
      return { regulation: "regA", rating_band: "1500_plus", player_battles: 400, baseline_win_rate: 0.47, min_n: 100,
               rows: [row("Incineroar", 120)] };
    };
    const data = await loadTeamUsage(m, "regA", "1500_plus", f, "data/");
    expect(urls).toEqual(["data/team_usage/regA__1500_plus.json"]);
    expect(data.rows.map((r) => r.n)).toEqual([120]);
  });

  it("rejects a file whose band does not match the request", async () => {
    const body = { regulation: "regA", rating_band: "all", player_battles: 1, baseline_win_rate: 0.5, min_n: 100, rows: [] };
    await expect(loadTeamUsage(m, "regA", "1500_plus", fetchJson(body), "")).rejects.toThrow(DataError);
  });

  it("rejects an unknown regulation x band", async () => {
    await expect(loadTeamUsage(m, "regB", "1500_plus", fetchJson({}), "")).rejects.toThrow(DataError);
  });
});

describe("filterRows", () => {
  it("matches species names case-insensitively and keeps order", () => {
    const rows = [row("Urshifu", 3), row("Incineroar", 2), row("Rillaboom", 1)];
    expect(filterRows(rows, "  inC ").map((r) => r.species)).toEqual(["Incineroar"]);
    expect(filterRows(rows, "").length).toBe(3);
  });
});

describe("paginate", () => {
  const rows = Array.from({ length: 32 }, (_, i) => i + 1);

  it("cuts pages of the given size and reports the shown range", () => {
    expect(paginate(rows, 1, 15)).toEqual({ rows: rows.slice(0, 15), page: 1, pages: 3, from: 1, to: 15 });
    expect(paginate(rows, 3, 15)).toEqual({ rows: [31, 32], page: 3, pages: 3, from: 31, to: 32 });
  });

  it("clamps an out-of-range page and handles an empty list", () => {
    expect(paginate(rows, 9, 15).page).toBe(3);
    expect(paginate(rows, 0, 15).page).toBe(1);
    expect(paginate([], 2, 15)).toEqual({ rows: [], page: 1, pages: 1, from: 0, to: 0 });
  });
});

describe("form rows", () => {
  const forms = [
    row("Calyrex", 2, { form: "calyrex-shadow", label: "Calyrex-Shadow" }),
    row("Urshifu", 1, { poke_id: null, form: null, form_basis: "unobserved", label: "Urshifu (form unknown)" }),
  ];

  it("search matches the form label and the species", () => {
    expect(filterRows(forms, "shadow").map((r) => r.label)).toEqual(["Calyrex-Shadow"]);
    expect(filterRows(forms, "calyrex").map((r) => r.label)).toEqual(["Calyrex-Shadow"]);
  });

  it("explains every masked or species-level row and leaves listed forms plain", () => {
    expect(formNote(forms[0])).toBe("");
    expect(formNote(forms[1])).toMatch(/never sent out/);
    expect(formNote(row("Urshifu", 1, { form_basis: "observed" }))).toMatch(/only teams where/);
    expect(formNote(row("Arceus", 1, { poke_id: null, form: null, form_basis: "species_only" }))).toMatch(/master data/);
  });
});

describe("URL filters", () => {
  const m = parseManifest(manifest()) as Manifest;

  it("round-trips regulation, band and search", () => {
    const qs = writeFilters({ regulation: "regA", band: "1500_plus", query: "inc", species: null });
    expect(readFilters(qs, m)).toEqual({ regulation: "regA", band: "1500_plus", query: "inc", species: null });
  });

  it("round-trips the selected species so a species detail view is linkable", () => {
    const qs = writeFilters({ regulation: "regA", band: "all", query: "", species: 727 });
    expect(qs).toBe("?reg=regA&band=all&sp=727");
    expect(readFilters(qs, m).species).toBe(727);
  });

  it("falls back to valid defaults for unknown values", () => {
    expect(readFilters("?reg=nope&band=nope&sp=x", m)).toEqual({ regulation: "regA", band: "all", query: "", species: null });
    expect(readFilters("?reg=regB&band=1500_plus", m)).toEqual({ regulation: "regB", band: "all", query: "", species: null });
  });
});

describe("partners and matchups", () => {
  const m = parseManifest(manifest()) as Manifest;
  const partner = (species_id: number, species: string, n: number) => ({
    species_id, species, n, share: 0.5, lift: 1.8, win_rate: 0.6, win_ci_low: 0.5, win_ci_high: 0.7, win_rate_delta: 0.05 });
  const file = { regulation: "regA", rating_band: "1500_plus", min_n: 100,
                 rows: [{ species_id: 727, species: "Incineroar", partners: [partner(892, "Urshifu", 150)] }] };

  it("requires the partners and matchups datasets of a v3 manifest", () => {
    const { partners: _p, ...rest } = manifest().datasets;
    expect(() => parseManifest(manifest({ datasets: rest }))).toThrow(expect.objectContaining({ code: "invalid" }));
  });

  it("loads exactly the selected regulation x band file", async () => {
    const urls: string[] = [];
    const data = await loadPairFile(m, "partners", "regA", "1500_plus", async (u) => { urls.push(u); return file; }, "d/");
    expect(urls).toEqual(["d/partners/regA__1500_plus.json"]);
    expect(speciesEntry(data, 727)?.partners?.map((p) => p.species)).toEqual(["Urshifu"]);
    expect(speciesEntry(data, 1)).toBeUndefined();
  });

  it("never substitutes another band when the selected band has no file", async () => {
    await expect(loadPairFile(m, "matchups", "regA", "all", async () => file, "")).rejects
      .toThrow(expect.objectContaining({ code: "not-found" }));
  });

  it("rejects a file of another band", async () => {
    await expect(loadPairFile(m, "partners", "regA", "all", async () => file, "")).rejects
      .toThrow(expect.objectContaining({ code: "mismatch" }));
  });
});

describe("monthly trend", () => {
  const m = parseManifest(manifest()) as Manifest;
  const point = (month: string, usage_share: number) =>
    ({ month, n: 150, usage_share, win_rate: 0.5, win_ci_low: 0.4, win_ci_high: 0.6 });
  const file = {
    regulation: "regA", rating_band: "1500_plus", min_n: 100,
    months: [
      { month: "2024-01", player_battles: 1000, tail: false },
      { month: "2024-02", player_battles: 900, tail: false },
      { month: "2024-03", player_battles: 800, tail: false },
      { month: "2024-04", player_battles: 30, tail: true },
    ],
    rows: [{ species_id: 727, species: "Incineroar",
             points: [point("2024-01", 0.4), point("2024-03", 0.3), point("2024-04", 0.1)] }],   // 2024-02: n < 100
  };

  it("requires the trend and tera datasets of a v4 manifest", () => {
    const { trend: _t, ...rest } = manifest().datasets;
    expect(() => parseManifest(manifest({ datasets: rest }))).toThrow(expect.objectContaining({ code: "invalid" }));
    const { tera: _x, ...rest2 } = manifest().datasets;
    expect(() => parseManifest(manifest({ datasets: rest2 }))).toThrow(expect.objectContaining({ code: "invalid" }));
  });

  it("loads exactly the selected regulation x band file and never another band", async () => {
    const urls: string[] = [];
    await loadTrendFile(m, "regA", "1500_plus", async (u) => { urls.push(u); return file; }, "d/");
    expect(urls).toEqual(["d/trend/regA__1500_plus.json"]);
    await expect(loadTrendFile(m, "regA", "all", async () => file, "")).rejects
      .toThrow(expect.objectContaining({ code: "not-found" }));
  });

  it("charts the non-tail months, leaves gaps for hidden points and discloses the tail months", () => {
    const c = chartPoints(file, 727);
    expect(c.months).toEqual(["2024-01", "2024-02", "2024-03"]);
    expect(c.points.map((p) => [p.month, p.usage_share])).toEqual([["2024-01", 0.4], ["2024-03", 0.3]]);
    expect(c.tailMonths).toEqual(["2024-04"]);
    expect(c.hiddenTailPoints).toBe(1);
  });

  it("gives the band's battles of each charted month and flags months with few battles in this band", () => {
    // tail is per regulation, so a band can have a tiny month that is still charted
    const thin = { ...file, months: file.months.map((x) => (x.month === "2024-03" ? { ...x, player_battles: 40 } : x)) };
    const c = chartPoints(thin, 727);
    expect(c.monthBattles).toEqual({ "2024-01": 1000, "2024-02": 900, "2024-03": 40 });
    expect(c.thinMonths).toEqual(["2024-03"]);   // 40 < 5% of the band's busiest month (1000)
    expect(chartPoints(file, 727).thinMonths).toEqual([]);
  });

  it("gives an empty series for a species without points", () => {
    const c = chartPoints(file, 1);
    expect(c.points).toEqual([]);
    expect(c.tailMonths).toEqual(["2024-04"]);
    expect(c.hiddenTailPoints).toBe(0);
  });
});

describe("tera", () => {
  const m = parseManifest(manifest()) as Manifest;
  const file = { regulation: "regA", rating_band: "1500_plus", min_n: 100,
                 rows: [{ species_id: 727, species: "Incineroar", n: 400, tera_events: 150, tera_rate: 0.375,
                          tera_rate_ci_low: 0.33, tera_rate_ci_high: 0.42, win_rate_tera: 0.6, win_rate_no_tera: null,
                          types: [{ tera_type: "Ghost", events: 120, type_share: 0.8 }] }] };

  it("loads the band's file and finds a species", async () => {
    const urls: string[] = [];
    const data = await loadTeraFile(m, "regA", "1500_plus", async (u) => { urls.push(u); return file; }, "d/");
    expect(urls).toEqual(["d/tera/regA__1500_plus.json"]);
    expect(teraEntry(data, 727)?.types.map((t) => t.tera_type)).toEqual(["Ghost"]);
    expect(teraEntry(data, 1)).toBeUndefined();
  });

  it("rejects a file of another band", async () => {
    const other = { ...file, rating_band: "all" };
    await expect(loadTeraFile(m, "regA", "1500_plus", async () => other, "")).rejects
      .toThrow(expect.objectContaining({ code: "mismatch" }));
  });
});
