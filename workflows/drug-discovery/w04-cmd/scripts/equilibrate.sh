#!/bin/bash
# Preproduction (equilibration) chain for one replica: the 10 steps ported
# from create_md_custom.sh's `if [ $preprod -eq 1 ]` block (schedule in
# prepare_replicas.py's PROTOCOL). Operates
# in-place on <dir>, a self-contained replica slot copied forward from
# prepare_replicas' output (workflow.yaml's `equilibrate` map task copies
# the whole slot into its own output first, then calls this): reads
# <dir>/preprod/<step>.in, writes <dir>/preprod/<step>.{out,rst,nc,info}.
#
# The production phase (scripts/production.sh, called by workflow.yaml's
# separate `produce` map task) consumes this stage's preprod/10_nvt.rst.
# Two map tasks instead of one so equilibration and production run as
# independent SLURM jobs -- their own walltime, independently resumable.
#
# Usage: equilibrate.sh <dir>
set -euo pipefail

dir="$1"
preprod="$dir/preprod"
prmtop="$dir/system.prmtop"
inpcrd="$dir/system.inpcrd"
# md_engine from prepare_replicas: pmemd/pmemd.cuda, or the OpenMM runner,
# which takes the same flags and writes the same files.
engine=$(cat "$dir/engine.txt" 2>/dev/null || echo pmemd)
md() { exe=$1; shift; if [ "$engine" = openmm ]; then python "$dir/mdin_openmm.py" "$@"; else "$exe" "$@"; fi; }

# Live digest for the UI while pmemd runs (no-op outside Horus); the EXIT
# trap publishes one last pass, so a failed step's mdout is visible too.
if [ -f "$dir/live_monitor.sh" ]; then
    bash "$dir/live_monitor.sh" "$preprod" "$prmtop" & mon=$!
    trap 'set +e; kill $mon 2>/dev/null; wait $mon 2>/dev/null; bash "$dir/live_monitor.sh" --once "$preprod" "$prmtop"' EXIT
fi

# A step is done when its restart exists and pmemd printed its closing
# TIMINGS section, so re-running in the same directory (Slurm requeue, a retry)
# continues after the last finished step instead of starting over.
done_step() { [ -s "$preprod/$1.rst" ] && grep -q "5.  TIMINGS" "$preprod/$1.out" 2>/dev/null; }

# Step order and engine come from the rendered inputs (prepare_replicas.py's
# PROTOCOL): N_name.in, minimizations on CPU pmemd, MD on pmemd.cuda.
prev="$inpcrd"
for name in $(cd "$preprod" && ls *.in | sed 's/\.in$//' | sort -t_ -k1,1n); do
    if done_step "$name"; then
        echo "skipping $name (already finished)"
    else
        exe=pmemd.cuda
        case "$name" in *_min) exe=pmemd ;; esac
        echo "starting $name"
        md "$exe" -O -i "$preprod/$name.in" -o "$preprod/$name.out" \
            -p "$prmtop" -c "$prev" -r "$preprod/$name.rst" \
            -inf "$preprod/$name.info" -ref "$prev" -x "$preprod/$name.nc"
    fi
    prev="$preprod/$name.rst"
done
