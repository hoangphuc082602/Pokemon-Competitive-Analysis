import "./style.css";
import { parseCalcMaster } from "./calc";
import { browserStorage, createTeamStore } from "./team";
import { mountTeamAnalysis } from "./team-analysis-panel";
import { mountTeamPanel } from "./team-panel";

// Team builder page (#17) and team analysis (#19). The Python engine (Pyodide) is loaded only when the visitor asks
// for the analysis; building and saving teams needs calc_master.json alone.
const BASE = `${import.meta.env.BASE_URL}data/`;

async function main() {
  const status = document.getElementById("data-status") as HTMLParagraphElement;
  let master;
  try {
    const res = await fetch(`${BASE}calc_master.json`);
    if (!res.ok) throw new Error(`calc_master.json: HTTP ${res.status}`);
    master = parseCalcMaster(await res.json());
  } catch (e) {
    status.textContent = `Could not load the game data (${e instanceof Error ? e.message : e}). Reload the page to retry.`;
    return;
  }
  status.hidden = true;
  const analyse = mountTeamAnalysis(document.getElementById("analysis")!, master);
  mountTeamPanel(document.getElementById("team")!, master, createTeamStore(browserStorage), "./calc.html", analyse);
  document.getElementById("analysis")!.hidden = false;
}

void main();
