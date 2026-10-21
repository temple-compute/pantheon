# W-11 · Protein-Ligand Docking with a Cluster90 Binding Site

Dock a ligand with AutoDock Vina into a binding site inferred from PDB Cluster90 homologs.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Docks one ligand into a receptor with AutoDock Vina (default p38-alpha MAP kinase, PDB 3HEC, imatinib STI). The docking box is placed where the `site_ligand` binds across the Cluster90 homologs of the receptor. The top pose is assembled into a protein-ligand complex. The workflow has 14 tasks.

## Pipeline

```
create_results_folder     Create results folder
fetch_pdb                 Download pdb_id
extract_molecule          Extract protein
pdb_cluster_zip           Download the Cluster90 collection
bindingsite               Extract binding site from the collection
box                       Docking box around the site
ideal_sdf                 Download ligand_code as SDF, or use the upload
babel_convert_sdf2pdb     SDF to PDB
babel_convert_pdb2pdbqt   Ligand PDBQT
str_check_add_hydrogens   Receptor PDBQT
autodock_vina_run         Docking
extract_model_pdbqt       Top pose
babel_convert_pdbqt2pdb   Pose to PDB
cat_pdb                   Protein + ligand complex
```

## Inputs / Outputs

- Inputs: `pdb_id` (receptor, no upload) and the ligand by code or SDF.
- Outputs (`results/`): `download.pdb`, `pdb_protein.pdb`, `pdb_cluster.zip`, `bindingsite.pdb`, `box.pdb`, `ideal.sdf`, `ligand.pdb`, `prep_ligand.pdbqt`, `prep_receptor.pdbqt`, `output_vina.pdbqt`, `output_vina.log`, `output_model.pdbqt`, `output_model.pdb`, `output_structure.pdb`.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `pdb_id` | `3HEC` | Receptor PDB code; its Cluster90 homologs define the site |
| `site_ligand` | `STI` | Ligand whose pose in the homologs defines the site; must bind a homolog |
| `ligand_code` | `STI` | Ligand to dock, as PDB code; clear it to use `ligand_sdf` |
| `ligand_sdf` | `examples/sti_ideal.sdf` | 3D SDF used when `ligand_code` is empty |
| `box_offset_a` | `12` | Padding around the site on each side of the box (A) |

## References

- [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina)
- [Open Babel](https://github.com/openbabel/openbabel)
- [biobb_vs](https://github.com/bioexcel/biobb_vs)
- [biobb_chemistry](https://github.com/bioexcel/biobb_chemistry)
- [biobb_structure_utils](https://github.com/bioexcel/biobb_structure_utils)
- [biobb_io](https://github.com/bioexcel/biobb_io)
- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [BioExcel protein-ligand docking tutorial (Cluster90 variant)](https://biobb-wf-virtual-screening.readthedocs.io)
