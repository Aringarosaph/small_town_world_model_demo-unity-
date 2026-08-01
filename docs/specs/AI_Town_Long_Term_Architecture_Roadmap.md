# AI 小镇：长期架构演化路线与完整版愿景

> 文档状态：`LONG_TERM_REFERENCE`  
> 目标读者：Codex Orchestrator、未来架构线程、模型线程、Unity 接口线程与项目维护者  
> 文档用途：记录首版完成后的可演化方向、阶段门槛、完整版目标形态与必须长期保持的架构原则  
> 当前实施基准：`AI_Town_V0_Orchestrator_Implementation_Spec.md`  
> 注意：本文件不是要求首版提前实现的任务清单。任何长期能力都必须在前一阶段通过验收后再进入实施。

---

# 0. 如何使用本规划

本规划用于回答三个问题：

1. V0 跑通以后，下一步最值得扩展什么；
2. 哪些结构应在 V0 保留接口，但不应提前实现；
3. 最终“完整版”应当是什么，而不至于在迭代中失去方向。

Orchestrator 必须把长期规划视为：

- 设计约束；
- ADR 参考；
- 路线图；
- 阶段性候选池；

而不是待办列表。

任何长期功能进入正式开发前，必须有一份新的阶段实施规范，明确：

```text
为什么现在需要
解决了什么已观察问题
需要修改哪些 Schema
迁移如何完成
新的验收是什么
是否影响 Unity 资产需求
是否增加运行成本
```

不得仅因为本文件提到某能力，就在 V0 或下一小版本中顺手加入。

---

# 1. 完整版的一句话愿景

完整版不是一个试图复制《模拟人生》内容体量的游戏，而是一个：

> **可以在家用电脑上持续运行、由有限但丰富的生活与社会行为组成、具备显式权威世界、个体主观信念、事件传播、承诺、关系、机构和短程未来推演，并通过 Unity 清晰表现其因果过程的小型社会世界模型实验平台。**

它应当让玩家观察到：

- 角色有身体需求和日程；
- 家庭共享资源并相互承担责任；
- 工作地点形成同事关系与压力；
- 公共场所形成偶遇与信息传播；
- 角色对同一事件持有不同认识；
- 承诺、失约、帮助、争执和道歉留下长期后果；
- 角色会根据人格、关系、信念和未来预测选择行为；
- 玩家语言能够改变角色的主观状态，但不能随意改写真实世界；
- 社会事件能跨越数日形成后续链条；
- 所有重要行为仍然可解释、可重放、可调试。

完整版的重点不是无限生成，而是：

> **有限规则与有限资产之上的高组合性、长期因果性和社会意义。**

---

# 2. 完整版目标规模

完整版仍以单机小社会为目标，而不是万人级社会实验。

## 2.1 推荐规模

| 项目 | V0 | 中期 | 完整版研究目标 |
|---|---:|---:|---:|
| NPC | 10 | 20–30 | 40–60 |
| 家庭 | 4 | 6–10 | 12–16 |
| 高层地点 | 8 | 12–18 | 18–24 |
| 同时高精度活跃 NPC | 10 | 10–20 | 12–24 |
| 高层行为 | 22 | 35–60 | 60–100 |
| 交互对象类型 | 15 | 25–45 | 40–80 |
| 需求 | 5 | 5–7 | 6–8 |
| 人格轴 | 4 | 5–8 | 6–10 |
| 关系连续维度 | 4 | 6–8 | 6–10 |
| 事件类型 | 20–30 | 50–100 | 100–200 |
| Claim Predicate | 无完整系统 | 30–80 | 80–200 |
| 模型规模 | 1–3M | 5–15M | 20–50M，必要时上限约 100M |
| 规划深度 | 1 步 | 2–3 步 | 3–5 个宏观步骤 |
| LLM | API 解析/表达 | 增加摘要与反思 | API/本地可切换、多级调用 |

## 2.2 高精度与低精度并存

完整版不要求所有 NPC 每时每刻同等精细。

### 高精度层

适用于：

- 玩家附近；
- 正在与玩家交互；
- 正在发生重要社会事件；
- 重要家庭或机构；
- 需要世界模型 Rollout 的决策。

运行：

- 完整局部观察；
- 社会世界模型；
- 事件与信念；
- 可见自然语言；
- Unity 详细表现。

### 中精度层

适用于：

- 当前场景外但仍活跃；
- 工作、家庭、公共活动；
- 普通社会事件。

运行：

- 固定行为；
- Batch 决策；
- 简化空间；
- SpeechEvent 不生成完整文本。

### 低精度层

适用于：

- 长时间不在玩家关注范围；
- 休眠家庭；
- 远离事件的 NPC。

运行：

- 日程段；
- 需求聚合；
- 宏观事件；
- 关系和资源的小步更新；
- 不运行逐行为表现。

完整版的本地流畅性主要依赖认知 LOD，而不是无限压缩模型。

---

# 3. 必须长期保持的架构原则

## 3.1 权威状态与学习模型分离

无论模型多强，以下内容长期由规则系统维护：

- 实体存在；
- 位置与可达性；
- 时间；
- 所有权；
- 金钱与物品数量；
- 对象占用；
- 工作合同；
- 房屋归属；
- 角色生存状态；
- 已提交承诺；
- 事件账本；
- 机构规则；
- 玩家已确认选择。

学习模型可以预测、建议、评价和解释，但不能成为唯一真相源。

## 3.2 真实、观察、信念、意图、表达分离

完整系统必须明确区分：

```text
World Fact
Observation
Belief
Goal / Intent
Speech Claim
Surface Language
```

例如：

```text
真实：A 拿走了钱
观察：B 只看到 A 从房间出来
信念：B 认为 A 有 65% 可能拿了钱
主张：C 告诉 D 是 A 拿的
意图：D 想当面询问 A
表达：D 说“昨晚你在那里做什么？”
```

任何模块不得把这些层合并成一段不可验证文本。

## 3.3 固定行为先于自由语言

即使完整版有更丰富语言，世界中的可执行行为仍来自行为目录、对象能力和机构规则。

LLM 可以：

- 解析行为意图；
- 决定语言策略；
- 表达；
- 提出候选内容；
- 生成非权威叙述。

LLM 不可以：

- 发明没有资产和实现的新动作；
- 直接创建关键物品；
- 绕过前置条件；
- 擅自赋予角色新权限。

## 3.4 语义资产契约长期存在

Unity 中每个具有世界意义的对象必须通过语义能力暴露给模拟器：

```text
Object Type
Capability
Slots
Location
Access Rule
Animation Semantic
Resource Semantics
```

美术可以替换，逻辑不依赖具体模型名或场景坐标。

## 3.5 事件溯源长期存在

所有重要社会后果必须能追溯到事件：

```text
关系为什么下降
NPC 为什么知道
谁承诺了什么
为什么冲突升级
为什么工作绩效变化
```

模型潜在状态可以辅助预测，但不能替代可审查事件账本。

## 3.6 多频率、事件驱动、Batch

完整版仍不采用“所有 NPC 每秒调用一次完整 Agent”。

必须继续使用：

- 模拟 Tick；
- 认知触发；
- 事件队列；
- Agent Batch；
- 公共世界编码复用；
- 重要决策 Rollout；
- 异步语言；
- 两阶段提交。

## 3.7 玩家可理解性优先于最优智能

一个无法解释的最优策略，不一定比一个有明显动机、可被玩家理解的次优策略更适合社会模拟。

完整系统仍需提供：

- 当前目标；
- 关键需求；
- 重要记忆；
- 对他人的信念；
- 候选预测；
- 选择理由；
- 事件来源。

---

# 4. 完整版分层架构

推荐长期架构分为九层。

## 4.1 Layer 1：Authority / Physical World

负责：

- 时间；
- 空间；
- 地点；
- 房间；
- 可达性；
- 角色位置；
- 对象与槽位；
- 资源；
- 所有权；
- 动作生命周期；
- 机构开放时间；
- 工作与工资；
- 事务提交。

实现性质：

- 确定性；
- 可回放；
- 事件溯源；
- 不依赖 LLM；
- 不依赖世界模型可用性。

## 4.2 Layer 2：Semantic Affordance

负责把 Unity 资产转为行为能力：

```text
BED → SLEEP
FRIDGE → PREPARE_MEAL
TABLE → EAT / SOCIALIZE
BAR → BUY_DRINK / WORK_SERVICE
NOTICE_BOARD → READ_PUBLIC_INFORMATION
PHONE → CALL / MESSAGE
```

长期应支持：

- 能力标签；
- 前置条件；
- 多槽位；
- 资源输入/输出；
- 对象状态；
- 权限；
- 组合对象；
- 行为表现序列；
- 机构规则。

## 4.3 Layer 3：Agent Body and Routine

负责：

- 需求；
- 健康或体力；
- 日程；
- 习惯；
- 当前动作；
- 工作；
- 家庭责任；
- 基础 Utility；
- 休眠 LOD。

这一层应当即使完全关闭神经模型，也能让角色基本生活。

## 4.4 Layer 4：Social and Cognitive State

负责：

- 人格；
- 情绪；
- 有向关系；
- 事件记忆；
- Claim/Belief；
- 来源可靠度；
- 承诺；
- 未解决冲突；
- 目标；
- 当前意图；
- 对他人的浅层估计。

## 4.5 Layer 5：Household and Institutions

负责：

- 家庭；
- 工作场所；
- 兴趣群体；
- 公共服务；
- 规则和规范；
- 职位；
- 集体资源；
- 共享责任；
- 声誉；
- 机构事件。

## 4.6 Layer 6：Learned Social World Model

负责：

- 候选行为软后果；
- 多实体关系变化；
- 信念更新；
- 事件概率；
- 目标持续；
- 对方回应；
- 短程想象；
- 不确定性；
- Value/Utility 残差。

## 4.7 Layer 7：Agent Policy and Planner

负责：

- 生成固定候选；
- 普通行为直接评分；
- 重要行为 Top-K；
- 3–5 步宏观 Rollout；
- 承诺和日程约束；
- 只执行第一步；
- 重新观察和规划。

## 4.8 Layer 8：Language and Narrative Interface

负责：

- Text → SpeechEvent；
- SpeechPlan → Text；
- 事件摘要；
- 记忆摘要；
- 角色反思；
- 玩家问询；
- 关键对话；
- 日记、短信、公告等表现。

不拥有权威状态。

## 4.9 Layer 9：Unity Presentation and Observability

负责：

- 场景；
- 导航；
- 动画；
- 表情；
- 道具；
- 摄像机；
- UI；
- 调试可视化；
- 时间控制；
- 玩家输入；
- 世界关系和事件浏览。

---

# 5. 完整版实体图

## 5.1 核心实体类型

```text
Person
Household
Location
Room
Object
Institution
JobRole
Group
Event
Claim
Commitment
Goal
Plan
Norm
Conversation
Action
ResourceAccount
```

## 5.2 主要关系边

### 空间与所有权

```text
LOCATED_AT
CONTAINS
LIVES_IN
OWNS
HAS_ACCESS_TO
RESERVED_BY
```

### 社会身份

```text
HOUSEHOLD_MEMBER_OF
WORKS_AT
HAS_ROLE
MEMBER_OF
SUPERVISES
NEIGHBOR_OF
```

### 人际关系

```text
KNOWS
LIKES
TRUSTS
RESPECTS
FEARS
RESENTS
DEPENDS_ON
```

连续关系不一定全部拆成图边对象；可以由一条 typed relationship 保存多维状态。

### 认知

```text
BELIEVES_CLAIM
KNOWS_EVENT
HEARD_FROM
WITNESSED
ESTIMATES_GOAL_OF
```

### 规范与承诺

```text
PROMISED_TO
OWES_DUTY_TO
BOUND_BY_NORM
VIOLATED_NORM
EXPECTED_BY
```

### 行为

```text
PERFORMED
AFFECTED
TARGETED
WITNESSED_ACTION
CAUSED_EVENT
```

## 5.3 图不是唯一存储形式

完整系统可以组合：

- 关系数据库或结构化对象；
- 事件日志；
- 稀疏图索引；
- 模型 Tensor；
- LLM 检索摘要。

不要为了“使用图神经网络”把所有内容强行变成同一种图结构。


# 6. 行为系统的长期演化

## 6.1 从固定行为到“受控组合行为”

V0 每个行为由手写定义直接绑定对象和动画。完整版仍不允许自由动作生成，但可以把行为拆成可复用层级：

```text
Behavior Intent
→ Preconditions
→ Required Affordances
→ Resource Reservations
→ Execution Script
→ Hard Effects
→ Learned Soft Effects
→ Presentation Semantics
```

例如：

```text
InviteToDinner
→ Ask/Accept
→ TravelTo(home)
→ AcquireMeal
→ ReserveSeats
→ EatTogether
→ ConversationWindow
→ Relationship/Event Resolution
```

这不是 LLM 自由拼装，而是由已注册的 Composite Behavior 模板生成。

## 6.2 行为层级

### Primitive

表现和规则中的最小操作：

- Move；
- Face；
- Sit；
- PickUp；
- PutDown；
- Consume；
- Pay；
- Speak；
- Wait；
- UseObject。

Primitive 不直接参与 Agent 高层选择。

### Atomic Behavior

可单独选择和结算：

- Sleep；
- Eat；
- Shower；
- WorkTask；
- Chat；
- Buy；
- Read；
- Call。

### Composite Behavior

由固定模板编排：

- PrepareAndEatMeal；
- GoToWorkShift；
- VisitFriend；
- InviteToDrink；
- HostDinner；
- ResolveConflict；
- AttendGroupEvent。

### Joint Behavior

多名角色共享一个事务：

- 一起吃饭；
- 聚会；
- 开会；
- 共同娱乐；
- 协作工作；
- 争执；
- 集体活动。

Joint Behavior 必须由中央 Resolver 管理参与者、资源、退出和失败，而不是让多个 Agent 各自认为活动已成立。

## 6.3 动作通道

为了支持更自然的并发行为，完整版可引入通道：

```text
LOCOMOTION
POSTURE
HANDS
ATTENTION
SPEECH
PRIMARY_ACTIVITY
```

例如坐着吃饭并聊天：

```text
POSTURE = SIT
HANDS = EAT
SPEECH = CHAT
PRIMARY_ACTIVITY = MEAL
```

并发必须由行为定义显式允许，不能依赖模型猜测。

## 6.4 行为资产契约升级

每个行为最终应声明：

```yaml
behavior_id:
required_capabilities:
optional_capabilities:
actor_roles:
target_roles:
channels:
preconditions:
reservations:
execution_graph:
hard_effects:
soft_effect_schema:
event_schema:
animation_semantics:
prop_semantics:
audio_semantics:
camera_interest:
interrupt_policy:
recovery_policy:
```

Orchestrator 在新增行为前必须要求：

1. 系统价值；
2. 需要的对象；
3. 需要的动画语义；
4. 是否复用已有 Primitive；
5. 产生哪些新状态；
6. 是否进入世界模型；
7. 测试场景；
8. Unity 资产责任人。

## 6.5 行为内容扩展优先级

推荐顺序：

### 生活增强

- PrepareMeal；
- CleanHouse；
- UseBathroom；
- Exercise；
- Read；
- Phone/Message；
- HouseholdChore。

### 工作增强

- 多种工作任务；
- 工作休息；
- 交接；
- 帮助同事；
- 请求调班；
- 绩效事件。

### 社交增强

- AskForHelp；
- OfferHelp；
- Thank；
- Promise；
- Remind；
- Refuse；
- Reconcile；
- Gossip；
- KeepSecret；
- IntroducePeople。

### 群体增强

- 聚餐；
- 小型聚会；
- 会议；
- 共同兴趣活动；
- 社区事件。

任何扩展都应优先产生跨系统反馈，而不是只增加动画种类。

---

# 7. 社会结构的长期演化

## 7.1 家庭

家庭不应只是共享金钱的容器。中期后可以增加：

- 家庭日程；
- 家务责任；
- 照护责任；
- 共同购物；
- 共享娱乐；
- 家庭预算偏好；
- 家庭冲突；
- 家庭计划；
- 家庭声誉。

但仍应限制为少量明确责任，例如：

```text
BUY_GROCERIES
COOK_MEAL
CLEAN_SHARED_SPACE
PAY_SHARED_COST
ATTEND_FAMILY_EVENT
```

责任可以生成 Commitment。

## 7.2 工作场所

工作场所是社会关系和资源依赖的重要节点。可扩展：

- 岗位角色；
- 任务负载；
- 同事协作；
- 主管；
- 工作评价；
- 调班；
- 请假；
- 工作场所规范；
- 晋升或警告。

完整系统不需要模拟真实企业全部细节，但必须让：

```text
缺勤
→ 他人负载
→ 同事关系
→ 主管评价
→ 收入/岗位
```

形成反馈。

## 7.3 兴趣群体

可以加入少量 Group：

- 运动；
- 阅读；
- 音乐；
- 游戏；
- 社区志愿活动。

Group 的价值在于稳定制造跨家庭关系，而不是无限标签。

Group 状态：

```text
members
meeting_schedule
preferred_location
shared_interest
group_cohesion
recent_events
```

## 7.4 公共场所作为社会路由器

每个地点应有明确社会语义：

| 地点 | 主要接触模式 |
|---|---|
| 家 | 高隐私、家庭和亲密互动 |
| 工作 | 重复接触、责任冲突、协作 |
| 酒吧/咖啡馆 | 自愿公共社交、信息传播 |
| 商店 | 短时偶遇、消费 |
| 公园 | 低压力偶遇、群体活动 |
| 社区中心 | 计划性群体活动、公告 |
| 电话/消息 | 跨地点低成本交流 |

地点设计应控制：

- 谁会相遇；
- 互动持续多久；
- 隐私；
- 目击者；
- 行为可用性；
- 信息传播速度。

## 7.5 有限经济

完整版仍不需要宏观经济模拟，但可以增加：

- 个人与家庭账户；
- 固定账单；
- 工资差异；
- 有限物品库存；
- 服务消费；
- 预算偏好；
- 临时经济压力；
- 借钱或帮助。

经济变量必须服务社会行为，例如：

```text
没钱参加活动
→ 拒绝邀请
→ 隐瞒原因
→ 关系误解
```

而不是只成为独立数值小游戏。

---

# 8. Claim、Belief 与信息传播

## 8.1 为什么需要升级

V0 只保存“某 NPC 知道某事件”。这无法表达：

- 不确定；
- 误解；
- 谎言；
- 多个来源；
- 来源可靠性；
- 事件细节分歧；
- 否认；
- 澄清。

中期应引入 Claim。

## 8.2 Claim

```yaml
claim_id: "claim_001"
predicate_id: "agent_missed_work"
arguments:
  agent: "npc_03"
  workplace: "workshop"
time_range:
  start: 2480
  end: 2960
polarity: true
origin_type: "EVENT_DERIVED"
origin_event_ids: ["event_123"]
```

Claim 是可被谈论的命题，不等于某个 NPC 相信它。

## 8.3 Belief

```yaml
agent_id: "npc_08"
claim_id: "claim_001"
belief_probability: 0.72
source_reliability: 0.66
evidence_event_ids: ["event_share_77"]
last_updated_minute: 3200
salience: 0.58
```

Belief 更新可由：

- 直接观察；
- 参与；
- 他人转述；
- 多来源一致；
- 反证；
- 来源被证明不可靠；
- 时间衰减；
- 世界模型；

共同决定。

## 8.4 Speech Claim

NPC 说出命题时记录：

```text
speaker
listeners
claim
asserted_probability
communicative_intent
truthfulness_intent
disclosure_scope
```

必须区分：

- 说话者相信；
- 说话者声称；
- 命题真实状态；
- 听者最终相信。

## 8.5 浅层 Theory of Mind

完整版本只建议保留一层：

```text
Agent A estimates:
- B knows Claim X
- B wants Goal Y
- B is likely to accept Action Z
```

不做无限递归。

估计可以是稀疏的，只为重要角色、重要 Claim 和当前决策保存。

## 8.6 传播机制

传播受：

- 同地点/联系方式；
- 隐私；
- 关系；
- 事件重要度；
- 角色 gossip 倾向；
- 来源可靠性；
- 目标兴趣；
- 机构渠道；
- 重复曝光；

影响。

信息曝光本身应成为世界状态，而不是把完整全局事件列表塞给所有 Agent。

---

# 9. 承诺、责任与规范

## 9.1 Commitment

完整社会演化需要“未来义务”。建议实体：

```yaml
commitment_id: "commit_001"
promisor_id: "npc_03"
promisee_ids: ["npc_04"]
commitment_type: "COVER_WORK_SHIFT"
created_minute: 5000
due_window:
  start: 6000
  end: 6480
conditions: []
status: "ACTIVE"
importance: 0.75
related_event_ids: []
```

状态：

```text
PROPOSED
ACCEPTED
ACTIVE
FULFILLED
BROKEN
CANCELLED
FORGIVEN
```

承诺影响：

- 日程；
- 候选生成；
- Utility；
- 关系；
- 事件；
- 对话。

## 9.2 Household Duty

家庭责任可视为特殊 Commitment：

```text
轮到谁购物
谁负责做饭
谁答应陪同活动
谁负责支付某项费用
```

## 9.3 Norm

Norm 是机构或群体规则：

```yaml
norm_id: "work_arrive_on_time"
scope_type: "INSTITUTION"
scope_id: "workshop"
trigger: "WORK_LATE"
expected_response:
  supervisor_disapproval: 0.6
  coworker_tension: 0.3
severity: 0.5
```

Norm 不应该由 LLM 即兴发明。它来自配置或受控系统。

## 9.4 Reputation

声誉可以由已传播 Claim 聚合，而不是独立无来源数值。

例如：

```text
reliability_reputation
helpfulness_reputation
sociability_reputation
conflict_reputation
```

每项必须可以追溯到事件和了解它的人群。

---

# 10. 目标、计划与记忆

## 10.1 目标层级

推荐三层：

### Drive

来自需求、责任和人格：

```text
保持健康
履行工作
维持家庭
获得社交
节约资金
```

### Goal

持续数小时到数日：

```text
补充家庭食物
修复与 npc_04 的关系
完成本周工作
参加周末聚会
```

### Intent

当前下一步：

```text
去商店
向 npc_04 道歉
邀请 npc_08 去酒吧
```

## 10.2 计划

计划只保存少量宏观步骤，并允许随时重规划：

```yaml
plan_id: "plan_001"
goal_id: "repair_relation_03_04"
steps:
  - "find_private_opportunity"
  - "apologize"
  - "offer_help"
current_step: 0
valid_until: 7200
```

计划不是不可变脚本。

## 10.3 记忆分层

### Event Memory

权威或主观事件记录。

### Episode Memory

若干相关事件形成摘要：

```text
“昨天在工作中，npc_03 迟到，npc_04 替他完成任务；晚上两人争执。”
```

### Semantic Memory

稳定概括：

```text
“npc_04 很重视工作责任。”
```

### Procedural Memory

行为偏好或习惯：

```text
“下班后常去公园。”
```

LLM 可以辅助生成摘要，但摘要必须引用事件 ID，不能成为无来源真相。

## 10.4 记忆检索

检索评分可包含：

```text
recency
salience
goal relevance
entity overlap
claim relevance
relationship relevance
```

不应把所有历史文本塞入 LLM。

---

# 11. 完整版社会世界模型

## 11.1 从 V0 MLP 到关系式时间模型

V0 的输入是一条 Actor-Candidate 行。完整版需要理解：

- 可变数量实体；
- 多人联合行动；
- 家庭和机构；
- 关系图；
- 事件历史；
- 信念；
- 多时间尺度。

推荐最终结构：

```text
Typed Field Encoders
        ↓
Entity and Relation Encoder
        ↓
Graph Transformer / Relational GNN
        ↓
Temporal Core: GRU or RSSM
        ↓
Global Dynamics Stream
        ├─ World Delta Head
        ├─ Event Head
        ├─ Institution Head
        └─ Uncertainty Head
        ↓
Agent Local Query Stream
        ├─ Intent Head
        ├─ Action/Target Head
        ├─ Belief Update Head
        ├─ Social Outcome Head
        ├─ SpeechPlan Head
        └─ Value Head
```

## 11.2 Global 与 Local 双流

### Global Stream

输入：

- 完整权威状态；
- 联合 Proposal；
- 机构规则；
- 全局事件。

用途：

- 世界转移；
- 中央 Critic；
- 训练；
- 后台模拟；
- 冲突预测。

### Local Stream

输入：

- 该 Agent 的观察；
- 自己的 Belief；
- 目标；
- 相关记忆；
- 允许看到的关系和事件。

用途：

- Agent 决策；
- SpeechPlan；
- 主观预测。

两者可以共享参数，但不得共享已经混入不可见全局信息的激活。

## 11.3 输入 Token 类型

```text
PERSON
HOUSEHOLD
LOCATION
OBJECT
INSTITUTION
GROUP
RELATION
EVENT
CLAIM
BELIEF
COMMITMENT
GOAL
ACTION
TIME
RESOURCE
```

每个 Token 可包含：

```text
type embedding
entity identity embedding or hash embedding
role embedding
owner embedding
visibility embedding
time embedding
continuous fields
categorical fields
mask
```

## 11.4 时间核心

推荐保留：

- 显式权威事件历史；
- 每个实体的小型 recurrent state；
- 可选随机潜变量。

例如：

```text
deterministic hidden state h_t
+
stochastic latent z_t
```

用途：

- 压缩近期动态；
- 表达不确定社会趋势；
- 多步 Rollout。

潜在状态不替代可解释状态。

## 11.5 输出 Heads

完整版可包含：

- `HardTransitionProposalHead`：仅提议，最终仍由规则验证；
- `SoftStateDeltaHead`；
- `RelationshipHead`；
- `BeliefUpdateHead`；
- `ClaimPropagationHead`；
- `CommitmentOutcomeHead`；
- `InstitutionResponseHead`；
- `EventHead`；
- `IntentHead`；
- `ActionTypeHead`；
- `TargetPointerHead`；
- `ArgumentHead`；
- `SpeechPlanHead`；
- `ValueHead`；
- `UncertaintyHead`。

不是所有 Head 都要同时上线。每个阶段按需求添加。

## 11.6 多任务专家

当共享骨干出现明显负迁移时，可以引入小型 MMoE：

```text
Physical Expert
Routine Expert
Economic Expert
Social Expert
Cognitive Expert
Institution Expert
```

每个 Head 使用独立 Gate。首选：

- Dense 小专家；
- Top-2；
- 共享融合层。

不建议为了扩大参数量使用大型稀疏 MoE。

## 11.7 规划

普通行为：

```text
Actor/Utility 一次推理
```

重要行为：

```text
Top-K 候选
→ 世界模型 3–5 个宏观步骤
→ Value/Constraint
→ 选择第一步
→ 真实执行
→ 重规划
```

触发条件：

- 承诺；
- 背叛；
- 重要关系；
- 工作/家庭重大冲突；
- 高不确定性；
- 候选分数接近；
- 玩家直接影响；
- 不可逆事件。

## 11.8 不确定性

模型应能报告：

- 不熟悉状态；
- 多模型分歧；
- 高熵事件；
- Rollout 漂移。

高不确定性时可以：

- 使用保守规则；
- 缩短规划；
- 请求更强教师离线标注；
- 标记为主动学习样本；
- 在玩家可见行为中选择更可解释的保底动作。


# 12. LLM 与语义桥的长期演化

## 12.1 参数弱耦合、协议强耦合

长期仍坚持：

```text
世界模型与 LLM 不联合依赖同一权重
+
通过稳定 SpeechEvent / SpeechPlan / MemorySummary 协议耦合
```

这样可以：

- 替换 API 厂商；
- 本地模型回退；
- 独立升级世界模型；
- 保持世界状态稳定；
- 控制成本；
- 独立测试。

## 12.2 LLM 长期职责

### 输入解析

- 玩家语言；
- 短信；
- 电话；
- 公开公告；
- 自由问询；
- 复杂邀请；
- 指责、否认、承诺。

输出结构化：

- SpeechAct；
- Claim；
- 请求；
- 承诺候选；
- 情绪/语用信号；
- 指代实体；
- 置信度。

### 输出表达

将：

- Intent；
- SpeechPlan；
- 已知 Claim；
- 人格风格；
- 情绪；
- 关系；
- 披露权限；

转成语言。

### 摘要

- Episode Memory；
- 关系变化摘要；
- 日记；
- 社交日志；
- 机构公告。

### 反思

仅在低频重要节点：

- 一天结束；
- 重大关系事件；
- 目标失败；
- 玩家改变关键认识；
- 多事件形成稳定概括。

反思输出必须是候选 Semantic Memory，由规则或校验器提交。

## 12.3 Embedding 残差桥

当结构化 SpeechEvent 无法表达语气细节时，可引入冻结文本编码器：

```text
surface text
→ local embedding encoder
→ projection adapter
→ language residual
```

融合：

\[
h_{language}=h_{schema}+g\odot r_{text}
\]

其中 gate 根据：

- 解析置信度；
- SpeechAct；
- 语言长度；
- 任务；
- 训练阶段；

决定是否使用。

要求：

- Schema 始终是主信息；
- 训练中随机丢弃 residual；
- 编码器版本记录；
- 向量缓存；
- 更换编码器时可重新生成；
- 不把向量作为权威记忆。

## 12.4 API 与本地模型切换

完整版应定义统一接口：

```python
class LanguageBackend:
    async def parse(self, request: ParseRequest) -> ParseResult: ...
    async def verbalize(self, plan: SpeechPlan) -> DialogueLine: ...
    async def summarize(self, request: SummaryRequest) -> SummaryResult: ...
```

实现可包括：

- DeepSeek API；
- 其他兼容 API；
- 本地小模型；
- 模板；
- Recorded Backend。

策略：

```text
玩家关键对话 → 高质量 API
普通可见对话 → 便宜 API 或本地模型
后台对话 → 结构化事件/模板
API 故障 → 本地/模板
```

## 12.5 对话不是状态数据库

完整台词可以存档用于表现和检索，但系统长期状态必须提取成：

- Claim；
- Commitment；
- Event；
- Relationship Delta；
- Goal；
- Memory Reference。

禁止后续逻辑只能通过重新阅读所有对话文本理解发生了什么。

## 12.6 对话安全边界

LLM 上下文必须按 NPC 权限构造：

```text
Identity and style
Current intent
Current observation
Known claims/events
Relevant memories
Relationship
Allowed disclosure
Forbidden knowledge
SpeechPlan
```

不提供：

- 完整数据库；
- 其他 NPC 私有信念；
- 未公开秘密；
- 未来脚本；
- 调试标签；
- 模型内部评分。

---

# 13. 训练数据与学习飞轮

## 13.1 数据来源层级

长期数据来源可以逐步增加：

1. 规则模拟器；
2. Codex 生成和审查的结构化锚点；
3. 大模型教师；
4. 玩家 Demo 运行日志；
5. 人工修订黄金场景；
6. 模型主动发现的不确定样本；
7. 对抗和边界场景；
8. 反事实 Rollout；
9. 可选偏好比较。

## 13.2 教师模型的边界

教师可以标注：

- 社会结果；
- 意图；
- 接受概率；
- Belief 更新；
- SpeechAct；
- 关系变化范围；
- 事件重要度；
- 计划合理性。

教师不能覆盖：

- 权威硬结果；
- 对象存在；
- 数量守恒；
- 工作合同；
- 资产能力；
- 真实目击范围。

## 13.3 主动学习

运行时记录：

- 模型高不确定性；
- Ensemble 分歧；
- 预测与真实/规则结果差异；
- 玩家认为不合理的行为；
- 长程 Rollout 崩坏；
- 新行为组合。

离线建立队列：

```text
uncertain_samples/
regression_samples/
player_flagged_samples/
new_schema_samples/
```

Orchestrator 分派：

- 自动规则检查；
- Codex Producer；
- 独立 Reviewer；
- 必要时人工确认；
- 加入下一版训练集。

## 13.4 课程学习

推荐训练顺序：

1. 单 Agent 生活状态；
2. 双人社会行为；
3. 多人同地点；
4. 事件传播；
5. Belief；
6. Commitment；
7. 家庭；
8. 工作机构；
9. 多步 Rollout；
10. 混合任务联合微调。

## 13.5 数据版本

每个训练样本必须标识：

```text
schema_version
behavior_catalog_version
event_ontology_version
claim_ontology_version
feature_version
label_version
simulator_version
teacher_version
generation_method
review_status
```

模型必须声明兼容范围。

## 13.6 模型发布

建议每个模型包包含：

```text
weights
model_config
feature_config
normalization
catalog_hash
schema_version
metrics
calibration
training_data_manifest
known_failures
license/provenance
```

## 13.7 可选强化学习

只有以下需求明确出现时才考虑：

- 多日延迟收益；
- 复杂承诺；
- 家庭协作；
- 策略性信息传播；
- 监督数据无法覆盖行为排序。

优先采用：

- Offline RL；
- Preference learning；
- Actor-Critic 在学习世界模型中短程训练；
- 约束策略。

不建议直接让在线 RL 在玩家存档中自由探索。

---

# 14. 运行时调度与认知 LOD

## 14.1 多时钟

### Frame Clock

Unity：

- 渲染；
- 动画；
- 导航；
- 摄像机；
- UI。

### Simulation Clock

Town Core：

- 时间；
- 需求；
- 资源；
- 动作；
- 事件；
- 日程。

### Cognitive Clock

Agent：

- 目标；
- 候选；
- 世界模型；
- Belief；
- 规划。

### Language Clock

LLM：

- 解析；
- 表达；
- 摘要；
- 反思。

四者不能串成一个全局阻塞循环。

## 14.2 Agent LOD

### LOD 0：休眠

- 日程段推进；
- 聚合需求；
- 无完整社会决策；
- 只处理高重要事件。

### LOD 1：后台

- 固定行为候选；
- 低频世界模型；
- 结构化 SpeechEvent；
- 地点级空间。

### LOD 2：活跃

- 完整局部观察；
- Batch Agent；
- 关系、Claim、Commitment；
- Unity 详细行为。

### LOD 3：焦点

- 玩家交互；
- 重要规划；
- 可见自然语言；
- 更丰富记忆；
- 调试追踪。

LOD 切换必须：

- 保持权威状态；
- 不丢失已提交事件；
- 对聚合期间的变化生成摘要；
- 避免角色瞬移或知识跳跃。

## 14.3 公共编码复用

对于同一地点或家庭：

```text
shared location encoding
+
agent-specific query
```

避免每个 Agent 完整重复编码公共对象和事件。

## 14.4 两阶段提交长期保持

即使模型升级为联合世界模型，也必须：

```text
快照
→ 多 Agent Proposal
→ 联合预测
→ Resolver
→ Commit
→ Observation
→ Belief Update
```

模型不能按 Batch 行顺序造成因果偏差。

## 14.5 重要性调度

每个待处理事件可计算：

```text
salience
affected_agent_count
player_relevance
irreversibility
model_uncertainty
deadline
```

高重要事件优先获得：

- 精细模型；
- 更深 Rollout；
- LLM；
- Unity 摄像机提示；
- 日志。

---

# 15. Unity 长期架构

## 15.1 Unity 仍是表现层，但语义更丰富

长期 Unity 负责：

- 空间与可见性；
- NavMesh；
- 房间和楼层；
- 动画；
- 道具；
- 交互站位；
- 表情；
- 声音；
- 玩家控制；
- 视听焦点；
- 调试。

Python/核心服务负责：

- 权威社会状态；
- 行为；
- 规则；
- 模型；
- LLM；
- 回放。

商业化或独立发布阶段可以把核心移植到 C#/ONNX，但不应提前牺牲实验效率。

## 15.2 Semantic Authoring Tools

长期可加入 Unity Editor 工具：

- 语义对象向导；
- 能力标签；
- 行为资产需求检查；
- 槽位可视化；
- 站位和朝向预览；
- 路径可达检查；
- 房间隐私区；
- 可听范围；
- 可见范围；
- 工作站标签；
- 一键导出资产注册；
- 行为-动画覆盖矩阵；
- 场景社会密度预览。

## 15.3 行为表现图

复杂行为可由 Unity Presentation Graph 表达：

```text
Navigate
→ Align
→ Play Animation
→ Spawn Prop
→ Attach Prop
→ Move to Secondary Slot
→ Play Secondary Animation
→ Despawn Prop
→ Complete
```

该图只负责表现，不拥有世界结果。

## 15.4 动画语义

长期应使用稳定语义接口：

```text
POSTURE_SIT
POSTURE_LIE
ACTION_EAT
ACTION_DRINK
ACTION_WORK_DESK
ACTION_CLEAN
SPEECH_NEUTRAL
SPEECH_WARM
SPEECH_HOSTILE
REACTION_SURPRISED
REACTION_EMBARRASSED
REACTION_ANGRY
```

具体动画资产可替换。

## 15.5 可听与可见

完整信息传播需要 Unity 或空间层提供：

- 同地点；
- 同房间；
- 距离；
- 遮挡；
- 私密空间；
- 是否面对；
- 音量等级；
- 玩家是否可听。

V0 只用高层地点，后续再增加房间级感知。

## 15.6 玩家界面

完整版应有：

### 世界视图

- 当前时间；
- 地点；
- 活跃事件；
- 家庭/机构状态。

### NPC 面板

- 需求；
- 情绪；
- 当前目标；
- 日程；
- 关系；
- 已知 Claim；
- 承诺；
- 最近事件；
- 行为原因。

### 社会图

- 人际关系；
- 信息传播；
- 家庭；
- 工作；
- 群体。

### 时间线

- 事件；
- Claim；
- 承诺；
- 对话；
- 关系变化。

### 模型调试

- Top-K；
- Rollout；
- 不确定性；
- 模型/规则差异；
- Global/Local 输入权限。

面向普通玩家时可以隐藏技术细节，作品集/研究模式应保留。

---

# 16. 数据存储与回放演化

## 16.1 事件溯源 + 周期快照

长期仍使用：

```text
Snapshot
+
Append-only Event Log
+
Decision Trace
+
External Input Log
```

## 16.2 数据库

规模增长后可使用：

- SQLite：单机首选；
- 可选 DuckDB：分析；
- Parquet：训练数据；
- 不必早期引入分布式数据库。

## 16.3 回放级别

### Authoritative Replay

完全重放已提交事件。

### Recompute Replay

重新运行模型和 Resolver，比较差异。

### Counterfactual Replay

从快照替换一个玩家选择、一个模型版本或一个事件，再继续模拟。

Counterfactual Replay 是完整版重要研究能力。

## 16.4 存档迁移

每次 Schema 升级必须：

- 保存版本；
- 提供迁移脚本；
- 验证前后守恒；
- 备份；
- 允许只读旧存档；
- 在模型不兼容时切换规则基线。

---

# 17. 评估框架的长期演化

## 17.1 状态正确性

- 守恒；
- 引用完整；
- 范围；
- 事务；
- 时间；
- 位置；
- 权限；
- 回放一致。

## 17.2 Agent 合理性

- 需求优先；
- 日程；
- 人格差异；
- 关系差异；
- 承诺；
- 事件影响；
- 不使用未知信息；
- 不重复循环。

## 17.3 社会因果性

检查：

```text
事件发生
→ 被谁观察
→ 谁相信
→ 如何传播
→ 如何改变关系/目标
→ 是否改变后续行为
```

任何社会变量若不能改变后续行为，应重新评估是否值得保留。

## 17.4 涌现而非随机噪声

目标不是事件多，而是：

- 可追溯；
- 有持久性；
- 有修复；
- 有跨系统反馈；
- 不同初始条件产生不同轨迹；
- 同一人格在相似局面保持统计一致。

## 17.5 玩家可读性

通过用户测试检查：

- 玩家能否解释 NPC 行为；
- 是否感到角色在“作弊”读取全局状态；
- 是否理解关系为何变化；
- 是否能通过行动和语言影响社会；
- 是否有足够意外但不显得随机。

## 17.6 性能

- 每层 LOD 成本；
- Batch 利用率；
- 世界模型延迟；
- LLM 请求率；
- Unity 帧率；
- 内存；
- 事件日志增长；
- 存档加载。

## 17.7 模型评估

除单步误差外：

- 多步 Rollout；
- 决策 regret；
- 校准；
- OOD；
- Uncertainty；
- Belief 一致性；
- 联合行动；
- 机构响应；
- 长期分布。


# 18. 阶段路线图

## Stage 0：V0 验证版

范围由首版实施规范定义。

### 核心证明

- 固定行为；
- 规则权威状态；
- 小型 MLP 后果模型；
- 事件传播；
- DeepSeek 语言边界；
- Unity 表现；
- 10 NPC。

### 不得提前引入

- Claim；
- Commitment；
- 图模型；
- 长程规划；
- 更多地点；
- 更多需求；
- 复杂经济。

---

## Stage 0.5：稳定化与工具化

只有 V0 完整验收后进入。

### 目标

让 V0 成为可持续实验基线，而不是一次性演示。

### 工作

- 配置编辑和验证；
- 更完善回放；
- 模型 A/B；
- Unity 语义编辑器；
- 场景自动检查；
- 测试覆盖；
- 性能分析；
- 主动学习样本收集；
- 清理技术债；
- 固定行为资产工作流。

### 退出条件

- 新行为可按模板添加；
- 旧回放可读取；
- 训练和运行一键化；
- 模型差异可比较；
- Unity 场景错误可自动报告。

---

## Stage 1：Claim / Belief 与更稳定的社会记忆

### 目标

从“知道事件”升级为“对命题持有不同置信度”。

### 规模

- NPC 仍可保持 10–16；
- 地点不急于增加；
- 重点扩展认知。

### 新能力

- Claim；
- Belief；
- 来源可靠性；
- 否认；
- 澄清；
- 简单谎言；
- 事件摘要；
- 一层他人知识估计；
- AskAboutClaim；
- Gossip；
- KeepSecret。

### 模型

- V0 MLP 增加 Belief Head；
- 可加入小型 GRU；
- 暂不必使用图模型。

### 退出条件

- 同一事件不同 NPC 可有不同 Belief；
- 信息传播路径可追踪；
- NPC 不把听说当成亲眼所见；
- 澄清会改变 Belief 和行为；
- LLM 不混淆 Claim 与 Fact。

---

## Stage 2：Commitment、家庭责任与中期目标

### 目标

让角色的社会行为跨越数小时到数日。

### 新能力

- Promise；
- RequestHelp；
- OfferHelp；
- Commitment；
- 家庭责任；
- 工作调班；
- 目标；
- 简单计划；
- 失约；
- 赔偿/修复；
- 家庭事件。

### 规模

- 16–24 NPC；
- 6–8 家庭；
- 10–14 地点。

### 模型

- 5–15M；
- GRU/RSSM；
- 两步或三步宏观 Rollout；
- Commitment Outcome Head；
- Goal Persistence Head。

### 退出条件

- 承诺进入日程与候选；
- 失约产生可追溯后果；
- 角色会为履约牺牲短期 Utility；
- 关系修复不只靠一次道歉；
- 家庭内部出现责任分工。

---

## Stage 3：关系式世界模型

### 目标

从 Actor-Candidate MLP 升级到可变实体图和联合行动。

### 新能力

- Typed entity graph；
- Graph Transformer/GNN；
- Global/Local 双流；
- 可变数量邻居；
- 多人 Joint Behavior；
- 群体事件；
- 关系网络传播；
- 模型不确定性；
- Counterfactual Rollout。

### 规模

- 20–30 NPC；
- 10 家庭左右；
- 12–18 地点；
- 35–60 行为。

### 模型

- 10–30M；
- 3–5 个短程步骤；
- 训练期集中信息；
- 运行期局部观察；
- 可选 MMoE。

### 退出条件

- 模型能处理可变实体数量；
- 局部 Agent 不泄漏全局信息；
- 多人活动正确结算；
- 图模型明显优于 V0 模型；
- 性能仍满足本地实时。

---

## Stage 4：机构、群体与有限经济

### 目标

让社会结构不只由一对一关系构成。

### 新能力

- 工作机构；
- 主管与岗位；
- Group；
- Norm；
- Reputation；
- 账单；
- 经济压力；
- 社区活动；
- 公共信息渠道；
- 机构响应。

### 规模

- 30–45 NPC；
- 12–16 家庭；
- 16–22 地点。

### 模型

- 20–50M；
- Institution Token；
- Norm/Institution Heads；
- 认知 LOD；
- 主动学习。

### 退出条件

- 机构规则能改变行为；
- 声誉有来源；
- 群体活动制造跨家庭网络；
- 经济压力产生社会后果；
- 不因规模增加失去可解释性。

---

## Stage 5：完整版研究版

### 目标

形成完整、稳定、可扩展的小社会世界模型平台。

### 推荐规模

- 40–60 NPC；
- 12–16 家庭；
- 18–24 地点；
- 60–100 行为；
- 40–80 语义对象类型；
- 100–200 事件；
- 80–200 Claim Predicate。

### 核心能力

- 多层权威/观察/信念/表达；
- 家庭、工作、群体、有限经济；
- 关系、Claim、Commitment、Norm；
- 关系式时间世界模型；
- 3–5 步重要决策规划；
- 认知 LOD；
- API/本地语言后端；
- Unity 丰富表现；
- Counterfactual Replay；
- 主动学习；
- 完整调试与研究工具。

### 完成标准

- 连续运行数十到上百游戏日；
- 社会事件跨日演化；
- 玩家干预产生可追踪影响；
- 同一事件在不同角色之间形成不同认识；
- 承诺和机构规则影响实际行动；
- 本地运行稳定；
- 模型退化时可回退；
- 所有关键结果可解释。

---

# 19. 版本迁移原则

## 19.1 V0 中应保留的稳定接口

长期应尽量延续：

- `OutcomeModel` 抽象；
- 行为目录；
- 对象能力；
- 事件账本；
- `state_version`；
- 两阶段提交；
- Unity 消息 envelope；
- 运行日志；
- 回放；
- Prompt 版本；
- ID 规则。

## 19.2 Schema 升级

例如从 KnownEvent 到 Belief：

```text
V0 KnowledgeRecord
→ 迁移为 Belief(event-derived claim, probability=confidence)
```

从关系四维到更多维：

```text
保留 familiarity/affinity/trust/tension
新增字段使用默认值
```

从 MLP 到图模型：

```text
保持 Candidate/Prediction 业务 DTO
替换内部 Feature Encoder
```

## 19.3 不兼容变更

必须有 ADR 和迁移：

- 删除行为；
- 改变事件含义；
- 改 ID；
- 改数值方向；
- 改时间单位；
- 改关系边方向；
- 改 LLM Claim 语义；
- 改 Unity 能力标签。

---

# 20. 资源与运行预算

以下为方向性规模，不是硬承诺。

## 20.1 模型训练

| 阶段 | 参数量 | 数据量 | 典型开发算力 |
|---|---:|---:|---:|
| V0 | 1–3M | 0.3–1M 行 | 20–80 GPU 小时总迭代 |
| Stage 1 | 3–8M | 1–5M 行 | 50–200 GPU 小时 |
| Stage 2 | 5–15M | 3–15M 行 | 100–500 GPU 小时 |
| Stage 3 | 10–30M | 10–50M 行 | 300–1500 GPU 小时 |
| Stage 4/5 | 20–50M | 30–150M 行 | 1000–5000 GPU 小时 |

最终训练可以租更强云算力；本地只要求推理。

## 20.2 本地运行

完整版通过：

- 量化；
- Batch；
- 共享编码；
- LOD；
- 事件触发；
- API 异步；
- 只对重要行为 Rollout；

控制成本。

目标可以设为：

```text
40–60 NPC 中
12–24 高精度活跃
其余后台/休眠
世界模型 20–50M
普通消费级 CPU 可运行
有消费级 GPU 时获得更高模拟倍率
```

## 20.3 LLM 成本

主要控制手段：

- 后台对话不生成全文；
- 缓存固定提示；
- SpeechPlan 简短；
- 只给相关事件；
- 玩家焦点优先；
- 模板和本地回退；
- 摘要低频；
- 限制同时会话。

---

# 21. 完整版示例：七日社会链

下面是一条理想的完整版事件链，用于说明各系统如何联动，不是固定剧情。

## 第一天：日常与承诺

- `npc_03` 的家庭食品不足；
- `npc_03` 承诺下班后采购；
- 工作中同事 `npc_04` 请求其第二天代班；
- `npc_03` 接受，形成 Commitment。

涉及：

- 家庭资源；
- Goal；
- Commitment；
- 工作关系。

## 第二天：冲突出现

- `npc_03` 前晚在酒吧停留过久；
- 第二天精力不足；
- 世界模型预测继续睡眠短期收益高；
- Commitment 和 discipline 提高上班 Utility；
- 角色仍可能迟到；
- `npc_04` 认为其不可靠；
- 主管记录违反准时 Norm。

涉及：

- 需求；
- 多步取舍；
- Commitment；
- Institution Norm；
- Reputation。

## 第三天：信息传播

- `npc_04` 向兴趣小组成员 `npc_08` 讲述；
- `npc_04` 声称 `npc_03` “经常不守承诺”；
- 该泛化 Claim 并不完全等同真实事件；
- `npc_08` 只部分相信；
- 公共活动邀请中，`npc_08` 降低对 `npc_03` 的优先级。

涉及：

- Claim；
- Belief；
- 来源可靠性；
- 群体；
- 行为后果。

## 第四天：玩家介入

玩家告诉 `npc_08`：

> “他那天是因为家里出了问题，并不是故意放你们鸽子。”

系统解析：

- 辩护；
- 新 Claim；
- 来源是玩家；
- 不直接改变事实。

`npc_08` 根据对玩家的信任更新 Belief。

涉及：

- 玩家语言；
- Claim；
- Belief；
- 信任；
- LLM 边界。

## 第五天：修复尝试

- `npc_03` 计划向 `npc_04` 道歉；
- 世界模型比较：
  - 公开道歉；
  - 私下道歉；
  - 帮忙完成工作；
  - 回避；
- 预测私下道歉并提供实际帮助长期价值更高；
- 角色只执行第一步。

涉及：

- 目标；
- 计划；
- 3–5 步 Rollout；
- 场所隐私；
- 社会后果。

## 第六天：机构与家庭反馈

- `npc_03` 为履行补偿承诺加班；
- 因此错过家庭采购；
- 家庭成员不满；
- 角色必须在工作修复和家庭责任间选择；
- 玩家可建议其请求家庭成员帮助。

涉及：

- 多重 Commitment；
- 家庭；
- 工作；
- 资源；
- 玩家干预。

## 第七天：新的稳定状态

根据前六天选择，可能形成：

- `npc_04` 恢复部分信任；
- 主管评价改善；
- 家庭 tension 上升；
- `npc_08` 对事件保持不确定；
- `npc_03` 形成“避免连续晚间娱乐”的习惯性 Semantic Memory；
- 新一周行为分布改变。

这条链展示的不是预写分支，而是：

```text
有限行为
+
显式义务
+
主观认识
+
社会传播
+
世界模型预测
+
玩家语言
```

共同产生的可追踪演化。

---

# 22. 完整版仍然不追求的内容

即使到 Stage 5，也不建议把目标扩大为：

- 复制商业《模拟人生》的资产数量；
- 任意职业和任意物品；
- 开放世界城市；
- 万人实时 Agent；
- 每个 NPC 永久完整自然语言思考；
- LLM 直接生成可执行代码；
- 无边界自由行为；
- 真实社会科学预测；
- 人类心理的完整模型；
- 取代所有规则的端到端神经网络；
- 视觉生成式世界；
- 完整政治、法律、犯罪、医疗、教育体系。

项目的优势来自边界清晰，而不是规模无限。

---

# 23. 长期 Orchestrator 治理

## 23.1 每阶段重新冻结

每进入新阶段，Orchestrator 必须冻结：

- 人口；
- 地点；
- 行为；
- 对象；
- 状态字段；
- 模型 Heads；
- Unity 资产需求；
- 训练数据版本；
- 验收场景。

## 23.2 研究功能采用实验旗标

新模型或社会机制先以 feature flag 存在：

```text
enable_claims
enable_commitments
enable_graph_model
enable_rollout_planning
enable_institutions
enable_embedding_residual
```

必须可与上一稳定版本 A/B。

## 23.3 每个长期线程仍有路径所有权

随着规模扩大，可以增加：

- `THREAD-COGNITION`
- `THREAD-INSTITUTIONS`
- `THREAD-BEHAVIOR-AUTHORING`
- `THREAD-MODEL-RESEARCH`

但 Schema、Authority 和 Unity Contract 仍需中央治理。

## 23.4 不允许模型研究脱离产品闭环

每次模型升级必须回答：

```text
哪个可见行为改善了
哪个验收指标改善了
运行成本增加多少
是否仍可解释
是否仍能回放
是否影响资产
规则基线是否仍可用
```

只提升离线 Loss 而不改善社会演示，不构成升级理由。

---

# 24. 完整版最终架构图

```text
Unity Semantic World
  ├─ Scene / Room / Navigation
  ├─ Semantic Objects / Slots
  ├─ Animation / Props / Audio
  ├─ Player Input
  └─ Debug Visualization
               ⇅ Versioned Protocol
Authority Core
  ├─ Time / Space / Resources
  ├─ Actions / Reservations
  ├─ Households / Institutions
  ├─ Event Ledger
  ├─ Claim / Commitment / Norm
  ├─ Two-phase Resolver
  └─ Replay / Snapshot
               ↓
Observation and Cognition
  ├─ Perception Filters
  ├─ Beliefs
  ├─ Memories
  ├─ Goals
  ├─ Relationships
  └─ Cognitive LOD
               ↓
Relational Temporal World Model
  ├─ Global Dynamics Stream
  ├─ Local Agent Query Stream
  ├─ Social / Belief / Event Heads
  ├─ Value / Uncertainty
  └─ 3–5 Step Salient Rollout
               ↓
Policy and Planner
  ├─ Fixed Candidate Generation
  ├─ Utility
  ├─ Commitment / Schedule Constraints
  ├─ Top-K Planning
  └─ First-step Execution
               ↓
Language Interface
  ├─ Text → SpeechEvent / Claim / Request
  ├─ SpeechPlan → Text
  ├─ Summary / Reflection
  ├─ API / Local / Template Backends
  └─ Strict Knowledge Permissions
```

---

# 25. 最终判断标准

完整版是否成功，不以 NPC 数量、模型参数或台词长度衡量，而以以下问题衡量：

1. 一个角色的行为能否由需求、日程、人格、关系、信念和承诺共同解释；
2. 一个事件能否通过目击和传播改变不同角色的认识；
3. 社会变量是否真正改变未来行为；
4. 玩家是否能通过行动与语言影响社会，但不能任意篡改现实；
5. 角色是否会在短期需求和长期责任之间做有意义的权衡；
6. 家庭、工作、公共场所和群体是否形成不同社会网络；
7. 模型是否只在适合学习的软状态上发挥作用；
8. 系统是否仍能在家用电脑流畅运行；
9. 任何关键结果是否可追溯、可重放、可测试；
10. 即使关闭 LLM 或神经模型，权威世界是否仍能安全运行。

项目最终应呈现的不是“十几个聊天机器人站在地图上”，而是：

> **一个由有限资产和明确规则承载、由小型社会世界模型增强、通过语言接口向玩家开放，并能持续形成可理解社会因果的小世界。**

