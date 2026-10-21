# W-13 · Protein-Ligand Docking into an fpocket Cavity

Dock a ligand with AutoDock Vina into a cavity found by fpocket.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Docks one ligand into a receptor with AutoDock Vina (default p38-alpha MAP kinase, PDB 3HEC, imatinib STI). fpocket detects cavities on the receptor, which are filtered by volume (800-2000 A^3); the chosen `pocket` defines the docking box. The top pose is assembled into a complex. The workflow has 14 tasks.

## Pipeline

```
fetch_pdb                    Download pdb_id or use the uploaded receptor
extract_protein              Remove ligands, ions, water
fpocket_run                  Detect cavities
fpocket_filter               Filter by volume
fpocket_select               Extract the chosen pocket
box                          Docking box around the cavity
str_check_add_hydrogens      Receptor PDBQT
ideal_sdf                    Download ligand_code as SDF, or use the upload
babel_convert_sdf_to_pdb     SDF to PDB
babel_convert_pdb_to_pdbqt   Ligand PDBQT
autodock_vina_run            Docking
extract_model_pdbqt          Top pose
babel_convert_pdbqt_to_pdb   Pose to PDB
cat_pdb                      Receptor + pose complex
```

## Inputs / Outputs

- Inputs: `pdb_id` or, when empty, the `structure` upload; the ligand by code or SDF.
- Outputs (`results/`): `download.pdb`, `pdb_protein.pdb`, `fpocket_all_pockets.zip`, `fpocket_summary.json`, `fpocket_filter_pockets.zip`, `fpocket_cavity.pdb`, `fpocket_pocket.pqr`, `box.pdb`, `ideal.sdf`, `ligand.pdb`, `prep_ligand.pdbqt`, `prep_receptor.pdbqt`, `output_vina.pdbqt`, `output_model.pdbqt`, `output_model.pdb`, `output_structure.pdb`.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `pdb_id` | `3HEC` | RCSB PDB code; clear it to use `structure` |
| `structure` | `examples/3hec.pdb` | Receptor used when `pdb_id` is empty |
| `pocket` | `6` | fpocket rank (after the volume filter) of the pocket that defines the box; differs per receptor |
| `box_offset_a` | `12` | Padding around the pocket on each side of the box (A) |
| `ligand_code` | `STI` | Ligand to dock, as PDB code; clear it to use `ligand_sdf` |
| `ligand_sdf` | `examples/sti_ideal.sdf` | 3D SDF used when `ligand_code` is empty |

## References

- [fpocket](https://github.com/Discngine/fpocket)
- [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina)
- [Open Babel](https://github.com/openbabel/openbabel)
- [biobb_vs](https://github.com/bioexcel/biobb_vs)
- [biobb_chemistry](https://github.com/bioexcel/biobb_chemistry)
- [biobb_structure_utils](https://github.com/bioexcel/biobb_structure_utils)
- [biobb_io](https://github.com/bioexcel/biobb_io)
- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [BioExcel protein-ligand docking tutorial (fpocket variant)](https://biobb-wf-virtual-screening.readthedocs.io)
