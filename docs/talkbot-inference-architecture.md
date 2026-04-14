# Talkbot Inference Architecture

## The Problem: On-Device Latency

The Pi CM4 (arm-01, CHI@Edge) is insufficient for natural conversation latency
with any useful language model:

| Model | Quantization | Latency | Usable? |
|-------|-------------|---------|---------|
| Qwen3-0.6B | Q8_0 | ~600ms/token, 10-20s/reply | No — too slow |
| Qwen3.5-0.8B | Q8_0 | ~1400ms/token | No |
| Qwen3.5-0.5B | Q8_0 | ~1400ms/token | No |

CPU pegs at 200%+ during generation. The Pi is appropriate for robot control,
camera capture, and data collection — not inference.

## The Solution: Off-Device Inference

The `arm-talk` container is designed to point at any OpenAI-compatible inference
server via a single env var:

```bash
TALKBOT_LOCAL_SERVER_URL=http://<inference-host>:8000/v1
```

The Pi makes API calls; inference runs elsewhere on the tailnet (or cloud).

## Inference Options

| Option | Expected Latency | Notes |
|--------|-----------------|-------|
| **OpenRouter** (cloud) | ~100-500ms total | Fastest path, per-token cost, no privacy |
| **Jetson Orin** (local GPU) | ~50-200ms/token | `arm-talk-jetson` image, build on device |
| **Chameleon MI100** (when active) | ~50-100ms/token | Reuse training node for inference |
| **Dedicated inference node** | depends on hardware | Any tailnet host running llama-server |
| **Pi CM4 on-device** | ~600ms+/token | Only viable for demos/testing |

## Recommended Setup

For interactive coaching sessions (natural conversation):

```bash
# Option A — OpenRouter (immediate, no hardware needed)
TALKBOT_LLM_BACKEND=openrouter
OPENROUTER_API_KEY=sk-or-...
# No TALKBOT_LOCAL_SERVER_URL needed

# Option B — Jetson Orin on tailnet
TALKBOT_LOCAL_SERVER_URL=http://talkbot-orin:8000/v1
# Run arm-talk-jetson image on the Jetson; see channels/arm-talk-jetson/

# Option C — MI100 training node (when leased)
TALKBOT_LOCAL_SERVER_URL=http://train-mi100:8000/v1
# Start llama-server on MI100: ssh cc@train-mi100 'llama-server --model ...'
```

All options use the same `talkbot serve` command on the Pi — only the env var changes.

## Qwen3 Thinking Mode — Required Fix

Qwen3 models enable thinking mode by default. In thinking mode, the model puts
all output in `reasoning_content` and returns an empty `content` field — Gradio
shows nothing.

**Fix:** append `/no_think` to the system prompt:

```bash
TALKBOT_AGENT_PROMPT="You are a coaching assistant for a robot arm. \
Help the student record quality demonstration episodes. /no_think"
```

This disables the reasoning chain and produces direct responses. Without it,
the UI appears to complete but shows no reply.

Affects: all Qwen3 family models (Qwen3-0.6B, Qwen3-1.7B, Qwen3-4B, etc.)
Does not affect: Qwen2.5 / Qwen3.5 series (no built-in thinking mode)

## CHI@Edge Operational Notes

- **Zun ignores Dockerfile CMD** — startup scripts must be launched manually
  or via the ENTRYPOINT (not CMD). The arm-talk entrypoint handles this.
- **Image cache** — CHI@Edge k8s nodes cache images by tag. A new push to the
  same tag is NOT pulled. Must use a new dated tag to force a fresh pull.
- **Model download** — run `curl` with `nohup` inside the container to survive
  SSH disconnection. Direct `ssh ... && curl ...` truncates on timeout.
- **Static llama.cpp build** — Debian Bookworm (GLIBC 2.36) requires
  `-DBUILD_SHARED_LIBS=OFF`; pre-built binaries and shared-lib builds both
  fail with missing `.so` errors.
