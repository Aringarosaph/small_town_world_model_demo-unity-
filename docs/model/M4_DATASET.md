# M4 规则教师数据集

M4 数据集用于把 M3 的确定性社会反应蒸馏为小型神经模型。数据生成器只观察合法候选和规则教师结果，不改变候选、Resolver、资源、预约、事件、知识或任何权威状态。

## 环境

- Python `3.12.*`；
- 项目基础依赖；
- 数据额外依赖 `pyarrow==19.0.1`，由 `m4-data` extra 和 `uv.lock` 固定；
- 生成目录必须位于 Git 仓库之外。

AutoDL 约定：

- 活跃生成：`/root/autodl-tmp/stwm-m4-work`；
- 持久数据：`/root/autodl-fs/STWM/m4/datasets`；
- 生成完毕后先校验 manifest、Parquet 行数及 SHA-256，再复制到持久目录。

## 受限 smoke 数据集

```bash
PYTHONPATH=python python -m town_core.modeling.dataset \
  --config config/v0 \
  --output-root /root/autodl-tmp/stwm-m4-work \
  --dataset-id m4_teacher_smoke_seed12345 \
  --seed 12345 \
  --maximum-rows 10000 \
  --maximum-minutes 10080 \
  --rows-per-shard 10000 \
  --source-commit <40位提交号>
```

生成物：

- `dataset-manifest.json`：`stwm.model.dataset-manifest/v1`；
- `shards/shard_XXXXX.parquet`；
- 每条 Parquet 记录含索引列及一份 canonical `stwm.model.training-example/v1` JSON；
- feature 与 label 分别严格验证 `stwm.model.candidate-feature-row/v1` 和 `stwm.model.outcome-label/v1`。

分割按完整 `scenario_group_id` 的稳定 SHA-256 桶执行，不能按行随机切分。一个 decision 的全部候选拥有同一 `decision_group_id`，且不会跨 shard 拆分。

正式原始训练矩阵使用五个冻结 seed 各 60 游戏日、每 seed 最多 100,000
行、每 shard 最多 25,000 行。`release_dataset` producer 可按 seed 隔离并行，
只有父进程写入状态和聚合 manifest；每个已完成 seed 独立校验和登记，
中断恢复时不会重做已完成 seed。AutoDL 16 核基线使用 5 个 worker：

```bash
PYTHONPATH=python python -m town_core.modeling.release_dataset \
  --config config/v0 \
  --output-root /root/autodl-tmp/stwm-m4-work/m4_teacher_release_raw_v1 \
  --source-commit <40位提交号> \
  --max-workers 5
```

## 训练输入质量审查

正式数据集在训练前必须用独立工具复验严格 manifest/shard 校验，并输出仓库外的
`stwm.model.dataset-quality-report/v1`：

```bash
PYTHONPATH=python python -m town_core.modeling.analyze_dataset \
  --config config/v0 \
  --dataset /root/autodl-fs/STWM/m4/datasets/m4_teacher_release_raw_v1 \
  --output /root/autodl-fs/STWM/m4/reports/m4_teacher_release_raw_v1-quality.json
```

质量门检查最小行/决策组、22 行为在三个 split 的候选覆盖、7 个 acceptance
行为覆盖、每组唯一 teacher 选中、分组无泄漏、feature mask 双态及事件上下文覆盖。
报告另外记录行为×split 的选中不平衡、组大小和各连续标签轴的正/负/零分布。
稀有行为的选中样本不足由加权/平衡采样、社会锚点和逐行为指标处理，不允许用总体准确率掩盖。

## 社会锚点任务选择

ADR-0013 在不改写原始 Parquet 和规则教师标签的前提下，冻结恰好 300 条待独立
审查的社会锚点任务。选择器会先完整复验数据集，再按七个行为和三个既有 split
执行确定性成对覆盖；输出目录必须位于仓库外且为空：

```bash
PYTHONPATH=python python -m town_core.modeling.anchors \
  --dataset /root/autodl-fs/STWM/m4/datasets/m4_teacher_release_raw_v1_73ca45f \
  --output-root /root/autodl-fs/STWM/m4/anchors/m4_social_anchor_tasks_v1
```

输出包括冻结 coverage policy、300 行 canonical task JSONL 和覆盖报告。每条 task
携带源 dataset/shard/example 的 SHA-256、完整 feature、原始 heuristic baseline、
覆盖签名和不可变 split。`test` 只能映射为 `ANCHOR_HOLDOUT`，不能进入训练、早停、
校准或超参数选择。选择器不会生成 Codex judgment，也不会把任务冒充为已批准锚点；
生产者判断、独立 reviewer issue 和最终 approval manifest 是后续分离的哈希链工序。

正式任务包必须再做一次从原始 Parquet 独立重选，逐行比较 canonical task 与覆盖
报告，并写出仓库外验证报告：

```bash
PYTHONPATH=python python -m town_core.modeling.validate_anchors \
  --dataset /root/autodl-fs/STWM/m4/datasets/m4_teacher_release_raw_v1_73ca45f \
  --tasks-root /root/autodl-fs/STWM/m4/anchors/m4_social_anchor_tasks_v1_75ba030 \
  --output /root/autodl-fs/STWM/m4/reports/m4_social_anchor_tasks_v1_75ba030-validation.json
```

## 当前边界

规则教师 rows 已生成并完成质量复验；当前增量只冻结并选择社会锚点任务。
Codex judgment、独立审查、连续邻域增强、模型训练和神经 rollout 均在后续分离
增量中执行。smoke 数据和未批准的 task 都不能充当 M4 发布数据或最终验收证据。
