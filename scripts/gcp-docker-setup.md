# GCP VM Docker setup for aip-skillbench (concurrency ~12)

Target VM: `e2-standard-16` (16 vCPU / 64 GB), Ubuntu 24.04 LTS, a single
250 GB `pd-balanced` disk (boot + Docker share it — no separate data disk).
No GPU. Copy blocks one at a time.

The workload is ~12 concurrent benchflow trials; each runs a `docker compose`
project with its own bridge network. The settings below address the things
that actually bite at that concurrency: network address-pool exhaustion,
image/log disk growth, and inotify/fd limits.

## 1. Install Docker Engine (not Desktop)

```bash
sudo apt-get update && sudo apt-get install -y docker.io
sudo usermod -aG docker "$USER"     # then log out/in so `docker` works rootless-of-sudo
```

Docker's default `data-root` (`/var/lib/docker`) lives on the 250 GB root disk —
~240 GB free, which comfortably covers images + build cache (~30–80 GB) plus
`runs/` output. No separate disk to mount.

## 2. `/etc/docker/daemon.json`

```bash
sudo tee /etc/docker/daemon.json >/dev/null <<'JSON'
{
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" },
  "default-address-pools": [
    { "base": "172.20.0.0/14", "size": 24 }
  ],
  "max-concurrent-downloads": 10,
  "max-concurrent-uploads": 10,
  "features": { "buildkit": true }
}
JSON
sudo systemctl restart docker
```

Why each line:
- **`log-opts`** — caps per-container logs (3×10 MB); long campaigns otherwise leak disk via unbounded JSON logs.
- **`default-address-pools`** — the important one. benchflow creates a network per trial; at concurrency 12 plus not-yet-torn-down networks, Docker's default pool runs out → cryptic `could not find an available, non-overlapping IPv4 address pool` build failures. `172.20.0.0/14` carved into `/24`s gives 1024 networks. **Verify `172.20–172.23` doesn't overlap your GCP VPC subnet CIDR** (GCP defaults are usually `10.x`, so this is normally safe); if it clashes, pick another private range.
- **`max-concurrent-downloads/uploads`** — speeds the image-pull burst when 12 builds kick off at once.
- **`buildkit`** — faster, parallel builds.

## 3. Kernel limits for many concurrent containers

```bash
sudo tee /etc/sysctl.d/99-skillbench.conf >/dev/null <<'CONF'
fs.inotify.max_user_watches=524288
fs.inotify.max_user_instances=1024
vm.max_map_count=262144
CONF
sudo sysctl --system
```

- **inotify** — many containers + file-watching tooling exhaust the default watch/instance caps.
- **`vm.max_map_count`** — JVM-heavy tasks (Druid, Flink) and some scientific stacks need the higher value or they OOM/crash on startup.

Raise the open-file limit for the Docker service too:

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/override.conf >/dev/null <<'CONF'
[Service]
LimitNOFILE=1048576
CONF
sudo systemctl daemon-reload && sudo systemctl restart docker
```

## 4. Project setup

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone --recurse-submodules git@github.com:zach-blumenfeld/aip-skillbench.git
cd aip-skillbench && uv sync
cp .env.example .env          # add ANTHROPIC_API_KEY (eval AND authoring read it)
# AIP authoring on the VM also needs the `claude` CLI installed; skip if you
# only run evals here and author on the laptop.
```

## 5. Verify

```bash
docker info | grep -E "Docker Root Dir|Storage Driver"   # Root Dir = /var/lib/docker
docker run --rm hello-world                              # daemon works
df -h /                                                   # ~240 GB available
uv run aip-skillbench --help
```

## During long campaigns

Networks and dangling images accumulate. From a second shell, periodically:

```bash
docker network prune -f
docker system df                              # watch disk growth
docker system prune -f --filter "until=2h"    # reclaim, leaves active <2h alone
```

## Concurrency note

Start `--concurrency 12`, watch `free -g` and `docker stats`. RAM is the binding
constraint (~2 GB/cell + build spikes); 64 GB comfortably holds 12 mediums, fewer
if several heavy tasks (energy MILP, JVM, torch) land in one wave. The other
ceiling is the Anthropic per-org TPM limit, which shows up as cell errors (`·`)
regardless of VM size.
