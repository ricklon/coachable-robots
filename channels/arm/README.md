# chi-edge channel — CHI@Edge / Chameleon managed Pi 5

Wraps the `app` image with `openssh-server` and `entrypoint.sh` so the container
is reachable via SSH at the Chameleon floating IP.

**Tag:** `rianders/lerobot-soarm101:chi-edge` (also `:latest`)  
**Base:** `rianders/lerobot-soarm101:app`  
**Launched by:** `Request_LeRobot_SOARM101.ipynb` (python-chi Container API)

## Device access (CHI@Edge — no --privileged)

```python
device_profiles=["ttyacm0", "ttyacm1", "video0", "video1", "video2", "video3"]
```

## SSH access

The control node's public key (`~/.ssh/id_ed25519.pub`) is injected at launch
via the `SSH_PUBKEY` environment variable. After Step 8 prints the floating IP:

```bash
ssh root@<floating-ip>
```

## Build and push

```bash
make build-chi-edge
make push-chi-edge
```

## Swap this Pi to balena channel

1. Run notebook Cleanup (delete container + release lease)
2. Balena supervisor auto-restarts; or `balena start` from balena dashboard
