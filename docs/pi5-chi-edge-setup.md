# Raspberry Pi 5 CHI@Edge Setup Guide

Enroll a Raspberry Pi 5 as a user-owned device on Chameleon Cloud's CHI@Edge
infrastructure for SO-ARM101 data collection with LeRobot.

This guide uses **Balena CLI** to download and flash BalenaOS and
**chi-edge CLI** to register, bake, and monitor the device.

## Prerequisites

| Item | Details |
|------|---------|
| Chameleon account | Active allocation on project `CHI-261589` |
| balena.io account | Free account at https://dashboard.balena-cloud.com |
| Pi 5 | 8 GB RAM |
| Boot media | microSD (16 GB+) or NVME SSD |
| SO-ARM101 | Follower arm + Feetech STS3215 servos |
| USB cameras | 2x, for top and side views |
| Workstation | Linux/macOS with Python 3.10+ and Node.js 18+ |

## Install CLIs

### Balena CLI

```bash
# Option 1: via npm (requires Node.js 18+)
npm install -g balena-cli

# Option 2: standalone installer
# Download from https://github.com/balena-io/balena-cli/releases
# then add to PATH

# Verify (expected output: balena-cli/24.x.x linux-x64 node-vX.X.X)
balena version
```

### chi-edge CLI

On Ubuntu/Debian, the system Python is externally managed (PEP 668).
Use `--break-system-packages` or install into a venv:

```bash
# Option 1: system-wide (simplest)
pip install python-chi-edge --break-system-packages

# Option 2: venv (no flag needed, no side effects)
python3 -m venv chi-edge-env
source chi-edge-env/bin/activate
pip install python-chi-edge

# Verify
chi-edge --help
```

## Step 1: Create a CHI@Edge Application Credential

1. Log in to **https://chi.edge.chameleoncloud.org**
2. Navigate to **Identity > Application Credentials**
3. Click **Create Application Credential**
   - Name: `edge-pi5`
   - Leave roles and expiration as defaults
4. **Save the secret immediately** — it is shown only once
5. Download the RC file (e.g., `app-cred-edge-openrc.sh`)

Source the RC file to load credentials into your shell:

```bash
source app-cred-edge-openrc.sh
```

Verify:

```bash
env | grep OS_APPLICATION_CREDENTIAL
```

## Step 2: Register the Device

```bash
chi-edge device register \
  --contact-email YOUR_EMAIL@example.edu \
  --application-credential-id "$OS_APPLICATION_CREDENTIAL_ID" \
  --application-credential-secret "$OS_APPLICATION_CREDENTIAL_SECRET" \
  --machine-name raspberrypi5 \
  soarm101-1
```

Notes:
- `--machine-name raspberrypi5` is the machine type for Pi 5. The CLI also
  lists `raspberrypi5-64` as an option; use `raspberrypi5` to match the
  BalenaOS device type used by `balena os download`
- Supported machine names: `raspberrypi3-64`, `raspberrypi4-64`,
  `raspberrypi5`, `jetson-nano`, `jetson-xavier-nx-emmc`,
  `jetson-agx-orin-devkit`, `coral-dev`
- `soarm101-1` is your device name — must match `DEVICE_NAME` in
  `Request_LeRobot_SOARM101.ipynb`
- The command returns a **device UUID** — save it for the bake step

## Step 3: Download BalenaOS via Balena CLI

Log in to balena.io:

```bash
balena login
# Choose "Web authorization" and follow the browser prompt
```

List available versions to find the latest:

```bash
balena os versions raspberrypi5
# v6.10.24
# v6.10.22
# v6.9.4+rev7
# ...
```

Download the BalenaOS **development** image for Pi 5. Append `.dev` to the
version string to select the development variant:

```bash
balena os download raspberrypi5 \
  --version 6.10.24.dev \
  -o balena-raspberrypi5-6.10.24.dev.img.gz
```

Notes:
- The development variant enables local SSH and serial console, which are
  required for CHI@Edge enrollment and debugging. Production images disable
  SSH and cannot be enrolled.
- `-o` is the output flag (short for `--output`)
- Omit `--version` to download the latest release (production); always
  specify `.dev` explicitly for the development image

Extract the image (balena flash can also read `.img.gz` directly, but
baking with chi-edge requires an uncompressed `.img`):

```bash
gunzip balena-raspberrypi5-6.10.24.dev.img.gz
# Result: balena-raspberrypi5-6.10.24.dev.img
```

## Step 4: Bake the Image

Baking injects your device-specific credentials and CHI@Edge registration
into the image. Use the device UUID returned in Step 2:

```bash
chi-edge device bake \
  --image balena-raspberrypi5-6.10.24.dev.img \
  DEVICE_UUID
```

This modifies the image in place — the output file is now personalized for
your specific device and should not be reused for other devices.

## Step 5: Flash the Image via Balena CLI

Choose the boot media that matches your setup.

### Option A: Flash to microSD

Insert the microSD card into your workstation, then:

```bash
# List available drives to identify the SD card device
balena util available-drives

# Flash — interactive: balena CLI prompts you to select the drive
balena local flash balena-raspberrypi5-6.10.24.dev.img
```

Balena CLI lists only removable drives and refuses to overwrite the system
disk. To specify the drive directly (useful in scripts):

```bash
balena local flash balena-raspberrypi5-6.10.24.dev.img --drive /dev/sdX --yes
```

Eject the card when flashing is complete, then insert it into the Pi 5.

### Option B: Flash to NVME

Booting from NVME gives faster I/O for dataset recording. Requires updating
the Pi 5 bootloader first.

**1. Update the Pi 5 EEPROM to enable NVME boot**

On a Pi 5 already running Raspberry Pi OS (booted from microSD):

```bash
sudo rpi-eeprom-update -a
sudo reboot
```

After reboot, set the NVME-first boot order:

```bash
sudo rpi-eeprom-config --edit
```

Set:

```
BOOT_ORDER=0xf416
```

Boot order digits (right to left): `6`=NVME, `1`=SD, `4`=USB, `f`=restart.
Save and reboot:

```bash
sudo reboot
```

**2. Connect the NVME drive to your workstation** (via USB-to-NVME adapter),
then flash:

```bash
balena util available-drives
balena local flash balena-raspberrypi5-6.10.24.dev.img --drive /dev/nvme0n1 --yes
```

Remove the microSD (or leave it — the updated boot order prefers NVME)
and power on the Pi.

## Step 6: Boot and Verify Enrollment

1. Insert boot media (microSD or NVME) into the Pi 5
2. Connect Ethernet — **Wi-Fi is not supported** by BalenaOS on CHI@Edge
3. Connect SO-ARM101 (USB serial) and cameras (USB) if available
4. Power on

The Pi will automatically:
- Boot BalenaOS
- Download CHI@Edge services
- Connect via WireGuard to the control plane
- Self-register as a reservable device

Monitor enrollment from your workstation (allow 5-10 minutes on first boot):

```bash
chi-edge device list
chi-edge device show soarm101-1
```

When health status shows **3/3** and all checks read **STEADY**, the device
is enrolled and available for reservation.

Confirm in the portal:
1. Go to **https://chi.edge.chameleoncloud.org**
2. Navigate to **Hardware > Devices**
3. Confirm `soarm101-1` appears with status **enrolled**

## Optional: Restrict Device Access

Limit which projects can lease your device:

```bash
chi-edge device set --authorized-projects CHI-261589 soarm101-1
```

## NVME Storage

### NVME as Boot Drive

If you flashed BalenaOS to NVME (Option B), the full NVME is used by
BalenaOS. Container storage and dataset recording will automatically use
NVME — no extra configuration needed. This is the recommended setup for
data collection since NVME write throughput far exceeds microSD.

### NVME as Data Drive (microSD boot + NVME for data)

Mount the NVME inside containers by adding a volume in your notebook:

```python
# In Request_LeRobot_SOARM101.ipynb
my_container = Container(
    ...
    mounts=["/mnt/nvme:/data"],
)
```

Format the NVME partition on first use (destroys existing data):

```bash
sudo mkfs.ext4 /dev/nvme0n1p1
sudo mkdir -p /mnt/nvme
sudo mount /dev/nvme0n1p1 /mnt/nvme
```

## Peripheral Access

Devices connected to the Pi are exposed to containers via device profiles:

| Profile | Exposes |
|---------|---------|
| `pi_serial` | `/dev/ttyACM*`, `/dev/ttyUSB*` — servo controllers |
| `pi_gpio` | GPIO pins |
| `pi_camera` | `/dev/video*` — cameras |

Configure in `Request_LeRobot_SOARM101.ipynb`:

```python
my_container = Container(
    ...
    device_profiles=["pi_serial", "pi_gpio", "pi_camera"],
)
```

## Troubleshooting

### `balena os download` fails with "Unauthorized"

```bash
balena login
# Re-authenticate via browser, then retry the download
```

### `balena local flash` fails with "EACCES"

```bash
# Run with sudo if your user lacks raw disk access
sudo balena local flash balena-raspberrypi5-6.10.24.dev.img
```

### Device not appearing in `chi-edge device list`

- Confirm Ethernet is connected — BalenaOS does not support Wi-Fi on CHI@Edge
- Wait 5-10 minutes on first boot for services to download
- Run `chi-edge device show soarm101-1` to see partial health check progress

### Health checks stuck at 1/3 or 2/3

- The device is still downloading container images — wait another 5 minutes
- Verify outbound internet access (WireGuard and Docker Hub must be reachable)
- Reboot the Pi and re-check

### Wrong image / architecture or variant

- Confirm the image is for `raspberrypi5` (not `raspberrypi4-64`)
- Confirm you downloaded the `.dev` variant — production images have SSH
  disabled and cannot complete CHI@Edge enrollment
- Verify available versions: `balena os versions raspberrypi5`
- Development version syntax: `6.10.24.dev` (append `.dev`, no `+rev` suffix)

### Application credential expired

If `chi-edge` commands fail with auth errors, create a new credential at
`https://chi.edge.chameleoncloud.org/identity/application_credentials/`,
download the new RC file, and re-source it.

### PyTorch CUDA not available on MI100 (cloud training)

```bash
pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/rocm6.3
python -c "import torch; print(torch.cuda.is_available())"  # True on ROCm
```

## Next Steps

Once the device is enrolled and healthy:

1. Open `Request_LeRobot_SOARM101.ipynb` on Chameleon JupyterHub
2. Set `DEVICE_NAME = "soarm101-1"`
3. Run through the notebook to lease the device, launch the LeRobot
   container, and collect demonstration episodes
4. See [README.md](../README.md) for the full edge-to-cloud pipeline
