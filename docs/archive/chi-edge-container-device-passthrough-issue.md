# CHI@Edge SO-ARM Container Device Passthrough Findings

## Current status: 2026-04-22

We split the original "device passthrough" problem into separate lease, video,
serial, and container lifecycle issues.

### Resolved: CHI@Edge lease creation

`python-chi` lease creation works when the CHI@Edge application credential is
created as **unrestricted**.

The previous application credential had only `member,reader` roles and was not
unrestricted. It could authenticate, list leases, list containers, and show
device health, but `Lease.submit()` failed with:

```text
error: internal server error
ERROR: Blazar lease creation failed: Unable to make lease
```

The CHI@Edge application credential creation page explains the missing piece:
restricted application credentials cannot create Keystone trusts. Blazar lease
creation appears to need trust creation. Creating a new unrestricted credential
fixed lease creation.

Working lease:

```text
name: arm-01-lease-20260422-025339
id: 2f887873-0cbe-4713-81b3-cbee28fccc77
status: ACTIVE
ends: 2026-04-29 02:53:00
```

### Resolved: video device profiles

Video-only CHI@Edge containers now schedule successfully with:

```text
EDGE_DEVICE_PROFILES=["video0", "video1", "video2", "video3"]
```

Inside the fresh video-only container, the expected nodes are present:

```text
/dev/video0
/dev/video1
/dev/video2
/dev/video3
```

V4L2 identifies the cameras:

```text
/dev/video0: HD USB Camera: HD USB Camera
/dev/video2: HD Pro Webcam C920
```

The real capture nodes are:

```text
/dev/video0
/dev/video2
```

The metadata nodes are:

```text
/dev/video1
/dev/video3
```

After stopping the Balena/Gradio camera workload, rebooting the Balena host,
and deploying a fresh CHI@Edge video-only container, OpenCV frame reads
succeeded:

```text
/dev/video0 opencv opened=True read=True shape=[480, 640, 3]
/dev/video2 opencv opened=True read=True shape=[480, 640, 3]
```

### Resolved: serial device profiles

Serial-profile containers originally failed during Kubernetes scheduling:

```text
EDGE_DEVICE_PROFILES=["ttyacm0"]
EDGE_DEVICE_PROFILES=pi_serial
EDGE_DEVICE_PROFILES=["ttyacm0", "ttyacm1", "video0", "video1", "video2", "video3"]
```

All of those failed with:

```text
Insufficient smarter-devices/ttyACM0
```

After powering the board, rebooting the Balena host, stopping competing Balena
camera workloads, and recreating fresh CHI@Edge containers, serial profiles
started scheduling successfully.

Individual serial tests passed:

```text
ttyacm0 -> /dev/ttyACM0 open=True
ttyacm1 -> /dev/ttyACM1 open=True
```

### Resolved: full robot device profile container

After removing all extra test containers and creating one canonical full-profile
container, all expected devices are present and usable:

```text
container: arm-01-container
id: 75f12366-fe03-4404-9ce4-3dd80dace33c
tailnet host: arm-01-31
tailnet ip: 100.121.166.111
```

Mounted device nodes:

```text
/dev/ttyACM0
/dev/ttyACM1
/dev/video0
/dev/video1
/dev/video2
/dev/video3
```

Container diagnostic result:

```text
/dev/ttyACM0 open=True
/dev/ttyACM1 open=True
/dev/video0 opencv opened=True read=True shape=[480, 640, 3]
/dev/video2 opencv opened=True read=True shape=[480, 640, 3]
```

`/dev/video1` and `/dev/video3` remain metadata nodes and do not open for image
capture.

### Operational lessons

- Run only one Pi-owning workload at a time. The Pi devices are exclusive; do
  not run Balena preview, video-only CHI@Edge containers, serial-only CHI@Edge
  containers, and full robot CHI@Edge containers at the same time.
- Do not run Balena camera preview and CHI@Edge camera containers at the same
  time. They share the same physical cameras, and camera capture reports
  `Device or resource busy`.
- After rebooting the Balena host, recreate the CHI@Edge container. CHI@Edge may
  still report the old container as `Running`, but Tailscale and device mounts
  can be stale.
- Tailscale hostnames may be suffixed, for example `arm-01-27`, because old
  names remain in the tailnet.
- Use `hints={"platform_version": "2"}` when creating CHI@Edge containers on
  open-enrollment devices.
- Papermill `-p device_profiles '[...]'` passes a string, so notebooks must
  normalize that parameter into a Python list before passing it to Zun.

### Diagnostic artifacts

Diagnostic notebook:

```text
notebooks/99_chi_edge_lease_container_diag.ipynb
```

Papermill outputs:

```text
bench/results/99_chi_edge_lease_container_diag_20260422_135703.ipynb
bench/results/99_chi_edge_video_only_diag_20260422_152154.ipynb
bench/results/99_chi_edge_video_diag_ssh_20260422_170642.ipynb
```

Container-side diagnostic script:

```text
scripts/chi_edge_device_diag.py
```

## Summary

The SO-ARM101 Pi host `soarm101-1` has working camera and serial devices under BalenaOS. CHI@Edge full-profile passthrough has now been confirmed working when a single canonical container owns the Pi devices.

The desired full robot container still needs access to:

```text
/dev/video0
/dev/video1
/dev/video2
/dev/video3
/dev/ttyACM0
/dev/ttyACM1
```

As of the current test, the full CHI@Edge profile works when one canonical
container owns the Pi devices.

## Evidence from BalenaOS host

SSH to the BalenaOS host works:

```text
ssh -p 22222 root@192.168.4.191
hostname: soarm101-1
arch: aarch64
```

The host exposes all expected device nodes:

```text
/dev/video0
/dev/video1
/dev/video2
/dev/video3
/dev/ttyACM0
/dev/ttyACM1
```

The running Balena preview container also sees the same devices.

Camera preview is reachable at:

```text
http://192.168.4.191:7860/
```

## Serial functional check

Both serial ports open from inside the Balena container:

```text
/dev/ttyACM0 OPEN_OK
/dev/ttyACM1 OPEN_OK
```

The Feetech bus responds on `/dev/ttyACM1` and reads all six STS3215 motors:

```text
/dev/ttyACM1 {'1': 1883, '2': 1716, '3': 2953, '4': 2214, '5': 1984, '6': 1082}
```

`/dev/ttyACM0` opens but currently sees no motors:

```text
Missing motor IDs: 1, 2, 3, 4, 5, 6
Full found motor list: {}
```

This confirms the serial device node is present and usable. The lack of motor responses on `/dev/ttyACM0` appears to be a separate arm/controller bus, cable, power, or role/configuration issue, not a CHI@Edge passthrough issue.

## CHI@Edge container issue

The CHI@Edge arm container is expected to run with device profiles:

```text
EDGE_DEVICE_PROFILES=ttyacm0,ttyacm1,video0,video1,video2,video3
```

The expected behavior is that the Zun container scheduled on `soarm101-1` receives these device nodes from the host:

```text
/dev/video0
/dev/video1
/dev/video2
/dev/video3
/dev/ttyACM0
/dev/ttyACM1
```

Currently, CHI@Edge can provide a usable full robot runtime when the Pi is not
also serving Balena/Gradio or other CHI@Edge test containers.

## Tailscale note

Tailscale is not believed to be the root cause of the device issue. It is only the intended access path for SSH into the running CHI@Edge container.

Old symptom from the control machine:

```text
ssh root@arm-01
# ssh: Could not resolve hostname arm-01: Name or service not known
```

`tailscale status --json` shows no online peer whose hostname starts with `arm-`.

In later tests, Tailscale worked once a fresh container was created. Containers
often enroll under suffixed names such as `arm-01-27`.

## Requested checks

Could you please check on the CHI@Edge side:

1. Whether the `soarm101-1` k3s node sees the host devices:

```text
/dev/video0
/dev/video1
/dev/video2
/dev/video3
/dev/ttyACM0
/dev/ttyACM1
```

2. Whether smarter-device-manager is advertising allocatable serial resources for:

```text
smarter-devices/ttyACM0
smarter-devices/ttyACM1
```

3. Why video resources initially scheduled successfully while serial resources
   did not until the host/device state was reset:

```text
video0,video1,video2,video3     # schedules successfully
ttyacm0,ttyacm1,pi_serial       # now schedules after reboot/power/reset
```

4. Whether smarter-device-manager or the k3s node needs a restart/resync after
   powering or reconnecting `/dev/ttyACM0`.

## Expected behavior

A CHI@Edge Zun container scheduled on `soarm101-1` with:

```text
EDGE_DEVICE_PROFILES=ttyacm0,ttyacm1,video0,video1,video2,video3
```

should start successfully and should contain:

```text
/dev/video0
/dev/video1
/dev/video2
/dev/video3
/dev/ttyACM0
/dev/ttyACM1
```

This now works in the canonical single-container configuration.

## Notes

Balena and CHI@Edge should not run the robot workload at the same time because they share the same cameras and serial devices.

For this diagnosis, BalenaOS is only being used to confirm that the physical Pi host, cameras, serial adapters, and at least one Feetech motor bus are functional.
