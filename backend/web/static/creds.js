const form = document.getElementById("proxmox-creds-form");
const result = document.getElementById("result");

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

function setCheckbox(checkboxId, value) {
  const el = document.getElementById(checkboxId);
  el.checked = Boolean(value);
}

async function loadExistingCreds() {
  const token = requireAuthToken();
  if (!token) return;

  const response = await fetch("/api/proxmox/creds", {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    localStorage.removeItem("access_token");
    window.location.href = "/login";
    return;
  }

  const json = await response.json();

  const baseUrlInput = form.elements["base_url"];
  const nodeInput = form.elements["node"];
  const tokenIdInput = form.elements["token_id"];

  if (json.base_url) baseUrlInput.value = json.base_url;
  if (json.node) nodeInput.value = json.node;
  if (json.token_id) tokenIdInput.value = json.token_id;

  setCheckbox("verify_ssl", json.verify_ssl);
  setCheckbox("dry_run", json.dry_run);

  // Never auto-fill token secret.
  form.elements["token_secret"].value = "";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  result.textContent = "";

  const token = requireAuthToken();
  if (!token) return;

  const body = {
    base_url: String(form.elements["base_url"].value),
    node: String(form.elements["node"].value),
    token_id: String(form.elements["token_id"].value),
    token_secret: String(form.elements["token_secret"].value),
    verify_ssl: Boolean(document.getElementById("verify_ssl").checked),
    dry_run: Boolean(document.getElementById("dry_run").checked),
  };

  const response = await fetch("/api/proxmox/creds", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });

  const json = await response.json().catch(() => ({}));
  result.textContent = JSON.stringify(json, null, 2);

  if (response.ok) {
    window.location.href = "/app";
  }
});

loadExistingCreds();

