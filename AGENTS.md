# AGENTS.md

## 一句话定位
本项目不是单一策略脚本，而是以“三账本资金宪法 + 中央银行闸门 + 自我迭代工厂”为终局方向、当前先落地 B 类趋势/鲨鱼系统的交易资管财富系统。

## 不可变宪法
- 终局不是策略最优，而是 `Treasury / Growth / Gamble` 三账本财富系统。
- 目标函数核心是下牌桌概率与系统生存，不是长期 Sharpe。
- `中央银行` 是制度化闸门、预算、权限和冻结机制，不是可有可无的叙事。
- 研发闭环不可改：策略创作 -> backtest/极限电池 -> replay 一致性 -> 模拟盘采样 -> 问题归因 -> 数据优化 -> 再迭代。
- 证据链不可省：`run_id / trace_id / commit / config_hash / dataset_version` 必须可追溯。
- 策略没有生存权，只有使用权；任何策略都必须可被冷酷关闭。
- Gamble 可以归零，但 Treasury 禁止反向救赌；赢了必须 Harvest 并回灌 Treasury。

## 当前阶段
- 一期只能落地 B 类：趋势 + 鲨鱼。
- 一期仍必须按终局主设计演化，先把账本语义、接口、门禁、状态机和证据链立起来。
- A 类现金流系统当前未落地，但其位置和制度边界必须预留。

## 工程边界
- 文档理解优先级固定：
  1. `docs/总纲清单（可复制）.md`
  2. `README.md`
  3. `docs/中央银行设计.md`
  4. `docs/基于资管双向非对称对冲策略手册.md`
  5. `docs/梦想中的交易资管财富系统想法.md`
  6. `docs/资管双向原始想法.md`
- 代码只用于确认“当前已经做到哪里”，不能反过来改写总纲。
- `docs/PROJECT_GUIDE.md` 是本项目同频核心，后续 AI/人接手必须先按题库与阅读顺序进入。

## 当前实现硬边界
- `main_controller.py` 是当前组合入口与主循环协调层。
- `data_synchronizer.py` 是状态同步与事实重建入口。
- `account_state.py` 是业务态账本。
- `advanced_risk.py` 承担当前中央银行闸门。
- `trend_engine.py` 与 `shark_engine.py` 是一期执行层。
- `tiny_oms.py`、`bitget_ws_bridge.py`、`base_bitget_ws.py`、`ccxt_utils.py` 组成执行与交易所桥接层。

## 与 foundation 的关系
- foundation 仓负责自动化研发 OS、session 主线、learnbaseline、gitclient 和证据沉淀。
- 本项目负责业务系统、运行态、执行数据、回放与后续迭代。
- 后续需求讨论、task/run 去噪、角色线程与 git 收尾默认沿用 foundation 规则。
