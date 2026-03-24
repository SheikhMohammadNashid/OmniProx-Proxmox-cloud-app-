const form = document.getElementById("vm-form");
const result = document.getElementById("result");
const jobsOutput = document.getElementById("jobs-output");
const refreshJobsBtn = document.getElementById("refresh-jobs");
const userMeta = document.getElementById("user-meta");
const logoutBtn = document.getElementById("logout-btn");

function getToken() {
  return localStorage.getItem("access_token");
}

function requireAuthToken() {
  const token = getToken();
  if (!token) {
    window.location.href = "/login";
    return null;
  }
  return token;
}

async function fetchMe() {
  const token = requireAuthToken();
  if (!token) return;
  const response = await fetch("/api/auth/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    localStorage.removeItem("access_token");
    window.location.href = "/login";
    return;
  }
  const me = await response.json();
  userMeta.textContent = `${me.username} (${me.role}) quota:${me.daily_quota}/day`;
}

async function fetchJobs() {
  const token = requireAuthToken();
  if (!token) return;
  const response = await fetch("/api/vm-jobs", {
    headers: { Authorization: `Bearer ${token}` },
  });
  const json = await response.json();
  jobsOutput.textContent = JSON.stringify(json, null, 2);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = requireAuthToken();
  if (!token) return;

  const data = new FormData(form);
  const payload = {
    hardware: {
      vmid: Number(data.get("vmid")),
      name: String(data.get("name")),
      cores: Number(data.get("cores")),
      memory_mb: Number(data.get("memory_mb")),
      disk_gb: Number(data.get("disk_gb")),
      storage: String(data.get("storage")),
      bridge: String(data.get("bridge")),
    },
    os_choice: String(data.get("os_choice")),
  };

  const response = await fetch("/api/vm-jobs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  const json = await response.json();
  result.textContent = JSON.stringify(json, null, 2);
  await fetchJobs();
});

refreshJobsBtn.addEventListener("click", fetchJobs);
logoutBtn.addEventListener("click", () => {
  localStorage.removeItem("access_token");
  window.location.href = "/login";
});

fetchMe();
fetchJobs();
