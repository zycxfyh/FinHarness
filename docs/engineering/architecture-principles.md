# Architecture Principles — EOS G5

状态:v0(2026-06-22)。EOS 的"方向盘和车架":[change-control](./change-control.md) 管"怎么安全变更",
本文件管"**代码该长在哪个 system、模块接口是什么**"。配合 [system-map.md](../architecture/system-map.md)。

定位修正(为什么写这个):早期保守、小 slice、独立 gate 把阶段 1–4 的危险面稳住了——这是**好的保守**
(财务/投资/写入/联网/证据语义必须 gate)。但继续"每个功能一个 mini-RFC + 一个 route + 一个前端块"散着长,会变成
"很多安全小块"而非"几个深模块"——这是**坏的保守**。本文件保留前者,减少后者:**从 slice-first 转向 system-first**。

## 原则

1. **最小可审计边界,不是最小 diff**(承自 change-control)。
   一个 300 行内聚子系统若比 6 个 50 行旁补更可审计/可回滚,就选子系统。判据是边界/默认行为/回滚/测试是否清晰,不是行数。

2. **每个 C2/C3 必须先选归属 system**。
   mini-RFC 增设 **Module Placement** 节:声明扩展 [system-map](../architecture/system-map.md) 中的哪个 system;
   跨多个则说明边界与依赖方向。无归属 = 设计没想清,先别开码。

3. **第 3 次重复 → 抽共享模块**。
   同一 system 内第 3 次散点加同类 route/renderer/read-model,**必须**先抽该 system 的共享接口
   (read model / command / adapter),再实现本次。前两次可旁补,第三次是信号。

4. **系统形状固定**:domain model / read model / command(write)model / adapters / tests。
   - read model:给 API/frontend 消费的**只读形状**,集中而非每个 route 内联拼。
   - command model:写入统一走 governed command + receipt(唯一 id → receipt → DB,失败清理)。
   - adapters:API/CLI/frontend 只是适配器,不放业务不变量。

5. **用户可见面不无限加顶级 tab**。
   新 cockpit view 先问信息架构:它属于哪个 system 的 read model?能否并入既有面?会不会增加认知负荷?
   宁可深化一个面,不要长成一排浅 tab(避免"第二个杂乱 dashboard")。

6. **gate 对象从"单个补丁"升级为"模块边界"**。
   design gate 除问风险面,还问:这是哪个 system?是否复用既有 read model?是否增加 cockpit 认知负荷?
   是否制造第二套语义(同一概念在不同上下文被重新定义)?(见 [gate-checklists](./gate-checklists.md))

7. **modular monolith,不微服务**。
   边界靠清晰接口,不靠拆进程。不为"强边界"引入分布式复杂度。

## 与既有 EOS 的关系
- change-control(C0–C3)不变;mini-RFC **新增 Module Placement 节**(模板已更新)。
- 重复风险继续进 `task governance:check`;**架构性重复**(散点 read-model/renderer)由本文件原则 3 拦,gate 人审。
- 复盘触发器([postmortem-triggers](./postmortem-triggers.md))新增一条:**同一 system 第 3 次散点实现**也触发"是否该深模块"复盘。

## 首个试点:Review System
R2/R3/R4 都属 Review System。落地顺序:**先抽它的统一 read model(timeline/retrospective/compare-marks)+
shared test fixtures,再实现 Compare**——见 R4 mini-RFC 的 Module Placement 节。这样 R4 不是散点功能,是 system 的自然扩展。
