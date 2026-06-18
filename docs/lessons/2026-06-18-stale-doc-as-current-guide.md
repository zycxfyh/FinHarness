# Lesson: 把过期文档当成现行指南

Date: 2026-06-18
Status: active
Source reviews: 本次方向讨论 + 工作区审查(2026-06-18);提交 629f4bd
Source ideas: operator 对 B1-B5 作为"存在理由"的质疑
Affected modules: AI 协作流程(非代码);docs 方向源治理

## Lesson

在长会话里,AI 脑中对某个文件内容的印象会和磁盘上的实际内容脱节——尤其当
operator 在并行提交、或一份文档刚被更新的文档取代时。回答"现在的方向/状态是
什么",必须先按修改时间或提交时间把文档排序、读最新的几份,并查 `git status` /
`git log` 有无并行改动,而不是凭会话早期建立的印象。

## Why It Matters

这次连犯两次同类错:

```text
1. 把 2026-06-12 / 06-13 的 Target-State-B 文档当成现行产品方向,
   而 docs/product-north-star.md(2026-06-17,已锁定)早已在产品方向上
   取代它们——是 operator 提醒"看最近文档"才翻出来的。
2. 把"给那两份旧文档加 supersession 指针"当成待办推给 operator,
   而 operator 已在提交 629f4bd 里做完,且结果干净。
```

两次根因相同:用过期的脑内模型当 ground truth。后果有两类——**断错**(说旧文档
是现行纲领),和**做重复/多余的工**(去加已经存在的指针)。

## Evidence

```text
- 会话早期读 06-13 ADR 时是 "Status: accepted"、Links 把 06-12 think 标为
  "(governing)";现盘上是 "Status: superseded for product direction" +
  "Supersession Note (2026-06-18)",由提交 629f4bd(07:02,本次讨论之后)写入。
- find docs -name '*.md' -printf '%T+ %p' | sort 一眼即可看出
  product-north-star.md(06-17)、controlled-vocabulary ADR(06-18)
  才是最新的方向源。
- B4(见 docs/reference/glossary.md)被重新定性为长期学习机制,
  不是项目存在理由;产品 B 是 B0(个人财务态势感知)。
```

## Rule / Heuristic

```text
- 回答"现行方向/状态"前:先 ls -t 或 find -printf 按时间排,读最新;
  再 git log / git status 看有无并行改动。
- 断言某文件内容、或判断某改动"还没做"之前:重读该文件的当前版本。
- 长会话中,把"我以为这个文件是这样"当作待核实假设,不是事实。
```

## Where It Should Live

AGENTS.md(AI 协作约定)中的一条 checklist;并已存入 Claude 跨会话记忆
`reread-current-state-before-asserting`。
