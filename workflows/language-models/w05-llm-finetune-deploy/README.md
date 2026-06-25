# W-05 · Domain-Specific LLM Fine-Tuning + Inference Deployment

![Status: draft](https://img.shields.io/badge/status-draft-lightgrey)
![Domain: Language Models](https://img.shields.io/badge/domain-language--models-yellow)
![GTM: Tier 1](https://img.shields.io/badge/GTM-Tier%201-green)

## Overview

Fine-tunes an open-weight large language model on proprietary or domain-specific data, evaluates the resulting model, quantizes it for cost-efficient serving, and deploys an OpenAI-compatible inference endpoint on a smaller, cheaper cluster.

This is the canonical multi-cluster Horus workflow. Training requires H100s with NVLink and high-bandwidth interconnect. Inference runs 10–20× cheaper on mid-tier GPUs (A10G, L4, L40S). Without Horus, H100s sit idle during evaluation and quantization — often for hours. With Horus, the expensive cluster is released immediately after training and the artifact is automatically transferred to the inference cluster.

**Target users:** ML engineers, AI product teams, enterprises building internal LLM-powered tools.

---

## Compute Pattern

| Stage | Name | Cluster Type | Resources | Est. Walltime |
|-------|------|-------------|-----------|---------------|
| 1 | `DATA_PREPARATION` | CPU cluster | 32 cores | 30 min–2h |
| 2 | `FINE_TUNING` | GPU — high-end (H100/H200), multi-node | 8–64×H100 | 2h–3 days |
| 3 | `EVALUATION` | GPU — mid-tier (A100/A10G) | 4×A100 | 1–3h |
| 4 | `QUANTIZATION` | GPU — mid-tier | 1–2×A100 | 30 min–2h |
| 5 | `INFERENCE_DEPLOYMENT` | GPU — low-cost (A10G/L4/L40S) | 1–4×A10G | persistent |

**Cost implication:** H100 nodes (stage 2) cost ~$3–5/GPU/hr. A10G nodes (stage 5) cost ~$0.50–0.80/GPU/hr. Proper cluster transition saves 80–90% on post-training compute.

---

## Tools & Dependencies

| Tool | Role | Source |
|------|------|--------|
| [Axolotl](https://github.com/axolotl-ai-cloud/axolotl) | Fine-tuning orchestration framework | Apache 2.0 |
| [DeepSpeed](https://github.com/microsoft/DeepSpeed) | Distributed training (ZeRO-2/3) | Apache 2.0 |
| [FSDP](https://pytorch.org/docs/stable/fsdp.html) | PyTorch native distributed training | BSD |
| [Hugging Face Transformers](https://github.com/huggingface/transformers) | Model loading, Trainer API | Apache 2.0 |
| [PEFT](https://github.com/huggingface/peft) | LoRA / QLoRA adapters | Apache 2.0 |
| [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) | Model evaluation benchmarks | MIT |
| [AutoGPTQ](https://github.com/AutoGPTQ/AutoGPTQ) | GPTQ quantization | MIT |
| [llm-compressor](https://github.com/vllm-project/llm-compressor) | AWQ / SparseGPT quantization | Apache 2.0 |
| [vLLM](https://github.com/vllm-project/vllm) | High-throughput inference server | Apache 2.0 |
| [Text Generation Inference (TGI)](https://github.com/huggingface/text-generation-inference) | Alternative inference server | Apache 2.0 |

**Supported base models** (open-weight, as of 2026): Llama 3.x, Mistral / Mixtral, Qwen 2.5, Gemma 2, DeepSeek-V3.

---

## Input / Output

**Inputs:**
- `data/train.jsonl` — training data in instruction-following or completion format
- `data/eval.jsonl` — held-out evaluation set
- `config.yaml` — workflow parameters (model, technique, training hyperparameters)

**Outputs:**
- `artifacts/model/` — fine-tuned model weights (HuggingFace format)
- `artifacts/model-quantized/` — quantized model for serving
- `results/eval_results.json` — evaluation scores on standard and custom benchmarks
- `deployment/endpoint_url.txt` — URL of the deployed inference endpoint

---

## Horus Configuration

```
Cluster A (stage 2):   GPU cluster — H100 or H200, NVLink preferred
                        min_gpus: 8, max_gpus: 64
                        requires: CUDA >= 12.1, NVLink for ZeRO-3

Cluster B (stages 3,4): GPU cluster — mid-tier (A100 40GB or A10G)
                          gpus: 2–4

Cluster C (stage 5):   GPU cluster — low-cost persistent (A10G, L4, L40S)
                        gpus: 1–4 (depends on model size and throughput target)
                        Note: persistent job; Horus should support long-running
                              services, not just batch jobs

Cluster D (stage 1):   CPU cluster — any
                        cores: 32
```

**Data flow:**
- Stage 1 → Stage 2: tokenized dataset as Arrow or parquet files
- Stage 2 → Stage 3/4: model checkpoint (safetensors, ~7GB for 7B model, up to ~70GB for 70B)
- Stage 4 → Stage 5: quantized model (GPTQ/AWQ, ~4GB for 7B INT4)

**Scheduler notes:**
- Stage 2 is a multi-node distributed training job. Requires all nodes to start simultaneously (gang scheduling). Horus must reserve all N nodes before launching.
- Stage 5 is a persistent service, not a batch job. Horus needs a concept of "persistent deployment" separate from batch job submission.
- Training checkpoints should be saved to shared storage accessible to both training and evaluation clusters.

---

## Parameterization

| Parameter | Description | Default |
|-----------|-------------|---------|
| `base_model` | HuggingFace model ID or local path | `meta-llama/Llama-3.1-8B` |
| `fine_tuning_method` | `lora`, `qlora`, or `full` | `lora` |
| `lora_rank` | LoRA rank (higher = more parameters) | `64` |
| `lora_target_modules` | Which layers to apply LoRA to | `all-linear` |
| `batch_size_per_gpu` | Per-GPU training batch size | `4` |
| `gradient_accumulation_steps` | Steps before optimizer update | `8` |
| `learning_rate` | Peak learning rate | `2e-4` |
| `epochs` | Training epochs | `3` |
| `eval_benchmarks` | Benchmark list for stage 3 | `["mmlu", "hellaswag"]` |
| `quantization_method` | `gptq` or `awq` | `awq` |
| `quantization_bits` | `4` or `8` | `4` |
| `inference_engine` | `vllm` or `tgi` | `vllm` |
| `max_concurrent_requests` | vLLM/TGI concurrency setting | `32` |

---

## Implementation Notes

- For models up to 13B parameters: LoRA on a single 8×H100 node is sufficient. For 70B+ models: use QLoRA with DeepSpeed ZeRO-3 across multiple nodes.
- Axolotl provides the simplest path from a YAML config to a running training job. It handles DeepSpeed, FSDP, LoRA, QLoRA, and chat template formatting.
- vLLM's `--tensor-parallel-size` should match the number of GPUs in the inference cluster. For a 7B INT4 model, a single A10G is usually sufficient.
- If the fine-tuned model is a LoRA adapter (not a merged model), the inference server must load both the base model and the adapter. Merge adapters before serving to reduce latency overhead.
- Evaluation (stage 3) should include at least one domain-specific benchmark, not just standard benchmarks. lm-evaluation-harness supports custom task definitions.

---

## Open Questions

- [ ] How does Horus handle persistent services (stage 5)? Is there a `horus deploy` concept separate from `horus submit`?
- [ ] What shared storage solution is used for large model checkpoints between stage 2 (training cluster) and stages 3/4 (evaluation cluster)?
- [ ] Should the workflow support experiment tracking integration (W&B, MLflow, Comet)?
- [ ] What is the SLA model for inference endpoints — auto-scale, fixed, or manual?

---

## References

- [Axolotl GitHub](https://github.com/axolotl-ai-cloud/axolotl)
- [vLLM GitHub](https://github.com/vllm-project/vllm)
- [DeepSpeed documentation](https://www.deepspeed.ai/)
- [LLM Fine-Tuning Guide (Heavybit, 2025)](https://www.heavybit.com/library/article/llm-fine-tuning)
- [Fine-tune & Deploy Open-Source LLMs (decodingai.com)](https://www.decodingai.com/p/playbook-to-fine-tune-and-deploy)
