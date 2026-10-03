#!/bin/bash
# Preproduction (equilibration) chain for one replica: the 10 steps ported
# from create_md_custom.sh's `if [ $preprod -eq 1 ]` block. Operates
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

run_step() {
    local exe="$1" name="$2" c_src="$3" ref_src="$4"
    echo "starting $name"
    "$exe" -O -i "$preprod/$name.in" -o "$preprod/$name.out" \
        -p "$prmtop" -c "$c_src" -r "$preprod/$name.rst" \
        -inf "$preprod/$name.info" -ref "$ref_src" -x "$preprod/$name.nc"
}

run_step pmemd      1_min  "$inpcrd"            "$inpcrd"
run_step pmemd.cuda 2_heat "$preprod/1_min.rst"  "$preprod/1_min.rst"
run_step pmemd.cuda 3_npt  "$preprod/2_heat.rst" "$preprod/2_heat.rst"
run_step pmemd.cuda 4_npt  "$preprod/3_npt.rst"  "$preprod/3_npt.rst"
run_step pmemd      5_min  "$preprod/4_npt.rst"  "$preprod/4_npt.rst"
run_step pmemd.cuda 6_npt  "$preprod/5_min.rst"  "$preprod/5_min.rst"
run_step pmemd.cuda 7_npt  "$preprod/6_npt.rst"  "$preprod/6_npt.rst"
run_step pmemd.cuda 8_npt  "$preprod/7_npt.rst"  "$preprod/7_npt.rst"
run_step pmemd.cuda 9_npt  "$preprod/8_npt.rst"  "$preprod/8_npt.rst"
run_step pmemd.cuda 10_nvt "$preprod/9_npt.rst"  "$preprod/9_npt.rst"
