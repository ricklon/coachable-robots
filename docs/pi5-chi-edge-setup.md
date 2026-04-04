# Raspberry Pi 5 CHI@Edge Setup Guide

Enroll a Raspberry Pi 5 as a user-owned device on Chameleon Cloud's CHI@Edge
infrastructure for SO-ARM101 data collection with LeRobot.

## Prerequisites

| Item | Details |
|------|---------|
| Chameleon account | Active allocation on project `CHI-261589` |
| Pi 5 | 8 GB RAM, microSD card (16 GB+) |
| NVME drive | Optional — for dataset storage inside containers |
| SO-ARM101 | Follower arm + leader arm, Feetech STS3215 servos |
| USB cameras | 2x, for top and side views |
| Workstation | Linux/macOS with Python 3.10+ for the CHI@Edge SDK |

## Step 1: Create an Application Credential

1. Log in to **https://chi.edge.chameleoncloud.org**
2. Navigate to **Identity > Application Credentials**
   (direct: `https://chi.edge.chameleoncloud.org/identity/application_credentials/`)
3. Click **Create Application Credential**
   - Name: `edge-pi5` (or any descriptive name)
   - Leave roles and expiration as defaults
4. **Save the secret immediately** — you only see it once. If lost, delete and
   recreate the credential.
5. Download the RC file (e.g., `app-cred-edge-openrc.sh`)

## Step 2: Install the CHI@Edge SDK

On your workstation (not the Pi):

```bash
python3 -m venv chi-edge-env
source chi-edge-env/bin/activate
pip install python-chi-edge
```

Source the RC file to load your credentials into the environment:

```bash
source app-cred-edge-openrc.sh
```

Verify the credentials are loaded:

```bash
env | grep OS_APPLICATION_CREDENTIAL
```

## Step 3: Register the Device

```bash
chi-edge device register \
  --contact-email YOUR_EMAIL@example.edu \
  --application-credential-id "$OS_APPLICATION_CREDENTIAL_ID" \
  --application-credential-secret "$OS_APPLICATION_CREDENTIAL_SECRET" \
  --machine-name raspberrypi5 \
  soarm101-1
```

Notes:
- `--machine-name raspberrypi5` is the device type for Pi 5
  (Pi 4 uses `raspberrypi4-64`, Pi 3 uses `raspberrypi3-64`)
- `soarm101-1` is the device name — this must match `DEVICE_NAME` in
  `Request_LeRobot_SOARM101.ipynb`
- Save the returned **device UUID** for the bake step

## Step 4: Download the BalenaOS Image

Download the BalenaOS image for `raspberrypi5`:
- Version: **6.10.24+rev3** (current as of April 2026)
- Must be the 64-bit variant

Unzip after downloading:

```bash
unzip balena-raspberrypi5-6.10.24+rev3.img.zip
```

## Step 5: Bake the Image

Baking injects your device-specific credentials and CHI@Edge registration
into the image:

```bash
chi-edge device bake \
  --image balena-raspberrypi5-6.10.24+rev3.img \
  DEVICE_UUID
```

Replace `DEVICE_UUID` with the UUID returned in Step 3.

This modifies the image in place — the output is the same file, now
personalized for your device.

## Step 6: Flash to MicroSD

Use [Balena Etcher](https://etcher.balena.io/) or `dd`:

```bash
# Find your SD card device (BE CAREFUL — wrong device = data loss)
lsblk

# Flash (replace /dev/sdX with your SD card)
sudo dd if=balena-raspberrypi5-6.10.24+rev3.img of=/dev/sdX bs=4M status=progress
sync
```

## Step 7: Boot and Verify

1. Insert the microSD card into the Pi 5
2. Connect Ethernet (required for initial enrollment — Wi-Fi is not
   supported by BalenaOS on CHI@Edge)
3. Connect the SO-ARM101 (USB serial) and cameras (USB) if available
4. Power on

The Pi will automatically:
- Boot BalenaOS from the microSD
- Download CHI@Edge services
- Connect via WireGuard to the control plane
- Self-register as a reservable device

Monitor enrollment from your workstation:

```bash
chi-edge device list
chi-edge device show soarm101-1
```

When health status shows **3/3** and all checks read **STEADY**, the device
is enrolled and available for reservation.

## Step 8: Verify in the CHI@Edge Portal

1. Go to **https://chi.edge.chameleoncloud.org**
2. Navigate to **Hardware > Devices**
3. Confirm `soarm101-1` appears with status **enrolled**

## NVME Drive

BalenaOS boots from microSD only. The NVME drive is not used for the OS
but can be mounted inside containers for dataset storage:

```python
# In Request_LeRobot_SOARM101.ipynb, add a volume mount if needed:
my_container = Container(
    ...
    mounts=["/mnt/nvme:/data"],  # mount NVME inside container
)
```

The NVME partition may need to be formatted on first use. You can do this
via SSH or by running a setup command in the container.

## Peripheral Access

The SO-ARM101 servos and cameras are exposed to containers via device
profiles specified at container creation time:

| Profile | Exposes |
|---------|---------|
| `pi_serial` | `/dev/ttyACM*`, `/dev/ttyUSB*` — servo controllers |
| `pi_gpio` | GPIO pins (if needed for additional hardware) |
| `pi_camera` | Camera devices (`/dev/video*`) |

These are already configured in `Request_LeRobot_SOARM101.ipynb`:

```python
my_container = Container(
    ...
    device_profiles=["pi_serial", "pi_gpio"],
)
```

You may need to add `pi_camera` if cameras are not accessible through
`pi_serial` alone.

## Optional: Restrict Device Access

Limit which projects can lease your device:

```bash
chi-edge device set --authorized-projects CHI-261589 soarm101-1
```

## Troubleshooting

### Device not showing as enrolled

- Ensure Ethernet is connected — BalenaOS requires wired networking
- Wait 5-10 minutes after first boot for services to download
- Check `chi-edge device show soarm101-1` for partial health checks

### Health checks stuck at 1/3 or 2/3

- The device may still be downloading container images
- Reboot the Pi and wait another 5 minutes
- Check that outbound internet access is available (no firewall blocking
  WireGuard or Docker Hub)

### Wrong BalenaOS version

- Confirm the image is for `raspberrypi5` (not `raspberrypi4-64`)
- Confirm version is **6.10.24+rev3** or the latest available

### Application credential expired

- Credentials can expire. If `chi-edge` commands fail with auth errors,
  create a new credential in the portal and re-source the RC file

## Next Steps

Once the device is enrolled and healthy:

1. Open `Request_LeRobot_SOARM101.ipynb` on Chameleon JupyterHub
2. Set `DEVICE_NAME = "soarm101-1"`
3. Run through the notebook to lease the device, launch the LeRobot
   container, and start collecting demonstration episodes
4. See [README.md](../README.md) for the full edge-to-cloud pipeline
