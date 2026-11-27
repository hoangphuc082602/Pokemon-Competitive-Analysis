// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import type { CalcMaster } from "./calc";
import { createTeamStore, decodeTeam } from "./team";
import { mountTeamPanel } from "./team-panel";

const stats = (v: number) => ({ hp: v, atk: v, def: v, spatk: v, spdef: v, spe: v });
const MASTER: CalcMaster = {
  schema_version: 2, level: 50, skipped: [], type_chart: [],
  items: [{ name: "focus-sash", category: "held-items" }],
  forms: [{ poke_id: 987, species: "Flutter Mane", form: "flutter-mane", types: ["ghost", "fairy"], base_stats: stats(100),
    abilities: ["protosynthesis"], moves: [585], borrowed_from: null }],
  moves: [{ id: 585, name: "moonblast", type: "fairy", power: 95, damage_class: "special" }],
  natures: [{ name: "hardy", increased: null, decreased: null }, { name: "timid", increased: "spe", decreased: "atk" }],
};

function mount() {
  const root = document.createElement("div");
  document.body.replaceChildren(root);
  mountTeamPanel(root, MASTER, createTeamStore(() => null), "calc.html");
  const button = (text: string) => [...root.querySelectorAll("button")].find((b) => b.textContent === text)!;
  const select = (label: string) => [...root.querySelectorAll("label")]
    .find((l) => l.firstChild?.textContent === label)!.querySelector("select")!;
  const pick = (label: string, value: string) => {
    const s = select(label);
    s.value = value;
    s.dispatchEvent(new Event("change", { bubbles: true }));
  };
  return {
    root, button, pick,
    share: root.querySelector<HTMLInputElement>("input[readonly]")!,
    paste: root.querySelector<HTMLTextAreaElement>("textarea")!,
    status: () => root.querySelector("[role=status]")!.textContent,
  };
}

describe("team panel", () => {
  it("hides a shown share link or paste as soon as the team changes", () => {
    const p = mount();
    p.button("Add Pokémon").click();
    const shown = () => {
      p.button("Share link").click();
      p.button("Showdown paste").click();
      expect([p.share.hidden, p.paste.hidden]).toEqual([false, false]);
    };
    shown();
    p.pick("Nature", "timid");                  // a member edited
    expect([p.share.hidden, p.paste.hidden]).toEqual([true, true]);
    shown();
    const name = p.root.querySelector<HTMLInputElement>("input[type=text]:not([readonly])")!;
    name.value = "Renamed";
    name.dispatchEvent(new Event("input"));     // the team renamed
    expect([p.share.hidden, p.paste.hidden]).toEqual([true, true]);
    shown();
    p.button("Add Pokémon").click();            // a member added
    expect([p.share.hidden, p.paste.hidden]).toEqual([true, true]);
    shown();
    p.button("Remove").click();                 // a member removed
    expect([p.share.hidden, p.paste.hidden]).toEqual([true, true]);
  });

  it("keeps the picked Tera type in the share link and the Showdown paste", () => {
    const p = mount();
    p.button("Add Pokémon").click();
    p.pick("Tera type", "fairy");
    p.button("Showdown paste").click();
    expect(p.paste.value).toMatch(/^Tera Type: Fairy$/m);
    p.button("Share link").click();
    expect(decodeTeam(p.share.value.split("#team=")[1]).members[0].tera).toBe("fairy");
  });

  it("asks to copy by hand when the clipboard is unavailable", () => {
    const p = mount();
    p.button("Add Pokémon").click();
    p.button("Share link").click();
    expect(p.status()).toBe("Copy the share link below.");
    p.button("Showdown paste").click();
    expect(p.status()).toBe("Copy the Showdown paste below.");
  });
});
