# Contributing to the Horus Workflow Repository

## Adding a New Workflow

### 1. Pick a name and ID

Workflow directories are named `wXX-short-description` where `XX` is the next available two-digit number *within the domain*. Check existing directories in the domain for the current highest ID.

Each workflow also has a global **W-number** (`W-01` through `W-43` so far, unique across the whole repo) assigned in the root `README.md` workflow table. Keep the two schemes straight: the directory is `workflows/bioexcel_building_blocks/w10-amber-protein-ligand-complex-md-setup/`, but its README header and root-table entry are `W-15`. When you add a workflow, reserve the next free W-number (largest existing `W-NN` + 1) and put it in both the new README header and the root table.

### 2. Create the directory

```bash
mkdir -p workflows/{domain}/wXX-your-workflow-name
```

Domains: `ai`, `bioexcel_building_blocks`, `bioinformatics`, `chemistry`, `clinical-trials`, `drug-discovery`, `engine-showcases`, `omics`, `omsf`. Add a new domain directory if yours doesn't fit, and list it in the root `README.md`.

### 3. Write the README.md

Use the template below. Keep it short (about 30–60 lines): no install or run instructions, no resource or runtime specifications, no implementation notes, no open questions.

```markdown
# W-NN · [Short Title]

One-line tagline.

![Domain: Name](https://img.shields.io/badge/domain-name-blue)

## Overview
2–4 sentences: what it does and with which tools. "The workflow has N tasks."

## Pipeline
One line per task.

## Inputs / Outputs
What the user provides; what they get back.

## Parameters
Table of the parameters a user can set (id, default, meaning).

## References
Links to papers, repos, and documentation.
```

### 4. Update the root README.md

Add your workflow to the structure table under its domain, using the next free global W-number. If you add a BioExcel workflow, also add a row to `workflows/bioexcel_building_blocks/README.md`.

### 5. Add the cover

Add `assets/cover.png` (4:1, 1600x400, tc-os palette: charcoal `#0f1419`, navy `#1a2332`, amber `#d4a574`, cream `#faf9f6`) and the square `assets/logo.png` (512x512, uploaded as the icon). Neither is embedded in the README. Cover text is the W-number badge, title and tool names only. The app crops covers to 4:1.

### 6. Open a PR

Branch naming: `workflow/wXX-short-description`. PRs require at least one review from a Temple Compute engineer before merge.

