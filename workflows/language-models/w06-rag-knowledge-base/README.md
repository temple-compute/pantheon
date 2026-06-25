# W-06 · RAG Knowledge Base Construction + Retrieval Endpoint

![Status: draft](https://img.shields.io/badge/status-draft-lightgrey)
![Domain: Language Models](https://img.shields.io/badge/domain-language--models-yellow)
![GTM: Tier 2](https://img.shields.io/badge/GTM-Tier%202-blue)

## Overview

Embeds a large document corpus at scale, builds a vector search index, and deploys a production retrieval-augmented generation (RAG) service. Designed for corpora too large to embed on a single machine — millions to hundreds of millions of document chunks — where GPU parallelization across a cluster reduces embedding time from days to hours.

The Horus value here is cost: stage 2 (batch embedding) is embarrassingly parallel and GPU-intensive, but only needed once (or on a schedule for incremental updates). Horus provisions a large GPU fleet for the duration of embedding, tears it down when done, and routes the index-build and serving stages to appropriately sized CPU/memory nodes.

**Target users:** Enterprises building internal knowledge bases, scientific publishers, legal/compliance teams, biotech companies with large document archives.

---

## Compute Pattern

| Stage | Name | Cluster Type | Resources | Est. Walltime |
|-------|------|-------------|-----------|---------------|
| 1 | `INGESTION_AND_CHUNKING` | CPU cluster | 32–64 cores | 1–4h |
| 2 | `BATCH_EMBEDDING` | GPU cluster (auto-scale) | 8–32×A100 | 2–8h |
| 3 | `INDEX_BUILD` | CPU, high-memory | 16 cores, 256–512GB RAM | 1–3h |
| 4 | `RAG_SERVICE` | CPU or light GPU | 1–2×A10G or 16 CPU cores | persistent |

---

## Tools & Dependencies

| Tool | Role | Source |
|------|------|--------|
| [Unstructured](https://github.com/Unstructured-IO/unstructured) | Document parsing (PDF, HTML, DOCX, etc.) | Apache 2.0 |
| [LangChain / LlamaIndex](https://github.com/langchain-ai/langchain) | Chunking strategies and pipeline orchestration | MIT |
| [sentence-transformers](https://github.com/UKPLab/sentence-transformers) | Embedding model inference | Apache 2.0 |
| [text-embeddings-inference (TEI)](https://github.com/huggingface/text-embeddings-inference) | High-throughput GPU embedding server | Apache 2.0 |
| [E5-large-v2 / BGE-M3 / Nomic Embed](https://huggingface.co/intfloat/e5-large-v2) | Embedding models | MIT/Apache |
| [FAISS](https://github.com/facebookresearch/faiss) | Vector index (flat, IVF, HNSW) | MIT |
| [Weaviate](https://github.com/weaviate/weaviate) | Alternative: managed vector database | BSD |
| [Qdrant](https://github.com/qdrant/qdrant) | Alternative: vector database with filtering | Apache 2.0 |
| [vLLM](https://github.com/vllm-project/vllm) | LLM generation for RAG responses | Apache 2.0 |

---

## Input / Output

**Inputs:**
- `corpus/` — document files (PDF, HTML, DOCX, TXT, markdown, code) or pre-chunked JSONL
- `config.yaml` — embedding model, chunking strategy, index type, serving config

**Outputs:**
- `artifacts/index/` — FAISS index file + metadata store (or Weaviate/Qdrant data directory)
- `artifacts/chunk_store/` — chunk text + source metadata (for display in RAG responses)
- `deployment/endpoint_url.txt` — RAG API endpoint URL

---

## Horus Configuration

```
Cluster A (stage 2):   GPU cluster — auto-scale based on corpus size
                        gpus: 8–32×A100 or A10G
                        Note: TEI server runs one instance per GPU;
                              Horus launches N instances and load-balances embedding jobs

Cluster B (stage 3):   CPU, high-memory
                        cores: 16, RAM: 256–512GB
                        Note: FAISS index build for 100M vectors requires ~200GB RAM

Cluster C (stage 4):   CPU or light GPU — persistent
                        For CPU-only serving: 16 cores, 64GB RAM
                        For GPU-accelerated generation: 1–2×A10G

Cluster D (stage 1):   CPU cluster — any
                        cores: 32–64
```

**Data flow:**
- Stage 1 → Stage 2: chunked text as JSONL (~GB range depending on corpus)
- Stage 2 → Stage 3: embedding vectors as numpy arrays or binary float32 files (~1.5GB per 1M chunks at 1024-dim)
- Stage 3 → Stage 4: FAISS index + metadata (~same size as embeddings)

**Scheduler notes:**
- Stage 2 scales linearly with corpus size. Horus should auto-calculate the number of GPU instances needed based on `corpus_size / chunks_per_gpu_per_hour`.
- Stage 2 is embarrassingly parallel; no inter-GPU communication required.
- Stage 4 is a persistent service. See W-05 notes on Horus service vs. batch job concept.

---

## Parameterization

| Parameter | Description | Default |
|-----------|-------------|---------|
| `embedding_model` | HuggingFace model ID | `intfloat/e5-large-v2` |
| `embedding_dim` | Embedding dimension | `1024` |
| `chunk_size_tokens` | Chunk size in tokens | `512` |
| `chunk_overlap_tokens` | Overlap between adjacent chunks | `64` |
| `index_type` | `flat`, `ivf`, or `hnsw` | `hnsw` |
| `index_nlist` | IVF: number of Voronoi cells | `1024` |
| `vector_db` | `faiss`, `weaviate`, or `qdrant` | `faiss` |
| `generation_model` | LLM for RAG generation | `meta-llama/Llama-3.1-8B-Instruct` |
| `top_k_retrieval` | Number of chunks to retrieve per query | `5` |
| `batch_size_embedding` | Chunks per embedding batch | `512` |

---

## Implementation Notes

- TEI (text-embeddings-inference) is significantly faster than sentence-transformers for batch embedding on GPU — prefer it for stage 2.
- For corpora >10M chunks, use FAISS IVF or HNSW indexes, not flat. Flat search at 100M vectors is too slow for interactive RAG.
- Weaviate and Qdrant offer filtering by metadata at query time (useful for multi-tenant RAG or date-filtered retrieval). FAISS does not.
- Embedding models are not interchangeable after index build. If the embedding model changes, the entire corpus must be re-embedded and re-indexed.
- For incremental updates (new documents added regularly), stage 2 should support delta embedding — only embed new/modified chunks and merge into the existing index.
- Consider a two-stage retrieval architecture: coarse FAISS retrieval (top-50) followed by a re-ranker (Cohere Rerank, BGE-Reranker) before passing to the LLM.

---

## Open Questions

- [ ] Does Horus support scheduled re-runs of stages 1–3 for incremental index updates (e.g., weekly)?
- [ ] What is the recommended solution for cross-cluster artifact transfer when stage 2 runs on a GPU cluster and stage 3 runs on a high-memory CPU cluster in a different datacenter?
- [ ] Should the RAG endpoint include a re-ranker stage? This adds latency but significantly improves precision.
- [ ] Is there a multi-tenant use case where multiple teams share one index but have access-controlled subsets?

---

## References

- [text-embeddings-inference (TEI)](https://github.com/huggingface/text-embeddings-inference)
- [FAISS documentation](https://faiss.ai/)
- [BGE-M3 embedding model](https://huggingface.co/BAAI/bge-m3)
- [Unstructured documentation](https://docs.unstructured.io/)
- [vLLM documentation](https://docs.vllm.ai/)
