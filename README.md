# Horus Workflow Repository

**Temple Compute** · [horus.templecompute.com](https://horus.templecompute.com)

A curated library of production-ready AI workflows for the [Horus](https://horus.templecompute.com) HPC/cloud orchestration platform. Each workflow is a multi-stage pipeline designed to run across heterogeneous compute — routing each stage to the right cluster type automatically.

---

## Why This Repository Exists

Modern AI workloads don't fit on a single cluster. A drug discovery pipeline might need:
- H100s for structure prediction
- InfiniBand-connected CPU nodes for molecular dynamics
- A cheap GPU for inference serving

Doing this manually means logging into multiple systems, watching jobs finish, and manually transferring artifacts. Horus automates the handoffs. This repository provides ready-to-run workflow definitions you can clone, configure with your data, and submit to Horus with a single command.

---

## Repository Structure

```
workflows/
├── drug-discovery/
│   ├── w01-boltz2-virtual-screening/       # Structure prediction + docking
│   ├── w02-de-novo-protein-design/         # RFdiffusion → ProteinMPNN → AF2
│   └── w03-abfe-pipeline/                  # AI pose prediction + free energy
├── genomics/
│   └── w04-scrna-seq-gpu/                  # Single-cell RNA-seq GPU pipeline
├── language-models/
│   ├── w05-llm-finetune-deploy/            # Fine-tune LLM → inference endpoint
│   ├── w06-rag-knowledge-base/             # Batch embed corpus → RAG service
│   └── w07-vlm-training-serving/          # Vision-language model train + serve
├── scientific-computing/
│   ├── w08-climate-emulator/               # Physics sim → ML surrogate → inference
│   └── w09-materials-discovery/           # DFT → MLIP training → screening
├── medical-imaging/
│   ├── w10-medical-segmentation/          # Train segmentation model + DICOM API
│   └── w11-satellite-imagery/             # Geospatial foundation model + tile inference
└── reinforcement-learning/
    └── w12-rl-training-policy/            # Multi-node RL + policy export
```

Each workflow directory contains:
- `README.md` — full context: purpose, compute pattern, tools, configuration guide, open implementation questions
- `workflow.yaml` *(coming soon)* — Horus workflow definition
- `config.example.yaml` *(coming soon)* — parameterization template
- `scripts/` *(coming soon)* — stage scripts and container references

---

## GTM Priority Tiers

| Tier | Workflows | Rationale |
|------|-----------|-----------|
| **1 — Build first** | W-01, W-02, W-05, W-04 | Highest demand, open-source tooling, clear multi-cluster story |
| **2 — Next wave** | W-06, W-08, W-09, W-10 | Strong HPC story, growing communities |
| **3 — Expansion** | W-03, W-07, W-11, W-12 | Niche but high-value; require domain partnerships |

---

## Getting Started

```bash
# Clone this repo
git clone https://github.com/templecompute/horus-workflows
cd horus-workflows

# Browse a workflow
cat workflows/drug-discovery/w01-boltz2-virtual-screening/README.md

# Submit a workflow to Horus (once workflow.yaml exists)
horus submit workflows/drug-discovery/w01-boltz2-virtual-screening/workflow.yaml \
  --config my-config.yaml
```

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for how to add new workflows or improve existing ones.

---

## License

Apache 2.0 — see [LICENSE](./LICENSE).
