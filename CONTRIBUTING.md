# Contributing to the Horus Workflow Repository

## Adding a New Workflow

### 1. Pick a name and ID

Workflows are named `wXX-short-description` where `XX` is the next available two-digit number. Check existing directories for the current highest ID.

### 2. Create the directory

```bash
mkdir -p workflows/{domain}/wXX-your-workflow-name
```

Domains: `drug-discovery`, `genomics`, `language-models`, `scientific-computing`, `medical-imaging`, `reinforcement-learning`. Add a new domain directory if yours doesn't fit.

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

Add your workflow to the structure table and, if appropriate, the GTM priority matrix.

### 5. Open a PR

Branch naming: `workflow/wXX-short-description`. PRs require at least one review from a Temple Compute engineer before merge.

---

## Workflow Maturity Levels

| Level | Meaning | Requirements |
|-------|---------|--------------|
| `draft` | Concept documented, not yet implementable | README complete |
| `spec` | Fully specified, ready for implementation | README + config.example.yaml |
| `alpha` | workflow.yaml exists, tested internally | All files present, tested on one cluster config |
| `stable` | Tested on multiple cluster types, documented edge cases | Full test coverage, public |

All workflows in this repo start at `draft`. Add a badge to your README header:

```markdown
![Status: draft](https://img.shields.io/badge/status-draft-lightgrey)
```

---

## Style Guidelines

- Stage names in `README.md` should be uppercase and match the names used in `workflow.yaml` when it exists.
- Estimated resources should be conservative (p50, not p10).
- All tool/model references should link to the canonical source (paper, GitHub, or HuggingFace).
- Do not include proprietary data paths or API keys anywhere in the repo.
