# Mini-RFC 模板

用于 **C2 / C3** slice(见 [change-control.md](../engineering/change-control.md))。C0/C1 不必用。
目标:让跨边界改动有**结构化历史 + 可追踪决策**,而不是只靠聊天描述。保持轻量——每节几行即可,
能回答问题比篇幅重要。

复制下面 8 节,填好后放进 `docs/proposals/<date>-<slug>.md`(或对应 proposal 的子节),交 design gate。

---

## <Slice 名> mini-RFC

### 1. Change Class
C2 还是 C3?命中了 change-control 的哪些触发器?(一行说清为什么是这个级别。)

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
默认行为是否**完全不变**?如何证明(快照/逐字段相等测试)?若默认行为会变,谁批准、影响谁?

### 6. Traceability Matrix
| 设计承诺 | 计划代码点 | 测试 | gate 探针 |
| --- | --- | --- | --- |
| | | | |

### 7. Test / Gate Plan
- 哪些进 `task check` / `task governance:check`?
- design gate 看什么、implementation gate 看什么、需不需要 independent / red-team gate?

### 8. Not claimed / Debt
这个 slice **不**主张什么?留了哪些已知债务(明确接受,不是遗漏)?后续哪个 slice 还。

---

> 写完自检:第 5 节能不能用一个测试证明?第 4 节的"失败面"和"用户可见面"是不是都进了第 6 节的探针?
> 如果不能,说明边界还没想清楚,先别开码。
