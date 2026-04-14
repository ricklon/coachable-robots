#!/bin/bash
# channels/diag/scripts/entrypoint.sh
#
# Diagnostic entrypoint for CHI@Edge Jetson Orin.
# Runs a comprehensive check at startup, writes /tmp/diag.json,
# then sleeps forever so results can be read via:
#   python: zun.containers.execute(name, command='cat /tmp/diag.json', run=True)
#   just:   just jetson-exec cmd="cat /tmp/diag.json"
#
# Does NOT use set -e — we want to capture failures, not die on them.

DIAG=/tmp/diag.json
LOG=/tmp/diag.log

exec > >(tee -a "$LOG") 2>&1
echo "[diag] starting at $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ── Export env to SSH sessions ────────────────────────────────────────────────
printenv | grep -v '^_=' | grep -v '^SHLVL=' > /etc/environment

# ── SSH daemon ────────────────────────────────────────────────────────────────
mkdir -p /run/sshd /root/.ssh
chmod 700 /root/.ssh
if [ -n "${SSH_PUBKEY:-}" ]; then
    echo "$SSH_PUBKEY" >> /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
fi
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/'              /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/'    /etc/ssh/sshd_config
ssh-keygen -A 2>/dev/null
/usr/sbin/sshd && echo "[diag] sshd started" || echo "[diag] sshd FAILED"

# ── Tailscale (best-effort) ───────────────────────────────────────────────────
TS_OK=false
if [ -n "${TS_AUTHKEY:-}" ]; then
    mkdir -p /var/run/tailscale /var/lib/tailscale
    tailscaled --state=/var/lib/tailscale/tailscaled.state \
               --socket=/var/run/tailscale/tailscaled.sock \
               --tun=userspace-networking \
               --statedir=/var/lib/tailscale &
    TS_PID=$!
    sleep 3
    if tailscale --socket=/var/run/tailscale/tailscaled.sock \
           up --authkey="${TS_AUTHKEY}" \
              --hostname="${TS_HOSTNAME:-diag-jetson}" \
              --accept-routes \
              --timeout=15s 2>/dev/null; then
        TS_OK=true
        echo "[diag] tailscale up — hostname: ${TS_HOSTNAME:-diag-jetson}"
    else
        echo "[diag] tailscale FAILED to connect (network restricted?)"
    fi
else
    echo "[diag] TS_AUTHKEY not set — skipping tailscale"
fi

# ── Run diagnostics ──────────────────────────────────────────────────────────
echo "[diag] running diagnostics..."

python3 - <<'PYDIAG'
import json, socket, subprocess, os, pathlib, time

def run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or r.stderr.strip()
    except Exception as e:
        return f"ERROR: {e}"

def tcp_check(host, port, timeout=5):
    try:
        ip = socket.gethostbyname(host)
        s = socket.socket()
        s.settimeout(timeout)
        s.connect((ip, port))
        s.close()
        return {"dns": ip, "tcp": "ok"}
    except socket.gaierror as e:
        return {"dns": "FAIL", "error": str(e)}
    except Exception as e:
        return {"dns": socket.getfqdn(host), "tcp": f"FAIL: {e}"}

def http_check(url, timeout=8):
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), "-o", "/dev/null",
             "-w", "%{http_code}", url],
            capture_output=True, text=True, timeout=timeout+2
        )
        return r.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"

diag = {
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "system": {},
    "network": {},
    "gpu": {},
    "devices": {},
    "kubernetes": {},
    "mounts": {},
}

# System info
diag["system"]["uname"] = run("uname -a")
diag["system"]["arch"] = run("uname -m")
diag["system"]["os_release"] = run("cat /etc/os-release | head -4")
diag["system"]["cpuinfo"] = run("grep 'Model name\\|model name\\|Hardware' /proc/cpuinfo | head -3")
diag["system"]["meminfo"] = run("grep MemTotal /proc/meminfo")

# Network interfaces and routes
diag["network"]["interfaces"] = run("ip addr show")
diag["network"]["routes"] = run("ip route")
diag["network"]["resolv_conf"] = run("cat /etc/resolv.conf")

# Connectivity checks
checks = {
    "controlplane.tailscale.com:443": ("controlplane.tailscale.com", 443),
    "api.openrouter.ai:443":          ("api.openrouter.ai", 443),
    "hub.docker.com:443":             ("hub.docker.com", 443),
    "huggingface.co:443":             ("huggingface.co", 443),
    "8.8.8.8:53":                     ("8.8.8.8", 53),
    "1.1.1.1:443":                    ("1.1.1.1", 443),
}
diag["network"]["connectivity"] = {k: tcp_check(h, p) for k, (h, p) in checks.items()}

# HTTP checks (only if TCP worked)
if diag["network"]["connectivity"]["hub.docker.com:443"].get("tcp") == "ok":
    diag["network"]["http_hub_docker"] = http_check("https://hub.docker.com")
if diag["network"]["connectivity"]["api.openrouter.ai:443"].get("tcp") == "ok":
    diag["network"]["http_openrouter"] = http_check("https://api.openrouter.ai/api/v1/models")

# GPU / CUDA
diag["gpu"]["nvidia_smi"]   = run("nvidia-smi")
diag["gpu"]["nvcc_version"] = run("nvcc --version")
diag["gpu"]["rocm_smi"]     = run("rocm-smi")
diag["gpu"]["dev_nvidia"]   = run("ls /dev/nvidia* 2>/dev/null || echo none")
diag["gpu"]["dev_dri"]      = run("ls /dev/dri/ 2>/dev/null || echo none")
diag["gpu"]["cuda_devices"]  = run("ls /dev/cuda* 2>/dev/null || echo none")
diag["gpu"]["lspci_gpu"]    = run("lspci | grep -iE 'vga|3d|display|nvidia'")

# Device files (what the host is passing through)
diag["devices"]["dev_listing"] = run("ls /dev/ | grep -iE 'nvidia|cuda|dri|video|ttyACM|ttyUSB'")
diag["devices"]["sys_class_drm"] = run("ls /sys/class/drm/ 2>/dev/null || echo none")

# Kubernetes environment
k8s_vars = {k: v for k, v in os.environ.items() if k.startswith("KUBERNETES") or k.startswith("K8S")}
diag["kubernetes"]["env_vars"] = k8s_vars
diag["kubernetes"]["serviceaccount"] = str(pathlib.Path("/var/run/secrets/kubernetes.io/serviceaccount").exists())
diag["kubernetes"]["node_name"] = os.environ.get("NODE_NAME", "not set")

# Mounts
diag["mounts"]["proc_mounts"] = run("cat /proc/mounts | grep -v '^proc\\|^sysfs\\|^devtmpfs\\|^cgroup'")

# Write results
with open("/tmp/diag.json", "w") as f:
    json.dump(diag, f, indent=2)
print("[diag] results written to /tmp/diag.json")

# Print summary
net = diag["network"]["connectivity"]
print("\n=== NETWORK SUMMARY ===")
for k, v in net.items():
    status = "OK" if v.get("tcp") == "ok" else "FAIL"
    print(f"  {status}  {k}  ({v.get('dns','?')})")

print("\n=== GPU SUMMARY ===")
print("  /dev/nvidia*:", diag["gpu"]["dev_nvidia"])
print("  nvidia-smi:  ", diag["gpu"]["nvidia_smi"][:80] if diag["gpu"]["nvidia_smi"] else "not found")

PYDIAG

echo "[diag] diagnostics complete. Results at /tmp/diag.json"
echo "[diag] container staying up — read results with:"
echo "[diag]   just jetson-exec cmd='cat /tmp/diag.json'"

# Stay up forever — do NOT exec into anything that might fail
exec sleep infinity
