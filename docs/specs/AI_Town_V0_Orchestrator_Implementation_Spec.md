# AI 小镇 V0：Orchestrator 实施总规范

> 文档状态：`READY_FOR_IMPLEMENTATION`  
> 目标读者：Codex Orchestrator 主线程及其长期生产线程  
> 文档用途：作为首版实验项目的唯一高层实施基准、任务拆分依据、验收依据与跨线程接口契约  
> 配套文档：`AI_Town_Long_Term_Architecture_Roadmap.md`  
> 首版目标：优先跑通一个可观察、可解释、可复现、能接入 Unity 的小型社会世界模型验证闭环  
> 非目标：制作商业化《模拟人生》替代品、构建通用社会仿真平台、训练视觉生成型世界模型、追求大规模 NPC 数量

---

## 0. Orchestrator 的首要指令

Orchestrator 在正式推进前，必须接受以下原则作为最高优先级约束：

1. **先完成可运行的规则基线，再训练世界模型。**
2. **先冻结有限行为与 Unity 资产契约，再扩展状态和模型。**
3. **权威硬状态永远由规则模拟器维护；模型只能预测软状态和概率结果。**
4. **首版世界模型只在固定候选行为上做条件后果预测，不自由生成新行为。**
5. **Unity 是表现层和玩家交互层；Python Town Core 是首版权威模拟层。**
6. **用户负责 Unity 场景搭建、模型、材质、动画资源和技术美术表现；Codex 负责脚本、接口、编辑器辅助工具、数据契约与调试工具。**
7. **DeepSeek API 只承担自然语言解析与语言表达，不承担世界持续运行的必经决策。**
8. **首版不引入 Transformer、GNN、RSSM、MoE、强化学习、完整 Belief Graph 或自由行为生成。**
9. **任何扩展必须先证明它解决了当前验收失败，而不是因为“未来可能需要”。**
10. **所有跨线程变更必须落到可审查的 Schema、ADR、测试或接口文件中，不允许只存在于聊天上下文。**

Orchestrator 的任务不是亲自完成所有代码，而是维护以下四件事：

- 单一事实源；
- 依赖顺序；
- 跨线程接口；
- 验收闭环。

当实现细节与本规范冲突时，Orchestrator 必须暂停合并，先形成 ADR，再决定是否修改规范。

---

# 1. 项目定义

## 1.1 一句话定义

本项目是一个由固定地点、固定对象、固定行为和有限社会变量构成的小型社会模拟 Demo。十名 NPC 在四个家庭和四个公共建筑之间生活、工作、消费、娱乐与社交；小型结构化世界模型批量预测候选行为的软状态后果；Unity 负责把行为、移动、动画、对话和调试信息可视化；DeepSeek API 负责玩家可见的自然语言理解与表达。

## 1.2 首版需要验证的研究问题

首版只验证以下问题：

1. 小型模型能否在固定 Schema 下理解：
   - 需求；
   - 人格；
   - 日程；
   - 地点；
   - 对象；
   - 关系；
   - 已知事件；
   - 候选行为。
2. 小型模型能否预测：
   - 社会行为是否被接受；
   - 情绪变化；
   - 关系变化；
   - 事件类型与概率。
3. 多个 NPC 的候选行为能否组成 Batch，在本地低成本推理。
4. 模型预测能否与确定性规则共同形成稳定状态转移。
5. 事件能否被目击、传播，并实际影响后续行为。
6. DeepSeek 能否在严格语义边界内：
   - 把玩家语言解析成有限结构化行为；
   - 把 NPC 的结构化 SpeechPlan 表达成自然语言。
7. Unity 中是否能直观看到 NPC “为什么这样做”。

## 1.3 首版成功的最低视觉效果

即使所有美术使用灰盒或简单资产，首版也必须能够看到：

- NPC 从住宅出发前往工作地点；
- NPC 使用固定家具完成吃饭、睡觉、洗澡、看电视等行为；
- NPC 按班次工作并获得工资；
- 家庭食品不足后有人去商店采购；
- NPC 在酒吧、工作地点、公园等场所相遇；
- NPC 进行聊天、玩笑、道歉、对质、传播事件等社会行为；
- 关系和情绪变化影响后续选择；
- 玩家可以询问 NPC 已知的事件；
- 调试 UI 能展示候选行为、模型预测和最终选择理由。

## 1.4 首版明确不做

以下内容属于正式的 V0 非范围，除非 Orchestrator 通过 ADR 证明不做就无法完成核心验收：

- 儿童、成长、衰老、死亡；
- 恋爱、生育、婚姻系统；
- 疾病和医疗；
- 房租、贷款、税收、复杂企业财务；
- 生产链、物流、动态市场价格；
- 程序化房屋生成；
- 大规模城镇；
- 复杂导航世界模型；
- 门锁、犯罪、警察系统；
- 角色自由创造新行为；
- 自然语言直接修改权威状态；
- 每次 NPC 对话都调用 LLM；
- 本地小 LLM 的训练或微调；
- 原始文本 Embedding 桥；
- 完整真假命题图；
- 多层 Theory of Mind；
- 强化学习；
- 长期多步规划；
- 视觉世界模型；
- 神经网络驱动物理、寻路或动画。

---

# 2. 固定规模与内容预算

## 2.1 人口

首版固定为 **10 名成年 NPC、4 个家庭单元**。

建议默认分配如下；具体名字、外观、性别和美术设定由用户后续决定，代码只依赖稳定 ID：

| 家庭 | 成员 ID | 人数 | 说明 |
|---|---|---:|---|
| `household_a` | `npc_01`, `npc_02` | 2 | 伴侣、亲属或合住均可 |
| `household_b` | `npc_03`, `npc_04`, `npc_05` | 3 | 合租 |
| `household_c` | `npc_06`, `npc_07` | 2 | 亲属或朋友 |
| `household_d` | `npc_08`, `npc_09`, `npc_10` | 3 | 合租或家庭 |

V0 不允许运行时新增或删除 NPC。所有 ID 必须来自配置。

## 2.2 地点节点

固定为 **8 个高层地点节点**：

| 地点 ID | 类型 | 主要行为语义 | 次要行为语义 |
|---|---|---|---|
| `home_a` | `HOME` | 睡眠、进食、清洁、家庭休闲 | 私人社交 |
| `home_b` | `HOME` | 同上 | 同上 |
| `home_c` | `HOME` | 同上 | 同上 |
| `home_d` | `HOME` | 同上 | 同上 |
| `cafe_bar` | `CAFE_BAR` | 工作、餐饮、饮酒 | 娱乐、公共社交 |
| `shop` | `SHOP` | 工作、采购 | 偶遇、闲聊 |
| `workshop` | `WORKPLACE` | 工作 | 同事社交、休息 |
| `park` | `PARK` | 散步、休闲 | 公共社交 |

高层地点数量不得在 V0 中增加。Unity 场景内部可以有房间、楼层、门和楼梯，但 Python Town Core 只把它们视为同一高层地点中的表现结构。

## 2.3 工作岗位与班次

默认配置：

| 岗位组 | NPC 数量 | 班次 |
|---|---:|---|
| 咖啡馆早班 | 2 | 06:00–14:00 |
| 咖啡馆晚班 | 2 | 14:00–22:00 |
| 商店 | 2 | 09:00–17:00 |
| 工坊/办公室 | 4 | 08:00–16:00 |

每名 NPC 固定一个工作地点和班次。V0 不做晋升、求职、解雇或换班。

## 2.4 需求

只保留 5 项，统一范围 `[0.0, 1.0]`，`1.0` 表示完全满足，`0.0` 表示极度不足：

- `hunger`
- `energy`
- `hygiene`
- `fun`
- `social`

## 2.5 人格

只保留 4 个稳定轴，统一范围 `[0.0, 1.0]`：

- `sociability`：社交倾向；
- `discipline`：日程与责任优先倾向；
- `frugality`：节俭倾向；
- `irritability`：易怒倾向。

人格不直接产生动作，只改变候选评分、社会结果先验和事件敏感度。

## 2.6 情绪

只保留：

- `valence`：愉悦度，范围 `[-1.0, 1.0]`；
- `stress`：压力，范围 `[0.0, 1.0]`。

## 2.7 关系

每条关系都是有向边，保存 4 个连续值：

- `familiarity` `[0,1]`
- `affinity` `[0,1]`
- `trust` `[0,1]`
- `tension` `[0,1]`

可额外保存不参与模型的离散角色标签：

- `HOUSEHOLD_MEMBER`
- `COWORKER`
- `NEIGHBOR`
- `ACQUAINTANCE`

V0 不做浪漫吸引、尊重、恐惧、债务等额外关系轴。

## 2.8 经济

只保留：

- 家庭共享资金，整数最小货币单位；
- 家庭食品库存，整数份数；
- 固定工资；
- 固定采购价格；
- 固定咖啡馆用餐价格；
- 固定酒吧消费价格。

不做个人账户、商店库存、物价波动和企业利润。

---

# 3. Orchestrator 与长期生产线程

## 3.1 线程划分

建议建立以下 6 个长期生产线程。线程名可以调整，但职责边界不得模糊。

### `THREAD-SCHEMA-CONTRACTS`

负责：

- 领域 Schema；
- 枚举；
- 配置文件；
- JSON Schema/Pydantic DTO；
- Python 与 Unity 共享协议；
- 行为目录；
- 对象目录；
- 事件目录；
- Schema 迁移；
- 协议版本。

主要拥有路径：

```text
/config/
/protocol/
/python/town_core/domain/
/docs/specs/
/docs/adr/
```

禁止：

- 自行实现完整模拟循环；
- 修改 Unity 场景或美术资源；
- 未经 ADR 改变核心规模和行为集合。

### `THREAD-SIMULATION-CORE`

负责：

- 权威状态；
- 时钟；
- 事件队列；
- 行为候选生成；
- 行为生命周期；
- 两阶段提交；
- 对象占用；
- 需求衰减；
- 工作、工资、采购；
- 事件账本；
- 已知事件传播；
- 规则基线 Agent；
- Headless 运行与回放。

主要拥有路径：

```text
/python/town_core/simulation/
/python/town_core/decision/
/python/town_core/events/
/python/town_core/replay/
/python/tests/simulation/
```

禁止：

- 改变 DTO 定义而不通知 Schema 线程；
- 把自然语言直接写入权威状态；
- 引入模型依赖作为模拟器必需项。

### `THREAD-UNITY-BRIDGE`

负责：

- Unity C# 连接；
- WebSocket 客户端；
- DTO；
- SemanticLocation、SemanticObject、InteractionSlot 等组件；
- NPC 导航和动作状态机；
- 动画驱动接口；
- 对话气泡；
- 玩家输入桥；
- 资产注册与验证；
- 调试 UI；
- Unity 侧集成测试与 Editor 校验工具。

主要拥有路径：

```text
/unity/Assets/AITown/Scripts/
/unity/Assets/AITown/Editor/
/unity/Assets/AITown/Tests/
/docs/unity/
```

边界：

- 用户负责场景搭建、模型、材质、动画片段、Animator Controller 的美术配置、NavMesh 烘焙和技术美术表现；
- Codex 可以提供组件、Inspector、Editor 校验器、动画参数约定和占位测试脚本；
- Codex 不得擅自重做用户资产、不修改第三方模型文件、不生成最终美术。

### `THREAD-DATA-WORLD-MODEL`

负责：

- 社会锚点数据；
- 程序化扩增；
- 候选转移数据集；
- 特征工程；
- 世界模型；
- 训练脚本；
- 评估；
- 模型导出；
- 推理服务；
- 版本与元数据。

主要拥有路径：

```text
/python/training/
/python/town_core/world_model/
/data/schemas/
/data/anchors/
/data/generated/
/models/
/python/tests/model/
```

禁止：

- 让模型修改硬状态；
- 将训练代码直接嵌入 Unity；
- 未经评估替换规则基线；
- 以“模型能自由生成”为理由绕过行为目录。

### `THREAD-LLM-DIALOGUE`

负责：

- DeepSeek API Gateway；
- 玩家语言解析；
- SpeechPlan 表达；
- Prompt 模板；
- JSON 输出校验；
- 缓存；
- 重试；
- 超时；
- 熔断；
- 模板回退；
- 对话会话；
- 语义权限过滤。

主要拥有路径：

```text
/python/town_core/llm/
/python/town_core/dialogue/
/config/prompts/
/python/tests/llm/
```

禁止：

- 直接访问完整权威状态；
- 将 LLM 输出直接提交为世界事实；
- 无 Schema 的自由 JSON；
- 把 API Key 写入仓库；
- 让世界时钟依赖 API 可用性。

### `THREAD-QA-OBSERVABILITY`

负责：

- 测试策略；
- 属性测试；
- 长时间稳定性测试；
- 黄金事件链；
- 决策追踪；
- 运行指标；
- 日志；
- 调试快照；
- 回归报告；
- 发布检查。

主要拥有路径：

```text
/python/tests/
/integration_tests/
/docs/qa/
/tools/diagnostics/
/reports/
```

禁止：

- 为了让测试通过修改产品逻辑；
- 绕过 Orchestrator 直接重构其他线程代码；
- 只报告失败而不提供可复现输入、种子和日志。

## 3.2 Orchestrator 必须维护的文件

建议在仓库中固定以下文件：

```text
/docs/orchestration/MASTER_PLAN.md
/docs/orchestration/CURRENT_STATUS.md
/docs/orchestration/DECISION_LOG.md
/docs/orchestration/INTEGRATION_MATRIX.md
/docs/orchestration/KNOWN_ISSUES.md
/docs/orchestration/RELEASE_CHECKLIST.md

/docs/handoffs/THREAD-SCHEMA-CONTRACTS.md
/docs/handoffs/THREAD-SIMULATION-CORE.md
/docs/handoffs/THREAD-UNITY-BRIDGE.md
/docs/handoffs/THREAD-DATA-WORLD-MODEL.md
/docs/handoffs/THREAD-LLM-DIALOGUE.md
/docs/handoffs/THREAD-QA-OBSERVABILITY.md
```

每个长期线程在完成任务后必须更新自己的 handoff，至少包括：

```text
Current responsibility
Completed since last handoff
Files changed
Interfaces changed
Tests added/run
Known limitations
Pending decisions
Next recommended task
Blocking dependencies
```

## 3.3 任务包格式

Orchestrator 向生产线程派发任务时，必须使用明确任务包。建议模板：

```markdown
# TASK-<ID>: <标题>

## Goal
一句话说明交付目标。

## Why now
说明依赖与当前阶段。

## Allowed scope
允许修改的目录和模块。

## Forbidden scope
明确不可修改的内容。

## Inputs
依赖的规范、Schema、接口、样例和上游提交。

## Required deliverables
必须产生的代码、配置、测试、文档和报告。

## Acceptance criteria
可执行、可验证的验收条件。

## Required validation
必须运行的命令、测试、性能检查或人工检查。

## Handoff requirements
线程结束时必须写入的 handoff 信息。

## Stop conditions
遇到哪些情况必须停止并回报 Orchestrator，而不是自行扩展范围。
```

## 3.4 合并规则

任何跨线程功能合并前至少需要：

1. 上游 Schema 已版本化；
2. 单元测试通过；
3. 接口测试通过；
4. 有回放或可复现样例；
5. QA 线程给出验证记录；
6. 若改变既有决策，存在 ADR；
7. `CURRENT_STATUS.md` 更新；
8. 不包含密钥、模型大文件、生成数据集或 Unity Library 等不应入库内容。

## 3.5 决策优先级

发生冲突时按以下顺序裁决：

1. 权威状态一致性；
2. 可复现和可测试；
3. Unity 接口稳定；
4. 首版范围控制；
5. 运行性能；
6. 模型效果；
7. 代码优雅程度；
8. 未来扩展性。

不得为了“未来架构更漂亮”破坏当前垂直切片。

---

# 4. 推荐仓库结构

```text
/
├─ README.md
├─ pyproject.toml
├─ .env.example
├─ .gitignore
│
├─ config/
│  └─ v0/
│     ├─ world.yaml
│     ├─ population.yaml
│     ├─ households.yaml
│     ├─ locations.yaml
│     ├─ objects.yaml
│     ├─ behaviors.yaml
│     ├─ schedules.yaml
│     ├─ economy.yaml
│     ├─ utility.yaml
│     ├─ events.yaml
│     ├─ model.yaml
│     └─ prompts/
│        ├─ parse_player_utterance.md
│        └─ verbalize_speech_plan.md
│
├─ protocol/
│  ├─ version.json
│  ├─ jsonschema/
│  └─ examples/
│
├─ python/
│  ├─ town_core/
│  │  ├─ domain/
│  │  ├─ catalogs/
│  │  ├─ simulation/
│  │  ├─ decision/
│  │  ├─ events/
│  │  ├─ knowledge/
│  │  ├─ world_model/
│  │  ├─ dialogue/
│  │  ├─ llm/
│  │  ├─ transport/
│  │  ├─ replay/
│  │  └─ observability/
│  ├─ training/
│  │  ├─ anchors/
│  │  ├─ generation/
│  │  ├─ features/
│  │  ├─ models/
│  │  ├─ train/
│  │  └─ evaluation/
│  ├─ tests/
│  └─ scripts/
│
├─ unity/
│  └─ Assets/
│     └─ AITown/
│        ├─ Scripts/
│        │  ├─ Bridge/
│        │  ├─ Semantic/
│        │  ├─ NPC/
│        │  ├─ Animation/
│        │  ├─ Dialogue/
│        │  ├─ UI/
│        │  └─ Debug/
│        ├─ Editor/
│        └─ Tests/
│
├─ data/
│  ├─ schemas/
│  ├─ anchors/
│  ├─ fixtures/
│  └─ README.md
│
├─ models/
│  └─ README.md
│
├─ docs/
│  ├─ specs/
│  ├─ orchestration/
│  ├─ handoffs/
│  ├─ adr/
│  ├─ unity/
│  └─ qa/
│
├─ integration_tests/
├─ tools/
└─ reports/
```

以下内容不得提交 Git：

```text
.env
API keys
Unity Library/
Unity Temp/
Unity Logs/
大型生成数据集
训练 checkpoint
运行日志
缓存的 LLM 响应
个人隐私数据
```

模型发布文件应通过 Git LFS、Release Artifact 或外部存储管理，首版仓库只保留下载/生成说明。


# 5. 领域模型与状态 Schema

## 5.1 通用约定

### ID

所有长期实体使用稳定字符串 ID：

```text
npc_01
household_a
home_a
home_a_bed_01
behavior_sleep
event_00001234
conversation_0000042
```

禁止：

- 以 Unity Instance ID 作为跨进程 ID；
- 以显示名称作为主键；
- 运行时随机重命名；
- 在同一世界存档中复用已删除事件的 ID。

### 数值范围

| 类型 | 范围 |
|---|---|
| 需求 | `[0,1]` |
| 人格 | `[0,1]` |
| 熟悉度/好感/信任/紧张 | `[0,1]` |
| 愉悦度 | `[-1,1]` |
| 压力 | `[0,1]` |
| 接受概率 | `[0,1]` |
| 事件置信度 | `[0,1]` |
| 金钱 | 非负整数 |
| 食品库存 | 非负整数 |
| 时间 | 自世界开始后的整数游戏分钟 |

所有范围约束必须在：

- 配置加载；
- 状态提交；
- 模型输出后处理；
- 存档加载；

四个入口重复校验。

### 时间

权威时间使用：

```python
game_minute: int
```

派生字段：

```text
game_day = game_minute // 1440
minute_of_day = game_minute % 1440
weekday = game_day % 7
```

不得同时把多个可变时间字段保存为真相源。

### 状态修改

禁止任意模块直接修改任意对象字段。所有权威状态变化必须通过以下之一：

- `HardEffect`
- `SoftEffect`
- `ResolvedAction`
- `WorldEvent`
- `StateTransaction`

提交前必须校验。

---

## 5.2 核心状态对象

### `WorldState`

建议字段：

```yaml
schema_version: "v0.1"
world_id: "demo_world"
game_minute: 0
random_seed: 12345
state_version: 0
agents: {}
households: {}
locations: {}
objects: {}
relationships: {}
active_actions: {}
dialogue_sessions: {}
event_cursor: 0
model_version: null
config_hash: "..."
```

说明：

- `state_version` 每次成功提交事务后递增；
- `config_hash` 用于判断回放是否匹配配置；
- `model_version` 记录当前推理模型；
- 历史事件不直接嵌入快照，可存储于事件账本并通过 cursor 引用。

### `AgentState`

```yaml
agent_id: "npc_01"
household_id: "household_a"
display_name_key: "npc_01_name"
home_location_id: "home_a"
current_location_id: "home_a"
assigned_work_location_id: "cafe_bar"
assigned_workstation_tag: "cafe_morning"
current_action_id: null
needs:
  hunger: 0.74
  energy: 0.82
  hygiene: 0.70
  fun: 0.55
  social: 0.48
personality:
  sociability: 0.68
  discipline: 0.75
  frugality: 0.33
  irritability: 0.20
mood:
  valence: 0.15
  stress: 0.18
schedule_id: "schedule_npc_01"
known_event_ids: []
social_cooldowns: {}
decision_due_at: 0
enabled: true
```

### `HouseholdState`

```yaml
household_id: "household_a"
member_ids: ["npc_01", "npc_02"]
home_location_id: "home_a"
money: 50000
food_units: 8
```

金钱建议使用最小货币单位，例如 `50000` 表示 `500.00`。

### `RelationshipState`

关系是有向的：

```yaml
source_agent_id: "npc_01"
target_agent_id: "npc_02"
roles: ["HOUSEHOLD_MEMBER"]
familiarity: 0.80
affinity: 0.65
trust: 0.70
tension: 0.10
last_interaction_minute: 120
```

必须为所有 NPC 对预先创建关系记录，或使用明确默认值。不得在读取时静默返回随机默认关系。

### `LocationState`

```yaml
location_id: "cafe_bar"
location_type: "CAFE_BAR"
display_name_key: "location_cafe_bar"
open_intervals:
  - start_minute_of_day: 360
    end_minute_of_day: 1320
capacity: 16
current_agent_ids: []
object_ids: []
travel_minutes:
  home_a: 12
  home_b: 9
  home_c: 15
  home_d: 11
  shop: 6
  workshop: 8
  park: 5
```

旅行时间矩阵必须：

- 对所有可达地点有定义；
- 大于零；
- 支持非对称，但 V0 建议对称；
- 由配置加载并验证；
- Headless 模式直接使用；
- Unity 模式作为预估与超时参考。

### `InteractionObjectState`

```yaml
object_id: "home_a_bed_01"
object_type: "BED"
location_id: "home_a"
capability_tags: ["SLEEP"]
slot_count: 1
occupied_slots: {}
enabled: true
unity_binding_required: true
metadata:
  household_id: "household_a"
```

### `ScheduleEntry`

```yaml
entry_id: "npc_01_work_monday"
kind: "WORK"
start_minute_of_week: 360
end_minute_of_week: 840
location_id: "cafe_bar"
required_behavior_id: "work_shift"
grace_minutes: 15
priority: 1.0
```

V0 中日程只需要工作条目。睡觉、吃饭和娱乐由需求驱动。

---

## 5.3 行为定义 Schema

所有行为必须来自 `behaviors.yaml`。建议结构：

```yaml
behavior_id: "apologize"
category: "SOCIAL"
actor_count: 1
target_kind: "AGENT"
allowed_location_types: ["HOME", "CAFE_BAR", "SHOP", "WORKPLACE", "PARK"]
required_actor_state: {}
required_target_state:
  same_location: true
duration_minutes:
  base: 8
  variance: 2
interruptible: true
reservations: []
hard_effects: []
soft_effect_mask:
  mood: true
  relationship: true
  acceptance: true
  events: true
output_bounds:
  actor_valence_delta: [-0.10, 0.15]
  actor_stress_delta: [-0.15, 0.10]
  target_affinity_delta: [-0.05, 0.10]
  target_trust_delta: [-0.05, 0.15]
  target_tension_delta: [-0.30, 0.05]
unity:
  animation_semantic: "TALK_POSITIVE_OR_NEUTRAL"
  requires_facing: true
  prop_semantic: null
cooldown_minutes: 60
```

行为定义必须清楚区分：

- **候选条件**：动作是否可以被提出；
- **资源预留**：目标槽位是否可以锁定；
- **硬效果**：确定性状态变化；
- **软效果掩码**：允许模型预测哪些字段；
- **输出范围**：模型结果合法区间；
- **表现语义**：Unity 播放什么类型的动画；
- **冷却**：避免反复刷同一行为。

---

# 6. 固定对象目录与 Unity 资产语义

## 6.1 15 种高层交互对象

| 对象类型 | 能力标签 | 主要行为 | 是否持久占用 |
|---|---|---|---|
| `BED` | `SLEEP` | Sleep | 是 |
| `FRIDGE` | `FOOD_SOURCE_HOME` | EatAtHome | 短暂 |
| `DINING_SEAT` | `SIT`, `EAT` | EatAtHome、EatAtCafe | 是 |
| `SHOWER` | `HYGIENE` | Shower | 是 |
| `SOFA` | `SIT`, `RELAX`, `WATCH_TV` | WatchTV、RelaxAtHome | 是 |
| `TV` | `ENTERTAINMENT` | WatchTV | 可多人共享 |
| `WORKSTATION` | `WORK` + 子标签 | WorkShift | 是 |
| `SHOP_SHELF` | `GROCERY_SOURCE` | BuyGroceries | 短暂 |
| `CHECKOUT_COUNTER` | `PURCHASE` | BuyGroceries | 短暂 |
| `CAFE_COUNTER` | `BUY_MEAL` | EatAtCafe | 短暂 |
| `BAR_COUNTER` | `BUY_DRINK` | DrinkAtBar | 短暂 |
| `PUBLIC_SEAT` | `SIT`, `REST` | TakeBreak、SitInPark | 是 |
| `PARK_ROUTE` | `WALK_ROUTE` | WalkInPark | 共享 |
| `LEISURE_SPOT` | `RELAX` | RelaxAtHome、SitInPark | 可配置 |
| `CONVERSATION_ANCHOR` | `SOCIAL_POSITION` | 可选社交站位 | 是或共享 |

说明：

- `CONVERSATION_ANCHOR` 是 Unity 表现辅助对象；社会行为目标仍然是 NPC。
- `WORKSTATION` 通过标签区分：
  - `CAFE_MORNING`
  - `CAFE_EVENING`
  - `SHOP`
  - `WORKSHOP`
- 门、楼梯、入口、NavMesh Link 不进入 Python 行为目录，而属于 Unity 导航组件。
- `Meal`、`Drink`、`GroceryBag` 是临时表现道具，不进入权威对象表。

## 6.2 Unity 资产边界

### 用户负责

- 建筑和室内场景；
- 模型；
- 材质；
- 灯光；
- 动画片段；
- Animator Controller 的最终状态和过渡；
- NavMesh 表面与烘焙；
- 门、楼梯和路径的视觉实现；
- 家具摆放；
- 特效、表情、音效；
- 最终 UI 美术。

### Codex 负责

- 语义组件；
- ID 和对象类型 Inspector；
- 交互槽位组件；
- 对象注册；
- 重复 ID 检查；
- 必需能力检查；
- NPC 导航控制脚本；
- 行为阶段驱动；
- 动画语义到 Animator 参数的映射接口；
- WebSocket 协议；
- DTO；
- 调试面板；
- 对话气泡逻辑；
- 玩家输入提交；
- Editor 校验器；
- 自动生成缺失配置报告；
- 占位测试 Prefab/Mock（仅测试用途）。

### 禁止边界越权

Codex 不得：

- 删除或替换用户制作的模型；
- 修改第三方资产源文件；
- 假定某个具体骨骼命名，除非通过适配器配置；
- 把场景坐标写死在 Python；
- 让 Python 决定具体路径节点；
- 把 Unity 动画完成事件作为唯一权威状态来源。

---

# 7. 首版行为目录

## 7.1 非社交行为

### 1. `idle`

- 目标：无；
- 地点：任意；
- 作用：保底，等待短时间；
- 时长：5–15 游戏分钟；
- 硬效果：无；
- 软效果：轻微压力下降或无；
- Unity：Idle；
- 候选条件：始终可用；
- 特别规则：除非无其他合法行为或所有候选分数过低，否则应施加负评分。

### 2. `sleep`

- 目标：`BED`；
- 地点：角色住宅；
- 时长：30–480 分钟，可被日程中断；
- 硬效果：占用床；
- 软/规则效果：持续恢复能量，轻微降低社交/饥饿；
- 候选条件：
  - 床可用；
  - 角色在家或可前往家；
  - 能量未满；
- Unity：Walk → Sleep；
- 中断：
  - 上班临近；
  - 玩家强制交互；
  - 极高饥饿；
  - 床不可用。

### 3. `eat_at_home`

- 目标：`FRIDGE` + `DINING_SEAT`；
- 地点：住宅；
- 时长：25–40 分钟；
- 硬效果：
  - 家庭食品库存 `-1`；
  - 预留座位；
- 结果：
  - 大幅恢复饥饿；
  - 小幅提升愉悦度；
- 候选条件：
  - 食品库存至少 1；
  - 可用座位；
  - 可进入对应住宅；
- Unity：取餐道具 → 坐下 → Eat。

### 4. `shower`

- 目标：`SHOWER`；
- 地点：住宅；
- 时长：20–35 分钟；
- 硬效果：占用淋浴；
- 结果：大幅恢复清洁，轻微降低压力；
- Unity：进入遮挡区/浴室 → ShowerHidden；
- 不生成裸露角色表现要求。

### 5. `watch_tv`

- 目标：`TV` + `SOFA`；
- 地点：住宅；
- 时长：30–120 分钟；
- 结果：
  - 恢复娱乐；
  - 与同地点共同观看者小幅增加熟悉度；
- 预留：
  - 一个 Sofa 槽位；
  - TV 可共享；
- Unity：坐下 → Watch/Idle；
- 可作为 InviteJoin 的联合活动。

### 6. `relax_at_home`

- 目标：`SOFA` 或 `LEISURE_SPOT`；
- 地点：住宅；
- 时长：20–60 分钟；
- 结果：中等恢复娱乐，小幅降低压力；
- Unity：Sit/Relax；
- 作为没有 TV 或不想消费时的低成本娱乐。

### 7. `work_shift`

- 目标：分配的 `WORKSTATION`；
- 地点：固定工作地点；
- 时长：从到岗到班次结束，可拆成工作段；
- 硬效果：
  - 记录出勤；
  - 班次完成后发放固定工资；
- 需求效果：
  - 降低能量、卫生、娱乐；
- 社会效果：
  - 与同事共处增加熟悉度；
  - 迟到或缺勤产生事件；
- Unity：按岗位标签选择 DeskWork、StandingWork、WorkshopWork；
- 候选评分应受 discipline 和班次临近强烈影响。

### 8. `take_break`

- 目标：`PUBLIC_SEAT` 或工作场所休息位；
- 地点：工作地点；
- 时长：10–30 分钟；
- 结果：
  - 小幅恢复能量/娱乐；
  - 可能与同事聊天；
- 候选条件：不应导致严重迟到或超出允许休息窗口。

### 9. `buy_groceries`

- 目标：`SHOP_SHELF` + `CHECKOUT_COUNTER`；
- 地点：商店；
- 时长：20–40 分钟；
- 硬效果：
  - 家庭资金减少；
  - 家庭食品库存增加固定份数；
- 候选条件：
  - 家庭资金足够；
  - 食品库存低于目标线；
  - 商店开放；
- Unity：选购 → GroceryBag → 结账；
- V0 不模拟商店库存。

### 10. `eat_at_cafe`

- 目标：`CAFE_COUNTER` + 可用座位；
- 地点：咖啡馆；
- 时长：25–50 分钟；
- 硬效果：家庭资金减少；
- 结果：
  - 恢复饥饿；
  - 小幅恢复娱乐；
  - 提高遇见其他 NPC 的机会；
- 候选评分受 frugality 负向影响。

### 11. `drink_at_bar`

- 目标：`BAR_COUNTER` + 可用座位；
- 地点：咖啡馆/酒吧；
- 时长：30–90 分钟；
- 硬效果：家庭资金减少；
- 结果：
  - 恢复娱乐；
  - 降低社交行为门槛；
  - 可能增加第二天能量损耗或晚睡风险；
- V0 不模拟酒精成瘾、醉酒物理或健康。

### 12. `walk_in_park`

- 目标：`PARK_ROUTE`；
- 地点：公园；
- 时长：20–60 分钟；
- 结果：
  - 恢复娱乐；
  - 降低压力；
  - 有机会触发 Greet/Chat；
- Unity：沿配置路线移动。

### 13. `sit_in_park`

- 目标：`PUBLIC_SEAT` 或 `LEISURE_SPOT`；
- 地点：公园；
- 时长：20–60 分钟；
- 结果：恢复娱乐、降低压力；
- Unity：Sit/Relax；
- 可作为 InviteJoin 的联合活动。

## 7.2 社交行为

所有社交行为要求目标 NPC：

- 同一高层地点；
- 当前可交互；
- 不处于不可中断行为；
- 不在社交冷却；
- 不等于自己。

### 14. `greet`

- 用途：首次或长时间未互动后建立联系；
- 时长：2–5 分钟；
- 结果：
  - 增加熟悉度；
  - 小幅影响好感；
- 首次见面优先；
- Unity：TalkNeutral / Wave。

### 15. `chat`

- 用途：普通交流；
- 时长：5–20 分钟；
- 结果：
  - 恢复双方社交需求；
  - 小幅改变熟悉度和好感；
- 接受概率通常较高；
- Unity：TalkNeutral。

### 16. `joke`

- 用途：娱乐型互动；
- 结果可能：
  - `POSITIVE_INTERACTION`
  - `AWKWARD_INTERACTION`
- 受：
  - 好感；
  - 熟悉度；
  - 目标压力；
  - 行为者 sociability；
  - 行为者 irritability；
  - 当前公开/私人环境；
  影响；
- Unity：TalkPositive 或尴尬 Reaction。

### 17. `compliment`

- 用途：提高好感；
- 可能因陌生、紧张或目标心情差而显得不自然；
- 结果：
  - 好感变化；
  - 愉悦度变化；
  - 少量信任变化；
- Unity：TalkPositive。

### 18. `share_event`

- 用途：传播自己已知的事件；
- 必须指定 `event_id`；
- 行为者必须拥有对应 `KnowledgeRecord`；
- 目标获得新的 KnowledgeRecord 或强化已有记录；
- 结果受：
  - 双方信任；
  - 事件重要度；
  - 来源可靠性；
  - 目标是否已知；
  影响；
- V0 不允许故意捏造不存在的事件；
- Unity：TalkNeutral，可显示事件图标。

### 19. `invite_join`

- 用途：邀请对方共同进行以下有限活动：
  - WatchTV
  - EatAtCafe
  - DrinkAtBar
  - WalkInPark
  - SitInPark
- 输出：
  - 接受/拒绝；
  - 若接受，创建 JointAction 或协调两个 Action；
- 接受概率受：
  - 关系；
  - 双方需求；
  - 日程；
  - 旅行成本；
  - 资金；
  - 当前压力；
  影响；
- 不允许邀请未实现的自由活动。

### 20. `apologize`

- 用途：处理已有紧张或相关负面事件；
- 候选条件：
  - `tension` 超过阈值，或存在行为者影响目标的负面事件；
- 可能结果：
  - 接受；
  - 部分接受；
  - 拒绝；
- 允许降低 tension，少量恢复 trust/affinity；
- 不能一次清空严重冲突；
- Unity：TalkPositive/Neutral + target reaction。

### 21. `confront`

- 用途：对已有矛盾、缺勤、失约或传播事件进行对质；
- 候选条件：
  - tension 高；
  - 或目标相关事件已知；
- 可能结果：
  - 澄清；
  - 冲突升级；
  - 对方道歉倾向提高；
- 允许提升或降低 tension；
- 高 irritability 增加选择概率和升级概率；
- Unity：TalkNegative。

### 22. `end_conversation`

- 用途：结束当前社交会话；
- 硬效果：释放会话与社交站位；
- 可由：
  - 行为超时；
  - 日程临近；
  - 需求危机；
  - 对话被拒绝；
  - 玩家结束；
  触发；
- Unity：恢复 Idle/后续导航。

## 7.3 内部执行阶段，不计入行为目录

以下是执行状态，不是模型可自由选择的行为：

```text
RESERVING
TRAVELING
ALIGNING
PERFORMING
RESOLVING
COMPLETED
CANCELLED
FAILED
```

`TravelTo` 是高层行为的自动阶段，不进入候选集合。

---

# 8. 世界事件与有限知识系统

## 8.1 事件账本

所有对后续决策有意义的事件写入追加式账本：

```yaml
event_id: "event_00001234"
event_type: "WORK_MISSED"
game_minute: 1100
location_id: "workshop"
actor_ids: ["npc_03"]
affected_agent_ids: ["npc_04", "npc_05"]
witness_agent_ids: ["npc_04", "npc_05"]
source_action_id: "action_0000098"
importance: 0.80
payload:
  scheduled_start: 480
  arrival_minute: null
  missed_minutes: 480
```

事件不允许原地改写。需要纠正时追加：

- `EVENT_CORRECTED`
- `EVENT_RETRACTED`
- `EVENT_SUPERSEDED`

V0 可以暂不实现纠正语义，但账本结构应保留扩展字段。

## 8.2 V0 事件类型

至少包括：

### 生活/经济

- `MEAL_CONSUMED`
- `GROCERIES_PURCHASED`
- `HOUSEHOLD_FOOD_LOW`
- `HOUSEHOLD_MONEY_LOW`
- `NEED_CRISIS`

### 工作

- `WORK_STARTED`
- `WORK_COMPLETED`
- `WORK_LATE`
- `WORK_MISSED`
- `COWORKER_EXTRA_LOAD`

### 社会

- `FIRST_GREETING`
- `POSITIVE_INTERACTION`
- `AWKWARD_INTERACTION`
- `INVITATION_ACCEPTED`
- `INVITATION_REJECTED`
- `APOLOGY_ACCEPTED`
- `APOLOGY_REJECTED`
- `CONFLICT_STARTED`
- `CONFLICT_ESCALATED`
- `CONFLICT_REDUCED`
- `EVENT_SHARED`
- `CONVERSATION_STARTED`
- `CONVERSATION_ENDED`

## 8.3 `KnowledgeRecord`

```yaml
agent_id: "npc_08"
event_id: "event_00001234"
source_agent_id: "npc_05"
acquisition_type: "TOLD"
confidence: 0.75
first_known_minute: 1800
last_reinforced_minute: 1800
```

`acquisition_type`：

- `DIRECT_PARTICIPANT`
- `WITNESSED`
- `TOLD`
- `PLAYER_TOLD`

## 8.4 知识生成规则

- 事件行为者和受影响者通常直接知道；
- 同地点且满足可感知条件者成为 witness；
- `share_event` 可以把事件传播给目标；
- 玩家对 NPC 的自然语言可以通过 `PLAYER_TOLD` 产生知识；
- NPC 只能在语言生成上下文中引用自己已知的事件；
- 未知事件不得因为 LLM “觉得合理”而被补全。

## 8.5 V0 不处理的知识问题

- 谎言；
- 真假命题冲突；
- 事件细节被扭曲；
- 来源链多跳衰减；
- “我知道你知道”；
- 秘密权限；
- 同一事件多个叙述版本。

这些进入后续规划文档。


# 9. Python Town Core：权威模拟架构

## 9.1 运行模式

Town Core 必须支持三种模式，并共用同一套领域逻辑：

### `HEADLESS_FAST`

用于：

- 自动测试；
- 数据生成；
- 训练评估；
- 长时间稳定性模拟。

特点：

- 不连接 Unity；
- 使用地点旅行时间矩阵；
- 可用数百倍游戏速度；
- 所有动画立即视为可表现；
- 可固定随机种子。

### `UNITY_LIVE`

用于：

- Unity Demo；
- 玩家交互；
- 可视化调试。

特点：

- Python 仍是权威状态；
- Unity 负责具体寻路、动画和玩家输入；
- Unity 报告抵达、导航失败、表现完成等信号；
- 游戏时间倍率由 Unity UI 请求、Python批准；
- API 对话异步运行。

### `REPLAY`

用于：

- 重放某次运行；
- 复现失败；
- Unity 演示固定事件链。

特点：

- 读取快照、事件日志和决策记录；
- 可选择：
  - 完全重放已提交结果；
  - 用相同随机种子重新计算并比较；
- 禁止写回原始运行目录。

## 9.2 模拟时钟

建议基础模拟步长为 1 游戏分钟，但不要求每分钟让所有 NPC 决策。

每个 Tick 只处理：

1. 时间推进；
2. 进行中动作的持续效果；
3. 到期事件；
4. 需求衰减；
5. 日程阈值；
6. 需要重新决策的 NPC；
7. 提案和结算；
8. 事件写入；
9. 快照/日志。

Unity 帧率与模拟 Tick 完全解耦。

## 9.3 决策触发

NPC 只在以下情况进入待决策集合：

- 当前动作完成；
- 当前动作失败或被取消；
- 到达目标地点；
- 工作开始时间临近；
- 需求跌破配置阈值；
- 收到邀请；
- 收到重要社会事件；
- 对话结束；
- 预设最大无决策时间到期；
- 玩家强制发起交互。

不得每个 Tick 对所有 NPC 全量重新决策。

## 9.4 候选生成

候选生成必须是确定性规则过程。世界模型不能创造候选。

伪代码：

```python
def enumerate_candidates(agent, world, catalogs) -> list[CandidateAction]:
    candidates = [build_idle(agent)]

    for behavior in catalogs.behaviors:
        if behavior.category == "SOCIAL":
            for target in visible_social_targets(agent, world):
                if behavior_preconditions_met(behavior, agent, target, world):
                    candidates.append(build_social_candidate(...))
        else:
            for target_bundle in find_valid_object_bundles(behavior, agent, world):
                if behavior_preconditions_met(behavior, agent, target_bundle, world):
                    candidates.append(build_candidate(...))

    return deduplicate_and_cap(candidates)
```

候选必须记录：

```yaml
candidate_id: "candidate_..."
actor_id: "npc_03"
behavior_id: "eat_at_cafe"
target_agent_id: null
target_object_ids: ["cafe_counter_01", "cafe_seat_03"]
destination_location_id: "cafe_bar"
estimated_travel_minutes: 12
estimated_duration_minutes: 35
hard_cost_preview:
  money: 800
  food_units: 0
schedule_conflict_minutes: 0
context_event_ids: []
```

## 9.5 候选数量控制

V0 建议每名待决策 NPC 最多保留 12 个候选：

- 每种非社交行为最多 1–2 个最佳对象组合；
- 每种社交行为最多 2 个目标；
- `share_event` 最多选择重要度最高的 2 个事件；
- `invite_join` 最多选择 2 个活动；
- 所有候选必须保留至少一个 `idle`。

对象选择的预排序可以使用：

- 旅行时间；
- 槽位可用性；
- 所属住宅；
- 当前日程；
- 目标关系；
- 事件重要度。

这一步是规则，不需要模型。

## 9.6 候选后果预测与评分

V0 使用：

```text
候选生成
→ 世界模型预测软后果
→ 硬规则预览确定硬后果
→ Utility Scorer 统一评分
→ 每名 NPC 选择一个 Proposal
```

建议评分形式：

\[
Score(a)=
w_N U_N(\hat{needs})
+w_M U_M(\hat{mood})
+w_S U_S(schedule)
+w_R U_R(\hat{relationship})
+w_K U_K(known\ events)
-w_C Cost(a)
-w_T Travel(a)
-w_I Interrupt(a)
+\epsilon
\]

其中：

- `w_N` 受当前需求危机影响；
- `w_S` 受 discipline 影响；
- `w_R` 受 sociability 和关系影响；
- `Cost` 受 frugality 影响；
- `Confront` 倾向受 irritability 影响；
- `epsilon` 是可复现的小随机扰动，避免完全机械化。

建议基础分量：

```text
need_utility:
  计算行为后需求相对于当前状态的改善，并对低需求加非线性权重

schedule_utility:
  准时工作高正值；迟到和缺勤高负值

relationship_utility:
  对当前目标关系变化和社交需求改善评分

money_cost:
  消费金额 / 家庭可用资金

travel_cost:
  旅行分钟 / 60

repetition_penalty:
  近期重复同一行为的惩罚

idle_penalty:
  有其他合理行为时惩罚
```

所有权重必须位于 `utility.yaml`，不得散落硬编码。

## 9.7 Proposal 与两阶段提交

所有待决策 NPC 基于同一个只读 `state_version` 产生 Proposal：

```yaml
proposal_id: "proposal_..."
state_version: 1024
actor_id: "npc_03"
candidate_id: "candidate_..."
behavior_id: "sit_in_park"
target_agent_id: null
target_object_ids: ["park_bench_02"]
score: 0.72
model_prediction_id: "prediction_..."
```

Resolver 统一处理：

1. 状态版本是否仍有效；
2. 对象槽位竞争；
3. 两人社交是否存在冲突；
4. 邀请是否接受；
5. 同一 NPC 是否被多个 Proposal 使用；
6. 资金/库存是否足够；
7. 地点是否仍开放；
8. 行为是否与当前动作兼容；
9. 预留；
10. 创建 Action。

不得按照 NPC ID 顺序直接逐个修改世界。

## 9.8 冲突解决

V0 推荐稳定规则：

1. 已接受的联合行为优先于普通单人行为；
2. 日程强制行为优先；
3. 已预留资源优先；
4. 分数高者优先；
5. 分数相同时使用由世界随机种子派生的稳定 tie-break；
6. 失败 Proposal 的 NPC 立即从剩余候选中重选一次；
7. 第二次仍失败则 Idle。

冲突解决必须记录原因：

```text
OBJECT_SLOT_CONFLICT
TARGET_UNAVAILABLE
STATE_STALE
INSUFFICIENT_FUNDS
LOCATION_CLOSED
SOCIAL_TARGET_COMMITTED
```

## 9.9 Action 生命周期

```text
CREATED
→ RESERVING
→ TRAVELING
→ ALIGNING
→ PERFORMING
→ RESOLVING
→ COMPLETED
```

异常分支：

```text
CANCELLED
FAILED
INTERRUPTED
```

### 预留

预留对象和目标时必须指定：

```yaml
reservation_id: "reservation_..."
owner_action_id: "action_..."
object_id: "home_a_bed_01"
slot_index: 0
valid_from_minute: 100
expires_at_minute: 160
```

过期自动释放。

### 旅行

`HEADLESS_FAST`：

- 使用地点旅行矩阵；
- 到达时间确定；
- 地点内对象移动可忽略或使用固定分钟。

`UNITY_LIVE`：

- Python 发出目的地点与目标交互槽位；
- Unity 导航；
- Unity 返回：
  - `movement_arrived`
  - `movement_failed`
  - `movement_cancelled`
- Python 在超时后可失败；
- 导航期间 NPC 的权威高层状态为 `TRAVELING`；
- 实际当前地点在抵达后更新。

### 表现与结算

Unity 动画是表现，不直接决定状态结果。推荐：

- Python 在 `PERFORMING` 开始时确定计划结束时间；
- Unity 播放对应动画；
- Unity 可发送 `presentation_ready` 和 `presentation_completed`；
- 如果动画未完成但时间到，Python可等待有限宽限或使用降级；
- 硬/软效果在 `RESOLVING` 一次提交，或按行为定义做持续效果；
- V0 除睡眠和工作外，优先使用结束时一次结算。

## 9.10 需求衰减

所有速率配置化。示例，仅作为初始调参值：

```yaml
per_game_hour:
  hunger: -0.045
  energy_awake: -0.035
  hygiene: -0.018
  fun: -0.020
  social: -0.015
```

行为持续效果示例：

```yaml
sleep:
  energy_per_hour: 0.18
eat_at_home:
  hunger_on_complete: 0.65
shower:
  hygiene_on_complete: 0.75
watch_tv:
  fun_per_hour: 0.25
chat:
  social_on_complete: 0.18
```

实际值由配置和测试调整，不作为代码常量。

## 9.11 工作与工资

- 到班次开始前 30–60 分钟，WorkShift 候选得到高日程分；
- 迟到超过 `grace_minutes` 产生 `WORK_LATE`；
- 缺席达到配置比例产生 `WORK_MISSED`；
- 完成有效工时比例后发固定工资；
- 同班同事在他人缺勤时可产生 `COWORKER_EXTRA_LOAD`；
- 该事件是首版社会链的重要来源；
- 工资直接进入家庭资金；
- 不做绩效或解雇。

## 9.12 社会结果

规则系统先确定：

- 是否同地点；
- 是否可交流；
- 行为是否有对应事件；
- 哪些关系边允许修改；
- 谁是目击者；
- 哪些输出范围合法。

世界模型预测：

- 接受概率；
- 关系 Delta；
- 情绪 Delta；
- 社会事件概率。

采样必须使用可复现随机源：

```text
seed = hash(world_seed, state_version, action_id, model_version)
```

采样结果写入决策日志。

---

# 10. 首版世界模型

## 10.1 模型职责

世界模型只回答：

> 在当前结构化状态下，某个固定候选行为被执行时，允许变化的软状态大致会怎样变化，这个社会行为是否被接受，可能触发什么社会事件？

它不负责：

- 枚举行为；
- 确定路径；
- 检查金钱；
- 决定对象是否存在；
- 修改库存；
- 生成自然语言；
- 创建新事件类型；
- 决定谁能看到事件；
- 保存世界状态。

## 10.2 输入单元

一条模型输入对应：

```text
一个 Actor
+
一个候选行为
+
可选目标 NPC
+
目标对象/地点摘要
+
局部社会与事件上下文
```

### Actor 连续特征

- 5 项需求；
- 2 项情绪；
- 4 项人格；
- 当前家庭资金归一化；
- 当前食品库存归一化；
- 距离下次工作开始分钟归一化；
- 当前班次进度；
- 当前行为持续时间；
- 最近社交间隔；
- 当前地点人数；
- 当前地点熟人数；
- 当前地点高紧张关系人数。

### Actor 离散特征

- agent ID 可不直接使用，避免记忆单个角色；
- household size bucket；
- current location type；
- assigned work type；
- current action type；
- day phase；
- weekday；
- behavior ID。

### 候选特征

- behavior embedding；
- destination location type embedding；
- target object capability embedding；
- 旅行时间；
- 行为时长；
- 金钱成本比例；
- 是否跨地点；
- 是否与工作冲突；
- 是否重复近期行为；
- 是否联合行为。

### 目标 NPC 特征

若无目标则 mask：

- 目标可见需求摘要；
- 目标情绪；
- 双方关系 4 维；
- 关系标签；
- 最近互动间隔；
- 是否家庭成员；
- 是否同事；
- 是否已在会话中；
- 目标是否知道相关事件。

### 事件上下文

不输入任意文本。最多选择与行为相关的 K 个事件，例如 K=4：

- event type embedding；
- importance；
- age；
- actor/target relation flag；
- target knows flag；
- actor is witness/participant flag。

使用 DeepSets：

```text
event token MLP
→ masked mean pooling
→ masked max pooling
→ context vector
```

## 10.3 推荐结构

首版建议：

```text
Continuous Feature Normalizer
Categorical Embeddings
Actor Encoder: 2-layer MLP
Candidate Encoder: 2-layer MLP
Target Encoder: 2-layer MLP
Event Context Encoder: DeepSets
          ↓ concatenate
Residual MLP Backbone:
  width 256
  4 blocks
  LayerNorm + GELU + residual
          ↓
Task Heads
```

目标参数量：

```text
1M–3M
```

不要求精确追求参数数量，优先保持可读和可消融。

## 10.4 输出 Head

### `NeedDeltaHead`

输出 5 维，但必须乘行为掩码。大多数社会行为只允许小幅影响 social/fun。

V0 中实际提交的需求变化仍以行为配置和规则系统为准；该 Head 主要用于：

- 验证模型是否理解行为后果；
- 候选预览；
- 多任务辅助训练；
- 为后续学习式连续状态做接口准备。

只有经过单独 ADR 和对照评估后，才允许让模型残差修正规则需求结果。

### `MoodDeltaHead`

输出：

- actor valence delta；
- actor stress delta；
- target valence delta；
- target stress delta。

无目标时 target mask。

### `RelationshipDeltaHead`

输出 Actor→Target 和可选 Target→Actor 的：

- familiarity delta；
- affinity delta；
- trust delta；
- tension delta。

V0 可先只预测 Target 对 Actor 的变化，再用规则确定 Actor 自身变化；如果数据足够再扩展双向。

### `AcceptanceHead`

用于：

- Greet；
- Chat；
- Joke；
- Compliment；
- InviteJoin；
- Apologize；
- Confront。

输出 logit。非社交行为 mask。

### `EventHead`

多标签或互斥组输出。建议分组：

```text
interaction_quality:
  NONE
  POSITIVE
  AWKWARD
  CONFLICT

response:
  ACCEPTED
  PARTIAL
  REJECTED

propagation:
  EVENT_SHARED
```

不要让互相排斥的事件同时被独立采样。

### `UncertaintyHead`（可选）

首版可输出每个连续头的 log variance，或只通过 ensemble/MC dropout 在离线评估中估计。不应因此显著拖延 V0。

## 10.5 模型输出约束

推理结果必须经过：

1. `sigmoid/tanh` 范围映射；
2. 行为允许字段 mask；
3. 行为级 delta bounds；
4. 全局状态范围 clamp；
5. 关系目标存在性检查；
6. 事件互斥检查；
7. 规则一致性检查；
8. 违规计数。

模型永远不能通过输出修改未授权字段。

## 10.6 规则基线

训练模型前必须实现可运行的 `HeuristicOutcomeModel`，接口与神经模型相同：

```python
class OutcomeModel(Protocol):
    def predict_batch(
        self,
        rows: Sequence[CandidateFeatureRow],
    ) -> Sequence[OutcomePrediction]:
        ...
```

实现：

- `HeuristicOutcomeModel`
- `TorchOutcomeModel`
- `RecordedOutcomeModel`（测试）

这允许：

- 没有模型时跑通 Unity；
- 对比模型；
- 回退；
- 生成数据；
- 做 A/B。

## 10.7 模型选择不直接替代规则

候选最终评分使用预测结果，但：

- 硬规则可以 veto；
- 工作等高优先行为有明确日程项；
- 极端需求有规则阈值；
- 模型不可让 NPC 在饥饿为零且有食物时无限聊天；
- 模型不可让 NPC 为喝酒花掉不存在的钱。

---

# 11. 数据与训练方案

## 11.1 数据目标

建议首版：

```text
世界状态样本：50,000–100,000
每状态候选：6–10
候选转移行：300,000–1,000,000
Codex 社会锚点：300–1,000
人工/重点验证场景：100–300
```

## 11.2 数据来源比例

建议：

```text
硬规则结果：100% 由模拟器产生
普通需求/经济结果：100% 由行为配置产生
社会软结果：
  规则函数与分布模板：主体
  Codex 社会锚点：校准关键区域
  程序化扩增：扩大覆盖
  少量人工修订：验证集
```

世界模型训练数据并不要求每行都由 LLM 标注。

## 11.3 社会锚点 Schema

```yaml
anchor_id: "apology_high_tension_private_001"
behavior_id: "apologize"
actor:
  personality:
    sociability: 0.4
    discipline: 0.6
    frugality: 0.5
    irritability: 0.2
  mood:
    valence: -0.1
    stress: 0.4
target:
  mood:
    valence: -0.4
    stress: 0.7
relationship:
  familiarity: 0.7
  affinity: 0.5
  trust: 0.3
  tension: 0.8
context:
  location_type: "HOME"
  public: false
  related_event_type: "WORK_MISSED"
  event_importance: 0.8
targets:
  acceptance_probability: 0.68
  actor_mood_delta:
    valence: 0.04
    stress: -0.05
  target_mood_delta:
    valence: 0.08
    stress: -0.10
  relationship_delta_target_to_actor:
    familiarity: 0.00
    affinity: 0.04
    trust: 0.06
    tension: -0.20
  event_distribution:
    APOLOGY_ACCEPTED: 0.68
    APOLOGY_REJECTED: 0.22
    CONFLICT_REDUCED: 0.55
rationale_tags:
  - "private_context_helps"
  - "existing_affinity_supports_acceptance"
  - "trust_damage_not_fully_repaired"
review:
  producer: "THREAD-DATA-WORLD-MODEL/anchor-producer"
  reviewer: null
  status: "DRAFT"
```

## 11.4 Orchestrator 调度锚点生产

Orchestrator 应在 `THREAD-DATA-WORLD-MODEL` 内部分配两个长期角色或子线程：

### Anchor Producer

负责：

- 按行为、关系区间、人格组合、地点公开性生成锚点；
- 遵守输出范围；
- 说明 rationale tags；
- 避免复制同一模板只改数字；
- 维护覆盖矩阵。

### Anchor Reviewer

负责：

- 独立检查方向一致性；
- 检查概率和 delta；
- 检查同类样本冲突；
- 检查人格影响是否稳定；
- 标记不确定样本；
- 不直接改 Producer 原稿，先给 review issue；
- 通过后将状态改为 `APPROVED`。

Orchestrator 负责：

- 限定每批任务规模；
- 定义覆盖网格；
- 抽查；
- 处理争议；
- 合并；
- 禁止 Producer 和 Reviewer 使用隐含聊天记忆作为唯一依据。

## 11.5 覆盖网格

至少覆盖：

- 行为类型；
- 熟悉度：低/中/高；
- 好感：低/中/高；
- 信任：低/中/高；
- 紧张：低/中/高；
- 目标压力：低/高；
- 行为者 sociability：低/高；
- 行为者 irritability：低/高；
- 地点：私人/公共；
- 相关事件：无/轻/重；
- 同家庭/同事/普通熟人。

不要做完整笛卡尔积。使用 pairwise 或分层采样，重点覆盖：

- 边界；
- 高风险组合；
- 验收黄金链。

## 11.6 程序化扩增

可用：

- 连续值扰动；
- 邻域插值；
- 有约束噪声；
- 角色 ID 替换；
- 地点同语义替换；
- 关系对称/非对称变体；
- 事件年龄变化；
- 人格轴局部变化。

不得：

- 让扩增突破行为输出范围；
- 把接受概率简单复制到完全不同语境；
- 用大噪声制造标签自相矛盾；
- 把扩增数据与原始锚点分到不同集合造成泄漏。

## 11.7 Headless 数据生成

流程：

```text
加载世界配置
→ 用 HeuristicOutcomeModel 跑 Episode
→ 在每次决策点枚举所有合法候选
→ 对每个候选生成反事实软结果标签
→ 记录输入、硬预览、软标签、场景组、种子
→ 输出 Parquet
```

数据行必须包含：

```text
schema_version
feature_version
label_version
episode_id
scenario_group_id
world_seed
state_version
actor_id
candidate_id
raw_structured_features
normalized_features
hard_preview
soft_targets
masks
```

## 11.8 数据划分

禁止逐行随机拆分。

建议按：

- `scenario_group_id`
- 完整 episode；
- 人格组合；
- 家庭布局；
- 某些行为-关系区域；

划分训练/验证/测试。

必须额外保留：

- 黄金事件链测试集；
- 边界条件集；
- 未见组合集；
- 长程 Rollout 集。

## 11.9 训练

建议：

```text
框架：PyTorch
精度：FP32 或 BF16
优化器：AdamW
损失：Huber + BCE/CE
早停：验证集综合指标
保存：best validation checkpoint
```

多任务损失：

\[
L =
\lambda_N L_{need}
+\lambda_M L_{mood}
+\lambda_R L_{relation}
+\lambda_A L_{accept}
+\lambda_E L_{event}
+\lambda_C L_{constraint}
\]

需要记录每个 Head 单独指标，禁止只看总 Loss。

## 11.10 评估指标

### 连续预测

- MAE；
- RMSE；
- 分行为 MAE；
- 高 tension 区域 MAE；
- 边界区间误差。

### 概率预测

- Brier Score；
- ROC-AUC（适用时）；
- Expected Calibration Error；
- 可靠性图；
- 分行为校准。

### 决策质量

- 与教师评分排序的一致性；
- Top-1 行为一致率；
- Top-3 覆盖率；
- 相对 regret；
- 黄金场景选择是否合理。

### 安全一致性

- 非法字段修改率必须为 0；
- 输出越界提交率必须为 0；
- 不存在目标的关系输出提交率必须为 0；
- 资源负数率必须为 0；
- 未知事件传播率必须为 0。

### Rollout

- 连续 30 游戏日状态不崩坏；
- 需求长期分布不过度堆在 0 或 1；
- NPC 不无限循环同一行为；
- 工作出勤分布合理；
- 家庭不会全部永久破产或永远富余；
- 社交事件能发生但不持续全员冲突。

## 11.11 模型上线门槛

神经模型只有在满足以下条件后才能替换默认基线：

1. 所有约束测试通过；
2. 关键概率已校准；
3. 黄金链行为选择不劣于规则基线；
4. 30 日 soak test 无严重退化；
5. CPU Batch 推理达到目标；
6. 支持一键切回 HeuristicOutcomeModel；
7. 模型元数据和配置 hash 完整；
8. QA 报告通过。

---

# 12. 性能目标

V0 目标机器不依赖独立显卡。

建议目标：

| 项目 | 目标 |
|---|---|
| NPC 数量 | 10 |
| 同时待决策 NPC | 通常 1–5，峰值 10 |
| 每 NPC 候选 | 平均 6–10，最大 12 |
| Batch 行数 | 峰值约 120 |
| 模型参数 | 1M–3M |
| CPU 单次推理 | 目标小于 50ms；理想小于 20ms |
| Python 模拟 Tick | 不含 LLM 时稳定低延迟 |
| Headless 速度 | 至少数十倍实时，目标百倍以上 |
| Unity 帧率 | 由表现层决定，不因模型推理明显卡顿 |
| 同时 LLM 请求 | 默认最多 2–4 |
| API 失败 | 不阻塞社会模拟 |

性能指标必须在实际开发机器和一个普通 CPU 环境分别测量并记录。


# 13. Unity 接口与脚本契约

## 13.1 通信方式

V0 推荐：

```text
Python FastAPI/ASGI Server
+
本地 WebSocket
+
JSON 消息
```

理由：

- 易调试；
- Unity 和 Python 均有成熟支持；
- 消息量很小；
- 可通过浏览器或脚本模拟；
- 不需要首版引入 gRPC、Protobuf 或共享内存。

后续若性能需要再迁移 MessagePack/Protobuf，不在 V0 提前优化。

## 13.2 消息封装

所有消息使用统一 envelope：

```json
{
  "protocol_version": "0.1.0",
  "message_id": "msg_000001",
  "message_type": "action_started",
  "sent_at_utc": "2026-01-01T00:00:00Z",
  "world_id": "demo_world",
  "state_version": 1024,
  "correlation_id": "action_0000098",
  "payload": {}
}
```

要求：

- `message_id` 唯一；
- 可重复消息必须幂等；
- 未识别协议版本时拒绝继续；
- 所有消息可写入调试日志；
- Unity 不以接收顺序代替 `state_version` 检查。

## 13.3 Unity 启动握手

推荐顺序：

1. Unity 启动并加载场景；
2. `TownBridgeClient` 连接；
3. Unity 发送 `client_hello`；
4. Python 返回 `server_hello`；
5. Unity 扫描并发送 `asset_registry`;
6. Python 验证地点、对象、槽位和 NPC 绑定；
7. Python 返回 `asset_registry_result`；
8. 验证通过后发送 `world_snapshot`；
9. Unity 绑定角色和对象；
10. Unity 发送 `client_ready`；
11. Python 开始或恢复模拟。

如果资产注册失败：

- Python 不开始正式模拟；
- Unity Debug Panel 显示缺失项；
- 允许进入诊断模式；
- 禁止静默忽略缺失对象。

## 13.4 Unity 侧核心组件

### `TownBridgeClient`

职责：

- WebSocket 连接；
- 心跳；
- 重连；
- 消息队列；
- 主线程分发；
- 协议版本检查；
- 请求/响应相关性；
- 连接状态 UI。

### `SemanticLocation`

字段：

```text
locationId
locationType
displayName
entranceAnchors
```

### `SemanticObject`

字段：

```text
objectId
objectType
locationId
capabilityTags
enabled
interactionSlots
```

### `InteractionSlot`

字段：

```text
slotIndex
anchorTransform
facingTransform
supportedAnimationSemantics
occupancyVisualization
```

### `NpcView`

字段：

```text
agentId
navigationController
animationDriver
dialogueBubble
statusIndicator
```

职责：

- 绑定权威 Agent ID；
- 接收动作表现指令；
- 不保存业务真相；
- 可显示本地缓存状态。

### `NpcNavigationController`

职责：

- 目的地与槽位导航；
- NavMesh；
- 门/楼梯链接；
- 抵达判定；
- 失败原因；
- 取消；
- 向 Python 回报。

### `NpcAnimationDriver`

通过语义而非具体 clip 名调用：

```text
IDLE
WALK
SIT
SLEEP
EAT
DRINK
SHOWER_HIDDEN
WORK_DESK
WORK_STANDING
WORK_WORKSHOP
TALK_NEUTRAL
TALK_POSITIVE
TALK_NEGATIVE
REACTION_POSITIVE
REACTION_AWKWARD
REACTION_ANGRY
CARRY_GROCERY
```

用户可以在 Inspector 中把这些语义映射到实际 Animator 参数或状态。

### `TownDebugPanel`

至少展示：

- 世界时间与倍率；
- 连接状态；
- 模型版本；
- 选中 NPC 状态；
- 当前行为与阶段；
- 需求；
- 情绪；
- 日程；
- 家庭资金/食品；
- 附近关系；
- 已知事件；
- Top-K 候选；
- 每个候选硬预览；
- 模型预测；
- Utility 分解；
- 最终选择；
- 最近 Resolver 冲突；
- 最近 LLM 请求状态。

## 13.5 Python → Unity 消息

至少包括：

### `world_snapshot`

完整或局部初始状态。

### `simulation_clock_updated`

```json
{
  "game_minute": 1024,
  "time_scale": 10.0,
  "paused": false
}
```

### `action_started`

```json
{
  "action_id": "action_0000098",
  "agent_ids": ["npc_03"],
  "behavior_id": "eat_at_home",
  "destination_location_id": "home_b",
  "target_object_ids": ["home_b_fridge_01", "home_b_seat_02"],
  "animation_semantic": "EAT",
  "prop_semantic": "MEAL",
  "planned_duration_minutes": 30
}
```

### `action_phase_changed`

### `action_cancelled`

### `agent_state_delta`

用于 UI，不要求 Unity重建业务逻辑。

### `relationship_delta`

用于调试表现、图标。

### `world_event_created`

用于事件提示。

### `dialogue_line_ready`

用于显示 DeepSeek 或模板生成的台词。

### `debug_decision_trace`

仅调试模式。

## 13.6 Unity → Python 消息

至少包括：

### `client_hello`

### `asset_registry`

### `client_ready`

### `movement_arrived`

```json
{
  "action_id": "action_0000098",
  "agent_id": "npc_03",
  "object_id": "home_b_fridge_01",
  "slot_index": 0
}
```

### `movement_failed`

带失败原因：

```text
NO_PATH
DESTINATION_DISABLED
SLOT_BLOCKED
AGENT_DISABLED
TIMEOUT
UNKNOWN
```

### `presentation_completed`

### `player_utterance`

```json
{
  "conversation_id": "conversation_00042",
  "player_id": "player",
  "target_agent_id": "npc_05",
  "text": "你为什么对 npc_03 这么生气？",
  "client_state_version": 1030
}
```

### `player_end_conversation`

### `set_time_scale_request`

### `pause_request`

## 13.7 资产注册验证

Python 必须检查：

- 8 个地点是否全部存在；
- 每个对象 ID 是否唯一；
- 对象类型是否合法；
- 对象是否位于正确地点；
- 每个住宅是否具备：
  - 足够床位；
  - 冰箱；
  - 餐椅；
  - 淋浴；
  - 沙发；
  - TV；
- 工作地点是否具备足够工作槽位；
- 商店是否具备货架和结账台；
- 咖啡馆是否具备柜台、吧台和座位；
- 公园是否具备路线和座位；
- 每名 NPC 是否有 Unity `NpcView`；
- 每个行为所需动画语义是否有映射；
- 必需交互槽位是否存在。

生成报告：

```text
ERROR
WARNING
INFO
```

只有 ERROR 阻止运行。

## 13.8 Unity 测试策略

Codex 应提供：

- EditMode：ID 重复、能力缺失、序列化 DTO；
- PlayMode：连接 Mock Server、导航到槽位、动作取消、重连；
- 无美术依赖的测试 Prefab；
- `MockTownServer` 或录制消息回放；
- 场景校验菜单，例如：
  - `AITown/Validate Current Scene`
  - `AITown/Export Asset Registry`
  - `AITown/Run Bridge Diagnostics`

---

# 14. DeepSeek 语言接口

## 14.1 语言职责

DeepSeek 只承担：

1. 玩家原始文本 → `PlayerSpeechParse`；
2. `SpeechPlan` → 玩家可见台词；
3. 可选的关键 NPC-NPC 对话渲染。

不承担：

- 世界候选生成；
- 社会结果计算；
- 硬规则；
- 已知事件决定；
- 权威事实创建；
- 工作、需求或经济推进。

## 14.2 玩家语言解析 Schema

允许的 `speech_act`：

```text
GREET
SMALL_TALK
ASK_ABOUT_AGENT
ASK_ABOUT_EVENT
COMPLIMENT
JOKE
INVITE
APOLOGIZE
ACCUSE
CONFRONT
FAREWELL
UNKNOWN
```

建议输出：

```json
{
  "speech_act": "ASK_ABOUT_EVENT",
  "target_agent_id": "npc_05",
  "referenced_agent_ids": ["npc_03"],
  "referenced_event_ids": ["event_00001234"],
  "invite_activity": null,
  "tone": {
    "warmth": 0.3,
    "hostility": 0.1,
    "urgency": 0.4
  },
  "claims": [],
  "confidence": 0.86,
  "requires_clarification": false
}
```

V0 中玩家提到的事件解析只能从提供给模型的候选事件列表中选择 ID。不能自由生成看似合法的事件 ID。

## 14.3 玩家语义处理

DeepSeek 解析后：

1. Pydantic 校验；
2. ID 白名单检查；
3. 会话和状态版本检查；
4. 转换为固定社会行为或问询；
5. 规则/世界模型计算社会效果；
6. NPC Agent 形成 SpeechPlan；
7. DeepSeek 表达。

`UNKNOWN` 或低置信度时：

- 使用中性 SmallTalk；
- 或生成不修改关键状态的澄清；
- 不允许猜测权威事实。

## 14.4 `SpeechPlan`

```yaml
speech_plan_id: "speech_plan_00042"
conversation_id: "conversation_00042"
speaker_agent_id: "npc_05"
listener_ids: ["player"]
speech_act: "ANSWER_ABOUT_EVENT"
communicative_goal: "explain_cold_attitude"
allowed_event_ids: ["event_00001234"]
allowed_agent_ids: ["npc_03", "npc_05"]
fact_payload:
  event_type: "WORK_MISSED"
  event_summary_key: "npc_missed_work_causing_extra_load"
stance:
  certainty: 0.75
  approval: -0.55
emotion:
  valence: -0.25
  stress: 0.42
style:
  directness: 0.68
  warmth: 0.25
  verbosity: 0.35
forbidden_topics: []
state_version: 1031
```

DeepSeek 只能使用 `allowed_event_ids` 和显式提供的信息。

## 14.5 Prompt 要求

系统 Prompt 必须强调：

- 不补充未提供事实；
- 不改变角色知识；
- 不声称世界状态已发生变化；
- 只输出指定 JSON 或自然语言；
- 不暴露内部 ID 给玩家，除非调试模式；
- 保持简短；
- 遵循角色说话风格；
- 无信息时明确不知道或含糊回应。

Prompt 模板必须版本化，并记录：

```text
prompt_version
model_name
temperature
max_tokens
schema_version
```

## 14.6 异步、超时与过期

### 解析请求

玩家等待当前语句解析，但世界其他 NPC 继续运行。目标 NPC 可进入 `IN_CONVERSATION_WAITING`，不参与普通自主行为。

### 表达请求

世界结果可以先提交，台词异步到达。

所有请求携带：

```text
conversation_id
state_version
speaker_id
listener_ids
allowed_event_ids
deadline_class
```

结果返回时检查：

- 会话仍存在；
- 说话者仍可说话；
- 监听者仍在；
- 事件权限未失效；
- 状态版本差距未超过阈值。

过期时：

- 丢弃；
- 重新生成；
- 或使用模板回退。

## 14.7 API 稳定性

必须实现：

- 环境变量密钥；
- 请求队列；
- 并发限制；
- 指数退避；
- 超时；
- JSON 修复仅限一次；
- Schema 验证；
- 熔断；
- 响应缓存；
- 可观测统计；
- 模板回退。

不得无限重试。

## 14.8 模板回退

每个 SpeechAct 至少有若干模板。例如：

```text
APOLOGIZE_ACCEPTED:
- “好吧，这次我接受你的道歉。”
- “我还需要一点时间，不过谢谢你愿意说清楚。”

ASK_ABOUT_UNKNOWN_EVENT:
- “这件事我不太清楚。”
- “我没有亲眼见过，最好问问别人。”
```

模板回退必须能够完成 Demo，不应出现空白气泡。

## 14.9 后台 NPC 对话

默认不调用 API：

```text
固定社会行为
→ SpeechEvent
→ 通用气泡/图标/模板
→ 社会结果
```

只有以下情况调用：

- 玩家在可听范围；
- 镜头聚焦；
- 黄金事件链关键节点；
- 用户主动查看详细对话；
- 调试开关强制。

---

# 15. 可观察性、回放与调试

## 15.1 运行目录

每次运行建立：

```text
runs/<run_id>/
  metadata.json
  config_snapshot/
  initial_snapshot.json
  events.jsonl
  decisions.jsonl
  actions.jsonl
  llm_requests.jsonl
  metrics.jsonl
  periodic_snapshots/
  errors.log
```

敏感内容可单独存储或脱敏，不提交 Git。

## 15.2 决策追踪

每次决策记录：

```yaml
decision_id: "decision_..."
state_version: 1024
agent_id: "npc_03"
trigger: "ACTION_COMPLETED"
candidate_ids: [...]
predictions:
  - candidate_id: "..."
    hard_preview: {}
    soft_prediction: {}
    utility_terms:
      needs: 0.43
      schedule: -0.10
      relationship: 0.12
      money: -0.04
      travel: -0.06
      repetition: 0.0
    total_score: 0.35
selected_candidate_id: "..."
resolver_result: "ACCEPTED"
random_draws: {}
model_version: "wm_v0_003"
```

## 15.3 快照

建议每 6 游戏小时保存一次，另在以下节点保存：

- 严重错误；
- 黄金事件链阶段；
- 模型热切换；
- LLM 结构化解析失败；
- 手动调试请求。

## 15.4 确定性

回放至少记录：

- 世界随机种子；
- 每个随机采样子种子；
- 配置 hash；
- Schema 版本；
- 模型 hash；
- Prompt 版本；
- 选择的候选；
- Resolver 冲突；
- 外部输入。

DeepSeek 文本不要求重新生成完全一致，但必须保存原始返回和最终结构化结果，以便回放社会状态。

---

# 16. 测试与验收

## 16.1 单元测试

必须覆盖：

- 时间计算；
- 需求范围；
- 家庭资金和库存；
- 行为前置条件；
- 对象能力查找；
- 槽位预留；
- 旅行；
- 工作迟到/缺勤；
- 工资；
- 候选生成；
- Utility 分解；
- 关系方向；
- 事件目击；
- ShareEvent 权限；
- 状态事务；
- 消息序列化；
- LLM Schema；
- 模型输出约束。

## 16.2 属性测试

建议使用 Hypothesis 或等价工具验证：

- 资金永不为负；
- 食品库存永不为负；
- 状态值不越界；
- 同一对象槽位不同时属于两个 Action；
- NPC 同时最多一个主动作；
- 未知事件不可传播；
- 不同地点 NPC 不能直接社交；
- 关闭地点不可开始消费行为；
- 失效 Proposal 不可提交；
- 模型不能修改不允许字段；
- 重放同一规则输入得到同一硬结果。

## 16.3 集成测试

至少包括：

1. Python 服务启动；
2. Unity Mock 客户端握手；
3. 资产注册成功；
4. 资产注册失败报告；
5. NPC 接收动作并抵达；
6. 导航失败；
7. 行为取消；
8. 重连后重新同步；
9. DeepSeek Mock 成功；
10. DeepSeek 超时模板回退；
11. 模型切换；
12. 回放运行。

## 16.4 Soak Test

至少运行：

- 7 游戏日快速测试；
- 30 游戏日发布测试；
- 多个随机种子；
- Heuristic 和 Neural 两种 OutcomeModel。

检查：

- 死循环；
- 内存增长；
- 事件爆炸；
- 关系全体极化；
- 全员永久 Idle；
- 全员永久工作；
- 需求持续归零；
- 家庭全体破产；
- 对象预留泄漏；
- LLM 队列堆积；
- Unity 连接失步。

## 16.5 黄金事件链

必须建立固定 fixture，确保可高概率或确定性触发：

### 第一天

1. `npc_03` 前一晚娱乐过晚；
2. 第二天 energy 低；
3. 候选中 Sleep 得分高于准时工作；
4. `npc_03` 迟到或缺勤；
5. 同事 `npc_04` 承担额外工作；
6. 生成 `WORK_LATE/WORK_MISSED` 和 `COWORKER_EXTRA_LOAD`；
7. `npc_04` tension 对 `npc_03` 上升。

### 当晚

8. `npc_04` 在酒吧遇见 `npc_08`；
9. `npc_04` 选择 ShareEvent；
10. `npc_08` 获得事件知识；
11. `npc_08` 对 `npc_03` 的未来社交评分发生变化。

### 第二天

12. `npc_03` 观察到与 `npc_04` 的高 tension；
13. 候选出现 Apologize、Chat、Avoid/Idle、Confront；
14. Apologize 被选择；
15. 结果可能接受或拒绝，并写入事件。

### 玩家

16. 玩家询问 `npc_08` 为什么对 `npc_03` 冷淡；
17. DeepSeek 只能根据 `npc_08` 已知的事件回答；
18. 台词与事件一致；
19. 若 API 不可用，模板仍可回答。

黄金链必须有：

- 自动测试；
- Headless 回放；
- Unity 演示预设；
- 决策追踪；
- QA 报告。

---

# 17. 分阶段执行计划

## M0：规范与仓库基线

### 目标

建立所有后续工作的稳定边界。

### 交付

- 仓库结构；
- pyproject；
- Unity 脚本目录；
- 配置 Schema；
- 协议版本；
- 核心枚举；
- 22 行为目录；
- 15 对象目录；
- 10 NPC 配置；
- 8 地点配置；
- Orchestrator 文件；
- CI 基线。

### 退出条件

- 所有配置可加载；
- Schema 测试通过；
- 不需要 Unity 或模型即可运行配置验证；
- Orchestrator 确认内容范围冻结。

## M1：Headless 硬规则垂直切片

### 目标

单 NPC 能完成生活与工作。

### 先实现行为

- Idle
- Sleep
- EatAtHome
- WorkShift

### 交付

- 时钟；
- 状态；
- 候选；
- Resolver；
- Action 生命周期；
- 需求；
- 日程；
- 工资；
- 事件账本；
- Headless CLI；
- 回放基础。

### 退出条件

- 1 NPC 连续运行 3 天；
- 不出现非法状态；
- 可重放；
- 决策日志完整。

## M2：Unity Bridge 垂直切片

### 目标

一个 NPC 在 Unity 中完成“家 → 工作 → 家”的表现闭环。

### 交付

- WebSocket；
- 握手；
- 资产注册；
- SemanticObject；
- InteractionSlot；
- NpcView；
- 导航；
- 动画语义接口；
- 基础调试面板。

### 退出条件

- Unity 可连接；
- 注册报告清楚；
- NPC 能走向床/工作站；
- 导航失败可回报；
- Python 状态不依赖动画成功。

## M3：完整规则小社会

### 目标

10 NPC、8 地点、22 行为全部由 HeuristicOutcomeModel 驱动。

### 交付

- 所有生活行为；
- 工作与采购；
- 所有社会行为；
- 家庭资金/食品；
- 关系；
- 事件知识；
- 背景对话模板；
- 30 日规则稳定测试。

### 退出条件

- 小社会可持续运行；
- 所有行为可在 Unity 表现；
- 无模型、无 API 仍能完整演示；
- Debug UI 可解释行为。

## M4：社会锚点与世界模型

### 目标

训练并接入 1M–3M 条件后果模型。

### 交付

- Anchor Producer/Reviewer 流程；
- 300–1000 锚点；
- 30万–100万训练行；
- 特征版本；
- 训练脚本；
- 评估报告；
- TorchOutcomeModel；
- 模型切换；
- CPU 性能测试。

### 退出条件

- 上线门槛全部通过；
- 神经模型不破坏硬状态；
- 黄金链不劣于基线；
- 可一键回退。

## M5：DeepSeek 玩家对话

### 目标

玩家能自然询问并影响有限社会行为。

### 交付

- API Gateway；
- PlayerSpeechParse；
- SpeechPlan；
- JSON 校验；
- 白名单；
- 缓存；
- 超时；
- 模板回退；
- Unity 输入与气泡；
- Mock 测试。

### 退出条件

- API 正常时自然语言可用；
- API 关闭时 Demo 仍完整；
- NPC 不泄露未知事件；
- 语言不能改写权威状态。

## M6：黄金链与展示版

### 目标

形成稳定可演示的两天社会事件链。

### 交付

- 固定世界配置；
- 固定种子；
- 引导演示模式；
- 自动回放；
- 调试面板；
- 性能报告；
- README；
- 架构图；
- 使用说明；
- 已知限制。

### 退出条件

- 从空启动可完成演示；
- 30 日 soak test；
- Unity 演示无阻塞错误；
- QA 发布清单通过。

---

# 18. Orchestrator 的并行策略

## 18.1 可以并行

M0 Schema 初步冻结后：

- Simulation Core 可以做 Headless；
- Unity Bridge 可以做 Mock 协议；
- QA 可以同步建立测试基线；
- LLM 线程可以先写 Mock 和 Schema；
- Model 线程可以先做特征接口和 HeuristicOutcomeModel Protocol。

## 18.2 不应过早并行

以下必须等待：

- 社会锚点生产必须等关系/行为 Schema 冻结；
- 大规模数据生成必须等规则基线稳定；
- 神经模型训练必须等特征版本冻结；
- DeepSeek Prompt 正式编写必须等 SpeechPlan/Knowledge 权限冻结；
- Unity 完整对象校验必须等对象目录冻结；
- 黄金链必须等事件和社会行为完成。

## 18.3 每个阶段的集成优先

每完成一组功能，先合并成可运行垂直切片，再开始下一组。禁止多个线程各自积累大规模未集成分支。

---

# 19. 关键风险与处理

| 风险 | 表现 | 首选处理 |
|---|---|---|
| 范围膨胀 | 不断增加需求、行为、地点 | 以 V0 非范围和 ADR 阻止 |
| 模型没有价值 | 规则已经能完全替代 | 重点验证未见组合、概率校准和社会差异 |
| 社会数据自相矛盾 | 同一场景标签方向相反 | Producer/Reviewer、覆盖矩阵、锚点版本 |
| NPC 行为循环 | 反复 WatchTV/Chat | repetition penalty、冷却、日程、阈值 |
| 地点过空 | NPC 很少相遇 | 8 地点上限、班次交汇、公共节点 |
| 全员冲突 | tension 累积无修复 | 衰减、道歉、事件上限、模型校准 |
| 全员友好 | 社会变化无意义 | 个性、拒绝、负面事件、资源/日程冲突 |
| Unity 与 Python 失步 | 动作已结束但动画未到 | state_version、动作阶段、超时、重同步 |
| 导航失败 | 场景路径不通 | Unity 回报、取消、Editor 校验 |
| API 延迟 | 玩家对话卡住 | 局部等待、全局继续、超时模板 |
| API 幻觉 | NPC 说出未知事实 | allowed IDs、结构化计划、Prompt、后验检查 |
| 数据泄漏 | 测试结果虚高 | episode/scenario 分组拆分 |
| 模型改硬状态 | 资源或所有权错误 | 输出 mask、事务校验、违规率门槛 |
| 调试困难 | 不知道为何选择 | 决策追踪和 Unity Top-K 面板 |
| Codex 线程冲突 | 多线程改同一接口 | 路径所有权、Schema 线程、任务包、ADR |

---

# 20. 首版 Definition of Done

项目只有同时满足以下条件才算 V0 完成：

## 模拟

- [ ] 10 NPC、4 家庭、8 地点配置可加载；
- [ ] 22 个行为全部实现；
- [ ] 15 类对象全部可注册；
- [ ] 5 项需求、4 项人格、2 项情绪、4 项关系有效；
- [ ] 工作、工资、采购和消费闭环有效；
- [ ] 事件账本和有限知识传播有效；
- [ ] Headless 可运行 30 游戏日；
- [ ] 同种子硬规则可复现；
- [ ] 无负资金、负库存、越界状态或槽位冲突。

## 世界模型

- [ ] HeuristicOutcomeModel 可独立运行；
- [ ] 神经模型参数量和性能符合目标；
- [ ] 数据和特征有版本；
- [ ] 概率预测有校准报告；
- [ ] 输出约束违规提交为 0；
- [ ] 可运行时切换模型；
- [ ] 模型失败时回退规则基线；
- [ ] 黄金链中模型行为可解释。

## Unity

- [ ] Unity 与 Python 可握手；
- [ ] 场景资产注册可验证；
- [ ] NPC 可导航到对象槽位；
- [ ] 所有行为有表现语义；
- [ ] 导航失败和断线可恢复或清楚报告；
- [ ] 玩家可选择 NPC 并发起对话；
- [ ] 调试 UI 展示候选、预测、评分与选择；
- [ ] 用户资产与 Codex 脚本边界没有混乱。

## LLM

- [ ] DeepSeek API 密钥不入库；
- [ ] 玩家语言解析符合固定 Schema；
- [ ] SpeechPlan 只包含允许信息；
- [ ] NPC 不引用未知事件；
- [ ] 超时、失败和无 API 时有模板回退；
- [ ] 世界持续运行不依赖 API；
- [ ] 请求和结果可追踪。

## 工程

- [ ] CI 通过；
- [ ] 单元、属性、集成、soak 测试通过；
- [ ] 黄金事件链可自动运行；
- [ ] 运行日志和回放可用；
- [ ] README、启动说明、架构图、已知限制完整；
- [ ] Orchestrator 状态与所有 handoff 更新；
- [ ] 无未记录的关键架构决策。

---

# 21. Orchestrator 开工顺序

Orchestrator 接到本规范后，应按以下顺序派发第一批任务：

1. `THREAD-SCHEMA-CONTRACTS`
   - 建立仓库骨架；
   - 定义核心枚举、Pydantic Schema、配置文件；
   - 固定 22 行为与 15 对象；
   - 生成协议示例。

2. `THREAD-QA-OBSERVABILITY`
   - 建立 CI、测试目录和最小配置验证；
   - 编写范围/Schema 回归测试；
   - 建立运行目录与日志格式。

3. `THREAD-SIMULATION-CORE`
   - 在 Schema 合并后实现 M1；
   - 只做 Idle、Sleep、EatAtHome、WorkShift；
   - 建立 Headless CLI 和动作生命周期。

4. `THREAD-UNITY-BRIDGE`
   - 基于协议 Mock 实现连接和资产注册；
   - 不等待完整模拟器；
   - 使用录制消息测试。

5. `THREAD-DATA-WORLD-MODEL`
   - 先定义 `OutcomeModel` 接口；
   - 实现 Recorded/Heuristic stub；
   - 暂不生成大规模数据。

6. `THREAD-LLM-DIALOGUE`
   - 先定义 Speech Schema 和 Mock；
   - 暂不接真实 API，直到事件知识边界稳定。

首个集成目标不是“训练模型”，而是：

> 一个 Headless NPC 在规则基线下从家中起床、吃饭、前往工作、完成工作并回家；同一行为序列能够通过 Unity Mock 或 Unity 灰盒表现出来。

完成该垂直切片后，再扩展到 10 人小社会。

---

# 22. 最终架构摘要

```text
固定世界配置
  ├─ 10 NPC
  ├─ 4 家庭
  ├─ 8 地点
  ├─ 22 行为
  └─ 15 对象类型
          ↓
Python Town Core
  ├─ 权威硬状态
  ├─ 候选生成
  ├─ 行为生命周期
  ├─ 两阶段 Resolver
  ├─ 事件账本
  ├─ 有限知识传播
  └─ 回放/调试
          ↓
OutcomeModel
  ├─ Heuristic 基线
  └─ 1M–3M 神经世界模型
          ↓
Utility Scorer
          ↓
固定行为 Proposal
          ↓
Unity Bridge
  ├─ 导航
  ├─ 对象槽位
  ├─ 动画
  ├─ 气泡
  └─ 调试 UI

玩家语言
  ↓
DeepSeek：结构化解析
  ↓
固定社会行为 / 问询
  ↓
Town Core + OutcomeModel
  ↓
SpeechPlan
  ↓
DeepSeek：自然语言表达
```

首版的核心判断标准始终是：

> 能否用有限内容和低成本模型，在 Unity 中稳定地展示一个具有工作、生活、娱乐、事件传播、关系变化和语言交互的小社会，并让每个关键行为都可追踪、可解释、可重放。



---

# 附录 A：建议的默认人口种子

该表用于首个可复现 Demo 和黄金链。显示名称、美术设定可以更换，但 ID、家庭、工作与初始人格应在一个版本周期内稳定。

| NPC | 家庭 | 工作 | 班次 | Sociability | Discipline | Frugality | Irritability | 设计用途 |
|---|---|---|---|---:|---:|---:|---:|---|
| `npc_01` | A | 咖啡馆 | 06–14 | 0.70 | 0.80 | 0.40 | 0.20 | 稳定早班、社交型 |
| `npc_02` | A | 工坊 | 08–16 | 0.40 | 0.70 | 0.60 | 0.30 | 稳定同事基线 |
| `npc_03` | B | 工坊 | 08–16 | 0.60 | 0.35 | 0.30 | 0.40 | 黄金链中的迟到者 |
| `npc_04` | B | 工坊 | 08–16 | 0.50 | 0.85 | 0.55 | 0.25 | 黄金链中的受影响同事 |
| `npc_05` | B | 商店 | 09–17 | 0.55 | 0.70 | 0.80 | 0.20 | 节俭型、家庭采购倾向 |
| `npc_06` | C | 咖啡馆 | 14–22 | 0.80 | 0.50 | 0.30 | 0.35 | 晚间公共社交节点 |
| `npc_07` | C | 商店 | 09–17 | 0.40 | 0.75 | 0.65 | 0.15 | 低冲突稳定角色 |
| `npc_08` | D | 咖啡馆 | 14–22 | 0.75 | 0.60 | 0.40 | 0.30 | 黄金链事件接收者 |
| `npc_09` | D | 工坊 | 08–16 | 0.30 | 0.80 | 0.70 | 0.20 | 安静、责任导向 |
| `npc_10` | D | 咖啡馆 | 06–14 | 0.65 | 0.55 | 0.20 | 0.45 | 消费和冲突倾向较高 |

建议家庭初始资源：

| 家庭 | 资金 | 食品 |
|---|---:|---:|
| A | 50,000 | 8 |
| B | 42,000 | 6 |
| C | 38,000 | 5 |
| D | 46,000 | 7 |

建议默认关系：

- 同家庭：
  - familiarity `0.75–0.95`
  - affinity `0.50–0.75`
  - trust `0.55–0.80`
  - tension `0.05–0.20`
- 同事：
  - familiarity `0.30–0.55`
  - affinity `0.35–0.55`
  - trust `0.35–0.60`
  - tension `0.05–0.15`
- 其他：
  - familiarity `0.00–0.20`
  - affinity `0.40–0.50`
  - trust `0.30–0.45`
  - tension `0.00–0.05`

关系初始化必须由固定种子生成并写入配置快照，不应每次启动随机变化。

---

# 附录 B：Codex 语义样本与 Prompt Fixture 生产

V0 不训练语言模型，但仍需要结构化测试语料，确保 DeepSeek Prompt 和 Schema 稳定。

## B.1 Parse Fixture

目标数量：

```text
每个 SpeechAct 20–40 条
总计约 250–500 条
```

每条包含：

```yaml
fixture_id: "parse_ask_event_001"
input_text: "你为什么对小陈这么冷淡？"
conversation:
  target_agent_id: "npc_08"
candidate_agent_ids: ["npc_03", "npc_04", "npc_08"]
candidate_events:
  - event_id: "event_00001234"
    safe_summary: "npc_03 missed work; npc_04 took extra load"
expected:
  speech_act: "ASK_ABOUT_EVENT"
  referenced_agent_ids: ["npc_03"]
  allowed_event_ids: ["event_00001234"]
  requires_clarification: false
forbidden:
  invented_event_ids: true
  authority_mutation: true
tags:
  - "implicit_reason_question"
review_status: "APPROVED"
```

覆盖：

- 明确表达；
- 口语；
- 指代；
- 拼写错误；
- 多意图；
- 无匹配事件；
- 有歧义；
- 恶意诱导 NPC 泄露未知信息；
- 玩家声称不存在事实；
- 邀请；
- 道歉；
- 对质；
- 告别。

## B.2 Verbalization Fixture

每条提供 SpeechPlan 和验证点：

```yaml
fixture_id: "verbalize_unknown_event_001"
speech_plan:
  speech_act: "ANSWER_UNKNOWN"
  allowed_event_ids: []
  style:
    directness: 0.5
    warmth: 0.4
assertions:
  must_express_lack_of_knowledge: true
  must_not_invent_fact: true
  max_sentences: 2
```

不要求文本逐字一致，而检查：

- 是否使用允许事实；
- 是否符合说话风格；
- 是否过长；
- 是否泄露内部 ID；
- 是否产生未授权承诺；
- 是否声称状态已改变。

## B.3 Codex 线程分工

Orchestrator 可在 `THREAD-LLM-DIALOGUE` 内部分派：

- `fixture-producer`：生成有限批次；
- `fixture-reviewer`：独立检查；
- `prompt-evaluator`：用 Mock 或真实 API 跑评估；
- `regression-curator`：把失败样本加入回归集。

每批不宜过大。建议 25–50 条一批，便于审查。

## B.4 不允许的用法

- 不使用 ChatGPT/Codex 前端做无人监管的百万级自动抽取；
- 不把 Codex 输出未经 Schema 校验直接当训练真相；
- 不因一次 Prompt 成功删除模板回退；
- 不把测试 Fixture 混入世界模型测试集而不标记来源。

---

# 附录 C：建议的开发命令接口

具体命令可由 Codex 调整，但仓库最终应提供等价入口：

```bash
# 验证配置与 Schema
python -m town_core.cli validate-config --config config/v0

# 运行 Headless
python -m town_core.cli run-headless \
  --config config/v0 \
  --seed 12345 \
  --days 3 \
  --out runs/demo

# 重放
python -m town_core.cli replay --run runs/demo

# 启动 Unity Bridge 服务
python -m town_core.cli serve \
  --config config/v0 \
  --host 127.0.0.1 \
  --port 8765

# 生成候选转移数据
python -m training.generate_dataset \
  --config config/v0 \
  --episodes 1000 \
  --out data/generated/v0.parquet

# 验证锚点
python -m training.anchors.validate data/anchors/v0

# 训练
python -m training.train \
  --config config/v0/model.yaml \
  --data data/generated/v0.parquet \
  --out models/wm_v0_001

# 评估
python -m training.evaluate \
  --model models/wm_v0_001 \
  --suite config/v0/eval.yaml \
  --out reports/wm_v0_001

# 运行全部 Python 测试
pytest

# 格式与静态检查
ruff check .
mypy python/town_core
```

Unity 应提供对应 Editor 菜单和测试说明。

---

# 附录 D：首版配置冻结检查表

Orchestrator 在 M0 结束时逐项确认：

- [ ] 10 个 NPC ID；
- [ ] 4 个 Household ID；
- [ ] 8 个 Location ID；
- [ ] 每名 NPC 的家庭、工作和班次；
- [ ] 22 个 Behavior ID；
- [ ] 15 个 Object Type；
- [ ] 每个行为的前置、对象、时长、硬效果、软 mask、输出范围；
- [ ] 5 个需求及方向；
- [ ] 4 个人格及方向；
- [ ] 2 个情绪及范围；
- [ ] 4 个关系及方向；
- [ ] 事件枚举；
- [ ] 经济价格和工资；
- [ ] 地点旅行矩阵；
- [ ] Unity 动画语义；
- [ ] WebSocket 协议版本；
- [ ] DeepSeek Speech Schema；
- [ ] 黄金事件链涉及的初始条件；
- [ ] 数据 Feature Version；
- [ ] 所有非范围条目进入测试或文档约束。

