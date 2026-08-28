#!/bin/bash
# Production chunk loop, ported from the `if [ $prod -eq 1 ]` block of
# MolBioMedUAB/protocols/MD/cMD/create_md_custom.sh. Runs inside the `prod`
# task of each replica's subworkflow (workflow.yaml), after `amber.sh` has
# already been sourced by the caller.
#
# Usage: production.sh <slot_dir> <preequil_dir> <out_dir>
#   slot_dir     the replica's self-contained input slot (has prod/*.in,
#                system.prmtop, steps.txt)
#   preequil_dir the 10_nvt step's output folder (has 10_nvt.rst)
#   out_dir      this task's output folder; chunk N's files land in
#                out_dir/prod_N.{rst,mdout,mdinf,nc}
set -euo pipefail

slot_dir="$1"
preequil_dir="$2"
out_dir="$3"

mkdir -p "$out_dir"
cntmax=$(cat "$slot_dir/steps.txt")
prmtop="$slot_dir/system.prmtop"

cnt=1
while [ "$cnt" -le "$cntmax" ]; do
    istep="prod_${cnt}"

    if [ "$cnt" -eq 1 ]; then
        prev_rst="$preequil_dir/10_nvt.rst"
        input="$slot_dir/prod/prod_1.in"
    else
        pcnt=$((cnt - 1))
        prev_rst="$out_dir/prod_${pcnt}.rst"
        input="$slot_dir/prod/prod.in"
    fi

    pmemd.cuda -O -ref "$prev_rst" -p "$prmtop" -c "$prev_rst" \
        -i "$input" -o "$out_dir/${istep}.mdout" -inf "$out_dir/${istep}.mdinf" \
        -r "$out_dir/${istep}.rst" -x "$out_dir/${istep}.nc"

    echo "Production chunk $cnt of $cntmax done"
    cnt=$((cnt + 1))
done
