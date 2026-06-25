# W-10 · Medical Image Segmentation: Training + DICOM Inference Service

![Status: draft](https://img.shields.io/badge/status-draft-lightgrey)
![Domain: Medical Imaging](https://img.shields.io/badge/domain-medical--imaging-red)
![GTM: Tier 2](https://img.shields.io/badge/GTM-Tier%202-blue)

## Overview

Trains a medical image segmentation model on large-scale CT, MRI, or histopathology datasets, then deploys a DICOM-compatible inference service that integrates with clinical or research radiology workflows. Designed for institutions or companies that need a custom model because their imaging protocol, anatomy of interest, or pathology type is not covered by existing pre-trained models.

The Horus value is straightforward: training needs a large GPU cluster for days; inference needs a persistent small-GPU or CPU service. Horus handles the checkpoint promotion and cluster transition automatically, with an optional human-approval gate before deployment.

**Target users:** Hospital radiology AI teams, medical device companies, academic medical centers, clinical research organizations (CROs).

---

## Compute Pattern

| Stage | Name | Cluster Type | Resources | Est. Walltime |
|-------|------|-------------|-----------|---------------|
| 1 | `DATA_PREPROCESSING` | CPU cluster, high-memory | 32–64 cores, 256GB RAM | 2–8h |
| 2 | `DISTRIBUTED_TRAINING` | GPU — high-end multi-node (H100) | 8–32×H100 | 12h–3 days |
| 3 | `VALIDATION` | GPU — mid-tier | 4×A100 | 1–3h |
| 4 | `MODEL_EXPORT` | CPU or mid-tier GPU | 4 cores or 1×GPU | 15–30 min |
| 5 | `INFERENCE_SERVICE` | GPU — small persistent | 2×A10G | persistent |

---

## Tools & Dependencies

| Tool | Role | Source |
|------|------|--------|
| [nnU-Net v2](https://github.com/MIC-DKFZ/nnUNet) | Self-configuring segmentation framework | Apache 2.0 |
| [MONAI](https://monai.io/) | Medical AI training framework | Apache 2.0 |
| [pydicom](https://github.com/pydicom/pydicom) | DICOM file reading/writing | MIT |
| [SimpleITK](https://simpleitk.org/) | Medical image I/O and processing | Apache 2.0 |
| [TotalSegmentator](https://github.com/wasserth/TotalSegmentator) | Pretrained whole-body CT segmentator (fine-tune base) | Apache 2.0 |
| [MedSAM / SAM2](https://github.com/bowang-lab/MedSAM) | Foundation model for medical segmentation | Apache 2.0 |
| [TorchIO](https://torchio.readthedocs.io/) | Medical image augmentation | MIT |
| [ONNX Runtime](https://onnxruntime.ai/) | Optimized inference runtime | MIT |
| [TensorRT](https://developer.nvidia.com/tensorrt) | NVIDIA inference optimization | NVIDIA license |
| [Orthanc](https://www.orthanc-server.com/) | Open-source DICOM server | GPL |

---

## Input / Output

**Inputs:**
- `data/dicom/` — DICOM files organized by study/series, or pre-converted NIfTI files
- `data/labels/` — segmentation masks in NIfTI (.nii.gz) or DICOM SEG format
- `config.yaml` — workflow parameters (anatomy, modality, training config)

**Outputs:**
- `artifacts/model/` — trained model weights (PyTorch checkpoint)
- `artifacts/model.onnx` — ONNX-exported model for inference
- `results/validation_metrics.json` — Dice score, HD95, NSD per class
- `results/validation_examples/` — overlay visualizations of predictions vs. ground truth
- `deployment/endpoint_url.txt` — DICOM-compatible inference service URL

---

## Horus Configuration

```
Cluster A (stages 2,3): GPU cluster — H100 (training) / A100 (validation)
                          training: 8–32×H100
                          validation: 4×A100

Cluster B (stage 5):    GPU — small persistent service
                          gpus: 2×A10G
                          Note: persistent DICOM service; not a batch job

Cluster C (stages 1,4): CPU cluster — high-memory
                          cores: 32–64, RAM: 256GB
                          Note: DICOM preprocessing is memory-intensive for large studies
```

**Data flow:**
- Stage 1 → Stage 2: NIfTI files + nnU-Net preprocessed dataset (~10–100GB)
- Stage 2 → Stage 3: model checkpoint (~100MB–1GB)
- Stage 3 → Stage 4: best checkpoint → ONNX export (~same size)
- Stage 4 → Stage 5: ONNX model file

**Optional gate:** Add a human-approval step between stages 3 and 4 (before deployment) for clinical applications. Horus should support pausing the workflow pending manual sign-off.

---

## Parameterization

| Parameter | Description | Default |
|-----------|-------------|---------|
| `modality` | `CT`, `MRI`, `PET`, or `histology` | — (required) |
| `anatomy` | Target anatomy/pathology to segment | — (required) |
| `n_classes` | Number of segmentation classes | — (required) |
| `framework` | `nnunet` or `monai` | `nnunet` |
| `pretrained_weights` | Starting checkpoint (TotalSegmentator or MedSAM) | `totalsegmentator` |
| `patch_size` | Training patch size (voxels) | auto (nnU-Net) |
| `batch_size` | Per-GPU batch size | auto (nnU-Net) |
| `max_epochs` | Training epochs | `1000` |
| `val_metric` | Metric for best checkpoint selection | `dice` |
| `export_format` | `onnx`, `torchscript`, or `tensorrt` | `onnx` |
| `require_deployment_approval` | Pause before deploy for human sign-off | `true` |

---

## Implementation Notes

- nnU-Net v2 is the safest default: it auto-configures patch size, batch size, and normalization based on the dataset fingerprint. Use MONAI for more custom architectures.
- DICOM preprocessing varies significantly by scanner vendor and protocol. Expect non-trivial data cleaning in stage 1. SimpleITK handles most standard formats; vendor-specific issues require manual intervention.
- TotalSegmentator (Apache 2.0) provides pretrained weights for 104 anatomical structures in CT. Use as a starting point for fine-tuning rather than training from scratch where possible.
- MedSAM/SAM2 is a strong choice for interactive segmentation tasks; for fully automatic batch inference, nnU-Net typically outperforms it.
- For regulatory compliance (FDA 510(k), CE mark): training data curation, model validation, and deployment procedures must meet specific documentation standards. This workflow does not handle regulatory documentation — it provides the technical pipeline only.
- The `require_deployment_approval` gate is important for clinical applications. Horus must support workflow pause states, not just batch completion.

---

## Open Questions

- [ ] How does Horus handle the human-approval gate (stage 3 → 4)? Does it support a `pending_approval` workflow state with a notification mechanism?
- [ ] What DICOM-web profile should the inference service implement: WADO-RS, STOW-RS, QIDO-RS?
- [ ] Should this workflow include data anonymization/de-identification as a pre-processing step before data lands on the HPC cluster?
- [ ] Is there interest in a federated learning variant where training data stays at each hospital site?

---

## References

- [nnU-Net v2 GitHub](https://github.com/MIC-DKFZ/nnUNet)
- [MONAI documentation](https://docs.monai.io/)
- [TotalSegmentator GitHub](https://github.com/wasserth/TotalSegmentator)
- [MedSAM GitHub](https://github.com/bowang-lab/MedSAM)
- [pydicom documentation](https://pydicom.github.io/)
- [SimpleITK documentation](https://simpleitk.org/)
