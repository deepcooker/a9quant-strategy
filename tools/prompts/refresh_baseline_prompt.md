refresh-baseline: 接下来请你把本轮稳定增量回灌到 baseline 学习模型。

目标：
- 不重复构建整个 baseline
- 优先吸收 run summary 中已经稳定的增量认知
- 只有在 run summary 缺失时才回退 current summary
- 更新 baseline 的主线理解、摘要和下一步

要求：
- 优先使用 run summary 中的有效结论；只有缺失时才使用 current summary
- 不把工作 session 噪音直接带回 baseline
- 输出必须可直接写回 baseline 学习快照
