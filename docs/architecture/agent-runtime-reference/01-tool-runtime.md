# 01 Tool Runtime

Hermes 的关键经验不是“工具很多”,而是工具进入模型前已经经过一条运行时链:

```text
tool definition -> registry -> toolset/profile selection -> availability check
-> optional schema patch -> model-visible schema -> tool call -> dispatch
-> handler -> structured result/error
```

这个形状适合 FinHarness,因为 Agent 工具不是普通 helper function。它们会影响用户如何理解资本状态、proposal、receipt 和审查边界。

## Hermes Pattern

Hermes 把每个工具包装成带 metadata 的 entry,而不是只暴露函数名。典型字段包括:

- `name`
- `toolset`
- `schema`
- `handler`
- `check_fn`
- `requires_env`
- `is_async`
- `description`
- `max_result_size_chars`
- `dynamic_schema_overrides`

这样工具运行时可以回答:

- 这个工具属于哪个能力集合?
- 当前环境是否可用?
- 是否需要隐藏、降级或修改 schema?
- 结果过大时如何裁剪?
- 出错时如何返回结构化错误?
- 调用者是否看见了真实的可用工具,而不是文档里的理想工具?

## FinHarness Mapping

FinHarness 的 Agent 工具已经开始走向 `AgentToolEntry` 风格:

| Field | Purpose |
| --- | --- |
| `name` | 稳定工具名,用于 profile、tests、agent description |
| `capability` | 例如 read/explain/propose/review-note/simulate |
| `profile_names` | 哪些 Agent profile 可见 |
| `mutating` | 是否写入 state/receipt/proposal |
| `receipt_required` | 写入或重要读模型是否必须有 receipt/context ref |
| `execution_allowed` | 对 FinHarness Agent 当前应始终 fail closed |
| `check_fn` | 环境、路径、数据、policy 可用性检查 |
| `description` | 给模型和人类的边界说明 |
| `max_result_size_chars` | 防止工具结果吞掉 prompt budget |

当前 Agent 工具边界仍应保持保守:

- default profile: read/explain/context first;
- review-draft style profile: only append-only governed proposal drafts;
- no profile exposes approval, attestation, broker order, fund transfer, receipt rewrite,
  or execution authority.

## Runtime Rules

1. Tool visibility is capability selection, not permission bypass.
2. Availability checks must fail closed for writes.
3. Governance primitives cannot be shadowed by plugin or user-defined tool names.
4. Agent-facing tool descriptions must match the active profile.
5. Tool errors should be structured and reviewable, not hidden in prose.

## Do Now

- Keep `AgentToolEntry` as the local source for tool metadata: capability,
  toolset, side-effect, availability check, and non-authority claims.
- Prefer tests that prove visible tools match the selected profile.
- Keep generated tool docs close to the registry, not manually duplicated in many docs.

## Later

- Add richer dynamic availability checks when tools depend on optional provider
  credentials, policy toggles, or runtime control-plane state.
- Add bounded result wrappers for larger context-pack tools.
- Add machine-readable guardrail metadata to each tool entry.

## Not Now

- Do not auto-discover arbitrary plugins into Agent authority.
- Do not expose execution or broker-write tools.
- Do not treat tool registry presence as proof that the tool is safe to show.
