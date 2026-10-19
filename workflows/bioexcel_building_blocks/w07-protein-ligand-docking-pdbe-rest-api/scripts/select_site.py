"""Pick the PDBe binding site of one ligand and write the biobb box_residues config.

Reads the residues.json written by biobb `api_binding_site` (PDBe REST API v2),
takes the site whose ligand accession matches --ligand, and writes a biobb JSON
config with its residue numbers as resid_list. Stdlib only.

    python select_site.py --residues residues.json --ligand 1N1 --offset 12 --out box.json
    python select_site.py --selftest
"""

import argparse
import json
import sys


def site_residues(residues: dict, ligand: str) -> list[int]:
    """Residue numbers (PDB numbering) of the binding site of `ligand`."""
    entry = next(iter(residues.values()))
    sites = entry["data"]
    for site in sites:
        if site["accession"].upper() == ligand.upper():
            nums = []
            for r in site["residues"]:
                nums.extend(range(int(r["startIndex"]), int(r["endIndex"]) + 1))
            return sorted(set(nums))
    found = ", ".join(s["accession"] for s in sites) or "none"
    raise SystemExit(f"site_ligand {ligand!r} has no PDBe binding site in this entry (sites: {found})")


def main(argv: list[str]) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--residues")
    p.add_argument("--ligand")
    p.add_argument("--offset", type=float)
    p.add_argument("--out")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args(argv)
    if a.selftest:
        return selftest()
    with open(a.residues) as f:
        resid = site_residues(json.load(f), a.ligand)
    cfg = {"properties": {"resid_list": resid, "offset": a.offset, "box_coordinates": True}}
    with open(a.out, "w") as f:
        json.dump(cfg, f)
    print(f"{a.ligand}: {len(resid)} residues {resid}")


def selftest() -> None:
    doc = {"3lfa": {"data": [
        {"accession": "BOG", "residues": [{"startIndex": 191, "endIndex": 191}]},
        {"accession": "1N1", "residues": [{"startIndex": 30, "endIndex": 30},
                                          {"startIndex": 51, "endIndex": 53}]},
    ]}}
    assert site_residues(doc, "1n1") == [30, 51, 52, 53]
    try:
        site_residues(doc, "STI")
    except SystemExit as e:
        assert "BOG, 1N1" in str(e)
    else:
        raise AssertionError("missing ligand must fail")
    print("selftest ok")


if __name__ == "__main__":
    main(sys.argv[1:])
