#!/bin/bash
# Production chunk loop, ported from the `if [ $prod -eq 1 ]` block of
# MolBioMedUAB/protocols/MD/cMD/create_md_custom.sh. Runs inside one clone of
# workflow.yaml's `produce` map task, after `amber.sh` has already been
# sourced by the caller.
#
# Usage: production.sh <slot_dir> <preequil_dir> <out_dir>
#   slot_dir     the replica's equilibrated slot (prod/prod_N.in,
#                system.prmtop, steps.txt, ...)
#   preequil_dir the 10_nvt step's output folder (has 10_nvt.rst)
#   out_dir      this task's output folder; chunk N's files land in
#                out_dir/prod_N.{rst,mdout,mdinf,nc}
#
# out_dir also gets the small slot files the `analyze` map task needs
# (topology, reference coordinates, scripts, settings, equilibration
# mdouts) so each produced item is self-contained like the slots before it.
set -euo pipefail

slot_dir="$1"
preequil_dir="$2"
out_dir="$3"

mkdir -p "$out_dir/preprod"
cntmax=$(cat "$slot_dir/steps.txt")
prmtop="$slot_dir/system.prmtop"
# md_engine from prepare_replicas: pmemd.cuda, or the OpenMM runner (same flags).
engine=$(cat "$slot_dir/engine.txt" 2>/dev/null || echo pmemd)
md() { exe=$1; shift; if [ "$engine" = openmm ]; then python "$slot_dir/mdin_openmm.py" "$@"; else "$exe" "$@"; fi; }

for f in amber.sh analyze.py system.prmtop system.inpcrd steps.txt \
         solute_residues.txt protocol.json engine.txt; do
    if [ -f "$slot_dir/$f" ]; then cp "$slot_dir/$f" "$out_dir/"; fi
done
cp "$preequil_dir"/*.out "$out_dir/preprod/" 2>/dev/null || true

# Live digest for the UI while pmemd runs (no-op outside Horus); the EXIT
# trap publishes one last pass, so a failed step's mdout is visible too.
if [ -f "$slot_dir/live_monitor.sh" ]; then
    bash "$slot_dir/live_monitor.sh" "$out_dir" "$prmtop" & mon=$!
    trap 'set +e; kill $mon 2>/dev/null; wait $mon 2>/dev/null; bash "$slot_dir/live_monitor.sh" --once "$out_dir" "$prmtop"' EXIT
fi

prev_rst="$preequil_dir/10_nvt.rst"
cnt=1
while [ "$cnt" -le "$cntmax" ]; do
    istep="prod_${cnt}"
    # A finished chunk (restart + pmemd's closing TIMINGS section) is kept, so a
    # re-run in the same directory continues where it stopped.
    if [ -s "$out_dir/${istep}.rst" ] && grep -q "5.  TIMINGS" "$out_dir/${istep}.mdout" 2>/dev/null; then
        echo "Production chunk $cnt of $cntmax already finished"
    else
        md pmemd.cuda -O -ref "$prev_rst" -p "$prmtop" -c "$prev_rst" \
            -i "$slot_dir/prod/${istep}.in" -o "$out_dir/${istep}.mdout" \
            -inf "$out_dir/${istep}.mdinf" -r "$out_dir/${istep}.rst" \
            -x "$out_dir/${istep}.nc"
        echo "Production chunk $cnt of $cntmax done"
    fi
    prev_rst="$out_dir/${istep}.rst"
    cnt=$((cnt + 1))
done
