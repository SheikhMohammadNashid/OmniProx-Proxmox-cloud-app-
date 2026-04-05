# Proxmox Pre-Setup Guide
### Fix common issues before running `SETUP_GOLDEN_IMAGE.sh`

---

## Step 1 — Fix DNS

Without working DNS, `apt` cannot reach any mirrors.

```bash
echo "nameserver 8.8.8.8" > /etc/resolv.conf
```

Verify it works:

```bash
ping -c 2 deb.debian.org
```

If ping succeeds, move to Step 2.

---

## Step 2 — Sync the System Clock

Proxmox's GPG signature verification will fail if the system clock is behind.
This shows up as errors like `Not live until 2026-XX-XXTXX:XX:XXZ`.

```bash
chronyc makestep
```

If `chrony` is not installed:

```bash
apt-get install -y chrony
chronyc makestep
```

Or force-set the time manually as a last resort:

```bash
date -s "$(curl -s --head http://google.com | grep ^Date: | sed 's/Date: //')"
```

Verify:

```bash
date
```

---

## Step 3 — Disable Enterprise Repos (Free Users Only)

If you are on the **free/community version** of Proxmox (no paid subscription),
the enterprise repos will block `apt` with `401 Unauthorized` errors.

Proxmox stores repo config in two formats — you need to disable both.

### 3a — Disable `.list` files

```bash
truncate -s 0 /etc/apt/sources.list.d/pve-enterprise.list
truncate -s 0 /etc/apt/sources.list.d/ceph.list
```

### 3b — Disable `.sources` files (DEB822 format)

```bash
sed -i 's/^Enabled: yes/Enabled: no/' /etc/apt/sources.list.d/ceph.sources
sed -i 's/^Enabled: yes/Enabled: no/' /etc/apt/sources.list.d/pve-enterprise.sources

# Add Enabled: no if the line doesn't exist yet
grep -q "^Enabled:" /etc/apt/sources.list.d/ceph.sources || \
  sed -i '1i Enabled: no' /etc/apt/sources.list.d/ceph.sources

grep -q "^Enabled:" /etc/apt/sources.list.d/pve-enterprise.sources || \
  sed -i '1i Enabled: no' /etc/apt/sources.list.d/pve-enterprise.sources
```

### 3c — Add the free community repo

```bash
grep -q "pve-no-subscription" /etc/apt/sources.list || \
  echo "deb http://download.proxmox.com/debian/pve trixie pve-no-subscription" \
  >> /etc/apt/sources.list
```

---

## Step 4 — Verify apt Works

```bash
apt-get update
```

You should see only `Hit:` and `Get:` lines with no `401` or `Unauthorized` errors.

If you still see enterprise repo errors, find which file is holding them:

```bash
grep -r "enterprise.proxmox.com" /etc/apt/
```

Then disable whichever file is listed in the output using the same `truncate`
or `sed` commands from Step 3.

---

## Step 5 — Run the Setup Script

```bash
chmod +x SETUP_GOLDEN_IMAGE.sh
./SETUP_GOLDEN_IMAGE.sh
```

If `apt` or `virt-customize` still fails for any reason, the script will
automatically fall back to a cloud-init snippet that installs `qemu-guest-agent`
on first boot. You do not need to do anything extra — the script handles it.

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `Temporary failure resolving` | DNS not set | Step 1 |
| `Not live until 20XX-XX-XX` | System clock wrong | Step 2 |
| `401 Unauthorized` | Enterprise repo, no subscription | Step 3 |
| `Unable to locate package libguestfs-tools` | Enterprise repo still active | Step 3 + Step 4 |
| `Could not get lock /var/lib/apt/lists/lock` | Another apt process running | Wait 30s and retry, or `kill <PID>` |
| VM has no IP after boot | `qemu-guest-agent` not running | Cloud-init snippet handles this automatically on first boot |

---

> **Note:** The `SETUP_GOLDEN_IMAGE.sh` script only needs to be run once per
> Proxmox node. Once the golden template (VMID 9000) exists, all subsequent
> VMs are cloned from it and inherit the cloud-init snippet automatically.
