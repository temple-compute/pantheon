# OMSF: Open Molecular Software Foundation workflows

Native Horus ports of selected workflows from the [OMSF workflow directory](https://directory.omsf.io/workflows/), covering [Open Force Field](https://openforcefield.org), [Open Free Energy](https://openfree.energy) and [OpenADMET](https://openadmet.org). The notebooks are split into real tasks. Each workflow installs the upstream packages and adds thin glue scripts instead of copying upstream code.

Inputs (molecule and database URLs) and run settings are workflow variables whose defaults match the upstream production setup. Point them at your own molecules or datasets (a `file:///` path works for local files). The heavy steps of w01 and w03 declare a GPU and are a one-field swap away from a Slurm or cloud GPU target; w02 runs on CPU only.

## Workflows

| # | Directory | Workflow | Upstream |
|---|---|---|---|
| 01 | [w01-openfe-rbfe-tyk2](w01-openfe-rbfe-tyk2/) | OpenFE Relative Binding Free Energies (TYK2) | [OpenFreeEnergy/ExampleNotebooks](https://github.com/OpenFreeEnergy/ExampleNotebooks) (MIT) |
| 02 | [w02-openadmet-cyp3a4](w02-openadmet-cyp3a4/) | OpenADMET CYP3A4 Inhibition Models | [OpenADMET/openadmet-demos](https://github.com/OpenADMET/openadmet-demos) (Apache-2.0) |
| 03 | [w03-openff-protein-ligand-md](w03-openff-protein-ligand-md/) | OpenFF Protein-Ligand MD | [openforcefield/openff-toolkit](https://github.com/openforcefield/openff-toolkit) (MIT) |

Port plan, triage of all 16 directory entries, and open gaps: [docs/plans/omsf-workflows.md](../../docs/plans/omsf-workflows.md).
