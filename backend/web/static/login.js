const loginForm = document.getElementById("login-form");
const result = document.getElementById("result");

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(loginForm);
  const body = new URLSearchParams();
  body.append("username", String(data.get("username")));
  body.append("password", String(data.get("password")));

  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  const json = await response.json();
  result.textContent = JSON.stringify(json, null, 2);
  if (response.ok) {
    localStorage.setItem("access_token", json.access_token);
    const statusResp = await fetch("/api/proxmox/creds/status", {
      headers: { Authorization: `Bearer ${json.access_token}` },
    });
    const statusJson = await statusResp.json().catch(() => ({}));
    if (statusJson.has_creds) {
      window.location.href = "/app";
    } else {
      window.location.href = "/creds";
    }
  }
});

