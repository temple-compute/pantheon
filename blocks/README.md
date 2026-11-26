# Blocks

Single-task blocks for the Temple Compute OS block library. Each folder holds:

- `workflow.yaml`: one task. Defaults sit on the task's inputs.
- `README.md`: the block page. Its first prose line is the description.
- `block.yaml`: `name`, `tags`, `example_inputs` (input ids whose files ship with the block) and optional `renamed_from` (a list of earlier names, so a rename keeps the line).

BioBB blocks in one folder share one pinned conda environment, so keep their `conda_requirements` identical. The Vina blocks use two: `vina` and `rdkit` need different boost builds.

`tc-os/scripts/seed_pantheon.py --blocks` publishes them. A change to a block publishes its next version; unchanged blocks are skipped.
