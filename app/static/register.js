const registerForm = document.getElementById("register-form");
const result = document.getElementById("result");

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(registerForm);
  const body = {
    username: String(data.get("username")),
    password: String(data.get("password")),
  };

  const response = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await response.json();
  result.textContent = JSON.stringify(json, null, 2);
  if (response.ok) {
    setTimeout(() => {
      window.location.href = "/login";
    }, 800);
  }
});
