# BioExcel Building Blocks — Workflow Collection

The **BioExcel Building Blocks** (biobb) software library is a collection of Python wrappers on top of popular biomolecular simulation tools. The library offers a layer of interoperability between the wrapped tools, making them compatible and directly interconnectable to build complex biomolecular workflows.

All building blocks share a unique syntax — requiring input files, output files, and input parameters (properties) — irrespective of the program wrapped.

## Workflows

| # | Directory | Workflow |
|---|---|---|
| 01 | [w01-gromacs-md-setup](w01-gromacs-md-setup/) | GROMACS Protein MD Setup |
| 02 | [w02-ligand-parameterization](w02-ligand-parameterization/) | Ligand Parameterization (GAFF / ACPype) |
| 03 | [w03-amber-md-setup](w03-amber-md-setup/) | AMBER Protein MD Setup |
| 04 | [w04-gromacs-protein-ligand-complex-md-setup](w04-gromacs-protein-ligand-complex-md-setup/) | GROMACS Protein-Ligand Complex MD Setup |
| 05 | [w05-mutation-free-energy-calculations](w05-mutation-free-energy-calculations/) | Mutation Free Energy (pmx, non-equilibrium TI) |
| 06 | [w06-protein-ligand-docking-cluster90](w06-protein-ligand-docking-cluster90/) | Protein-Ligand Docking with a Cluster90 Binding Site |
| 07 | [w07-protein-ligand-docking-pdbe-rest-api](w07-protein-ligand-docking-pdbe-rest-api/) | Protein-Ligand Docking with PDBe Binding Sites |
| 08 | [w08-protein-ligand-docking-fpocket](w08-protein-ligand-docking-fpocket/) | Protein-Ligand Docking into an fpocket Cavity |
| 10 | [w10-amber-protein-ligand-complex-md-setup](w10-amber-protein-ligand-complex-md-setup/) | AMBER Protein-Ligand Complex MD Setup |
| 11 | [w11-amber-constant-ph-md-setup](w11-amber-constant-ph-md-setup/) | AMBER Constant-pH MD Setup |
| 12 | [w12-dna-helical-parameters](w12-dna-helical-parameters/) | BioExcel DNA Helical Parameters Analysis |
| 13 | [w13-abc-md-setup](w13-abc-md-setup/) | ABC DNA MD Setup (AMBER) |
| 14 | [w14-protein-conformational-ensembles](w14-protein-conformational-ensembles/) | Protein Conformational Ensembles (FlexDyn) |
| 15 | [w15-protein-conformational-transitions](w15-protein-conformational-transitions/) | Protein Conformational Transitions (GOdMD) |
| 16 | [w16-macromolecular-coarse-grained-flexibility](w16-macromolecular-coarse-grained-flexibility/) | Coarse-Grained Protein Flexibility (FlexServ) |
| 17 | [w17-classical-molecular-interaction-potentials](w17-classical-molecular-interaction-potentials/) | Molecular Interaction Potentials (CMIP) |
| 18 | [w18-molecular-structure-checking](w18-molecular-structure-checking/) | Molecular Structure Checking |
| 19 | [w19-haddock3-protein-protein-docking](w19-haddock3-protein-protein-docking/) | HADDOCK3 Antibody-Antigen Docking |
| 20 | [w20-autoencoders-md-analysis](w20-autoencoders-md-analysis/) | Autoencoder Collective Variables from MD |
| 21 | [w21-protein-membrane-md-analysis](w21-protein-membrane-md-analysis/) | Protein-Membrane MD Analysis |
| 22 | [w22-cavity-guided-virtual-screening](w22-cavity-guided-virtual-screening/) | Cavity-Guided Virtual Screening |
| 23 | [w23-cavity-analysis](w23-cavity-analysis/) | Cavity Analysis across a Conformational Ensemble |

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [Horus Workflow Runtime](https://github.com/orgs/temple-compute/repositories)
- [BioExcel tutorials](https://mmb.irbbarcelona.org/biobb/)
