// ── DOM refs ──────────────────────────────────────────────────────────────────
const form           = document.getElementById("vm-form");
const result         = document.getElementById("result");
const jobList        = document.getElementById("job-list");
const refreshJobsBtn = document.getElementById("refresh-jobs");
const userMeta       = document.getElementById("user-meta");
const logoutBtn      = document.getElementById("logout-btn");

// ── Auth helpers ──────────────────────────────────────────────────────────────
function getToken() { return localStorage.getItem("access_token"); }
function requireAuthToken() {
  const t = getToken();
  if (!t) { window.location.href = "/login"; return null; }
  return t;
}

// ── Fetch current user ────────────────────────────────────────────────────────
async function fetchMe() {
  const token = requireAuthToken(); if (!token) return;
  const res = await fetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) { localStorage.removeItem("access_token"); window.location.href = "/login"; return; }
  const me = await res.json();
  userMeta.textContent = `${me.username} (${me.role}) — quota: ${me.daily_quota}/day`;
}

// ── Proxmox creds check ───────────────────────────────────────────────────────
async function ensureProxmoxCreds() {
  const token = requireAuthToken(); if (!token) return false;
  const res = await fetch("/api/proxmox/creds/status", { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) { localStorage.removeItem("access_token"); window.location.href = "/login"; return false; }
  const json = await res.json();
  if (!json.has_creds) { window.location.href = "/creds"; return false; }
  if (json.dry_run) userMeta.textContent = (userMeta.textContent||"") + " | DRY RUN";
  return true;
}

// ── Render job cards ──────────────────────────────────────────────────────────
function badgeClass(status) {
  return { success: "badge-success", running: "badge-running", queued: "badge-queued", failed: "badge-failed" }[status] || "badge-queued";
}

function renderJobs(jobs) {
  if (!jobs.length) {
    jobList.innerHTML = '<p style="color:#94a3b8;margin-top:12px">No VMs yet.</p>';
    return;
  }

  jobList.innerHTML = jobs.map(j => {
    const ip  = j.proxmox_response?.vm_ip || null;
    const err = j.error_message ? `<div style="color:#f87171;font-size:13px;margin-top:4px">⚠ ${j.error_message}</div>` : "";

    const ipSection = j.status === "success" ? (ip
      ? `<div class="ip-row">
           <span class="ip-value">${ip}</span>
           <button class="copy-btn" onclick="copyIp('${ip}', this)">Copy</button>
         </div>
         <div class="ssh-hint">ssh ${j.ssh_user}@${ip}</div>`
      : `<div class="ip-row">
           <span class="ip-pending">⏳ Waiting for IP… (auto-refreshing)</span>
           <button class="fetch-ip-btn" onclick="triggerFetchIp(${j.id})">Retry now</button>
         </div>`)
      : "";

    return `
      <div class="job-card">
        <div class="job-card-header">
          <span class="job-name">${j.vm_name} <span style="color:#475569;font-weight:400;font-size:13px">VMID ${j.vmid}</span></span>
          <span class="badge ${badgeClass(j.status)}">${j.status}</span>
        </div>
        <div class="job-meta">
          <span>${j.os_choice}</span>
          <span>user: ${j.ssh_user}</span>
          <span>${new Date(j.created_at).toLocaleString()}</span>
        </div>
        ${ipSection}
        ${err}
      </div>`;
  }).join("");
}

// ── Fetch jobs ────────────────────────────────────────────────────────────────
async function fetchJobs() {
  const token = requireAuthToken(); if (!token) return;
  const res = await fetch("/api/vm-jobs", { headers: { Authorization: `Bearer ${token}` } });
  const json = await res.json();
  renderJobs(json.jobs || []);
}

// ── Copy IP ───────────────────────────────────────────────────────────────────
function copyIp(ip, btn) {
  navigator.clipboard.writeText(ip).then(() => {
    btn.textContent = "Copied!";
    setTimeout(() => btn.textContent = "Copy", 2000);
  });
}

// ── Manually trigger IP fetch for existing job ────────────────────────────────
async function triggerFetchIp(jobId) {
  const token = requireAuthToken(); if (!token) return;
  await fetch(`/api/vm-jobs/${jobId}/fetch-ip`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  // auto-refresh will pick it up
}

// ── VM creation ───────────────────────────────────────────────────────────────
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const token = requireAuthToken(); if (!token) return;
  const data = new FormData(form);

  const payload = {
    hardware: {
      vmid:      Number(data.get("vmid")),
      name:      String(data.get("name")),
      cores:     Number(data.get("cores")),
      memory_mb: Number(data.get("memory_mb")),
      disk_gb:   Number(data.get("disk_gb")),
      storage:   String(data.get("storage")),
      bridge:    String(data.get("bridge")),
    },
    os_choice:    String(data.get("os_choice")),
    ssh_user:     String(data.get("ssh_user")),
    ssh_password: String(data.get("ssh_password")),
  };

  const btn = form.querySelector("button[type=submit]");
  btn.textContent = "Creating…";
  btn.disabled = true;

  const res = await fetch("/api/vm-jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  const json = await res.json();

  btn.textContent = "Create VM";
  btn.disabled = false;

  if (!res.ok) {
    result.style.display = "block";
    result.textContent = json.detail || JSON.stringify(json);
  } else {
    result.style.display = "none";
    await fetchJobs();
  }
});

refreshJobsBtn.addEventListener("click", fetchJobs);
logoutBtn.addEventListener("click", () => {
  localStorage.removeItem("access_token");
  window.location.href = "/login";
});

// ── Auto-refresh every 10 s so IP appears without manual action ───────────────
setInterval(fetchJobs, 10000);

// ── Boot ──────────────────────────────────────────────────────────────────────
ensureProxmoxCreds().then(ok => { if (ok) fetchMe().then(fetchJobs); });
