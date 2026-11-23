import { describe, expect, it } from "vitest";
import {
  DataError,
  SCHEMA_VERSION,
  filterRows,
  loadTeamUsage,
  parseManifest,
  readFilters,
  selectFile,
  writeFilters,
  type Manifest,
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
  },
  ...over,
});

const row = (species: string, n: number) => ({
  species_id: n, species, n, usage_share: 0.1, win_rate: 0.5, win_ci_low: 0.4, win_ci_high: 0.6,
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

describe("URL filters", () => {
  const m = parseManifest(manifest()) as Manifest;

  it("round-trips regulation, band and search", () => {
    const qs = writeFilters({ regulation: "regA", band: "1500_plus", query: "inc" });
    expect(readFilters(qs, m)).toEqual({ regulation: "regA", band: "1500_plus", query: "inc" });
  });

  it("falls back to valid defaults for unknown values", () => {
    expect(readFilters("?reg=nope&band=nope", m)).toEqual({ regulation: "regA", band: "all", query: "" });
    expect(readFilters("?reg=regB&band=1500_plus", m)).toEqual({ regulation: "regB", band: "all", query: "" });
  });
});
