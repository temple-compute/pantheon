# Contributing to the Horus Workflow Repository

## Adding a New Workflow

### 1. Pick a name and ID

Workflow directories are named `wXX-short-description` where `XX` is the next available two-digit number *within the domain*. Check existing directories in the domain for the current highest ID.

Each workflow also has a global **W-number** (`W-01` through `W-31`, unique across the whole repo) assigned in the root `README.md` workflow table. Keep the two schemes straight: the directory is `workflows/bioexcel_building_blocks/w09-amber-protein-md-setup/`, but its README header and root-table entry are `W-14`. When you add a workflow, reserve the next free W-number (largest existing `W-NN` + 1) and put it in both the new README header and the root table.

### 2. Create the directory

```bash
mkdir -p workflows/{domain}/wXX-your-workflow-name
```

Domains: `ai`, `bioexcel_building_blocks`, `drug-discovery`, `engine-showcases`. Add a new domain directory if yours doesn't fit, and list it in the root `README.md`.

### 3. Write the README.md

Use the template below. All sections are required before a workflow is considered ready for Tier 1 status.

```markdown
# WXX · [Short Title]

## Overview
One paragraph: what problem this solves, who runs it, and why it needs HPC.

## Compute Pattern
Table of stages with cluster type, GPU/CPU requirements, and estimated walltime.

## Tools & Dependencies
List every model, library, and container image required.

## Horus Configuration
Describe the cluster types needed, data flows between stages, and any special scheduler requirements (MPI, NVLink, InfiniBand).

## Input / Output
What the user provides; what they get back.

## Parameterization
Key variables a user will need to set (dataset path, library size, model choice, etc.).

## Implementation Notes
Known gotchas, performance tips, container caveats.

## Open Questions
What needs to be resolved before this workflow can be implemented.

## References
Links to papers, repos, and documentation.
```

### 4. Update the root README.md

Add your workflow to the structure table under its domain, using the next free global W-number. If you add a BioExcel workflow, also add a row to `workflows/bioexcel_building_blocks/README.md` and check the macOS ARM64 executor table there for any affected packages.

### 5. Document run instructions

Add a `## Quick start` section to your workflow README following the standard block (install uv, `uv sync`, `uv run horus run workflow.yaml`) and note which executors the workflow uses (conda, Docker, or both), since that determines the prerequisites.

### 6. Open a PR

Branch naming: `workflow/wXX-short-description`. PRs require at least one review from a Temple Compute engineer before merge.

