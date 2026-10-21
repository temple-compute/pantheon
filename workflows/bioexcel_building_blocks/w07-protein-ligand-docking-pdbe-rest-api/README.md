# W-12 · Protein-Ligand Docking with PDBe Binding Sites

Dock a ligand with AutoDock Vina into the binding site PDBe annotates for a chosen ligand.

![Domain: BioExcel Building Blocks](https://img.shields.io/badge/domain-bioexcel-green)

## Overview

Docks one ligand into a receptor with AutoDock Vina (default p38-alpha MAP kinase, PDB 3LFA, dasatinib 1N1). The docking box comes from the PDBe REST API binding-site annotation of `site_ligand`; the top pose is assembled into a protein-ligand complex. The workflow has 13 tasks.

## Pipeline

```
download_pdb              Download pdb_id
extract_protein           Remove ligands, water, ions
get_binding_sites         Query PDBe REST API (residues.json)
select_binding_site       Pick the site of site_ligand (scripts/select_site.py)
generate_cavity_box       Docking box around the site residues
download_ligand_sdf       Download ligand_code as SDF, or use the upload
convert_sdf_to_pdb        SDF to PDB
prepare_ligand_pdbqt      Ligand PDBQT
prepare_receptor_pdbqt    Receptor PDBQT
run_docking               AutoDock Vina
extract_docking_pose      Top pose
convert_pose_to_pdb       Pose to PDB
assemble_complex          Receptor + pose complex
```

## Inputs / Outputs

- Inputs: `pdb_id` (receptor, no upload) and the ligand by code or SDF.
- Outputs (`results/`): `download.pdb`, `pdb_protein.pdb`, `residues.json`, `box.pdb`, `ideal.sdf`, `ligand.pdb`, `prep_ligand.pdbqt`, `prep_receptor.pdbqt`, `output_vina.pdbqt`, `output_vina.log`, `output_model.pdbqt`, `output_model.pdb`, `output_structure.pdb`.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `pdb_id` | `3LFA` | Receptor PDB code; its PDBe binding sites are used |
| `site_ligand` | `1N1` | Ligand whose PDBe site defines the box; the run stops and lists the available sites if there is none |
| `ligand_code` | `1N1` | Ligand to dock, as PDB code; clear it to use `ligand_sdf` |
| `ligand_sdf` | `examples/1n1_ideal.sdf` | 3D SDF used when `ligand_code` is empty |
| `box_offset_a` | `12` | Padding around the site residues on each side of the box (A) |

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina)
- [Open Babel](https://github.com/openbabel/openbabel)
- [biobb_vs](https://github.com/bioexcel/biobb_vs)
- [biobb_chemistry](https://github.com/bioexcel/biobb_chemistry)
- [biobb_structure_utils](https://github.com/bioexcel/biobb_structure_utils)
- [biobb_io](https://github.com/bioexcel/biobb_io)
- [PDBe REST API](https://www.ebi.ac.uk/pdbe/pdbe-rest-api)
- [BioExcel protein-ligand docking tutorial (PDBe REST-API variant)](https://biobb-wf-virtual-screening.readthedocs.io)
