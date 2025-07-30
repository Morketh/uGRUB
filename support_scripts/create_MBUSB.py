#!/usr/bin/env python3

import os
import subprocess
import sys
from pathlib import Path

SRC_DIR = Path.home() / "src" / "uGRUB"
DEVICE = ""
EFI_PART = ""
EXT_PART = ""

def run(cmd, check=True, capture_output=False, shell=False, input=None):
    print(f"[+] Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    return subprocess.run(cmd, check=check, capture_output=capture_output, shell=shell, text=True, input=input)

def confirm(prompt):
    ans = input(f"{prompt} (yes/no): ").strip().lower()
    if ans not in ["yes", "y"]:
        print("Aborted.")
        sys.exit(1)

def partition_device():
    print(f"[!] Partitioning {DEVICE} (ALL DATA WILL BE LOST)")
    confirm("Are you sure you want to continue")

    # Partition table: EFI (FAT32) + EXT4
    fdisk_script = "o\nn\np\n1\n\n+300M\nt\nc\nn\np\n2\n\n\nw\n"
    run(["sudo", "fdisk", DEVICE], input=fdisk_script.encode())

    run(["sudo", "partprobe", DEVICE])

def format_partitions():
    print("[+] Formatting partitions")
    run(["sudo", "umount", EFI_PART], check=False)
    run(["sudo", "umount", EXT_PART], check=False)

    run(["sudo", "mkfs.vfat", "-F", "32", "-n", "EFI", EFI_PART])
    run(["sudo", "mkfs.ext4", "-F", "-L", "MULTIBOOT", EXT_PART])

def mount_partitions():
    print("[+] Mounting EXT4 as /mnt")
    run(["sudo", "mount", EXT_PART, "/mnt"])
    run(["sudo", "mkdir", "-p", "/mnt/boot/efi"])
    run(["sudo", "mount", EFI_PART, "/mnt/boot/efi"])

def install_grub():
    print("[+] Installing GRUB (BIOS mode)")
    run([
        "sudo", "grub-install",
        "--target=i386-pc",
        "--boot-directory=/mnt/boot",
        DEVICE
    ])

    print("[+] Installing GRUB (UEFI mode)")
    run([
        "sudo", "grub-install",
        "--target=x86_64-efi",
        "--efi-directory=/mnt/boot/efi",
        "--boot-directory=/mnt/boot",
        "--removable",
        "--no-nvram"
    ])

def copy_with_pv(src: Path, dest: Path):
    size_bytes = int(subprocess.check_output(["du", "-sb", str(src)]).split()[0])
    print(f"[+] Copying {src} → {dest} ({size_bytes // (1024 * 1024)} MB)")
    tar_cmd = f"cd {src} && tar -cf - ."
    extract_cmd = f"sudo tar -xf - -C {dest}"
    pv_cmd = f"pv -s {size_bytes}"
    full_cmd = f"{tar_cmd} | {pv_cmd} | {extract_cmd}"
    run(full_cmd, shell=True)

def copy_files():
    print("[+] Copying payload files")

    images_src = SRC_DIR / "images"
    grub_src = SRC_DIR / "grub"
    grub_dst = Path("/mnt") / "boot" / "grub"

    if not images_src.exists() or not grub_src.exists():
        print("[-] Source directories not found. Aborting.")
        sys.exit(1)

    copy_with_pv(images_src, Path("/mnt"))
    run(["sudo", "mkdir", "-p", str(grub_dst)])
    copy_with_pv(grub_src, grub_dst)

def unmount_all():
    print("[+] Unmounting /mnt and /mnt/boot/efi")
    run(["sudo", "umount", "/mnt/boot/efi"], check=False)
    run(["sudo", "umount", "/mnt"], check=False)

def main():
    global DEVICE, EFI_PART, EXT_PART

    if os.geteuid() != 0:
        print("[-] Please run this script as root or with sudo.")
        sys.exit(1)

    if len(sys.argv) != 2:
        print(f"Usage: sudo {sys.argv[0]} /dev/sdX")
        sys.exit(1)

    DEVICE = sys.argv[1]
    if not Path(DEVICE).exists():
        print(f"[-] Device {DEVICE} not found.")
        sys.exit(1)

    # Handle NVMe vs standard block naming
    EFI_PART = DEVICE + ("p1" if "nvme" in DEVICE else "1")
    EXT_PART = DEVICE + ("p2" if "nvme" in DEVICE else "2")

    partition_device()
    format_partitions()
    mount_partitions()
    install_grub()
    copy_files()
    unmount_all()

    print("[✓] USB multiboot drive created successfully.")

if __name__ == "__main__":
    main()
