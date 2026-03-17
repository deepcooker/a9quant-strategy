# PROJECT_GUIDE.md

## 一句话北极星
先按总纲建立同频，再用代码确认当前实现，最终把一期趋势/鲨鱼系统收成面向三账本财富系统演化的稳定基座。

## 使用方式
- 本文件是本项目的同频核心，不是摘要页。
- 题目结构保留为固定课程资产，只更新标准答案与证据锚点。
- 默认阅读顺序固定为：
  1. `docs/总纲清单（可复制）.md`
  2. `README.md`
  3. `docs/中央银行设计.md`
  4. `docs/基于资管双向非对称对冲策略手册.md`
  5. `docs/梦想中的交易资管财富系统想法.md`
  6. `docs/资管双向原始想法.md`
  7. 关键实现文件
- 前 6 份文档先定义“项目是什么、终局是什么、一期是什么”；代码只回答“当前做到哪里”。
- 一旦讨论漂移，就回到本题库重答，不继续闲聊。

## 建议入口顺序
- 首轮同频优先答：`Q1 -> Q2 -> Q5 -> Q6 -> Q10 -> Q11 -> Q17`
- 然后再补：`Q3/Q4/Q7/Q8/Q9/Q12/Q13/Q14/Q15/Q16`

### Q1. 这个项目到底是什么？
#### 为什么问这题
先定项目身份，否则后面会把它看成单一策略脚本或普通交易 bot。
#### 标准答案
这个项目是交易资管财富系统的一期业务仓。终局不是“某个策略赚更多”，而是形成 `Treasury / Growth / Gamble` 三账本财富系统；一期在资源约束下只能先落地 B 类，也就是趋势 + 鲨鱼，但必须按终局主设计演化。当前仓库的角色是：把 Bitget 上的趋势/鲨鱼执行链、中央银行闸门、状态同步、订单执行和回放验证先打通，并为未来 A 类现金流系统预留制度插槽。
#### 必查文件
- `docs/总纲清单（可复制）.md`
- `README.md`
#### 查找线索
- 看总纲里的三账本、下牌桌概率、中央银行定义。
- 看 README 里“机构级量化交易基座”和“一期聚焦 Bitget + 趋势/鲨鱼”。
#### 主线意义
- 这题负责防止把项目误看成“只做趋势策略”或“只做交易 runtime”。

### Q2. 项目终局、第一性原则和一期落地分别是什么？
#### 为什么问这题
这题负责区分终局制度、一期资源约束和当前落地范围。
#### 标准答案
终局是三账本财富系统：Treasury 负责保全和现金流，Growth 负责可重复增长，Gamble 负责凸性跃迁；目标函数核心是下牌桌概率，而不是长期 Sharpe。第一性原则包括：风险前置、制度化闸门、研发闭环、证据链、允许“不交易”。一期落地只能先做 B 类：趋势 + 鲨鱼，通过 Bitget 首个落地验证中央银行架构、状态机、风险监管、订单执行和 replay 证据链。
#### 必查文件
- `docs/总纲清单（可复制）.md`
- `README.md`
- `docs/基于资管双向非对称对冲策略手册.md`
#### 查找线索
- 总纲里的“三件事路线图”和“一期只能落地 B 类”。
- README 里的“第一阶段落地聚焦”。
#### 主线意义
- 这题负责防止把终局和一期混成一层。

### Q3. 三账本在本项目里分别意味着什么？
#### 为什么问这题
如果三账本只是口号，后续文档和系统设计都会散。
#### 标准答案
`Treasury` 是主资产库和生存边界，负责保全、锁定、下牌桌和未来现金流系统的位置；`Growth` 是可重复增长池，一期主要由趋势承担；`Gamble` 是凸性池，当前更接近鲨鱼 L2/L3 一类的高赔率跃迁模块，允许归零，但必须券化、冻结、冷却和 Harvest。当前仓库还没有完整 Treasury 策略实现，但文档和风控必须先把三账本语义写死。
#### 必查文件
- `docs/总纲清单（可复制）.md`
- `docs/梦想中的交易资管财富系统想法.md`
#### 查找线索
- 看总纲中的三账本定义、Coupon、Freeze/Resume、Harvest。
- 看原始想法里的 Pool A/B/C 和资金流规则。
#### 主线意义
- 这题决定后续 AGENTS/ENTITIES/WORKFLOW 是否能统一口径。

### Q4. 中央银行在这个项目里到底是什么？
#### 为什么问这题
中央银行是项目特色，如果理解成普通风控模块就会偏。
#### 标准答案
中央银行不是策略，也不是抽象哲学，而是现金流主权与制度闸门：判断状态是否可信、是否允许风险暴露、如何分配预算、何时冻结/解冻系统，以及何时冷酷关闭任一策略。它当前落地在 `advanced_risk.py` 为核心，围绕 `AccountState/DataSynchronizer/MainController` 形成四态状态机和事实优先原则。
#### 必查文件
- `docs/中央银行设计.md`
- `main_controller.py`
- `advanced_risk.py`
- `data_synchronizer.py`
#### 查找线索
- 看中央银行设计里的四态状态机、立即冻结红线、唯一合法信息流。
- 看主循环里 `evaluate_policy()` 和 `disable_strategies`。
#### 主线意义
- 这题负责把项目核心亮点写成制度，而不是“高级风控”空话。

### Q5. 一期策略落地的真正内容是什么？
#### 为什么问这题
不把一期规则写清楚，PROJECT_GUIDE 就会空转。
#### 标准答案
一期不是“做所有资管模块”，而是把趋势引擎 + 鲨鱼引擎按双向非对称对冲手册落地。趋势负责先赚钱、扩大战果、承担 Growth；鲨鱼负责在回调/均值回归阶段吃大波动，偏向 Gamble。两者共享中央银行审批，所有动作都必须先过 RiskManager 和状态闸门。
#### 必查文件
- `docs/基于资管双向非对称对冲策略手册.md`
- `trend_engine.py`
- `shark_engine.py`
- `advanced_risk.py`
#### 查找线索
- 看策略手册里的日线状态、趋势 L1/L2/L3、鲨鱼 L1/L2/L3、杠杆与否决规则。
#### 主线意义
- 这题负责说明一期具体是“什么策略、怎么打”。

### Q6. 这个项目当前主架构是什么？
#### 为什么问这题
避免把代码理解成散乱脚本。
#### 标准答案
当前主架构是“中央银行式交易执行架构”：`MainController` 负责启动与协调；`DataSynchronizer` 负责 WS 主、REST 校准辅的事实同步；`AccountState` 负责业务态账本；`RiskManager` 负责中央银行闸门；`TrendEngine/SharkEngine` 负责策略决策；`TinyOMS + BitgetWSBridge + BaseBitgetWsClient + ExchangeTrader` 负责执行与交易所桥接；`MarketDataHub` 负责行情枢纽；`contracts.py` 提供跨模块契约。
#### 必查文件
- `README.md`
- `docs/中央银行设计.md`
- `main_controller.py`
- `data_synchronizer.py`
- `contracts.py`
#### 查找线索
- 先看 README 中央银行架构三层。
- 再看 `main_controller.py` 的初始化顺序和主循环。
#### 主线意义
- 这题把终局制度和当前实现连接起来。

### Q7. 当前已经实现到哪一步？
#### 为什么问这题
需要分清“设计文档里想做的”和“代码里已经有的”。
#### 标准答案
当前不是空想仓。代码里已经存在真实主入口、状态同步、中央银行闸门、趋势/鲨鱼执行链、OMS 和桥接层，也有 integration/regression/replay 相关验证资产。但它还远没到终局财富系统：三账本制度主要还体现在文档和风控框架上，A 类现金流系统尚未落地，Treasury 还未形成完整策略与运行闭环。
#### 必查文件
- `main_controller.py`
- `data_synchronizer.py`
- `account_state.py`
- `test_integration.py`
- `test_regression.py`
- `replay_runner.py`
#### 查找线索
- 看主循环是否真的串起状态 -> 风控 -> 策略 -> OMS -> 校准。
- 看测试面是否覆盖 live gate、risk gate、replay。
#### 主线意义
- 防止把愿景当现状，也防止低估当前实现。

### Q8. 当前最关键的事实账本和状态机在哪里？
#### 为什么问这题
如果事实链不清楚，后续所有风险讨论都是假的。
#### 标准答案
事实链核心是：交易所现实 -> 执行/回报 -> `DataSynchronizer` -> `AccountState` -> `RiskManager` -> 系统模式 -> 策略权限。`DataSynchronizer` 负责 WS 主、REST 校准辅，`AccountState` 承接业务态视图，`RiskManager` 决定 NORMAL/DEFENSIVE/FROZEN/REBUILD 等监管逻辑。任何绕开这条链的状态修改都应视为非法。
#### 必查文件
- `docs/中央银行设计.md`
- `data_synchronizer.py`
- `account_state.py`
- `advanced_risk.py`
#### 查找线索
- 看“唯一合法信息流”和四态状态机。
- 看同步器的 `force_rest_sync`、不确定态与校准。
#### 主线意义
- 这题是后续风控与执行所有判断的底座。

### Q9. 当前最大的系统亮点是什么？
#### 为什么问这题
如果不能说清亮点，后续 owner docs 会退化成普通项目说明。
#### 标准答案
本项目最大亮点不是“能下单”，而是把交易系统上升到现金流治理：先从敌人视角列出击穿场景，再建立不可绕过的现金流宪法、四态状态机、中央银行权限清单、合法信息流、冻结与重建逻辑。换句话说，真正的亮点是“把策略执行系统做成制度化的生存机器”，而不是仅做策略盈利器。
#### 必查文件
- `docs/中央银行设计.md`
- `docs/总纲清单（可复制）.md`
#### 查找线索
- 看“现金流主权”“冻结红线”“系统死亡标准”“中央银行唯一权限”。
#### 主线意义
- 这题决定 AGENTS/WORKFLOW 是否会抓住项目灵魂。

### Q10. 这个项目和 foundation 的关系是什么？
#### 为什么问这题
需要说清 business repo 和 foundation repo 的分工，不然流程会混。
#### 标准答案
foundation 仓负责自动化研发 OS：`init / learnbaseline / fork-current / role-thread / summarize / refresh-baseline / gitclient` 这套流程、session 主线与证据沉淀。`a9quant-strategy` 负责业务系统本身：文档宪法、策略与风控设计、执行实现、回放与运维数据演化。需求讨论、task/run 去噪和 git 收尾仍默认承接 foundation 规则，但业务理解必须先从本项目自己的总纲与 PROJECT_GUIDE 进入。
#### 必查文件
- `AGENTS.md`
- `docs/WORKFLOW.md`
- foundation 仓 `AGENTS.md / docs/WORKFLOW.md`
#### 查找线索
- 看 foundation 负责什么，本项目负责什么。
#### 主线意义
- 这题防止把 foundation 叙事直接拷贝成业务项目自述。

### Q11. 这个项目现在最重要的阅读顺序是什么？
#### 为什么问这题
这是同频核心题，答错了后面都错。
#### 标准答案
固定顺序是：
1. `docs/总纲清单（可复制）.md`
2. `README.md`
3. `docs/中央银行设计.md`
4. `docs/基于资管双向非对称对冲策略手册.md`
5. `docs/梦想中的交易资管财富系统想法.md`
6. `docs/资管双向原始想法.md`
7. `main_controller.py`
8. `data_synchronizer.py`
9. `account_state.py`
10. `advanced_risk.py`
11. `trend_engine.py / shark_engine.py`
12. `tiny_oms.py / bitget_ws_bridge.py / base_bitget_ws.py / ccxt_utils.py`
13. `test_integration.py / test_regression.py / replay_runner.py`
#### 必查文件
- 同上
#### 查找线索
- 先定制度，再定入口，再定核心闸门，再定一期规则，最后才用代码确认。
#### 主线意义
- 这题直接决定新 AI 会不会同频。

### Q12. 准备工作完成后，需求讨论从哪一步开始？
#### 为什么问这题
防止一上来就写代码。
#### 标准答案
准备工作完成后，先用 foundation 的 `learnbaseline` 建项目级同频，再围绕本项目 `PROJECT_GUIDE` 和当前 run 方向做需求收敛，明确本轮是改制度、改实现、补验证还是补运维数据面，然后才拆最小 task。若文档理解还没稳，就回题库，不进实现。
#### 必查文件
- foundation 仓 `docs/WORKFLOW.md`
- 本项目 `docs/PROJECT_GUIDE.md`
#### 查找线索
- 看需求到底是制度层、实现层还是验证层。
#### 主线意义
- 这题负责防止先做后补。

### Q13. 分支与交付规则是什么？
#### 为什么问这题
需要让业务项目承接 foundation 的交付纪律。
#### 标准答案
本项目默认沿用 foundation 的分支与交付规则：一轮 task 对应一条分支和一组证据；提交、回滚、PR、合并、同步 main 由 `gitclient` 管；任何重要变更都要能回溯到 run/task/evidence，而不是只在聊天里成立。
#### 必查文件
- foundation 仓 `AGENTS.md`
- foundation 仓 `docs/WORKFLOW.md`
#### 查找线索
- 看 `gitclient` 和 docs freshness/evidence gate。
#### 主线意义
- 这题负责把业务迭代接回工程纪律。

### Q14. 每次任务做完必须做什么？
#### 为什么问这题
防止“代码改完就算完成”。
#### 标准答案
每次任务结束后，至少要完成：验证、证据更新、必要文档更新、git 提交/PR/回滚。如果这次改动影响了项目认知、制度、流程或对象边界，就必须同步更新本项目的 owner docs，而不是只改代码。
#### 必查文件
- foundation 仓 `AGENTS.md`
- 本项目 7 份 owner docs
#### 查找线索
- 看 evidence gate 和 docs freshness gate。
#### 主线意义
- 这题定义“完成”的工程含义。

### Q15. 当前最需要优先优化什么？
#### 为什么问这题
避免被局部实现带偏。
#### 标准答案
当前最需要优先优化的不是继续扩策略种类，而是把制度、状态机、执行一致性和回放验证收稳：中央银行闸门是否真不可绕过，状态同步是否真以事实为准，执行与 replay 是否可复现，证据链是否可追溯。只有这些稳定后，三账本终局才有真实落地基础。
#### 必查文件
- `docs/总纲清单（可复制）.md`
- `docs/中央银行设计.md`
- `test_integration.py`
- `test_regression.py`
- `replay_runner.py`
#### 查找线索
- 看研发闭环、冻结规则、回放一致性与测试面。
#### 主线意义
- 这题负责把注意力放回制度与验证，不是功能堆叠。

### Q16. 这个项目里 AI/工具系统的正确打开方式是什么？
#### 为什么问这题
要明确 foundation 工具怎么服务业务仓。
#### 标准答案
正确打开方式是：在 foundation 仓使用 `init / learnbaseline / fork-current / role-thread / summarize / refresh-baseline / gitclient` 这套流程服务本项目；在本项目侧，owner docs 提供同频课程与业务宪法。AI 不应直接跳过文档与证据，更不应把聊天当单一真相源。
#### 必查文件
- foundation 仓 `AGENTS.md`
- foundation 仓 `docs/WORKFLOW.md`
- 本项目 `docs/PROJECT_GUIDE.md`
#### 查找线索
- 看 foundation 是如何驱动目标项目的。
#### 主线意义
- 这题负责把“工具系统”和“业务文档系统”接起来。

### Q17. 根据当前主线，你现在最该做什么？
#### 为什么问这题
这是最终回拉题。
#### 标准答案
当前最该做的是：先让本项目 owner docs 稳定，把 `PROJECT_GUIDE` 真正写成同频核心，再继续承接 foundation 的自动化主线与后续 task/run 演化。只要 `PROJECT_GUIDE` 还不稳、文档优先级还没写死、制度和当前实现还没分清，任何自动化都只是放大误解。
#### 必查文件
- `docs/PROJECT_GUIDE.md`
- `AGENTS.md`
- `docs/WORKFLOW.md`
- `docs/FILE_INDEX.md`
#### 查找线索
- 看这 7 份 owner docs 是否已统一口径。
#### 主线意义
- 这题负责把一切拉回“先同频、后自动化”。
