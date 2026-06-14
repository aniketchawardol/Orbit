// Tiny fetch wrapper: same-origin /api, session cookies, CSRF.

function getCookie(name) {
  const m = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
  return m ? decodeURIComponent(m[2]) : null;
}

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// Build an Error that also carries the HTTP status and parsed JSON body, so
// callers can branch on e.status / read structured fields (e.g. e.data.warnings)
// while existing code keeps using e.message.
function httpError(data, status) {
  const err = new Error(data?.detail || `Request failed (${status})`);
  err.status = status;
  err.data = data;
  return err;
}

async function request(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (method !== "GET") headers["X-CSRFToken"] = getCookie("csrftoken") || "";

  // For GET requests, retry a few times with exponential backoff in case the
  // backend is still starting up (useful on container boot).
  if (method === "GET") {
    const maxAttempts = 6;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        const res = await fetch(`/api${path}`, {
          method,
          headers,
          credentials: "same-origin",
        });
        if (res.status >= 500) {
          // Server error — retry
          if (attempt < maxAttempts) await sleep(200 * Math.pow(2, attempt));
          else {
            const data = await res.json().catch(() => null);
            throw httpError(data, res.status);
          }
          continue;
        }
        if (res.status === 204) return null;
        const data = await res.json().catch(() => null);
        if (!res.ok) {
          throw httpError(data, res.status);
        }
        return data;
      } catch (err) {
        // Network error or other failure — retry
        if (attempt < maxAttempts) {
          await sleep(200 * Math.pow(2, attempt));
          continue;
        }
        throw err;
      }
    }
  }

  // Non-GET requests: single attempt
  const headers2 = { "Content-Type": "application/json" };
  if (method !== "GET") headers2["X-CSRFToken"] = getCookie("csrftoken") || "";
  const res = await fetch(`/api${path}`, {
    method,
    headers: headers2,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw httpError(data, res.status);
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
    throw httpError(data, res.status);
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
