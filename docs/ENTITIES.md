# ENTITIES

## 顶层制度对象

### Treasury
- `Type`: 账本 / 保全池 / 下牌桌池
- `Owns`: 锁定资产、生存边界、长期供血权
- `Input`: Harvest 收割、利润回灌、制度拨款
- `Output`: 可用预算、锁定资产、对 Growth/Gamble 的拨款边界
- `Does not own`: 一期具体交易执行

### Growth
- `Type`: 增长池
- `Owns`: 可重复增长型风险暴露
- `Input`: 趋势类机会、中央银行预算、策略 intent
- `Output`: 增长收益、对 Treasury 的回灌
- `Does not own`: 现金流保全、凸性彩票逻辑

### Gamble
- `Type`: 凸性池 / 券化赌博池
- `Owns`: 小资金高赔率跃迁机会
- `Input`: 已沉淀利润拨款、中央银行额度与冻结规则
- `Output`: 高赔率收益、归零事件、Harvest 机会
- `Does not own`: Treasury 资金、无限救援权

## 当前实现核心对象

### MainController
- `Type`: coordinator
- `Owns`: 模块初始化、主循环编排、策略权限应用
- `Input`: 配置、市场事实、风险策略结果
- `Output`: 调度后的执行链路
- `Does not own`: 交易所事实真相、风险宪法本身

### DataSynchronizer
- `Type`: source-of-truth synchronizer
- `Owns`: WS 主、REST 校准辅的原始状态同步
- `Input`: 交易所 WS/REST 数据、执行回报
- `Output`: `DataSnapshot`、校准动作、不确定态标记
- `Does not own`: 业务决策、策略信号

### AccountState
- `Type`: typed business ledger
- `Owns`: 仓位、账户、策略快照的业务态表达
- `Input`: `DataSynchronizer` 原始快照
- `Output`: 风控快照、策略视图
- `Does not own`: 直接对接交易所

### RiskManager
- `Type`: 中央银行闸门 / policy gate
- `Owns`: 系统模式、风险预算、策略允许性、冻结/降级
- `Input`: `AccountState`、策略请求、当前系统条件
- `Output`: policy、approve/deny、disable_strategies
- `Does not own`: 行情生产、订单发送

### MarketDataHub
- `Type`: market data hub
- `Owns`: 行情聚合与分发
- `Input`: WS/REST 行情流
- `Output`: 统一市场数据给策略
- `Does not own`: 风控或交易权限

### TrendEngine
- `Type`: strategy engine / Growth candidate
- `Owns`: 趋势识别、趋势侧 intent 生成
- `Input`: 市场数据、策略快照、系统模式
- `Output`: 趋势 intent
- `Does not own`: 风险审批、订单执行

### SharkEngine
- `Type`: strategy engine / Gamble candidate
- `Owns`: 回调/均值回归侧 intent 生成
- `Input`: 市场数据、策略快照、系统模式
- `Output`: 鲨鱼 intent
- `Does not own`: 风险审批、订单执行

### TinyOMS
- `Type`: execution boundary
- `Owns`: 订单创建、跟踪、撤改单、idempotency
- `Input`: 已审批 intent、交易所桥接能力
- `Output`: 订单状态与执行回报
- `Does not own`: 策略判断、中央银行政策

### BitgetWSBridge / BaseBitgetWsClient
- `Type`: exchange bridge / transport
- `Owns`: Bitget WS 连接、消息标准化、私有/公共通道桥接
- `Input`: 交易所消息、订单发送请求
- `Output`: 标准化事件、桥接层执行结果
- `Does not own`: 风险预算、业务态账本

### ExchangeTrader
- `Type`: REST / CCXT adapter
- `Owns`: 账户、持仓、下单、撤单等 REST 访问
- `Input`: 标准化交易请求
- `Output`: 交易所 API 结果
- `Does not own`: WS 实时状态链

### Contracts
- `Type`: contract layer
- `Owns`: 跨模块 dataclass / schema 契约
- `Input`: 模块间标准化数据
- `Output`: 统一结构对象
- `Does not own`: 业务逻辑
