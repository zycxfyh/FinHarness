# Mini-RFC 模板

用于 **C2 / C3** slice(见 [change-control.md](../engineering/change-control.md))。C0/C1 不必用。
目标:让跨边界改动有**结构化历史 + 可追踪决策**,而不是只靠聊天描述。保持轻量——每节几行即可,
能回答问题比篇幅重要。

复制下面各节,填好后放进 `docs/proposals/<date>-<slug>.md`(或对应 proposal 的子节),交 design gate。
端到端推进纪律见 [Operating Model](../engineering/operating-model.md)。

---

## <Slice 名> mini-RFC

### 1. Change Class
C2 还是 C3?命中了 change-control 的哪些触发器?(一行说清为什么是这个级别。)

### 1b. Product Claim / Layer / Thin Slice
这个 PR 推进哪个用户能力?归属 L0-L8 哪一层?最小可合并切片是什么?

### 1c. Module Placement / System Boundary  (G5)
本改动扩展 [system-map](../architecture/system-map.md) 中的**哪个 system**?(跨多个则说明边界 + 依赖方向。)
是否复用该 system 既有 **read model / command / adapter**,还是新增?这是该 system 内**第几次**加同类
route/renderer/read-model——若是第 3 次,先抽共享模块(G5 原则 3)。用户可见面:是否新增顶级 cockpit tab?
为什么不能并入既有面?

### 2. Current behavior
今天系统怎么做的?默认路径产出什么?(可引用文件:line。)

### 3. Target behavior
改完之后怎么做?**默认路径**和 **opt-in 路径**分别是什么?

### 4. Surface Inventory
- **输入**:
- **输出**:
- **外部调用 / 网络面**:
- **失败面**:
- **用户可见面**:
- **排除面(明确不碰的)**:

### 5. Default Path Invariant
默认行为是否**完全不变**?先写下**现状事实**(今天默认路径真实输出/shape,可引用文件:line),
而不是"我以为不变"的意图——再说明用哪个**快照/逐字段相等测试**锁住它。若默认行为会变,谁批准、影响谁?
> 规则来自 RE3 复盘 R1(见 [postmortem-triggers.md](../engineering/postmortem-triggers.md)):
> 不接受口头"一致";不变量必须可被一个快照测试验证。

### 6. Traceability Matrix
| 设计承诺 | 计划代码点 | 测试 | gate 探针 |
| --- | --- | --- | --- |
| | | | |

### 7. Test / Gate Plan
- 哪些进 `task check` / `task governance:check`?
- design gate 看什么、implementation gate 看什么、需不需要 independent / red-team gate?
- capability-specific verification matrix 覆盖哪些层:unit / integration / contract / boundary / migration /
  data quality / agent / frontend / security?

### 8. Product Surface Review
用户完成后多看见、比较、验证、理解、复盘了什么?如果答案只是多一个 receipt/gate/non-claim,为什么仍值得合并?

### 9. Not claimed / Debt
这个 slice **不**主张什么?留了哪些已知债务(明确接受,不是遗漏)?后续哪个 slice 还。

### 10. Release Decision
合并前填写:merge now / keep draft / split PR / request changes / abandon。理由覆盖 product value、
boundary safety、test confidence、future maintainability。

---

> 写完自检:第 5 节能不能用一个测试证明?第 4 节的"失败面"和"用户可见面"是不是都进了第 6 节的探针?
> 如果不能,说明边界还没想清楚,先别开码。
