# CHI@Edge Helpdesk Ticket: Device Profiles Not Advertised

Subject: CHI@Edge soarm101-1 schedules plain container, but all smarter-device profiles are unavailable

Hello,

I am using the CHI@Edge enrolled Raspberry Pi 5 device `soarm101-1` for a SO-ARM101 robot setup. The device itself appears healthy in `chi-edge device show`, and CHI@Edge can schedule a plain container onto the device. However, any container requesting the expected smarter-device-manager profiles fails scheduling because the resources are not advertised or available.

Device:

- CHI@Edge device name: `soarm101-1`
- Machine: `raspberrypi5`
- Blazar device driver: `k8s`
- Lease: `lerobot-soarm101-lease-20260413`
- Lease status: `ACTIVE`
- Lease id: `7b7776bc-8d59-4e68-b002-806803883260`
- Current reservation id used by container request: `d8ad213d-0562-417e-b4dd-126a7ce6eb52`

Device health from `chi-edge device show soarm101-1` reports `STEADY` for:

- `balena`
- `blazar.device`
- `k8s`
- `tunelo`

A no-device-profile debug container schedules successfully:

- Container name: `arm-01-container`
- Container id: `009f2d16-0d98-467b-8621-12b4d16b0c56`
- Image: `rianders/lerobot-soarm101:chi-edge`
- Status: `Running`
- Tailscale hostname: `arm-01-19`

Inside that running debug container:

- SSH works as root.
- Tailscale works.
- `coachable` is installed.
- `lerobot-record` is installed.
- `sshd` and `tailscaled` are running.
- No robot/camera devices are mounted, as expected because the debug container requested no device profiles.
- `balena` is not available inside the container.
- `kubectl` is not available inside the container.
- Kubernetes service-account files are mounted, but `KUBERNETES_SERVICE_HOST` / `KUBERNETES_SERVICE_PORT` are not set.

Relevant debug output:

```bash
root@arm-01-19:~# tailscale ip -4
100.85.54.87

root@arm-01-19:~# which coachable
/usr/local/bin/coachable

root@arm-01-19:~# which lerobot-record
/usr/local/bin/lerobot-record

root@arm-01-19:~# ls /dev/ttyACM* /dev/video* 2>/dev/null || echo "no robot/camera devices mounted"
no robot/camera devices mounted
```

The intended `python-chi` request that fails is:

```python
from chi.container import Container

my_container = Container(
    name="arm-01-container",
    image_ref="rianders/lerobot-soarm101:chi-edge",
    reservation_id="d8ad213d-0562-417e-b4dd-126a7ce6eb52",
    command=["sleep", "infinity"],
    environment={
        "HF_USER": "rianders",
        "LEADER_PORT": "/dev/ttyACM0",
        "FOLLOWER_PORT": "/dev/ttyACM1",
        "CAMERA_INDEX": "0",
    },
    device_profiles=[
        "ttyacm0",
        "ttyacm1",
        "video0",
        "video1",
        "video2",
        "video3",
    ],
)

my_container.submit(wait_for_active=True, wait_timeout=600, show=None, idempotent=True)
```

That container immediately enters `Error` state with this scheduler reason:

```text
0/50 nodes are available: 1 Insufficient smarter-devices/ttyACM0, 1 Insufficient smarter-devices/ttyACM1, 1 Insufficient smarter-devices/video0, 1 Insufficient smarter-devices/video1, 1 Insufficient smarter-devices/video2, 1 Insufficient smarter-devices/video3, 43 node(s) didn't match Pod's node affinity/selector, 6 node(s) had untolerated taint {node.kubernetes.io/unreachable: }. preemption: 0/50 nodes are available: 1 No preemption victims found for incoming pod, 49 Preemption is not helpful for scheduling.
```

As a negative-control test, I also tried the legacy `pi_serial` device profile by launching with:

```bash
EDGE_DEVICE_PROFILES=pi_serial just restart-arm
```

That failed with the same underlying serial resource issue:

```text
Insufficient smarter-devices/ttyACM0
```

Because `pi_serial` maps only to `/dev/ttyACM0`, this suggests the failure is not caused by the custom `ttyacm0` / `ttyacm1` / `video*` profile list. The k3s node is not advertising even the legacy serial profile as allocatable.

So basic CHI@Edge scheduling works on `soarm101-1`, but the smarter-device-manager resources are unavailable:

- `smarter-devices/ttyACM0`
- `smarter-devices/ttyACM1`
- `smarter-devices/video0`
- `smarter-devices/video1`
- `smarter-devices/video2`
- `smarter-devices/video3`

Could you please check:

1. Whether the Pi host currently sees `/dev/ttyACM0`, `/dev/ttyACM1`, and `/dev/video0` through `/dev/video3`.
2. Whether smarter-device-manager is running on the k3s node for `soarm101-1`.
3. Whether the smarter-device-manager configuration includes profiles for `ttyacm0`, `ttyacm1`, `video0`, `video1`, `video2`, and `video3`.
4. Whether the k3s node for this device advertises those resources as allocatable.
5. Whether any stale Balena/k3s/smarter-device-manager state needs to be restarted, resynced, or repaired.
6. Whether the current lease/reservation is correctly bound to the `soarm101-1` k8s node.

This same device previously worked with these profile names. The current evidence suggests the issue is specifically with smarter-device-manager resource advertisement, not the image, lease, auth, Tailscale, or basic CHI@Edge scheduling.

Thank you.

Suggested attachments:

```bash
just edge-status
just edge-device-show
just restart-arm
```

The plain debug container is currently reachable at:

```bash
ssh root@arm-01-19
```
