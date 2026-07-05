# Gate Checklists

减少"每次临场想该查什么"。三道门职责分离:**author 机械自查 → independent gate 创造性对抗 →
release 收口**。配合 [operating model](./operating-model.md)、[change-control.md](./change-control.md)
与 [mini-rfc 模板](../templates/mini-rfc.md)。

职责切分(详见 [engineering-roles.md](../reference/engineering-roles.md)):
- **Author**:负责机械自查——surface inventory、traceability、schema coverage、默认路径不回归。
- **Independent Gate**:负责创造性边界——产品语义、误导风险、架构方向、用户解释、滥用路径。
- 目标:gate **不再**人肉抓机械漏项(那些进 `task governance:check`),把判断力留给真正需要判断的地方。

---

## Author 自查(交 gate 前必须自己过)

- [ ] mini-RFC 必填小节填全(C2/C3),Surface Inventory + Traceability Matrix 完整。
- [ ] **Default Path Invariant**:有测试证明默认行为不变(快照/逐字段相等)。
- [ ] 每条设计承诺都有对应测试 + gate 探针(traceability 无空行)。
- [ ] schema / 红线覆盖:新增输出字段都分配了 policy;无 Pydantic 对象泄漏。
- [ ] 本地 `task check` REAL_EXIT=0(捕获真实退出码,不是 `| tail`)。
- [ ] 工作树只含本 slice 文件;无夹带。

## Design Gate(开码前)

打**需要判断力**的边界,不复述机械项:

- [ ] **默认行为**:这个改动会不会悄悄改变默认路径?是否被显式 opt-in 隔离?
- [ ] **边界 / 外部面**:网络/外部依赖是否只在 opt-in 后出现?失败面是否都收敛成安全产出(脱敏、不崩)?
- [ ] **用户误读**:用户可见解释会不会被读成建议/预测/执行?披露是否强制常显、贴着 claim?
      缺披露是否 **fail-closed**(宁可 omit,不裸渲 claim)?(RE3 复盘 R3)
- [ ] **载体自守红线**:新增的证据/输出载体是否在**构造点**自守红线,而不是只信上游?(RE3 复盘 R2)
- [ ] **架构方向**:是补 if 还是抽稳定接缝?依赖方向对不对(证据被拉取、不反向驱动)?
- [ ] **系统边界(G5)**:声明了归属哪个 [system](../architecture/system-map.md) 吗?复用既有 read model/command
      还是新增?是不是同一 system 第 3 次散点(该抽共享模块了)?有没有制造第二套语义?
- [ ] **cockpit 认知负荷**:新增顶级 tab 是否必要?能否并入既有面?(避免第二个杂乱 dashboard)
- [ ] **回滚**:出问题能不能干净回退?默认 Noop 是否保证零副作用回退路径?

## Implementation Gate(开码后,独立 reviewer)

- [ ] 代码**符合设计**:mini-RFC 的承诺逐条兑现,没有偷偷扩面。
- [ ] 测试**覆盖承诺**:traceability 每行都有真实测试,且测的是边界不是当前 bug。
- [ ] **没有夹带**:无设计外的行为、字段、端点、网络面。
- [ ] 复现作者的验证命令,确认 REAL_EXIT;不轻信声明(见
      [[verify-real-exit-code-not-piped-tail]] 的教训)。
- [ ] 机械可枚举项已被 `task governance:check` 覆盖的,确认它确实在跑。

## Release Gate(提交前)

- [ ] 工作树:只 stage 本 slice 文件(含 untracked 显式按文件名 add)。
- [ ] `git diff --check` 干净;`task check` REAL_EXIT=0。
- [ ] commit message 含 gate 结论 + 证据(测试数 / REAL_EXIT);按规范带 Co-Authored-By。
- [ ] **Receipt Boundary**:claim / not claimed / remaining debt 写清(对应 mini-RFC Not claimed / Debt)。
- [ ] **Merge Decision**:merge now / keep draft / split / request changes / abandon,并写明 product value、
      boundary safety、test confidence、future maintainability。

---

> 复盘触发器与铁律见 [postmortem-triggers.md](./postmortem-triggers.md):同类 blocker ≥2 次、`task check`
> 误报、默认行为被意外改变、source_refs 不可重建、红线漏面、联网进默认路径、gate 发现"设计没定义"的问题——
> 任一触发轻量复盘,产物**必须**转成文档规则 / 测试 / 脚手架 / 明确接受的债务(四选一)。
