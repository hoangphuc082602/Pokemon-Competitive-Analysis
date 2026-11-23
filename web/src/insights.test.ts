import { describe, expect, it } from "vitest";
import { aboveBaselineByHalf, bandShift, overviewLink, popularityPoints, teraSummary, textOn, typeColor } from "./insights";
import type { TeamUsage, UsageRow } from "./data";

const row = (species_id: number, species: string, n: number, usage_share: number,
             over: Partial<UsageRow> = {}): UsageRow => ({
  species_id, species, poke_id: species_id, form: species.toLowerCase(), form_basis: "listed", label: species,
  n, usage_share, win_rate: 0.5, win_ci_low: 0.49, win_ci_high: 0.51, win_rate_delta: 0, lead_rate: 0.3, ...over,
});
const usage = (band: string, rows: UsageRow[]): TeamUsage => ({
  regulation: "regA", rating_band: band, player_battles: 10000, baseline_win_rate: 0.5, min_n: 100, rows,
});

describe("bandShift", () => {
  const low = usage("below_1200", [
    row(1, "Alpha", 4000, 0.40),
    row(2, "Beta", 3000, 0.04),
    row(3, "Gamma", 2500, 0.25),
    row(4, "Masked", 5000, 0.30, { form_basis: "observed", label: "Masked-A (seen in battle)" }),
    row(5, "Split", 3000, 0.10, { label: "Split-A" }),
    row(5, "Split", 2500, 0.08, { label: "Split-B", poke_id: 99 }),
    row(6, "Rare", 1500, 0.20),
  ]);
  const high = usage("1500_plus", [
    row(1, "Alpha", 3000, 0.31),
    row(2, "Beta", 2200, 0.104),
    row(3, "Gamma", 2600, 0.26),
    row(4, "Masked", 3000, 0.45, { form_basis: "observed" }),
    row(5, "Split", 2100, 0.20, { label: "Split-A" }),
    row(6, "Rare", 2500, 0.30),
  ]);

  it("compares one listed form per species in both bands, sorted by shift", () => {
    const out = bandShift(low, high, 2000);
    expect(out.map((r) => r.label)).toEqual(["Alpha", "Gamma", "Beta"]);
    expect(out[0]).toMatchObject({ species_id: 1, low: 0.40, high: 0.31, nLow: 4000, nHigh: 3000 });
    expect(out[0].shift).toBeCloseTo(-0.09, 10);
    expect(out[2].shift).toBeCloseTo(0.064, 10);
  });

  it("never merges forms, never reads masked rows and drops species under the threshold in either band", () => {
    const ids = bandShift(low, high, 2000).map((r) => r.species_id);
    expect(ids).not.toContain(4);   // observed (masked) form
    expect(ids).not.toContain(5);   // two forms in one band
    expect(ids).not.toContain(6);   // n 1500 < 2000 below 1200
  });
});

describe("teraSummary", () => {
  const tr = (species_id: number, n: number, tera_events: number, types: [string, number][]) => ({
    species_id, species: `S${species_id}`, n, tera_events, tera_rate: tera_events / n, tera_rate_ci_low: 0,
    tera_rate_ci_high: 1, win_rate_tera: null, win_rate_no_tera: null, win_rate_tera_delta: null,
    win_rate_no_tera_delta: null, types: types.map(([tera_type, type_share]) => ({ tera_type, events: 0, type_share })),
  });
  const file = { regulation: "regA", rating_band: "all", min_n: 100, baseline_win_rate: 0.5, rows: [
    tr(1, 1000, 300, [["Water", 0.5], ["Steel", 0.3]]),
    tr(2, 3000, 300, [["Fairy", 0.9]]),
    tr(3, 1000, 400, []),
  ] };

  it("pools Tera events over sent-out appearances of the exported species (not a mean of rates)", () => {
    const s = teraSummary(file, 2);
    expect(s.appearances).toBe(5000);
    expect(s.events).toBe(1000);
    expect(s.rate).toBeCloseTo(0.2, 10);
    expect(s.species).toBe(3);
  });

  it("lists the species with most Tera events that have a type split, most events first", () => {
    expect(teraSummary(file, 2).top.map((r) => r.species_id)).toEqual([1, 2]);
  });
});

describe("popularityPoints", () => {
  it("keeps listed forms with n >= minN, as usage and win rate vs the band baseline", () => {
    const data = usage("all", [
      row(1, "Alpha", 4000, 0.40, { win_rate_delta: 0.02 }),
      row(2, "Beta", 1999, 0.02, { win_rate_delta: -0.05 }),
      row(4, "Masked", 9000, 0.30, { form_basis: "unobserved", win_rate_delta: 0.05 }),
    ]);
    expect(popularityPoints(data, 2000)).toEqual([{ species_id: 1, label: "Alpha", n: 4000, usage: 0.40, delta: 0.02 }]);
  });
});

describe("overviewLink", () => {
  it("opens the Meta Overview at a regulation and band", () => {
    expect(overviewLink("gen9vgc2026regf", "1500_plus")).toBe("./?reg=gen9vgc2026regf&band=1500_plus");
  });
  it("opens the species detail when a species is given", () => {
    expect(overviewLink("gen9vgc2026regf", "all", 977)).toBe("./?reg=gen9vgc2026regf&band=all&sp=977#detail");
  });
});

describe("aboveBaselineByHalf", () => {
  const p = (usage: number, delta: number) => ({ species_id: 0, label: "", n: 2000, usage, delta });
  it("counts forms above the band baseline in the more used and the less used half", () => {
    const out = aboveBaselineByHalf([p(0.5, 0.01), p(0.4, -0.01), p(0.3, 0.02), p(0.02, -0.03), p(0.01, 0.0), p(0.03, -0.02)]);
    expect(out).toEqual({ upper: { above: 2, of: 3 }, lower: { above: 0, of: 3 } });
  });
  it("puts the middle form of an odd count in the less used half", () => {
    const out = aboveBaselineByHalf([p(0.5, 0.01), p(0.3, 0.01), p(0.1, 0.01)]);
    expect(out).toEqual({ upper: { above: 1, of: 1 }, lower: { above: 2, of: 2 } });
  });
});

describe("typeColor / textOn", () => {
  it("gives each Tera type its colour, case-insensitively, and null for an unknown type", () => {
    expect(typeColor("Fire")).toBe("#EE8130");
    expect(typeColor("fairy")).toBe("#D685AD");
    expect(typeColor("Stellar")).not.toBeNull();
    expect(typeColor("other")).toBeNull();
  });
  it("puts dark text on light colours and white text on dark ones", () => {
    expect(textOn("#F7D02C")).toBe("#1c1d1f");   // Electric
    expect(textOn("#6F35FC")).toBe("#ffffff");   // Dragon
  });
});
