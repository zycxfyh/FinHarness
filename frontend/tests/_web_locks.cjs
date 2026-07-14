"use strict";

function createSerialLockManager() {
  let tail = Promise.resolve();

  return {
    request(name, options, callback) {
      let operation = callback;
      let lockOptions = options;

      if (typeof options === "function") {
        operation = options;
        lockOptions = {};
      }

      const run = tail.then(() =>
        operation({
          name,
          mode:
            (lockOptions && lockOptions.mode) ||
            "exclusive",
        }),
      );

      tail = run.catch(() => {});
      return run;
    },
  };
}

function installWebLocks(
  window,
  manager = createSerialLockManager(),
) {
  Object.defineProperty(
    window.navigator,
    "locks",
    {
      configurable: true,
      value: manager,
    },
  );
  return manager;
}

function createSharedStorage() {
  const values = new Map();
  let removeFailure = null;

  return {
    get length() {
      return values.size;
    },

    key(index) {
      return [...values.keys()][index] || null;
    },

    getItem(key) {
      const normalized = String(key);
      return values.has(normalized)
        ? values.get(normalized)
        : null;
    },

    setItem(key, value) {
      values.set(
        String(key),
        String(value),
      );
    },

    removeItem(key) {
      if (removeFailure) {
        const error = removeFailure;
        removeFailure = null;
        throw error;
      }
      values.delete(String(key));
    },

    clear() {
      values.clear();
    },

    failNextRemove(error) {
      removeFailure = error;
    },
  };
}

function installSharedStorage(window, storage) {
  Object.defineProperty(
    window,
    "localStorage",
    {
      configurable: true,
      value: storage,
    },
  );
}

module.exports = {
  createSerialLockManager,
  createSharedStorage,
  installSharedStorage,
  installWebLocks,
};
