# BioExcel Building Blocks — Workflow Collection

The **BioExcel Building Blocks** (biobb) software library is a collection of Python wrappers on top of popular biomolecular simulation tools. The library offers a layer of interoperability between the wrapped tools, making them compatible and directly interconnectable to build complex biomolecular workflows.

All building blocks share a unique syntax — requiring input files, output files, and input parameters (properties) — irrespective of the program wrapped.

## Workflows

| # | Directory | Workflow |
|---|---|---|
| 01 | [w01-gromacs-md-setup](w01-gromacs-md-setup/) | BioExcel MD Setup — Lysozyme 1AKI (GROMACS) |
| 02 | [w02-ligand-parameterization](w02-ligand-parameterization/) | BioExcel Ligand Parameterization |
| 03 | [w03-amber-md-setup](w03-amber-md-setup/) | BioExcel AMBER MD Setup — Lysozyme 1AKI |
| 04 | [w04-gromacs-protein-ligand-complex-md-setup](w04-gromacs-protein-ligand-complex-md-setup/) | BioExcel MD Setup — Protein-Ligand Complex (3HTB + JZ4) |
| 05 | [w05-mutation-free-energy-calculations](w05-mutation-free-energy-calculations/) | PMX Mutation Free Energy Calculations |
| 06 | [w06-protein-ligand-docking-cluster90](w06-protein-ligand-docking-cluster90/) | Virtual Screening — Protein-Ligand Docking (Cluster90 Binding Site) |
| 07 | [w07-protein-ligand-docking-pdbe-rest-api](w07-protein-ligand-docking-pdbe-rest-api/) | Virtual Screening — Protein-Ligand Docking via EBI PDBe API |
| 08 | [w08-protein-ligand-docking-fpocket](w08-protein-ligand-docking-fpocket/) | Virtual Screening — Protein-Ligand Docking with fpocket |
| 09 | [w09-amber-protein-md-setup](w09-amber-protein-md-setup/) | BioExcel AMBER MD Setup — Lysozyme 1AKI |
| 10 | [w10-amber-protein-ligand-complex-md-setup](w10-amber-protein-ligand-complex-md-setup/) | BioExcel AMBER MD Setup — Protein-Ligand Complex (3HTB + JZ4) |
| 11 | [w11-amber-constant-ph-md-setup](w11-amber-constant-ph-md-setup/) | BioExcel AMBER Constant pH MD Setup — BPTI 6PTI |
| 12 | [w12-dna-helical-parameters](w12-dna-helical-parameters/) | BioExcel DNA Helical Parameters Analysis |
| 13 | [w13-abc-md-setup](w13-abc-md-setup/) | BioExcel AMBER ABC Setup — Drew-Dickerson Dodecamer DNA |
| 14 | [w14-protein-conformational-ensembles](w14-protein-conformational-ensembles/) | BioExcel FlexDyn — Protein Flexibility and Dynamics Analysis |
| 15 | [w15-protein-conformational-transitions](w15-protein-conformational-transitions/) | BioExcel GoDMD — Adenylate Kinase Conformational Transition |
| 16 | [w16-macromolecular-coarse-grained-flexibility](w16-macromolecular-coarse-grained-flexibility/) | BioExcel FlexServ — Protein Conformational Dynamics |
| 17 | [w17-classical-molecular-interaction-potentials](w17-classical-molecular-interaction-potentials/) | BioExcel CMIP — Classical Molecular Interaction Potentials |
| 18 | [w18-molecular-structure-checking](w18-molecular-structure-checking/) | BioExcel Structure Checking |
| 19 | [w19-haddock3-protein-protein-docking](w19-haddock3-protein-protein-docking/) | BioExcel HADDOCK — Antibody-Antigen Protein-Protein Docking |
| 20 | [w20-autoencoders-md-analysis](w20-autoencoders-md-analysis/) | BioExcel Autoencoder — MD Trajectory Analysis with Machine Learning |
| 21 | [w21-protein-membrane-md-analysis](w21-protein-membrane-md-analysis/) | BioExcel Membrane MD Analysis — GABA-gated Chloride Channel |

## macOS ARM64 (Apple Silicon) — Executor Strategy

Several biobb packages have **no osx-arm64 conda package** and cannot be installed via conda on Apple Silicon:

| Package | Workflows affected |
|---|---|
| `biobb_amber` | w03, w09, w10, w11, w13, w17, w18 |
| `biobb_vs` | w06, w07, w08 |
| `biobb_pmx` | w05 |
| `biobb_dna` | w12 |
| `biobb_flexdyn` | w14 |
| `biobb_flexserv` | w14, w16 |
| `biobb_cmip` | w17 |
| `biobb_mem` | w21 |

Packages that **do** have arm64 conda builds and run natively: `biobb_io`, `biobb_analysis`, `biobb_structure_utils`, `biobb_chemistry`, `biobb_gromacs`, `biobb_model`, `biobb_godmd`, `biobb_haddock`, `biobb_pdb_tools`, `biobb_pytorch`.

### How it works

Horus supports **multiple executors within the same workflow**. Each task declares which executor to use via a single `executor:` field — the `runtime.command` string is **never modified**. This means the same workflow definition runs identically on any platform; only the executor changes.

Affected workflows use a mixed strategy:

- **Docker executor** — tasks that call ARM64-incompatible tools run inside a `quay.io/biocontainers/biobb_<pkg>` Linux/amd64 image, transparently emulated via Rosetta 2 / QEMU on Apple Silicon. Docker pulls the image automatically on first run.
- **Conda executor** — tasks that call ARM64-compatible tools (biobb_io, biobb_analysis, etc.) run in the native conda environment, built from each workflow's `conda_env.yaml`.

```yaml
# Two executor definitions at the top of workflow.yaml
_executor: &executor
  kind: conda_python_environment
  environment_file: conda_env.yaml

_docker_executor: &docker_executor
  kind: docker
  image: quay.io/biocontainers/biobb_amber:5.2.1--py312hc5e4ab4_0

# Each task picks one — the command never changes
- id: sander_mdrun
  executor: *docker_executor      # ← ARM64-incompatible: runs in Docker
  runtime:
    command: sander_mdrun --config ...

- id: cpptraj_rms
  executor: *executor             # ← ARM64-compatible: runs in conda
  runtime:
    command: cpptraj_rms --config ...
```

This is a key design benefit of Horus: **workflow portability without touching command definitions**. Swapping a task between conda, Docker, and a remote HPC cluster is a one-field change.

### Prerequisites for ARM64-affected workflows

- **micromamba**, **mamba**, or **conda** — for the conda executor tasks
- **Docker** — for the Docker executor tasks; images are pulled automatically on first run

## References

- [BioExcel Building Blocks (biobb)](https://github.com/bioexcel/biobb)
- [Horus Workflow Runtime](https://github.com/orgs/temple-compute/repositories)
- [BioExcel tutorials](https://mmb.irbbarcelona.org/biobb/)
