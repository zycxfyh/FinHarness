// FinHarness Cockpit — governed write-action shell.
"use strict";

(() => {
window.FinHarness = window.FinHarness || {};

const ReviewActionShell = Object.freeze({
  /**
   * Submit a governed review write and reject any response that does not
   * explicitly preserve the execution boundary.
   */
  async submit(method, endpoint, payload) {
    const normalizedMethod = String(method).toUpperCase();
    const request = {
      POST: window.FinHarness.api.apiPost,
      PATCH: window.FinHarness.api.apiPatch,
    }[normalizedMethod];
    if (!request) {
      throw new Error(`Unsupported governed write method: ${normalizedMethod}`);
    }

    const start = performance.now();
    try {
      const body = await request(endpoint, payload);
      if (body.execution_allowed !== false) {
        throw new Error("Governed write returned unexpected execution_allowed");
      }
      console.debug("ReviewActionShell: write completed", {
        endpoint,
        method: normalizedMethod,
        duration_ms: Math.round(performance.now() - start),
      });
      return body;
    } catch (error) {
      console.error("ReviewActionShell: write failed", {
        endpoint,
        method: normalizedMethod,
        error: error.message,
      });
      throw error;
    }
  },

  post(endpoint, payload) {
    return ReviewActionShell.submit("POST", endpoint, payload);
  },

  patch(endpoint, payload) {
    return ReviewActionShell.submit("PATCH", endpoint, payload);
  },
});

window.FinHarness.ReviewActionShell = ReviewActionShell;
})();
