# W-07 · Multimodal Vision-Language Model Training + Serving

![Status: draft](https://img.shields.io/badge/status-draft-lightgrey)
![Domain: Language Models](https://img.shields.io/badge/domain-language--models-yellow)
![GTM: Tier 3](https://img.shields.io/badge/GTM-Tier%203-orange)

## Overview

Fine-tunes a vision-language model (VLM) on domain-specific image-text pairs and deploys an inference API. Targeted at domains where off-the-shelf VLMs underperform: medical imaging, satellite imagery, scientific figures, industrial inspection, microscopy.

This workflow is a natural extension of W-05 (LLM fine-tuning) to the multimodal case, with an additional heavy CPU data pipeline stage for image preprocessing. The compute pattern is identical — expensive H100 cluster for training, cheap GPU for inference — but the data pipeline requirements are heavier.

**Target users:** Computer vision + NLP teams, medical AI companies, geospatial AI teams.

---

## Compute Pattern

| Stage | Name | Cluster Type | Resources | Est. Walltime |
|-------|------|-------------|-----------|---------------|
| 1 | `DATA_PIPELINE` | CPU cluster (high I/O) | 32–64 cores, fast local NVMe | 2–8h |
| 2 | `VLM_TRAINING` | GPU — high-end multi-node (H100 NVLink) | 8–64×H100 | 6h–3 days |
| 3 | `EVALUATION` | GPU — mid-tier | 4×A100 | 1–3h |
| 4 | `INFERENCE_DEPLOYMENT` | GPU — mid-tier persistent | 2–4×A10G | persistent |

---

## Tools & Dependencies

| Tool | Role | Source |
|------|------|--------|
| [LLaVA-Next / LLaVA-1.6](https://github.com/LLaVA-VL/LLaVA-NeXT) | Base VLM architecture | Apache 2.0 |
| [InternVL2](https://github.com/OpenGVLab/InternVL) | Alternative high-performance VLM | MIT |
| [Idefics3 / SmolVLM](https://huggingface.co/HuggingFaceM4/Idefics3-8B-Llama3) | Lightweight VLM option | Apache 2.0 |
| [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory) | Unified fine-tuning framework (supports VLMs) | Apache 2.0 |
| [DeepSpeed](https://github.com/microsoft/DeepSpeed) | Distributed training | Apache 2.0 |
| [CLIP score](https://github.com/jmhessel/clipscore) | Image-text alignment filtering | MIT |
| [img2dataset](https://github.com/rom1504/img2dataset) | Large-scale image downloading + processing | MIT |
| [torchvision](https://github.com/pytorch/vision) | Image transforms and augmentations | BSD |
| [vLLM](https://github.com/vllm-project/vllm) | Multimodal inference server (VLM support in v0.5+) | Apache 2.0 |

---

## Input / Output

**Inputs:**
- `data/images/` — image files (JPG, PNG, TIFF) or a WebDataset tar archive
- `data/annotations.jsonl` — image-text pairs in LLaVA conversation format
- `config.yaml` — workflow parameters

**Outputs:**
- `artifacts/model/` — fine-tuned VLM weights
- `results/eval_results.json` — VQA accuracy, captioning BLEU/CIDEr scores
- `deployment/endpoint_url.txt` — multimodal inference API endpoint

---

## Horus Configuration

```
Cluster A (stage 2):   GPU cluster — H100, NVLink, NVMe storage for image data
                        min_gpus: 8, max_gpus: 64
                        Note: image data should be co-located with GPU nodes to avoid
                              I/O bottlenecks during training

Cluster B (stages 3,4): GPU cluster — mid-tier (A100 / A10G)
                          gpus: 2–4

Cluster C (stage 1):   CPU cluster — high I/O
                        cores: 32–64
                        requires: fast local NVMe or high-bandwidth shared storage
```

**Data flow:**
- Stage 1 → Stage 2: preprocessed images as WebDataset tarballs + annotation JSONL
- Stage 2 → Stage 3: model checkpoint
- Stage 3 → Stage 4: model weights (merged, ready for vLLM)

---

## Parameterization

| Parameter | Description | Default |
|-----------|-------------|---------|
| `base_model` | Base VLM model ID | `llava-hf/llava-v1.6-mistral-7b-hf` |
| `image_resolution` | Training image resolution (pixels) | `336` |
| `fine_tuning_method` | `lora` or `full` | `lora` |
| `clip_score_threshold` | Minimum CLIP score for data filtering | `0.25` |
| `epochs` | Training epochs | `2` |
| `learning_rate` | Peak learning rate | `1e-4` |
| `eval_task` | VQA evaluation task | `vqav2` |

---

## Implementation Notes

- Image I/O is often the training bottleneck, not GPU compute. Use WebDataset format (sharded tarballs) to maximize throughput. Pre-process images to training resolution in stage 1.
- CLIP score filtering in stage 1 removes low-quality image-text pairs before training. Set threshold based on domain (lower for synthetic data, higher for web-scraped data).
- vLLM supports multimodal inputs (images + text) as of v0.5+. Confirm version compatibility before deploying.
- For medical imaging: DICOM files must be converted to PNG/JPG in stage 1. TIFF support in training frameworks varies; PNG is safest.

---

## Open Questions

- [ ] Should this workflow merge with W-10 (medical imaging segmentation) for a unified medical vision workflow, or stay separate?
- [ ] What evaluation benchmarks are appropriate for domain-specific VLMs? Standard VQAv2 may not reflect real task performance.
- [ ] Is there demand for video-language models? Would require a significantly different data pipeline.

---

## References

- [LLaVA-NeXT GitHub](https://github.com/LLaVA-VL/LLaVA-NeXT)
- [InternVL2 GitHub](https://github.com/OpenGVLab/InternVL)
- [LLaMA-Factory GitHub](https://github.com/hiyouga/LLaMA-Factory)
- [img2dataset GitHub](https://github.com/rom1504/img2dataset)
- [vLLM multimodal support](https://docs.vllm.ai/en/latest/models/vlm.html)
