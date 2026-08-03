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

## 当前边界

本阶段只生成规则教师 rows。人工社会锚点、连续邻域增强、模型训练和神经 rollout 均在后续独立增量中执行。smoke 数据不能充当 M4 发布数据或最终验收证据。
