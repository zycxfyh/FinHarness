// FinHarness Cockpit — governed write-action shell.
"use strict";

(() => {
window.FinHarness = window.FinHarness || {};

const ReviewActionShell = Object.freeze({
  /**
   * Submit a governed review write and acknowledge its persistent
   * mutation attempt only after the response preserves the
   * execution boundary.
   */
  async submit(method, endpoint, payload) {
    const normalizedMethod =
      String(method).toUpperCase();
    if (
      !["POST", "PATCH"].includes(normalizedMethod)
    ) {
      throw new Error(
        `Unsupported governed write method: ${normalizedMethod}`,
      );
    }

    const start = performance.now();
    try {
      const response =
        await window.FinHarness.api.apiMutation(
          normalizedMethod,
          endpoint,
          payload,
        );
      const body = response.body;

      if (body.execution_allowed !== false) {
        throw new Error(
          "Governed write returned unexpected execution_allowed",
        );
      }

      response.acknowledge();

      console.debug(
        "ReviewActionShell: write completed",
        {
          endpoint,
          method: normalizedMethod,
          replayed: response.replayed,
          identity_receipt_id:
            response.identityReceiptId,
          duration_ms: Math.round(
            performance.now() - start,
          ),
        },
      );
      return body;
    } catch (error) {
      console.error(
        "ReviewActionShell: write failed",
        {
          endpoint,
          method: normalizedMethod,
          attempt_retained:
            error.attemptRetained === true,
          error: error.message,
        },
      );
      throw error;
    }
  },

  post(endpoint, payload) {
    return ReviewActionShell.submit(
      "POST",
      endpoint,
      payload,
    );
  },

  patch(endpoint, payload) {
    return ReviewActionShell.submit(
      "PATCH",
      endpoint,
      payload,
    );
  },
});

window.FinHarness.ReviewActionShell =
  ReviewActionShell;
})();
