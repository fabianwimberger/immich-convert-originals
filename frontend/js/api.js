/** Thin fetch wrapper for the backend API. */
async function _handle(res, path, method) {
  if (!res.ok) {
    let detail = `${method} ${path} failed: ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch (_) {
      // response body wasn't JSON; keep the generic message
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

const api = {
  async get(path) {
    const res = await fetch(`/api${path}`);
    return _handle(res, path, "GET");
  },

  async put(path, body) {
    const res = await fetch(`/api${path}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return _handle(res, path, "PUT");
  },

  async post(path, body) {
    const res = await fetch(`/api${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return _handle(res, path, "POST");
  },

  async del(path) {
    const res = await fetch(`/api${path}`, { method: "DELETE" });
    return _handle(res, path, "DELETE");
  },
};
