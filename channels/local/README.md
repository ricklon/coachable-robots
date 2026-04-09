# local channel — Standalone Docker (no cloud)

Runs the `app` image directly with full device access. Works on Pi 5 or Linux laptop.
No Chameleon account or balena subscription required.

**Image:** `rianders/lerobot-soarm101:app` (pulled directly, no channel wrapper needed)

## Usage

```bash
export HF_TOKEN=hf_xxx
export HF_USER=yourname

# Compose (recommended — handles volumes and port binding)
docker compose -f channels/local/docker-compose.yml up

# Or direct docker run
docker run -it --privileged -v /dev:/dev -p 7860:7860 \
  -v $(pwd)/config/fleet.yaml:/app/config/fleet.yaml \
  -e HF_TOKEN=$HF_TOKEN -e HF_USER=$HF_USER \
  rianders/lerobot-soarm101:app
```

## Gradio preview

`http://localhost:7860` or `http://<pi-ip>:7860`
