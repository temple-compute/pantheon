# Horus Workflow Repository

A curated library of production-ready workflows for the [horus-runtime](https://github.com/temple-compute/horus-runtime). Each workflow is a multi-stage pipeline designed to run across heterogeneous compute, routing each stage to the right cluster type automatically.

Each workflow directory contains:
- `README.md` — full context: purpose, compute pattern, tools, configuration guide, open implementation questions
- `workflow.yaml` or `run.py` — a plain Horus workflow definition or Python workflow builder
- `scripts/` — small stage scripts and helper code when needed

## Getting Started

```bash
# Clone this repo
git clone https://github.com/temple-compute/pantheon
cd pantheon

# Browse a workflow
cat workflows/drug-discovery/w01-boltz2-virtual-screening/

# Submit a workflow using the horus-runtime
horus run workflow.yaml
```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for how to add new workflows or improve existing ones.
