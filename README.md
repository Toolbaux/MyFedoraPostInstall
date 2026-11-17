# Fedora Post-Install Lite

A Python helper for the usual setup on a fresh Fedora install. It asks before each step. A real run needs root.

## Requirements

- Fedora
- Python 3
- `sudo` (not required for `--dry-run`)

## Steps

| Step | What it does |
| --- | --- |
| `dnf` | Sets `fastestmirror=True` and `max_parallel_downloads=10` in `/etc/dnf/dnf.conf`. Backs the file up first, and leaves it alone when those settings are already present. |
| `repos` | Installs the RPM Fusion free and nonfree release packages for this Fedora version. |
| `rawhide` | Checks whether any RPM Fusion rawhide repo is enabled. If one is, enables `rpmfusion-free`, `rpmfusion-free-updates`, `rpmfusion-nonfree`, and `rpmfusion-nonfree-updates`, and disables the `-rawhide` repos. Uses `dnf5` `setopt`, or dnf4 `--set-enabled` / `--set-disabled`. |
| `ffmpeg` | Runs `dnf swap ffmpeg-free ffmpeg --allowerasing`, then upgrades the `multimedia` and `core` groups. |
| `firmware` | Runs `fwupdmgr refresh --force`, `get-devices`, `get-updates`, and `update`. Installs `fwupd` when `fwupdmgr` is missing. |
| `ntsync` | Checks `lsmod` for the `ntsync` module. If it isn't loaded, runs `modinfo ntsync` to see whether the kernel includes it. Skips when the kernel doesn't have it, and notes when it's built in. When it's a module, writes `ntsync` to `/etc/modules-load.d/ntsync.conf` (skipping if it's already there) so it loads at boot, then optionally runs `modprobe ntsync` to load it now. |

Step names for `--only` and `--skip`: `dnf`, `repos`, `rawhide`, `ffmpeg`, `firmware`, `ntsync`.

## Usage

Preview the commands first:

```bash
python3 fedora_postinstall_lite.py --dry-run
```

Then run it, confirming each step:

```bash
sudo python3 fedora_postinstall_lite.py
```

Run every step without prompts:

```bash
sudo python3 fedora_postinstall_lite.py --yes
```

Run or skip specific steps:

```bash
sudo python3 fedora_postinstall_lite.py --only repos rawhide
sudo python3 fedora_postinstall_lite.py --skip firmware
sudo python3 fedora_postinstall_lite.py -y --only dnf
```

## Afterward

Reboot when the script finishes. Firmware updates in particular apply on the next boot.
