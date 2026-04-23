# chi-edge channel — CHI@Edge / Chameleon managed Pi 5

Wraps the `app` image with `openssh-server`, Tailscale, and `entrypoint.sh` so
the container is reachable over the tailnet.

**Tag:** `rianders/lerobot-soarm101:chi-edge` (also `:latest`)  
**Base:** `rianders/lerobot-soarm101:app`  
**Launched by:** `just reserve-edge` / `just restart-arm`

## Device access (CHI@Edge — no --privileged)

```python
device_profiles=["ttyacm0", "ttyacm1", "video0", "video1", "video2", "video3"]
```

## SSH access

The container enrolls in Tailscale at startup using `TS_AUTHKEY`.

```bash
ssh root@arm-01
```

## Build and push

```bash
just build-arm
just push-arm
```

## Swap this Pi to balena channel

1. Release or stop the CHI@Edge container.
2. Balena supervisor auto-restarts; or `balena start` from balena dashboard
