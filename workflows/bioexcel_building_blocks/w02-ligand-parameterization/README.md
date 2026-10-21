# W-04 · Ligand Parameterization (GAFF / ACPype)

GAFF force-field parameters for a small molecule, ready for GROMACS.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Generates GROMACS parameters for a ligand with GAFF via ACPype. The ligand comes from a PDB ligand code (default IBP, ibuprofen) or an upload; OpenBabel adds hydrogens at the chosen pH and minimizes them. The workflow has 4 tasks.

## Pipeline

```
fetch_ligand         Fetch ligand_code from the PDB, or use the uploaded ligand
add_hydrogens        Add hydrogens at the chosen pH (OpenBabel)
minimize_hydrogens   Minimize hydrogen positions (OpenBabel, GAFF)
parameterize         ACPype / GAFF parameters
```

## Inputs / Outputs

- Input: `ligand_code` or, when empty, the `ligand` upload.
- Outputs: `results/ligand.pdb`, `ligand.H.mol2`, `ligand.H.min.pdb`, `ligand.params.gro`, `ligand.params.itp`, `ligand.params.top`.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `ligand_code` | `IBP` | PDB Chemical Component code; clear it to use `ligand` |
| `ligand` | `examples/ibp.pdb` | Ligand used when `ligand_code` is empty (heavy atoms suffice) |
| `ph` | `7.4` | pH for adding hydrogens |
| `net_charge` | `-1` | Formal net charge at that pH, passed to ACPype |

`net_charge` must match the ligand at the chosen pH, otherwise ACPype (AM1-BCC) fails or gives wrong charges.

## References

- [ACPype](https://github.com/alanwilter/acpype)
- [Open Babel](https://github.com/openbabel/openbabel)
- [biobb_chemistry](https://github.com/bioexcel/biobb_chemistry)
- [biobb_io](https://github.com/bioexcel/biobb_io)
- [GROMACS](https://www.gromacs.org)
- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [GAFF (General AMBER Force Field)](https://ambermd.org/antechamber/gaff.html)
- [BioExcel ligand parameterization tutorial](https://biobb-wf-ligand-parameterization.readthedocs.io)
