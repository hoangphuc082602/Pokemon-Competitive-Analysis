// Runs the project's Python damage engine in the browser with Pyodide (ADR-014, #16). Imported only by the calc page
// and the team page (team analysis, #19, loaded on request), so no other page downloads Pyodide. The engine source files are bundled as text (?raw) straight from python/ —
// one source of truth, tested by pytest — and written into Pyodide's file system before the façade is imported.
import pkgInit from "../../python/__init__.py?raw";
import calcInit from "../../python/calculations/__init__.py?raw";
import baseDamage from "../../python/calculations/base_damage.py?raw";
import calcFacade from "../../python/calculations/calc_facade.py?raw";
import damageCalc from "../../python/calculations/damage_calc_v2.py?raw";
import battleStats from "../../python/calculations/get_battle_stats.py?raw";
import percentageKo from "../../python/calculations/percentage_ko.py?raw";
import roleLabel from "../../python/calculations/role_label.py?raw";
import speedCalc from "../../python/calculations/speed_calc.py?raw";
import stabModifier from "../../python/calculations/stab_modifier.py?raw";
import statsCalc from "../../python/calculations/stats_calc.py?raw";
import teamSynergy from "../../python/calculations/team_synergy.py?raw";
import typeCalc from "../../python/calculations/type_calc.py?raw";
import type { CalcResult } from "./calc";
import type { TeamSummary } from "./team-analysis";

export const PYODIDE_VERSION = "0.26.4";   // Python 3.12, as CI
export const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

/** Every module the façade imports, transitively (pytest checks this list against the façade's imports). */
export const ENGINE_FILES: Record<string, string> = {
  "python/__init__.py": pkgInit,
  "python/calculations/__init__.py": calcInit,
  "python/calculations/base_damage.py": baseDamage,
  "python/calculations/calc_facade.py": calcFacade,
  "python/calculations/damage_calc_v2.py": damageCalc,
  "python/calculations/get_battle_stats.py": battleStats,
  "python/calculations/percentage_ko.py": percentageKo,
  "python/calculations/role_label.py": roleLabel,
  "python/calculations/speed_calc.py": speedCalc,
  "python/calculations/stab_modifier.py": stabModifier,
  "python/calculations/stats_calc.py": statsCalc,
  "python/calculations/team_synergy.py": teamSynergy,
  "python/calculations/type_calc.py": typeCalc,
};

const HOME = "/home/pyodide";

interface PyodideLike {
  FS: { mkdirTree(path: string): void; writeFile(path: string, data: string): void };
  runPython(code: string): unknown;
  globals: { get(name: string): (arg: string) => string };
}

export interface Engine {
  calculate(request: unknown): CalcResult;
  /** calc_facade.team_summary (#19). */
  teamSummary(request: unknown): TeamSummary;
  /** Seconds from the start of the download to the façade being importable. */
  seconds: number;
  /** Bytes transferred for Pyodide's own files (0 when the browser does not report it, e.g. from cache). */
  bytes: number;
}

/** "Traceback ... ValueError: EVs total 516 > 508" -> "EVs total 516 > 508". */
export function pythonErrorMessage(e: unknown): string {
  const text = e instanceof Error ? e.message : String(e);
  const last = text.trim().split("\n").pop() ?? text;
  return last.replace(/^\w+(Error|Exception): /, "");
}

let pending: Promise<Engine> | null = null;

export function loadEngine(): Promise<Engine> {
  pending ??= (async () => {
    const t0 = performance.now();
    const mod = (await import(/* @vite-ignore */ `${PYODIDE_URL}pyodide.mjs`)) as {
      loadPyodide(opts: { indexURL: string }): Promise<PyodideLike>;
    };
    const py = await mod.loadPyodide({ indexURL: PYODIDE_URL });
    for (const [path, source] of Object.entries(ENGINE_FILES)) {
      py.FS.mkdirTree(`${HOME}/${path.slice(0, path.lastIndexOf("/"))}`);
      py.FS.writeFile(`${HOME}/${path}`, source);
    }
    py.runPython(`import sys\nsys.path.insert(0, "${HOME}")\nfrom python.calculations.calc_facade import calculate_json, team_summary_json`);
    const calculateJson = py.globals.get("calculate_json");
    const teamSummaryJson = py.globals.get("team_summary_json");
    const bytes = performance.getEntriesByType("resource")
      .filter((e) => e.name.startsWith(PYODIDE_URL))
      .reduce((t, e) => t + ((e as PerformanceResourceTiming).transferSize || 0), 0);
    return {
      calculate: (request: unknown) => JSON.parse(calculateJson(JSON.stringify(request))) as CalcResult,
      teamSummary: (request: unknown) => JSON.parse(teamSummaryJson(JSON.stringify(request))) as TeamSummary,
      seconds: (performance.now() - t0) / 1000,
      bytes,
    };
  })();
  pending.catch(() => { pending = null; });   // a failed load can be retried
  return pending;
}
