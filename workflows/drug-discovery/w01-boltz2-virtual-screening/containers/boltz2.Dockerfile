# Boltz-2 GPU image for the W-01 predict stage.
#
# Build on the GPU host (the workflow does not build it for you):
#   docker build -t boltz2:latest -f containers/boltz2.Dockerfile .
#
# Singularity/Apptainer (set engine: singularity, image: ./boltz2.sif):
#   apptainer build boltz2.sif docker-daemon://boltz2:latest
#
# Requires NVIDIA Container Toolkit on the host (`docker run --gpus all`).
# Boltz-2 needs >=40GB VRAM for typical protein-ligand complexes.

FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

# Boltz pulls structure/affinity model weights on first run; keep them in a
# stable cache so repeated containers reuse them.
ENV BOLTZ_CACHE=/opt/boltz-cache
RUN mkdir -p "$BOLTZ_CACHE"

RUN pip install --no-cache-dir boltz

WORKDIR /work

# Smoke check: the CLI resolves. Real runs are driven by run.py:
#   boltz predict inputs --out_dir out --use_msa_server
ENTRYPOINT ["boltz"]
CMD ["--help"]
