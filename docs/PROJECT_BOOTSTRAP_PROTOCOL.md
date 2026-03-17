# PROJECT_BOOTSTRAP_PROTOCOL

## 目标
让任何新 AI / 新接手者先完成项目同频，再进入 foundation 的自动化主线。

## 启动原则
- 先文档，后代码。
- 先制度与终局，后当前实现。
- 先 `PROJECT_GUIDE`，后 task/run 自动化。
- 如果同频不准，暂停自动化，不继续放大误解。

## 固定阅读顺序
1. `docs/总纲清单（可复制）.md`
2. `README.md`
3. `docs/中央银行设计.md`
4. `docs/基于资管双向非对称对冲策略手册.md`
5. `docs/梦想中的交易资管财富系统想法.md`
6. `docs/资管双向原始想法.md`
7. `docs/PROJECT_GUIDE.md`
8. 关键实现文件与测试

## 进入代码前必须回答的问题
- 项目终局是什么？
- 一期落地是什么？
- 三账本分别意味着什么？
- 中央银行在本项目中是什么？
- 当前实现做到哪里？
- 当前事实链、状态机和风控闸门在哪里？

这些问题统一通过 `docs/PROJECT_GUIDE.md` 的 17 问完成。

## 与 foundation 的衔接
当上述问题答稳后，再进入 foundation 仓主线：
- `init`
- `learnbaseline`
- `fork-current`
- role/thread/task/run 去噪
- `gitclient`

## 禁止事项
- 不准跳过总纲直接从代码倒推项目定位
- 不准把 README 权重放到总纲之前
- 不准把原始想法文档当作当前实现状态
- 不准在 `PROJECT_GUIDE` 未稳定前直接追求自动化
