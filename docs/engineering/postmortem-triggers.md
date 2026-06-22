# Postmortem Triggers — EOS v0.1 (G6)

复盘的目的**不是追责,是修系统和流程**(Google SRE 原则)。这里固化"**什么时候必须做轻量复盘**",
以及"复盘必须产出什么",让重复痛点变成机器护栏,而不是回到"靠人记得"。

## 何时必须做一次轻量复盘

命中任一即触发(不分大小):

- [ ] **同类 blocker ≥2 次**(同一类问题在不同 slice/载体上重复被 gate 抓到)。
- [ ] **gate 发现"设计没定义"的问题**(mini-RFC 漏掉一个本该锁的边界)。
- [ ] **机械项被 gate 抓到**(本可由 `task check`/`governance:check` 兜的,却靠人肉发现)。
- [ ] **用户可见误读面**(展示/措辞可能被读成建议/预测/执行)。
- [ ] `task check` 误报(绿了但其实坏,或红了但其实没问题)。
- [ ] **默认行为被意外改变** / **source_refs 不可重建 claim** / **红线漏一个输出面** /
      **联网或外部依赖进入默认路径**。
- [ ] **同一 system 第 3 次散点实现**(同类 read-model/renderer/route 第 3 次旁补,未抽共享模块)——
      触发"是否该深模块"复盘(见 [architecture-principles.md](./architecture-principles.md) G5 原则 3)。

## 铁律:复盘必须产出**四选一**

不接受"以后注意"。每条复盘项必须收敛成下列之一,否则复盘不算完成:

1. **规则**(写进 change-control / gate-checklists / mini-RFC)
2. **测试**(单测 / jsdom / property)
3. **脚手架**(`task governance:check` 探针 / helper)
4. **明确接受的债务**(写下来,带 owner 和触发再处理的条件)

**升级阶梯**:同类问题第 1 次 → 至少出"规则";**第 2 次出现,默认动作是"机器化"(测试或脚手架),不是继续手补。**

## 复盘模板(每条一个)

```
### <短标题>
- Trigger: 命中了上面哪个触发器
- What happened: 一两句事实(可引用 commit / gate 轮次)
- Root pattern: 不是"谁错了",是"什么系统性模式让它发生"
- Preventive change: 规则 / 测试 / 脚手架 / 接受债务(四选一,要具体到文件)
- Owner: 谁落地
- Follow-up: 是否还有下一步(没有就写 none)
```

---

## RE3 复盘(2026-06-22;commit `a46bcd8`)

RE3 是首个走完 EOS mini-RFC 全流程的 slice,三轮 gate 各抓到一类问题,值得固化。

### R1 — Default Path Invariant 只写意图,没写"现状快照事实"
- **Trigger**: gate 发现"设计没定义"。
- **What happened**: design gate 第一轮 BLOCKED —— mini-RFC 声称默认 Noop"输出逐字节一致",
  但当前代码今天就写 `research_evidence: []`;"省略空键"反而会改 content hash 触发 revision。
- **Root pattern**: 不变量用**意图**(我以为不变)而非**现状事实**(今天真实输出)表述,无法被验证。
- **Preventive change(规则)**: [mini-rfc.md](../templates/mini-rfc.md) §5 要求 Default Path Invariant
  **必须附"现状快照事实 + 锁它的快照测试"**,不接受口头"一致"。已在 RE3 落地
  `test_default_path_keeps_pre_re3_research_shape`。
- **Owner**: author(写 mini-RFC 时)。
- **Follow-up**: none。

### R2 — 新输出载体没在构造点自守红线,信了上游
- **Trigger**: 同类 blocker ≥2 次(RE2 claim 红线 → RE3 attachment 红线;输出面守门反复)。
- **What happened**: impl gate 后端第一轮 BLOCKED —— `ResearchEvidenceAttachment` 直接构造可绕过
  RE1 的 data_gaps 红线,advice 文本能经 `research_evidence_gaps` 流入 proposal。
- **Root pattern**: **每新增一个证据载体,红线都要在它的构造点重新守一次**,只信上游(RE1/RE2)不够。
- **Preventive change(规则 + 脚手架)**: [gate-checklists.md](./gate-checklists.md) Design Gate 增"新输出载体
  是否在构造点自守红线";`governance:check` 已加 attachment 红线探针
  (`tests/test_governance_invariants.py::AttachmentRedlineProbe`)。复用模式 = `__post_init__` 复用 RE1 契约。
- **Owner**: author + independent gate。
- **Follow-up(债务)**: 抽一个通用 "redline-owning carrier" helper,避免每个载体手写 `__post_init__`;
  触发条件 = 出现第 3 个证据载体时做。

### R3 — 用户可见 claim 未 fail-closed
- **Trigger**: 用户可见误读面。
- **What happened**: impl gate RE3c 第一轮 BLOCKED —— malformed/旧 receipt 缺 grade/non_claims 时,
  前端仍单独渲染历史风险 claim,丢了强制披露。
- **Root pattern**: cockpit 是**最后一道防误读面**,不能假设后端正常路径恒供披露;缺披露必须 fail-closed。
- **Preventive change(规则 + 测试)**: [gate-checklists.md](./gate-checklists.md) Design Gate 增"用户可见 claim
  缺披露是否 fail-closed";jsdom 负例已锁(缺 non_claims / 缺 grade → omit + 安全提示)。
- **Owner**: author + design gate。
- **Follow-up**: none(其他用户可见 claim 面接入时沿用此 jsdom 负例模式)。
