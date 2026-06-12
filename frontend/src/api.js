// Tiny fetch wrapper: same-origin /api, session cookies, CSRF.

function getCookie(name) {
  const m = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
  return m ? decodeURIComponent(m[2]) : null;
}

async function request(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (method !== "GET") headers["X-CSRFToken"] = getCookie("csrftoken") || "";
  const res = await fetch(`/api${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(data?.detail || `Request failed (${res.status})`);
  }
  return data;
}

async function requestForm(path, formData) {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "X-CSRFToken": getCookie("csrftoken") || "" },
    credentials: "same-origin",
    body: formData, // browser sets multipart boundary
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(data?.detail || `Request failed (${res.status})`);
  }
  return data;
}

export const api = {
  get: (p) => request(p),
  post: (p, body = {}) => request(p, { method: "POST", body }),
  postForm: (p, formData) => requestForm(p, formData),
  patch: (p, body = {}) => request(p, { method: "PATCH", body }),
  del: (p) => request(p, { method: "DELETE" }),
};
