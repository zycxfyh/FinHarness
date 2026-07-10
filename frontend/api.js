// FinHarness Cockpit — API helper namespace.

(() => {

async function apiGet(path) {
  const response = await fetch(path, { headers: { accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function apiPost(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      accept: "application/json",
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail ? JSON.stringify(body.detail) : response.statusText;
    throw new Error(`${response.status} ${detail}`);
  }
  return body;
}

async function apiPatch(path, payload) {
  const response = await fetch(path, {
    method: "PATCH",
    headers: {
      accept: "application/json",
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail ? JSON.stringify(body.detail) : response.statusText;
    throw new Error(`${response.status} ${detail}`);
  }
  return body;
}

window.FinHarness = window.FinHarness || {};
window.FinHarness.api = Object.freeze({ apiGet, apiPost, apiPatch });
})();
