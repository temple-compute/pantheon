# W-16 · AMBER Constant-pH MD Setup

Predict per-residue pKa values with constant-pH MD in AMBER.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Runs constant-pH MD with AmberTools on a protein (default BPTI, PDB 6PTI): ff14SB with constph templates, truncated octahedron TIP3P box, ions, a `cpinutil` input for the chosen titratable residues, heat/NVT/NPT equilibration, constant-pH production with sander, and protonation analysis with `cphstats`. The workflow has 16 tasks.

## Pipeline

```
fetch_pdb          Download pdb_id or use the uploaded structure
pdb4amber          Prepare structure for constant-pH AMBER
leap_gen_top       Topology (ff14SB + constph)
leap_solvate       Truncated octahedron TIP3P box
leap_add_ions      Neutralize and add ions
parmed_cpinutil    Constant-pH input for titratable residues
sander_min ──► process_min     Minimize with backbone restraints
sander_heat ──► process_heat   Heat 0 to 300 K
sander_nvt ──► process_nvt     NVT equilibration
sander_npt ──► process_npt     NPT equilibration
sander_cph_free    Constant-pH production MD (solvph = solvent_ph)
cphstats           Protonation states and pKa
```

## Inputs / Outputs

- Input: `pdb_id` (RCSB code) or, when empty, the `structure` upload.
- Outputs (`results/`): `structure.pdb`, `structure.pdb4amber.pdb`, `structure.leap.{pdb,top,crd}`, `structure.ions.{pdb,parmtop,crd}`, `structure.cpin`, `structure.cpH.parmtop`, `sander.pH.{netcdf,rst,cpout,cprst,log,mdinfo}`, `cphstats.pH.dat`, `cphstats.pH.pop.dat`.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `pdb_id` | `6PTI` | RCSB PDB code; clear it to use `structure` |
| `structure` | `examples/6pti.pdb` | Protein used when `pdb_id` is empty |
| `solvent_ph` | `7.0` | Solvent pH of the constant-pH Monte Carlo moves (`solvph`) |
| `titratable_residues` | `AS4`, `GL4`, `CYS`, `LYS`, `TYR` | Residue types allowed to change protonation (also `HIP`) |
| `salt_m` | `0.1` | Ionic strength for generalized-Born protonation energies (`saltcon`, M) |
| `production_steps` | `2500` | sander steps of the production run (2 fs/step; moves every 100 steps) |

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [AmberTools](https://ambermd.org/AmberTools.php)
- [cpptraj](https://github.com/Amber-MD/cpptraj)
- [biobb_amber](https://github.com/bioexcel/biobb_amber)
- [biobb_analysis](https://github.com/bioexcel/biobb_analysis)
- [biobb_structure_utils](https://github.com/bioexcel/biobb_structure_utils)
- [biobb_io](https://github.com/bioexcel/biobb_io)
- [biobb_wf_amber tutorial notebooks](https://github.com/bioexcel/biobb_wf_amber)
- [AMBER Constant pH MD Tutorial](https://ambermd.org/tutorials/advanced/tutorial18/index.htm)
