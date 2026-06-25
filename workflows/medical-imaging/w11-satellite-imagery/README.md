# W-11 · Satellite/Aerial Imagery Foundation Model Fine-Tuning + Tile Inference

![Status: draft](https://img.shields.io/badge/status-draft-lightgrey)
![Domain: Geospatial](https://img.shields.io/badge/domain-geospatial-red)
![GTM: Tier 3](https://img.shields.io/badge/GTM-Tier%203-orange)

## Overview

Fine-tunes a geospatial foundation model on a downstream remote sensing task (land cover classification, damage assessment, crop type mapping, deforestation detection), then runs inference over a large tile archive covering potentially millions of km². The output is a geospatial raster or vector dataset with per-pixel or per-object predictions.

The scale of the inference stage is the defining challenge: a single Sentinel-2 tile is 110×110 km; global coverage at 10m resolution produces millions of tiles. This makes inference embarrassingly parallel at massive scale — a natural auto-scaling workload for Horus.

**Target users:** Geospatial AI companies, government mapping agencies, agricultural analytics firms, insurance risk teams, environmental monitoring organizations.

---

## Compute Pattern

| Stage | Name | Cluster Type | Resources | Est. Walltime |
|-------|------|-------------|-----------|---------------|
| 1 | `TILE_PREPROCESSING` | CPU cluster | 32–64 cores | 2–8h |
| 2 | `FINE_TUNING` | GPU — high-end (H100/A100) | 8–16×H100 | 4–12h |
| 3 | `BATCH_INFERENCE` | GPU — auto-scale (any tier) | 4–128×A10G | 1–24h (area-dependent) |
| 4 | `MOSAICKING_AND_EXPORT` | CPU cluster | 32 cores | 1–3h |

---

## Tools & Dependencies

| Tool | Role | Source |
|------|------|--------|
| [Prithvi (NASA/IBM)](https://huggingface.co/ibm-nasa-geospatial/Prithvi-100M) | Geospatial foundation model | Apache 2.0 |
| [SatMAE](https://github.com/sustainlab-group/SatMAE) | Satellite imagery foundation model | MIT |
| [torchgeo](https://github.com/microsoft/torchgeo) | Geospatial datasets and transforms for PyTorch | MIT — Microsoft |
| [rasterio](https://rasterio.readthedocs.io/) | Raster data I/O and processing | BSD |
| [GDAL](https://gdal.org/) | Geospatial data abstraction library | MIT/X |
| [pyproj](https://pyproj4.github.io/pyproj/) | Cartographic projections and coordinate transforms | MIT |
| [geopandas](https://geopandas.org/) | Vector geospatial data manipulation | BSD |
| [rio-cogeo](https://github.com/cogeotiff/rio-cogeo) | Cloud-Optimized GeoTIFF creation | BSD |
| [Dask](https://dask.org/) | Parallel array processing for large rasters | BSD |
| [STAC](https://stacspec.org/) | Spatiotemporal Asset Catalog — data discovery | Apache 2.0 |

---

## Input / Output

**Inputs:**
- `tiles/` — satellite imagery tiles (GeoTIFF, COG, or STAC catalog reference)
- `labels/` — training labels as GeoTIFF masks or shapefiles
- `aoi.geojson` — area of interest for inference
- `config.yaml` — workflow parameters

**Outputs:**
- `results/predictions/` — per-tile prediction GeoTIFFs
- `results/mosaic.tif` — mosaicked Cloud-Optimized GeoTIFF for the full AOI
- `results/vectors.gpkg` — optional vectorized output (GeoPackage)
- `results/report.html` — coverage map, class distribution, sample predictions

---

## Horus Configuration

```
Cluster A (stage 2):    GPU cluster — H100 or A100
                         gpus: 8–16×H100

Cluster B (stage 3):    GPU cluster — auto-scale
                         gpus: 4–128×A10G or any available GPU
                         Note: stage 3 is embarrassingly parallel; Horus should
                               auto-scale based on tile count and deadline parameter

Cluster C (stages 1,4): CPU cluster — any
                          cores: 32–64
```

**Data flow:**
- Stage 1 → Stage 2: preprocessed tile tensors as numpy archives or PyTorch dataset (~GB–TB)
- Stage 2 → Stage 3: fine-tuned model weights (~GB)
- Stage 3 → Stage 4: per-tile prediction GeoTIFFs (~MB per tile; GB–TB total)
- Stage 4 → user: mosaicked COG + vectors

**Auto-scaling note:** Stage 3 is the showcase for Horus auto-scaling. The user specifies `target_completion_hours` and Horus determines how many GPU instances to allocate based on tile count and per-tile inference time. More tiles = more GPUs, up to `max_gpus`.

---

## Parameterization

| Parameter | Description | Default |
|-----------|-------------|---------|
| `foundation_model` | `prithvi`, `satmae`, or HuggingFace model ID | `prithvi` |
| `task` | `segmentation`, `classification`, or `change_detection` | `segmentation` |
| `sensor` | `sentinel2`, `landsat8`, `naip`, or `custom` | `sentinel2` |
| `bands` | Spectral bands to use | `[B2, B3, B4, B8, B11, B12]` |
| `resolution_m` | Output resolution in meters | `10` |
| `tile_size_px` | Inference tile size in pixels | `512` |
| `tile_overlap_px` | Overlap between adjacent tiles (for boundary artifacts) | `64` |
| `target_completion_hours` | Target time for inference stage | `4` |
| `max_gpus` | Maximum GPUs for auto-scaling | `64` |
| `output_format` | `geotiff`, `cog`, or `both` | `cog` |

---

## Implementation Notes

- Always use Cloud-Optimized GeoTIFF (COG) for outputs. Standard GeoTIFFs at large scale are unusable with GIS tools.
- Tile overlap (parameter `tile_overlap_px`) is essential to avoid boundary artifacts in segmentation. Merge overlapping predictions using max confidence or averaging.
- Prithvi (NASA/IBM, Apache 2.0) is the most accessible geospatial foundation model with documented fine-tuning examples. SatMAE is a strong alternative.
- Large AOIs (continental or global scale) generate terabytes of output. Budget for output storage in addition to compute.
- Stage 4 mosaicking with GDAL `gdal_merge` or `rio-cogeo` is CPU-bound but can be slow for very large outputs. Parallelize across geographic tiles if needed.
- For time-series analysis (change detection, crop phenology), multiple acquisition dates must be stacked in stage 1 — this significantly increases data volume.

---

## Open Questions

- [ ] Should the workflow support STAC catalog as input (query tiles by AOI + date range) rather than requiring pre-downloaded imagery?
- [ ] What is Horus's model for deadline-based auto-scaling — is it a first-class feature or does the user always specify GPU count manually?
- [ ] Should vectorization (raster → polygon) be an optional stage 5, or always included?
- [ ] Is there a standard Horus pattern for very large output data management (TB-scale GeoTIFF mosaics)?

---

## References

- [Prithvi on HuggingFace (NASA/IBM)](https://huggingface.co/ibm-nasa-geospatial/Prithvi-100M)
- [SatMAE GitHub](https://github.com/sustainlab-group/SatMAE)
- [torchgeo GitHub (Microsoft)](https://github.com/microsoft/torchgeo)
- [rasterio documentation](https://rasterio.readthedocs.io/)
- [STAC specification](https://stacspec.org/)
