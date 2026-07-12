// FinHarness Cockpit — API helper namespace.

(() => {

class ApiError extends Error {
  constructor({ status, detail, traceId }) {
    const message = typeof detail === "string" ? detail : JSON.stringify(detail || "Request failed");
    super(`${status} ${message} (trace: ${traceId || "unavailable"})`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.traceId = traceId || null;
  }
}

async function responseBody(response) {
  return response.json().catch(() => ({}));
}

function apiError(response, body) {
  return new ApiError({
    status: response.status,
    detail: body.detail || response.statusText,
    traceId: response.headers.get("x-finharness-trace-id"),
  });
}

async function apiGet(path) {
  const response = await fetch(path, { headers: { accept: "application/json" } });
  const body = await responseBody(response);
  if (!response.ok) {
    throw apiError(response, body);
  }
  return body;
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
  const body = await responseBody(response);
  if (!response.ok) {
    throw apiError(response, body);
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
  const body = await responseBody(response);
  if (!response.ok) {
    throw apiError(response, body);
  }
  return body;
}

window.FinHarness = window.FinHarness || {};
window.FinHarness.api = Object.freeze({ ApiError, apiGet, apiPost, apiPatch });
})();
