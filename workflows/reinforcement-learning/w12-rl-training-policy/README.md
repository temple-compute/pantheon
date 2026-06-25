# W-12 · Large-Scale Reinforcement Learning Training + Policy Export

![Status: draft](https://img.shields.io/badge/status-draft-lightgrey)
![Domain: Reinforcement Learning](https://img.shields.io/badge/domain-reinforcement--learning-darkblue)
![GTM: Tier 3](https://img.shields.io/badge/GTM-Tier%203-orange)

## Overview

Trains a reinforcement learning agent at scale using distributed rollout workers (CPU-heavy) feeding a centralized neural network learner (GPU-heavy), evaluates the policy across thousands of environment seeds, and exports the trained policy for deployment (robot controller, simulation agent, logistics optimizer).

This workflow demonstrates Horus's most distinctive multi-resource capability: **simultaneous CPU and GPU allocation with high-bandwidth data flow between them**. RL training requires both to run at the same time — CPU workers generate experience; the GPU learner trains on it in near real-time. A mismatch in capacity between the two directly degrades sample efficiency. Horus's co-scheduling makes optimal allocation possible.

**Target users:** Robotics companies (Isaac Lab, physical robots), game AI teams, logistics/operations research teams, autonomous systems groups.

---

## Compute Pattern

| Stage | Name | Cluster Type | Resources | Est. Walltime |
|-------|------|-------------|-----------|---------------|
| 1+2 | `ROLLOUT_WORKERS` + `POLICY_LEARNER` | CPU cluster + GPU cluster (concurrent) | 256–1024 CPU cores + 8–32×H100 | 6h–7 days |
| 3 | `POLICY_EVALUATION` | CPU cluster | 256–512 cores | 2–6h |
| 4 | `POLICY_EXPORT` | CPU | 4 cores | 15–30 min |

**Note:** Stages 1 and 2 run **concurrently and continuously** — this is not a sequential pipeline. The CPU rollout workers and GPU learner are co-running processes that communicate via a shared replay buffer or experience queue.

---

## Tools & Dependencies

| Tool | Role | Source |
|------|------|--------|
| [RLlib](https://docs.ray.io/en/latest/rllib/index.html) | Distributed RL training (Ray-based) | Apache 2.0 |
| [Sample Factory](https://github.com/alex-petrenko/sample-factory) | High-throughput RL framework | MIT |
| [CleanRL](https://github.com/vwxyzjn/cleanrl) | Single-file RL implementations (reference) | MIT |
| [Isaac Lab](https://isaac-sim.github.io/IsaacLab/) | GPU-accelerated robot simulation (NVIDIA) | BSD — NVIDIA |
| [Brax](https://github.com/google/brax) | JAX-based physics simulation | Apache 2.0 |
| [Gymnasium](https://gymnasium.farama.org/) | Standard RL environment API | MIT |
| [PyTorch](https://pytorch.org/) | Neural network training | BSD |
| [ONNX](https://onnx.ai/) | Policy export format | MIT |
| [TensorRT](https://developer.nvidia.com/tensorrt) | Policy optimization for embedded/edge inference | NVIDIA license |
| [Weights & Biases](https://wandb.ai/) | Training monitoring and experiment tracking | Commercial/free tier |

---

## Input / Output

**Inputs:**
- `env_config.yaml` — environment specification (Gymnasium env ID or custom env config)
- `algorithm_config.yaml` — RL algorithm choice and hyperparameters
- `config.yaml` — workflow parameters (compute budget, early stopping criteria)

**Outputs:**
- `artifacts/policy/` — trained policy weights (PyTorch checkpoint)
- `artifacts/policy.onnx` — ONNX-exported policy for deployment
- `results/training_curves/` — episode return, policy entropy, value loss over training
- `results/evaluation_results.json` — mean/std episode return across evaluation seeds
- `results/policy_video/` — optional: rendered evaluation episodes

---

## Horus Configuration

```
Concurrent resources (stages 1+2):
  CPU rollout workers:    256–1024 CPU cores
                           RAM: 4–8GB per worker
                           Note: co-located with GPU learner for low-latency
                                 experience transfer (ideally same datacenter)

  GPU policy learner:     8–32×H100 or A100
                           Note: runs concurrently with CPU workers, not sequentially

Sequential resources (stage 3): CPU cluster
                                  cores: 256–512

Sequential resources (stage 4): CPU — any, 4 cores
```

**Data flow (continuous during stages 1+2):**
- CPU workers → GPU learner: experience tuples (obs, action, reward, next_obs) via Ray object store, shared memory, or Redis queue
- GPU learner → CPU workers: updated policy weights (periodic broadcast, every N gradient steps)
- Throughput requirement: 100k–10M environment steps/second target; bandwidth-sensitive

**Scheduler notes:**
- This is **not a sequential DAG** for stages 1+2. Horus must support co-scheduling a CPU job and GPU job that run simultaneously and communicate.
- RLlib handles internal communication via Ray. Horus needs to launch the Ray head node + worker nodes across the allocated CPU/GPU resources.
- Stage 3 is a standard batch job array (independent evaluation episodes). Sequential after stages 1+2 complete.

---

## Parameterization

| Parameter | Description | Default |
|-----------|-------------|---------|
| `environment` | Gymnasium env ID or custom env class | — (required) |
| `algorithm` | `ppo`, `sac`, `dreamerv3`, or `impala` | `ppo` |
| `n_rollout_workers` | Number of parallel environment workers | `256` |
| `n_envs_per_worker` | Environments per worker process | `8` |
| `total_timesteps` | Training budget in environment steps | `1e9` |
| `policy_network` | `mlp`, `cnn`, or `transformer` | `mlp` |
| `policy_hidden_dim` | Hidden layer size | `512` |
| `learning_rate` | Policy learning rate | `3e-4` |
| `n_eval_seeds` | Number of seeds for final evaluation | `1000` |
| `export_format` | `onnx`, `torchscript`, or `tflite` | `onnx` |
| `early_stopping_reward` | Stop training if mean reward exceeds threshold | `null` |

---

## Implementation Notes

- For robotics (Isaac Lab, MuJoCo): GPU-accelerated simulation can run thousands of environments on GPU instead of CPU. In this case, the rollout "workers" are GPU environments, not CPU processes. The compute pattern changes significantly — may be single-node multi-GPU rather than CPU+GPU co-scheduling. Consider this a variant of the workflow.
- RLlib is the most general-purpose framework supporting the widest range of algorithms. Sample Factory is faster for specific on-policy algorithms (PPO) on CPU environments.
- The experience buffer is the critical shared resource between stages 1 and 2. For large-scale training, a dedicated Redis or Ray Plasma object store node may be needed.
- DreamerV3 (world model RL) is worth supporting as an algorithm option — it is more sample-efficient than PPO for many tasks and has become popular in 2024–2025.
- Policy export to ONNX is straightforward for MLP/CNN policies. Recurrent policies (LSTM, transformer) require specific ONNX opset version considerations.

---

## Open Questions

- [ ] Does Horus have a concept of co-scheduled jobs that run concurrently and share data, as opposed to sequential DAG stages? This is required for RL.
- [ ] How does Horus handle Ray cluster initialization across a mixed CPU/GPU resource allocation?
- [ ] Should GPU-accelerated simulation environments (Isaac Lab) be treated as a separate workflow variant (W-12b)?
- [ ] What is the recommended approach for streaming training metrics to an external dashboard (W&B, MLflow) from within a Horus-managed job?

---

## References

- [RLlib documentation (Ray)](https://docs.ray.io/en/latest/rllib/index.html)
- [Sample Factory GitHub](https://github.com/alex-petrenko/sample-factory)
- [Isaac Lab (NVIDIA)](https://isaac-sim.github.io/IsaacLab/)
- [Brax GitHub (Google)](https://github.com/google/brax)
- [DreamerV3 paper](https://arxiv.org/abs/2301.04104)
- [SAGA: Workflow-Atomic Scheduling for AI Agent Inference](https://arxiv.org/html/2605.00528v1)
