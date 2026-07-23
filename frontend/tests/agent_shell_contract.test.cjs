const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const html = fs.readFileSync(path.join(root, "frontend-agent/index.html"), "utf8");
const js = fs.readFileSync(path.join(root, "frontend-agent/app.js"), "utf8");

assert.match(html, /FinHarness Agent/);
assert.match(html, /live_execution_allowed=false/);
assert.match(html, /Structured paper Effect/);
assert.doesNotMatch(html, /API Key|api[_ -]?key|secret/i);

assert.match(js, /\/agent\/bootstrap/);
assert.match(js, /\/agent\/missions/);
assert.match(js, /paper-effects/);
assert.match(js, /Idempotency-Key/);
assert.match(js, /X-FinHarness-Browser-Mutation-Binding/);
assert.doesNotMatch(js, /executable\s*:/);
assert.doesNotMatch(js, /environment\s*:/);
assert.doesNotMatch(js, /OPENAI_API_KEY|api[_ -]?key/i);

console.log("agent shell frontend contract: ok");
