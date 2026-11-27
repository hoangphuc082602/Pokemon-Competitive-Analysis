"""#37: which PokéAPI version group gives the learnset of a regulation. Seam: regulation_sources.version_group."""
import json
from pathlib import Path

import pytest

from python.analytics.regulation_sources import UnmappedRegulationError, version_group

MANIFEST = Path(__file__).resolve().parents[2] / "web" / "public" / "data" / "manifest.json"


@pytest.mark.parametrize("regulation, group", [
    ("gen9vgc2023regd", "scarlet-violet"), ("gen9vgc2025regj", "scarlet-violet"), ("gen9vgc2026regi", "scarlet-violet"),
    ("gen9championsvgc2026regm-a", "champions")])
def test_each_regulation_family_maps_to_its_game(regulation, group):
    assert version_group(regulation) == group


@pytest.mark.parametrize("regulation", ["gen10vgc2027rega", "gen9ou", "gen9vgc", "", "xgen9vgc2025regh"])
def test_an_unmapped_regulation_fails_loudly(regulation):
    with pytest.raises(UnmappedRegulationError, match="version group"):
        version_group(regulation)


@pytest.mark.skipif(not MANIFEST.exists(), reason="no web export in this checkout")
def test_every_regulation_of_the_published_manifest_is_mapped():
    regulations = [r["id"] for r in json.loads(MANIFEST.read_text(encoding="utf-8"))["regulations"]]
    assert regulations and all(version_group(r) for r in regulations)
