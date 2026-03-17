# TOOLS_METHOD_FLOW_MAP

## 1. 文档理解流
```text
总纲清单
  -> README
  -> 中央银行设计
  -> 策略手册
  -> 原始想法来源
  -> 关键实现文件
```

next reads:
- `docs/总纲清单（可复制）.md`
- `README.md`
- `docs/中央银行设计.md`

## 2. 交易运行流
```text
Market / Exchange
  -> BaseBitgetWsClient / CCXT
  -> BitgetWSBridge
  -> DataSynchronizer
  -> AccountState
  -> RiskManager
  -> TrendEngine / SharkEngine
  -> TinyOMS
  -> Exchange Execution
  -> Reconcile
```

next reads:
- `main_controller.py`
- `data_synchronizer.py`
- `advanced_risk.py`
- `tiny_oms.py`

## 3. 状态与治理流
```text
Exchange Facts
  -> DataSynchronizer
  -> AccountState
  -> RiskManager
  -> System Mode
  -> Strategy Permission
```

next reads:
- `docs/中央银行设计.md`
- `data_synchronizer.py`
- `account_state.py`
- `advanced_risk.py`

## 4. 策略执行流
```text
MarketDataHub
  -> TrendEngine / SharkEngine
  -> Intent
  -> RiskManager approve/deny
  -> TinyOMS
  -> Bridge / Exchange
```

next reads:
- `trend_engine.py`
- `shark_engine.py`
- `advanced_risk.py`
- `tiny_oms.py`

## 5. 验证与迭代流
```text
Strategy Candidate
  -> Backtest / Battery
  -> Replay
  -> Paper / Sampling
  -> Issue Analysis
  -> Data Optimization
  -> Promotion / Demotion
```

next reads:
- `docs/总纲清单（可复制）.md`
- `test_integration.py`
- `test_regression.py`
- `replay_runner.py`

## 6. 与 foundation 的研发流
```text
foundation init
  -> learnbaseline
  -> fork-current
  -> role threads
  -> summarize-current
  -> refresh-baseline
  -> gitclient
```

next reads:
- foundation `AGENTS.md`
- foundation `docs/WORKFLOW.md`
- foundation `docs/PROJECT_GUIDE.md`
