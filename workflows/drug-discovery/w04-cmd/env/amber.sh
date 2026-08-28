# Site AMBER environment.
#
# Sourced (". ${amber_env}") by every MD step before calling pmemd/pmemd.cuda,
# so pmemd/pmemd.cuda are on PATH. This is the one file that captures a site's
# "machine" choice from the original create_md_custom.sh -m flag (csuc, local,
# picard, slurm...) -- swap the module line below for the target cluster and
# nothing else in the workflow changes. Save this file as a tc-os library item
# per site/cluster and point the `amber_env` artifact at whichever one applies.
#
# Examples seen in the source protocol (MolBioMedUAB/protocols):
#   csuc:   module load amber/24
#   local:  module load Amber
#   picard: ml Amber/24-foss-2023a-AmberTools-24-CUDA-11.8.0

module load amber/24
