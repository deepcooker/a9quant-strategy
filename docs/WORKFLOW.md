# WORKFLOW

本文件定义 `a9quant-strategy` 的两条主线：
- 研发主线：如何借助外部 `quant-factory-os` 仓提供的 foundation 角色能力推进学习、需求收敛、task 执行、证据与交付
- 业务运行主线：交易系统从行情、策略、风控到执行与回放的真实流转

## 1. 阅读与理解主线
任何新接手者先按以下顺序进入：
1. `docs/总纲清单（可复制）.md`
2. `README.md`
3. `docs/中央银行设计.md`
4. `docs/基于资管双向非对称对冲策略手册.md`
5. `docs/梦想中的交易资管财富系统想法.md`
6. `docs/资管双向原始想法.md`
7. 关键实现文件与测试

这一步的目标不是写代码，而是先定：
- 终局制度
- 一期范围
- 当前实现程度
- 后续最小 task

## 2. 研发主线
本项目默认承接 `quant-factory-os` 提供的 foundation 工具链：

```text
准备层（init）
  -> learnbaseline
  -> 确认 run 方向
  -> fork-current
  -> role/thread 拆最小 task
  -> summarize-current
  -> refresh-baseline
  -> gitclient 收尾
```

研发期分两段：

### 2.1 首轮同频
- 先完成本项目 owner docs 理解
- `PROJECT_GUIDE` 是同频核心
- 只有同频稳了，才进入 baseline/session 主线

### 2.2 日常迭代
- 需求先在 run 层收敛
- 再拆 task
- 再改实现/补验证
- 再更新证据和文档
- 最后走 `gitclient`

## 3. 业务运行主线
当前真实运行链路是：

```text
Market / Exchange Reality
  -> BaseBitgetWsClient / CCXT
  -> BitgetWSBridge
  -> DataSynchronizer
  -> AccountState
  -> RiskManager (中央银行)
  -> System Mode / Strategy Permission
  -> TrendEngine / SharkEngine
  -> TinyOMS
  -> Exchange Execution
  -> DataSynchronizer Reconcile / Replay / Tests
```

### 3.1 主入口
- `main_controller.py` 负责模块初始化与主循环调度

### 3.2 事实链
- 交易所现实先进入 `DataSynchronizer`
- `AccountState` 承接业务态
- `RiskManager` 基于事实账本决定系统模式与策略权限

### 3.3 策略层
- `TrendEngine` 偏 Growth
- `SharkEngine` 偏 Gamble
- 策略只能提交 intent，不能绕过中央银行闸门

### 3.4 执行层
- `TinyOMS` 统一管理订单生命周期
- `BitgetWSBridge` / `BaseBitgetWsClient` / `ExchangeTrader` 负责真实对接

## 4. 四态治理主线
系统必须围绕四态理解，不允许把它降级成“普通风控”：
- `NORMAL`
- `DEFENSIVE`
- `FROZEN`
- `REBUILD`

关键规则：
- 状态不可信时优先生存，不优先收益
- FROZEN 后策略信号无效
- REBUILD 只允许极小风险试跑
- 任一失败直接退回 FROZEN

## 5. 一期落地主线
一期的真实业务目标不是落地三账本全系统，而是：
- 用趋势 + 鲨鱼先打通 B 类执行链
- 把中央银行闸门、状态同步、执行一致性和 replay 证据链立起来
- 为未来 A 类现金流系统保留账本语义与接口插槽

## 6. 收尾动作
每次任务完成后必须做：
- 验证
- 更新证据
- 更新必要 owner docs
- 通过 foundation 的 `gitclient` 完成交付或回滚
