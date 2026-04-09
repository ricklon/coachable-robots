# balena channel — Balena cloud managed Pi 5

Wraps the `app` image with a balena supervisor label.
No openssh-server — BalenaOS provides SSH at the host level.
Application stack is identical to chi-edge: same Gradio, same coachable, same LeRobot.

**Tag:** `rianders/lerobot-soarm101:balena`  
**Base:** `rianders/lerobot-soarm101:app`  
**Launched by:** balena cloud (supervisor auto-starts at boot)

## Deploy

```bash
cd channels/balena
balena push <app-name>
```

## SSH access (via BalenaOS host)

```bash
# Default BalenaOS SSH on port 22222:
ssh -p 22222 root@<pi-ip>
# Or via balena CLI:
balena ssh <device-uuid>
```

## Gradio preview

Available at `http://<pi-ip>:7860` when the robot service is running.

## Swap this Pi to chi-edge channel

**IMPORTANT:** balena and chi-edge share the same physical cameras and serial ports.
They must not run simultaneously.

1. Stop the balena service: balena dashboard → device → stop service  
   (or `balena stop <device-uuid> <service>`)
2. Run `Request_LeRobot_SOARM101.ipynb` Steps 4b → 5 to launch CHI@Edge container
3. All hardware is now exclusively available to CHI@Edge

**Do NOT** leave balena services running when launching CHI@Edge — they will hold
`/dev/video0-3` and block camera access in the container.
