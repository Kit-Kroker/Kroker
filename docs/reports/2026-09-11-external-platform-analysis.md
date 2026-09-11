# External platform analysis — 2026-09-11 (third source, verbatim)

| | |
|---|---|
| Status | Verbatim record, **never edited after it lands**. Input, not scope: nothing here is committed work until the user admits it (the register's rule) |
| Source | A third-party analysis of Kroker (a ChatGPT conversation), supplied by the user on 2026-09-11, in Russian. Everything below the rule is reproduced byte-for-byte from the capture; only line endings are normalized to LF |
| Assessed in | [`external-ideas-2026-09.md`](external-ideas-2026-09.md) §H (verdict per candidate, verified against `main`); design `docs/superpowers/specs/2026-09-11-roadmap-platform-analysis-design.md` |

---

Да. Если собрать всё, что мы разобрали, я бы видел Kroker не просто как orchestration layer для coding agents, а как **платформу для конструирования, запуска и измерения agentic software delivery workflows**.

Сейчас фундамент уже довольно сильный. Главный следующий шаг — сделать систему **programmable, observable и experimentally optimizable**.

## Что уже хорошо есть

[Kroker на GitHub](https://github.com/Kit-Kroker/Kroker)

### Архитектурный фундамент

```text
Idea / Spec
    ↓
Planning
    ↓
Dev Tasks
    ↓
Agent + Harness
    ↓
QA / Review
    ↓
Repair
    ↓
Merge Gate
    ↓
Deploy
    ↓
Retro / Memory
```

При этом есть:

* Temporal orchestration
* isolated git worktrees
* Claude Code / OpenCode / Cursor harnesses
* agent registry
* роли и разные model families
* frozen Validation Contract
* deterministic checks
* QA/reviewer в clean context
* bounded repair loops
* gates и human approval
* artifacts/provenance
* memory
* cost/token telemetry
* benchmarks
* board/TUI/dashboard
* security/containment primitives

То есть **базовая платформа уже существует**.

---

# Что я бы добавил

Я бы разделил roadmap на **7 крупных направлений**.

---

## 1. 🟢 Visual Workflow Builder — самая очевидная большая фича

Это то, о чём ты изначально спрашивал.

Не просто dashboard, а настоящий:

> **"Figma для agent workflows"**

Например:

```text
┌─────────┐
│  Idea   │
└────┬────┘
     ↓
┌──────────┐
│ Planner  │
└────┬─────┘
     ↓
 ┌───┴────┐
 ↓        ↓
Backend  Frontend
Agent     Agent
 ↓        ↓
 QA       QA
 └───┬────┘
     ↓
┌──────────┐
│ Security │
└────┬─────┘
     ↓
┌──────────┐
│  Human   │
│ Approval │
└────┬─────┘
     ↓
   Merge
```

Node types:

* Agent
* Coding Agent
* Researcher
* Reviewer
* QA
* Gate
* Human approval
* Condition
* Parallel
* Merge
* Retry
* Tool
* Subflow
* Deploy
* Benchmark

### И главное:

GUI **не должен быть отдельной логикой**.

```text
GUI
 ↓
FlowSpec
 ↓
Validator
 ↓
Temporal Compiler
 ↓
Runtime
```

Тогда тот же workflow можно:

```text
GUI
YAML
CLI
API
```

запустить одинаково.

**Приоритет: 🔥🔥🔥🔥🔥**

---

# 2. 🟢 Workflow-as-Code / FlowSpec

Это фундамент для предыдущего пункта.

Сейчас `FeatureWorkflow` слишком сильно является конкретной реализацией.

Я бы ввёл:

```text
FlowSpec
```

например:

```yaml
name: secure-feature

nodes:

  - id: plan
    type: agent
    role: planner

  - id: implementation
    type: agent
    role: developer

  - id: security
    type: agent
    role: adversarial-reviewer

  - id: qa
    type: gate
    checks:
      - pytest
      - security

edges:
  - from: plan
    to: implementation

  - from: implementation
    to: security

  - from: security
    to: qa
```

И дальше:

```text
FlowSpec
   ↓
validate
   ↓
compile
   ↓
Temporal
```

Это превращает Kroker из:

> "системы с одним основным SDLC workflow"

в:

> **workflow platform**.

**Приоритет: 🔥🔥🔥🔥🔥**

---

# 3. 🟢 Benchmark Lab

Вот здесь я бы сильно усилил существующую систему.

Сейчас есть instrumentation и benchmark primitives.

Следующий уровень:

> **Experiment = first-class object**

Например:

```text
Experiment #42

Dataset:
  100 feature specs

Workflow:
  secure-feature-v3

Variables:
  Model:
    Claude
    GPT
    GLM

  Developer:
    OpenCode
    Claude Code

  QA:
    Model A
    Model B
```

Kroker сам запускает матрицу:

```text
             Claude    GPT    GLM
OpenCode       100     100    100
Claude Code    100     100    100
```

И собирает:

```text
correctness
success rate
repair count
cost
latency
token usage
security failures
test failures
human interventions
```

---

## А потом — настоящий comparison

Например:

```text
                    Claude    GLM

Success              91%      84%
Avg repair            0.8      1.9
Cost                  $1.8     $0.7
Latency              16m      11m
Security failures     2%       7%
Human intervention    4%      11%
```

И главное — **Pareto frontier**:

```text
quality
  ↑
  │                ●
  │          ●
  │      ●
  │   ●
  │ ●
  └──────────────────→ cost
```

Это уже настоящий **Agent Evaluation Lab**.

**Приоритет: 🔥🔥🔥🔥🔥**

---

# 4. 🟡 Evaluation Contracts должны стать отдельным продуктом

Это одна из самых сильных идей Kroker, и я бы её развил.

Сейчас:

```text
Planner
   ↓
Validation Contract
   ↓
Developer
```

Я бы сделал отдельный UI:

```text
Feature specification

Acceptance criteria
────────────────────────

☑ POST /users returns 201
☑ invalid password → 401
☑ password never logged
☑ migration is reversible

Validation
────────────────────────

pytest tests/auth
ruff
mypy
semgrep
coverage > 80%
```

Причём Kroker должен показывать:

```text
Criterion #3
   ↓
Task T7
   ↓
Files
   ↓
Tests
   ↓
Evidence
   ↓
PASS
```

Это даёт **traceability matrix**:

```text
Requirement
     ↓
Acceptance Criterion
     ↓
Task
     ↓
Code
     ↓
Test
     ↓
Evidence
```

Это очень сильная enterprise-фича.

**Приоритет: 🔥🔥🔥🔥**

---

# 5. 🟡 Observability / Replay

У Kroker уже есть provenance, artifacts и Temporal history.

Я бы сделал поверх этого:

## Run Replay

Пользователь открывает:

```text
Run #1832
```

и видит timeline:

```text
12:03  Intake             ✓
12:05  Architecture       ✓
12:08  Planning           ✓
12:14  Backend Agent      ✓
12:31  QA                 ✗
12:33  Repair #1          ✓
12:45  Security           ✗
12:48  Repair #2          ✓
13:02  Merge Gate         ✓
13:04  Deploy             ✓
```

И может открыть каждую ноду:

```text
Agent
─────────────────
Model: ...
Tokens: ...
Cost: $0.34
Duration: 8m 21s

Input
Output
Tools
Diff
Tests
Evidence
```

Это было бы очень полезно для debugging agent workflows.

---

# 6. 🟡 Workflow simulation / dry-run

Перед тем как запускать дорогой workflow:

```text
▶ Simulate
```

Kroker проверяет:

```text
✓ DAG valid
✓ no cycles
✓ all roles exist
✓ all harnesses available
✓ validation contract executable
✓ gates reachable
✓ no impossible dependencies
✓ budget estimate available
```

И показывает:

```text
Estimated:

Tasks:        17
Agent calls:  31
Max parallel: 4
Estimated cost: $8–14
Estimated time: 25–45 min
Human gates: 2
```

Особенно важно для visual builder.

---

# 7. 🟡 Subflows

Когда появится FlowSpec, очень быстро понадобится:

```text
Security Review
```

как reusable component.

Например:

```text
Main Flow
    │
    ├── implementation
    │
    ├── security-review ← subflow
    │
    └── merge
```

А subflow:

```text
Security Review
   ├── SAST
   ├── dependency scan
   ├── threat model
   ├── adversarial agent
   └── security gate
```

Тогда появляется **workflow marketplace/library** внутри проекта.

---

# 8. 🟠 Policy Engine

Ещё один очень естественный следующий слой.

Например:

```yaml
policy:
  production:
    require:
      - reviewer
      - security_scan
      - human_approval

  high_risk:
    require:
      - adversarial_review
      - two_person_approval
```

То есть workflow говорит:

```text
deploy
```

а policy engine решает:

```text
Можно ли?
```

Это позволит отделить:

```text
Workflow
```

от:

```text
Governance
```

что для enterprise очень важно.

---

# 9. 🟠 Cost / Budget Optimizer

Kroker уже знает стоимость и budget.

Следующий шаг:

> **автоматически выбирать execution strategy.**

Например:

```text
Simple task
→ cheap model

Complex architecture
→ frontier model

Security
→ expensive adversarial model

Retry
→ cheaper model first
```

Можно получить:

```text
Task complexity
       ↓
Model Router
       ↓
┌──────┼──────┐
↓      ↓      ↓
cheap  medium frontier
```

И benchmark определяет, действительно ли routing улучшает:

```text
quality / $
```

---

# 10. 🔵 Self-optimization workflow

А вот это уже почти research-level фича.

Если есть:

```text
FlowSpec
+
Benchmark
+
Metrics
```

можно экспериментировать с самим workflow.

Например:

```text
Flow v12
  success 87%
  cost $1.4

        ↓ modify

Flow v13
  success 91%
  cost $1.6

        ↓ modify

Flow v14
  success 93%
  cost $1.5
```

И Kroker постепенно ищет:

> **какая структура workflow оптимальна для данного класса задач.**

Например автоматически выясняется:

```text
Backend tasks:
Planner → Developer → QA

Security-sensitive:
Planner → Developer → Security → QA → Reviewer

Large refactor:
Architect → Planner → parallel developers
          → integration → QA → reviewer
```

Вот это уже действительно интересная идея.

---

# Если расставить приоритеты

Я бы сделал roadmap примерно таким:

| Feature                       | Ценность |       Сложность |
| ----------------------------- | -------: | --------------: |
| **FlowSpec**                  |    ⭐⭐⭐⭐⭐ |         высокая |
| **Visual Workflow Builder**   |    ⭐⭐⭐⭐⭐ |         высокая |
| **Benchmark Lab**             |    ⭐⭐⭐⭐⭐ | средняя/высокая |
| **Validation/Evidence UI**    |    ⭐⭐⭐⭐⭐ |         средняя |
| **Run Replay**                |     ⭐⭐⭐⭐ |         средняя |
| **Workflow Simulation**       |     ⭐⭐⭐⭐ |         средняя |
| **Reusable Subflows**         |     ⭐⭐⭐⭐ |         средняя |
| **Policy Engine**             |     ⭐⭐⭐⭐ |         средняя |
| **Cost/Model Router**         |     ⭐⭐⭐⭐ |         средняя |
| **Self-optimizing workflows** |    ⭐⭐⭐⭐⭐ |   очень высокая |

---

# Какой продукт в итоге получается

И вот тут, мне кажется, самое интересное.

Сейчас Kroker можно описать как:

> **Control plane для agent-driven software development.**

Если добавить вышеперечисленное, он превращается в:

```text
                    KROKER
                      │
       ┌──────────────┼──────────────┐
       ↓              ↓              ↓
   DESIGN          EXECUTE        EVALUATE
       │              │              │
   FlowSpec        Temporal       Benchmark
   Visual UI       Agents         Metrics
   Subflows        Harnesses      Evidence
   Policies        Worktrees      Reports
       │              │              │
       └──────────────┼──────────────┘
                      ↓
                 OPTIMIZE
                      │
                Workflow v2
```

И тогда главный объект Kroker становится уже не `FeatureWorkflow`, а:

> **Workflow + Evidence + Evaluation**

То есть пользователь не просто говорит:

> «сделай мне feature».

Он говорит:

> **«Вот workflow, по которому ты должен делать software. Вот критерии качества. Запусти его. Докажи результат. А теперь сравни этот workflow с предыдущей версией и скажи, какой эффективнее»**.

Вот это, на мой взгляд, **самое сильное направление развития Kroker**.

И я бы особенно не откладывал **FlowSpec + Visual Builder + Benchmark Lab**: именно эти три компонента начинают усиливать друг друга и превращают существующий набор orchestration primitives в цельную платформу.
