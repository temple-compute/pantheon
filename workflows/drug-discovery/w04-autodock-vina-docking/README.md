# W-04 · AutoDock Vina Docking

![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)

## Overview

Given a **receptor** (PDB) and a **ligand library** (SMILES or 3D SDF), this
workflow does the whole molecular-docking pipeline end to end: it prepares every
input into the PDBQT format [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina)
needs, docks each ligand into a defined search box, and returns ranked binding
energy tables (CSV). Vina's empirical scoring is fast enough to screen a library
on CPU, which makes it a natural cheap-first pass before more expensive physics
(FEP) or ML affinity models.

The point on Horus: prep and summary are light CPU steps that run locally; the
docking step is the compute-heavy stage and is the one you route to a bigger box.
Horus provisions the per-stage environments from **conda-forge** (Meeko/OpenBabel
for prep, Vina for docking) and moves the data across the boundary automatically —
swapping where the docking stage runs is a one-line `target:` change.

## Pipeline

```
prep (local, CPU)        receptor.pdb + ligands.smi ──► vina_inputs.tar.gz
   │  OpenBabel → receptor.pdbqt, Meeko → ligands/*.pdbqt, box.json
dock (CPU, Vina)         AutoDock Vina per ligand   ──► docking_out.tar.gz
   │  best poses + REMARK VINA RESULT affinities
summary (local, CPU)     parse affinities           ──► summary.csv + poses.csv
```

## Quick start

```bash
# Install the horus-runtime and plugins (one time)
uv sync
# (or: pip install horus-runtime horus-environments)

# You can install UV with this command if you don't have it yet:
curl -LsSf https://astral.sh/uv/install.sh | sh

# The prep/dock stages build conda envs from conda-forge, so a conda-family
# tool must be on PATH. workflow.yaml defaults to `conda:` — set it to `mamba`
# or `micromamba` in the prep/dock executors if that's what you have.

# Run the workflow
horus run workflow.yaml
```

> Requires a `horus-environments` with conda channel / `conda_requirements`
> support (temple-compute/horus-environments#3). Until that ships in a release,
> install it from that branch.

Outputs land in `results/`: `vina_inputs.tar.gz`, `docking_out.tar.gz`, and the
two energy tables `summary.csv` (ranked best-first) and `poses.csv` (per pose).

## Inputs / Outputs

**Inputs**
- `receptor.pdb` — the target protein. Hydrogens are added automatically at
  pH 7.4; the bundled example is chain A of [1IEP](https://www.rcsb.org/structure/1IEP)
  (Abl kinase).
- `ligands.smi` — one `SMILES [name]` per line (`name` becomes the table id), or
  point `--ligands` at a 3D `.sdf` file instead (auto-detected by extension).

**Outputs**
- `summary.csv` — one row per ligand, ranked best (most negative) first:
  `rank, ligand, best_affinity_kcal_mol, mean_affinity_kcal_mol, num_poses`.
- `poses.csv` — one row per pose: `ligand, pose, affinity_kcal_mol, rmsd_lb, rmsd_ub`.

Lower (more negative) affinity = stronger predicted binding.

## Parameterization

Edit the `prep` task's `args:` in `workflow.yaml`:

- **Docking box** — the key knob. Set `--center X Y Z` and `--size X Y Z` (Å) to
  your pocket (the example uses the 1IEP ATP pocket, `15.190 53.903 16.917`).
  Alternatively pass `--ref-ligand <file>` to center the box on a bound reference
  ligand, or omit `--center` entirely for blind, whole-receptor docking (then use
  a large `--size`).

Edit the `dock` task's `args:` for search effort:

- `--exhaustiveness` (default 16) — higher is more thorough but slower.
- `--n-poses` (default 9) — poses written/scored per ligand.
- `--cpu` (default 0 = autodetect).

## Implementation notes

- **Dependencies come from conda-forge**, not pip: the whole stack (`vina`,
  `openbabel`, `meeko`, `rdkit`, `gemmi`, `numpy`, `scipy`) ships prebuilt there.
  This matters most for `vina` — its PyPI package has no macOS/arm64 wheel and
  builds from source (needs Boost), whereas conda-forge `vina` 1.2.7 provides
  Python bindings for **osx-arm64, osx-64, linux-64 and linux-aarch64**, so the
  docking stage runs anywhere, including Apple Silicon. (This uses the
  `channels` / `conda_requirements` fields added to `horus-environments`'
  `conda_python_environment` executor.)
- **Receptor prep uses OpenBabel** (`obabel -xr -p 7.4`) rather than Meeko's
  `mk_prepare_receptor.py`: it is far more robust across arbitrary/truncated
  crystal structures. Vina's default `vina` scoring function uses atom types, not
  receptor partial charges, so a rigid OpenBabel PDBQT is sufficient.
- **Ligand prep uses Meeko** (`mk_prepare_ligand.py`) for correct small-molecule
  atom typing and torsions; SMILES are first embedded to 3D with RDKit (ETKDG +
  MMFF).
- A ligand that fails to dock is logged and skipped (recorded in the archive's
  `manifest.json`) so one bad structure never sinks the screen.
- Each stage script has a dependency-free `--selftest`
  (`python scripts/<stage>.py --selftest`).

## References

- [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina) ·
  [docs](https://autodock-vina.readthedocs.io) ·
  [1.2.0 paper](https://pubs.acs.org/doi/10.1021/acs.jcim.1c00203)
- [Meeko](https://github.com/forlilab/Meeko) · [OpenBabel](https://openbabel.org)
