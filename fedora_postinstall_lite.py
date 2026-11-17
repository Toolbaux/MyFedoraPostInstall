#!/usr/bin/env python3
"""
Fedora Post-Install Lite

Runs the usual post-install steps on a fresh Fedora system:
  1. Speed up DNF (fastestmirror, max_parallel_downloads=10 in /etc/dnf/dnf.conf)
  2. Add the RPM Fusion free and non-free repos
  3. Make sure the RPM Fusion Rawhide repos are disabled (and fix them if not)
  4. Swap ffmpeg-free for the full ffmpeg and upgrade the multimedia/core groups
  5. Check for and apply firmware updates with fwupdmgr
  6. Make sure the ntsync kernel module loads at boot (if the kernel has it)

Usage:
  sudo python3 fedora_postinstall_lite.py              # asks before each step
  sudo python3 fedora_postinstall_lite.py --yes        # runs every step, no prompts
  python3 fedora_postinstall_lite.py --dry-run         # just prints the commands
  sudo python3 fedora_postinstall_lite.py --only repos rawhide
Steps: dnf, repos, rawhide, ffmpeg, firmware, ntsync
"""
import argparse
import configparser
import os
import shutil
import subprocess
import sys
from datetime import datetime

DNF_CONF = "/etc/dnf/dnf.conf"
DNF_SETTINGS = {"fastestmirror": "True", "max_parallel_downloads": "10"}
STEPS = ["dnf", "repos", "rawhide", "ffmpeg", "firmware", "ntsync"]
NTSYNC_CONF = "/etc/modules-load.d/ntsync.conf"

DRY_RUN = False
ASSUME_YES = False


# ---------- helpers ----------
def info(msg):
    print(f"\033[1;34m==>\033[0m {msg}")


def warn(msg):
    print(f"\033[1;33m[!]\033[0m {msg}")


def ok(msg):
    print(f"\033[1;32m[ok]\033[0m {msg}")


def run(cmd, check=True, capture=False):
    """Run a command (list). In dry-run mode just print it."""
    print("    $ " + " ".join(cmd))
    if DRY_RUN:
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    return subprocess.run(cmd, check=check, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if capture else None)


def confirm(question):
    if ASSUME_YES or DRY_RUN:
        return True
    ans = input(f"{question} [Y/n] ").strip().lower()
    return ans in ("", "y", "yes")


def fedora_version():
    out = subprocess.run(["rpm", "-E", "%fedora"], text=True,
                         stdout=subprocess.PIPE).stdout.strip()
    if not out.isdigit():
        sys.exit("Could not detect the Fedora version. Is this Fedora?")
    return out


def dnf_cmd():
    """Prefer dnf5 if present (Fedora 41+), else dnf."""
    return "dnf5" if shutil.which("dnf5") else "dnf"


def setopt(repo_opt):
    """Set a repo option, handling dnf5 vs dnf4 config-manager syntax."""
    if dnf_cmd() == "dnf5":
        run(["dnf", "config-manager", "setopt", repo_opt])
    else:
        repo, val = repo_opt.split("=", 1)
        repo_id = repo.rsplit(".enabled", 1)[0]
        flag = "--set-enabled" if val == "1" else "--set-disabled"
        run(["dnf", "config-manager", flag, repo_id])


# ---------- steps ----------
def step_dnf():
    info(f"Tuning DNF in {DNF_CONF}")
    cfg = configparser.ConfigParser()
    cfg.optionxform = str  # keep key case
    cfg.read(DNF_CONF)
    if not cfg.has_section("main"):
        cfg.add_section("main")
    changed = False
    for key, val in DNF_SETTINGS.items():
        if cfg["main"].get(key) != val:
            print(f"    set {key}={val}")
            cfg["main"][key] = val
            changed = True
    if not changed:
        ok("dnf.conf already has these settings")
        return
    if DRY_RUN:
        return
    backup = f"{DNF_CONF}.bak-{datetime.now():%Y%m%d%H%M%S}"
    shutil.copy2(DNF_CONF, backup)
    with open(DNF_CONF, "w") as f:
        cfg.write(f, space_around_delimiters=False)
    ok(f"dnf.conf updated (backup at {backup})")


def step_repos():
    info("Adding RPM Fusion free and non-free repos")
    ver = fedora_version()
    base = "https://mirrors.rpmfusion.org"
    run(["dnf", "install", "-y",
         f"{base}/free/fedora/rpmfusion-free-release-{ver}.noarch.rpm",
         f"{base}/nonfree/fedora/rpmfusion-nonfree-release-{ver}.noarch.rpm"])
    ok("RPM Fusion repos installed")


def step_rawhide():
    info("Checking whether any RPM Fusion Rawhide repo is enabled")
    if DRY_RUN:
        run(["dnf", "repolist", "--enabled"])
        print("    (dry run: would disable any enabled rpmfusion-*-rawhide repos)")
        return
    else:
        out = run(["dnf", "repolist", "--enabled"], capture=True).stdout
        enabled = [line.split()[0] for line in out.splitlines()
                   if "fusion" in line.lower() and "rawhide" in line.lower()]
    if not enabled:
        ok("No RPM Fusion Rawhide repos are enabled")
        return
    warn("Rawhide enabled: " + ", ".join(enabled))
    if not confirm("Disable Rawhide and enable the normal RPM Fusion repos?"):
        return
    for kind in ("free", "nonfree"):
        setopt(f"rpmfusion-{kind}.enabled=1")
        setopt(f"rpmfusion-{kind}-updates.enabled=1")
        setopt(f"rpmfusion-{kind}-rawhide.enabled=0")
    ok("Rawhide disabled, stable RPM Fusion repos enabled")


def step_ffmpeg():
    info("Swapping ffmpeg-free for full ffmpeg and upgrading media groups")
    run(["dnf", "swap", "-y", "ffmpeg-free", "ffmpeg", "--allowerasing"])
    run(["dnf", "group", "upgrade", "-y", "multimedia"])
    run(["dnf", "group", "upgrade", "-y", "core"])
    ok("Multimedia codecs installed")


def step_firmware():
    info("Checking firmware updates")
    if not shutil.which("fwupdmgr") and not DRY_RUN:
        warn("fwupdmgr not found; installing fwupd")
        run(["dnf", "install", "-y", "fwupd"])
    run(["fwupdmgr", "refresh", "--force"], check=False)
    run(["fwupdmgr", "get-devices"], check=False)
    # get-updates exits 2 when there's nothing to update
    res = run(["fwupdmgr", "get-updates"], check=False)
    if res.returncode == 2:
        ok("No firmware updates available")
        return
    if confirm("Apply firmware updates now? (may require a reboot)"):
        run(["fwupdmgr", "update", "-y"], check=False)


def step_ntsync():
    info("Checking for the ntsync kernel module")
    # These checks only read, so they run for real even in dry-run mode.
    print("    $ lsmod | grep ntsync")
    if not (shutil.which("lsmod") and shutil.which("modinfo")):
        warn("lsmod/modinfo not found (install kmod); skipping")
        return
    lsmod = subprocess.run(["lsmod"], text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL).stdout
    loaded = any(line.split()[0] == "ntsync" for line in lsmod.splitlines()[1:] if line.strip())
    if loaded:
        ok("ntsync is already loaded")
    else:
        print("    (not loaded)")
        print("    $ modinfo ntsync")
        mi = subprocess.run(["modinfo", "ntsync"], text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
        if mi.returncode != 0:
            warn(f"This kernel ({os.uname().release}) doesn't include ntsync; skipping")
            return
        if "(builtin)" in mi.stdout:
            ok("ntsync is built into the kernel, so nothing needs to load at boot")
            return
        ok("The kernel includes ntsync as a module")

    if os.path.exists(NTSYNC_CONF):
        with open(NTSYNC_CONF) as f:
            if "ntsync" in f.read().split():
                ok(f"{NTSYNC_CONF} already loads ntsync at boot")
                return
    if not confirm("Load ntsync automatically at boot?"):
        return
    print(f"    $ echo ntsync | sudo tee {NTSYNC_CONF}")
    if not DRY_RUN:
        with open(NTSYNC_CONF, "w") as f:
            f.write("ntsync\n")
    ok(f"ntsync will load at boot ({NTSYNC_CONF})")
    if not loaded and confirm("Load ntsync now as well?"):
        run(["modprobe", "ntsync"], check=False)


STEP_FUNCS = {"dnf": step_dnf, "repos": step_repos, "rawhide": step_rawhide,
              "ffmpeg": step_ffmpeg, "firmware": step_firmware,
              "ntsync": step_ntsync}
STEP_TITLES = {"dnf": "Speed up DNF", "repos": "Add RPM Fusion repos",
               "rawhide": "Check/disable Rawhide repos",
               "ffmpeg": "Full ffmpeg + multimedia groups",
               "firmware": "Firmware updates",
               "ntsync": "Enable ntsync at boot"}


def main():
    global DRY_RUN, ASSUME_YES
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print commands without running them")
    ap.add_argument("-y", "--yes", action="store_true", help="don't ask before each step")
    ap.add_argument("--only", nargs="+", choices=STEPS, help="run only these steps")
    ap.add_argument("--skip", nargs="+", choices=STEPS, default=[], help="skip these steps")
    args = ap.parse_args()
    DRY_RUN, ASSUME_YES = args.dry_run, args.yes

    if not DRY_RUN and os.geteuid() != 0:
        sys.exit("Please run with sudo (or use --dry-run to preview).")
    if not os.path.exists("/etc/fedora-release") and not DRY_RUN:
        sys.exit("This script is for Fedora only.")

    steps = [s for s in (args.only or STEPS) if s not in args.skip]
    print("Fedora Post-Install Lite" + ("  (DRY RUN)" if DRY_RUN else ""))
    failed = []
    for s in steps:
        print()
        if not confirm(f"Run step '{STEP_TITLES[s]}'?"):
            warn(f"Skipped {s}")
            continue
        try:
            STEP_FUNCS[s]()
        except subprocess.CalledProcessError as e:
            warn(f"Step '{s}' failed (exit {e.returncode}); continuing")
            failed.append(s)

    print()
    if failed:
        warn("Finished with errors in: " + ", ".join(failed))
        sys.exit(1)
    ok("All done. A reboot is recommended.")


if __name__ == "__main__":
    main()
