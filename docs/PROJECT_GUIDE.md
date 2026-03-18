# PROJECT_GUIDE.md

## 一句话北极星
先按总纲建立同频，再用代码确认当前实现，最终把一期趋势/鲨鱼系统收成面向三账本财富系统演化的稳定基座。

## 使用方式
- 这是本项目 `learn` 的主课程、问题库、标准答案和主线锚点。
- 题目本身与整体结构是 owner 精选后的固定课程资产，不应被随意改写、重排或替换。
- 正常允许变化的是：项目真实变化后同步更新标准答案，或为保持同频质量做最小必要微调。
- 首轮同频固定遵守以下阅读顺序：
  1. `docs/总纲清单（可复制）.md`
  2. `README.md`
  3. `docs/中央银行设计.md`
  4. `docs/基于资管双向非对称对冲策略手册.md`
  5. `docs/梦想中的交易资管财富系统想法.md`
  6. `docs/资管双向原始想法.md`
  7. 关键实现文件与测试
- 前 6 份文档先定义“项目是什么、终局是什么、一期是什么”；代码只回答“当前做到哪里”。
- 一旦讨论漂移，不是继续闲聊，而是回到本题库重答，并重新引用证据把主线拉回。

## 与 foundation 的关系
- `quant-factory-os` 是外部基建仓库名，foundation 是它对本项目提供的工程执行角色名。
- foundation 只负责研发执行与交付工具链，不负责本项目的业务逻辑定义。
- 如果需要理解它和本项目的关系，只看 `docs/FOUNDATION_BRIDGE.md`。
- 本项目的业务真相仍由总纲、README、中央银行设计和策略手册定义。

### 建议入口顺序
- 新 agent 首轮同频，优先按 `Q1 -> Q2 -> Q5 -> Q6 -> Q7 -> Q8 -> Q17` 作答。
- 这组题的作用分别是：项目定位、当前阶段、宪法、工作流、当前局面、session continuity、最终主线回拉。
- 这组题答稳之后，再继续 `Q3/Q4/Q9...Q16`，避免一开始就陷进局部实现细节。

### Q1. 整个项目是做什么的，背景，目标是什么，我最终要什么，我是用什么开发方式来完成这个项目的？
#### 为什么问这题
这题决定 agent 是否理解项目的根目标。如果连项目定位都没对齐，后续所有流程都会变成“会跑命令，但不知道为什么要跑”。
#### 标准答案
`a9quant-strategy` 是交易资管财富系统的一期业务仓，不是单一策略脚本，也不是普通交易 runtime。它的终局不是“找一个最赚钱的策略”，而是建立 `Treasury / Growth / Gamble` 三账本财富系统：Treasury 负责生存边界、锁定收益和未来现金流主权，Growth 负责可重复增长，Gamble 负责凸性跃迁与有限预算下注。这个项目的一期并不是先做完整 AI 自我迭代工厂，而是先以中央银行为总控、以《基于资管双向非对称对冲策略手册》里的确定性策略试点为入口，接通模拟盘、接入实盘、采集执行与运行数据，再用这些数据反哺策略优化。也就是说，一期先收“中央银行总控 + 确定性策略试点 + 模拟盘/实盘 + 数据分析反哺”的业务闭环；二期才把 `AI策略创作 -> backtesting/极限电池 -> replay仿真一致性` 这一组更偏 lab 的能力补上。开发方式也因此不是“想到一个策略就写代码”，而是先按总纲、README、中央银行设计和策略手册建立业务同频，再通过 `quant-factory-os` 提供的 foundation 工具链推进 `learnbaseline -> fork-current -> run/task -> summarize -> refresh -> gitclient` 这条工程主线，完成实现、验证和交付。
#### 必查文件
- `docs/总纲清单（可复制）.md`
- `README.md`
- `docs/中央银行设计.md`
#### 查找线索
- 先看总纲里的三账本、下牌桌概率、中央银行和研发闭环。
- 再看 README 里的项目定位和第一阶段落地范围。
- 最后看中央银行设计，确认这个项目的核心不是“策略集合”，而是制度化生存机器。
#### 主线意义
- 这题是总开关，回答错了，后面所有题都会偏。
- 最常见漂移是把项目理解成“Bitget 上的趋势/鲨鱼 bot”，忽略三账本终局和中央银行制度。

### Q2. 项目有几个阶段性目标，现在完成到哪个阶段，每个阶段都完成了什么？
#### 为什么问这题
这题用来判断 agent 是否知道“我们现在在哪”，避免拿未来形态要求当前实现，或者拿历史方案约束当前方向。
#### 标准答案
这个项目至少分三层阶段。第一层是总纲/制度阶段：先把三账本财富系统、中央银行制度、下牌桌概率、冻结/重建逻辑和研发闭环写成不可变宪法。第二层是一期业务闭环阶段：在资源不足的现实下只做 B 类，也就是趋势 + 鲨鱼，优先把中央银行闸门、事实优先的状态链、模拟盘/实盘接通、数据分析和策略反哺优化跑起来。这里的一期重点不是 AI 自动生成策略，而是先拿确定性策略试点把业务闭环跑通。第三层才是二期 lab/扩展阶段：把 `AI策略创作 -> backtesting/极限电池 -> replay仿真一致性` 这组实验室能力补全，并在一期基座稳定后继续把 Treasury/A 类现金流系统、券化拨款、Harvest/Lockbox 和更完整的财富分配制度接进来。当前仓库已经明显过了纯愿景阶段，因为主入口、同步器、业务态账本、中央银行闸门、趋势/鲨鱼、OMS/桥接和集成/回归测试都已经存在；但它仍处于“一期基座强化”阶段，还不是完整三账本终局系统，更不是已经稳定上线的 Treasury 系统。
#### 必查文件
- `docs/总纲清单（可复制）.md`
- `README.md`
- `docs/基于资管双向非对称对冲策略手册.md`
- `main_controller.py`
- `test_integration.py`
- `test_regression.py`
#### 查找线索
- 总纲看终局与阶段路线。
- README 看当前聚焦范围。
- 策略手册看一期到底在做什么。
- 代码和测试只用来确认“当前已实现到哪”。
#### 主线意义
- 这题负责时间定位。
- 最常见漂移是把终局财富系统当成当前已经完整实现，或者反过来把当前代码当成项目全部。

### Q3. 这个项目完成后会形成什么基座能力，接下来第一个落地项目会是什么，你准备怎么承接和落地？
#### 为什么问这题
这题是把“基座仓”与“业务仓”分开，防止把所有问题都堆在一个仓里，造成基建和业务互相污染。
#### 标准答案
对这个仓库来说，完成后形成的不是 foundation 那种自动化研发 OS，而是一个业务侧的交易资管执行基座：它要把中央银行闸门、事实优先的状态链、趋势/鲨鱼执行链、OMS/交易所桥接、模拟盘/实盘运行链、数据分析与策略反哺优化收稳，并为三账本终局预留制度与接口位置。对它的“第一个落地项目”来说，一期本身就是第一个真实落地：Bitget 上以中央银行总控的趋势 + 鲨鱼确定性策略试点。我的承接方式不该再把它当成“未来模板”，而是先按总纲、README、中央银行设计和策略手册理解业务制度，再用代码确认当前实现边界，最后通过 foundation 的自动化主线承接后续研发和交付；其中二期 lab 能力是后续增强，不是一期前提。
#### 必查文件
- `docs/总纲清单（可复制）.md`
- `README.md`
- `docs/中央银行设计.md`
- `docs/基于资管双向非对称对冲策略手册.md`
#### 查找线索
- 看总纲里终局与一期关系。
- 看 README 里当前首阶段聚焦。
- 看中央银行设计和策略手册，确认“一期业务基座”具体包含哪些制度和执行链。
#### 主线意义
- 这题防止把业务仓讲成 foundation 仓。
- 常见漂移是把“承接落地”理解成生成模板，而不是收稳当前业务系统。

### Q4. 如果把不同 AI 界面或运行时分别作为决策端和执行端，它们应如何保持同频，各自承担什么职责？
#### 为什么问这题
这题负责定义脑和手的协作边界，不然模型会把战略、评审、实现、修复混成一层。
#### 标准答案
这个项目里，业务制度和同频课程主要沉淀在本项目 owner docs。更适合的分工是：网页端/对话端负责方向讨论、方案反驳、制度辨析和业务收敛；本地执行端负责按本项目 `PROJECT_GUIDE` 同频、读取证据、修改实现、补测试和回写证据。foundation 在这里不是业务解释源，只是研发执行与交付工具链；它和本项目的关系只需通过 `docs/FOUNDATION_BRIDGE.md` 理解一次即可，不应反复压进业务正文。
#### 必查文件
- `AGENTS.md`
- `docs/PROJECT_GUIDE.md`
- `docs/WORKFLOW.md`
- `docs/FILE_INDEX.md`
- foundation 仓 `AGENTS.md`
- foundation 仓 `docs/WORKFLOW.md`
#### 查找线索
- 先看本项目 owner docs，明确业务制度。
- 再看 foundation 文档，明确自动化主线和交付纪律。
#### 主线意义
- 这题直接决定“同频”是不是靠证据完成。
- 常见漂移是把 foundation 的自动化流程和业务项目的制度内容混成同一层。

### Q5. 这个项目当前的宪法是什么样的？
#### 为什么问这题
这题判断 agent 是否知道谁是硬规则，谁只是说明文档。
#### 标准答案
这个项目当前的业务宪法是一个有主次关系的组合，而不是单一一个文件。源头宪法是 `docs/总纲清单（可复制）.md`，它定义终局、第一性原则、三账本、研发闭环和不可变资金规则，并明确一期/二期边界；制度核心是 `docs/中央银行设计.md`，它把现金流主权、四态状态机、立即冻结红线、系统死亡标准和合法信息流落到工程制度；执行硬契约是本项目的 `AGENTS.md`，它把这些制度压成后续 agent 必须遵守的规则；而 `docs/基于资管双向非对称对冲策略手册.md` 则回答“一期的趋势/鲨鱼如何在这套宪法内行动”。因此，这个项目的宪法不是“某个文件写得最硬谁就赢”，而是“总纲定终局和阶段边界，中央银行设计定制度，本项目 AGENTS 定执行边界，策略手册定一期落地”。
#### 必查文件
- `AGENTS.md`
- `docs/总纲清单（可复制）.md`
- `docs/中央银行设计.md`
- `docs/基于资管双向非对称对冲策略手册.md`
#### 查找线索
- 看总纲定终局与第一性原则。
- 看中央银行设计定制度闸门。
- 看 AGENTS 把这些制度收成可执行约束。
#### 主线意义
- 这题负责分清“制度层”和“普通说明层”。
- 常见漂移是只把 `AGENTS.md` 当宪法，而忽略总纲和中央银行设计才是制度源头。

### Q6. 这个项目当前工作流是什么样的？
#### 为什么问这题
这题用于确认 agent 是否知道从哪一步开始、什么时候停、什么时候不能直接改代码。
#### 标准答案
这个项目当前有两条必须分开的工作流。第一条是研发主线：通过 foundation 的 `init -> learnbaseline -> fork-current -> role/thread -> summarize -> refresh-baseline -> gitclient` 推进需求收敛、最小 task 执行、验证和交付；它回答的是“这轮该怎么改、怎么验证、怎么提交”。第二条是业务运行主线：交易所现实 -> `DataSynchronizer` -> `AccountState` -> `RiskManager(中央银行)` -> 系统模式/策略权限 -> 确定性趋势/鲨鱼策略 -> `TinyOMS / BitgetWSBridge / ExchangeTrader` -> 模拟盘/实盘执行 -> 数据分析 -> 策略优化与反哺。这里要特别区分阶段：一期业务运行主线的重点是“中央银行总控 + 确定性策略试点 + 模拟盘/实盘 + 数据反哺”；而 `AI策略创作 -> backtesting/极限电池 -> replay仿真一致性` 这条更偏实验室的能力，属于二期 lab 强化，不是当前一期主线。
#### 必查文件
- `docs/WORKFLOW.md`
- `AGENTS.md`
- `main_controller.py`
- `data_synchronizer.py`
- `advanced_risk.py`
- `tiny_oms.py`
#### 查找线索
- 先看 WORKFLOW 里研发主线和业务主线的拆分。
- 再用主入口和关键模块确认业务链条不是想象。
#### 主线意义
- 这题负责把 agent 拉回流程，而不是细节。
- 常见漂移是把“如何研发这个项目”和“项目运行链路”混在一起。

### Q7. 我们现在的项目有没有未完成的任务呢，最新的批次在讨论什么问题，你是怎么查的？
#### 为什么问这题
这题要求 agent 具备“看当前局面”的能力，而不是只会泛泛复述项目介绍。
#### 标准答案
对这个项目来说，未完成任务必须分成两层看。业务层面，A 类现金流系统、Treasury 的完整落地、三账本真实资金分层和更稳定的运维数据闭环都还没完成；一期层面，当前重点仍是把中央银行闸门、状态同步、确定性策略试点、模拟盘/实盘接通、执行一致性、replay 和验证面收稳。工程推进层面，如果需要确认当前自动化批次在做什么，再去看 foundation 的 run/task/evidence；但业务判断本身不能反过来依赖 foundation 才成立。
#### 必查文件
- `docs/PROJECT_GUIDE.md`
- `docs/WORKFLOW.md`
- foundation 仓 `tools/project_config.json`
- foundation 仓 `reports/<RUN_ID>/summary.md`
- foundation 仓 `reports/<RUN_ID>/decision.md`
#### 查找线索
- 先定业务层面的“未完成”。
- 再定当前 foundation run 层面的“正在推进什么”。
#### 主线意义
- 这题把学习拉回“当前在做什么”。
- 常见漂移是只会讲业务愿景，不知道当前工程推进点。

### Q8. 你查了最近的 session 说了什么，你是从哪里查的？
#### 为什么问这题
这题要求 agent 具备 session continuity，不然一换会话就会忘掉当前主线。
#### 标准答案
最近 session 的内容不能靠聊天记忆猜。对这个项目来说，先要从本项目 owner docs 和当前实现判断业务主线是否稳定；如果还需要确认当前自动化批次在推进什么，再去看 foundation 侧的 `runtime_state`、当前 `RUN_ID` 下的 `summary.md / decision.md`。session continuity 的关键不是复述所有聊天，而是知道最近是在推进：owner docs 同频、一期业务闭环、还是具体工程兼容问题。
#### 必查文件
- foundation 仓 `tools/project_config.json`
- foundation 仓 `reports/<RUN_ID>/summary.md`
- foundation 仓 `reports/<RUN_ID>/decision.md`
#### 查找线索
- 先看当前 run 和 task 指针。
- 再看 summary 和 decision 的稳定结论。
#### 主线意义
- 这题是“主线连续性”的核心。
- 常见漂移是把当前 session 当成完全新问题，不看已有稳定结论。

### Q9. 项目需求讨论应该使用什么流程？
#### 为什么问这题
这题负责把“讨论”和“执行”分开，防止先写代码后补理由。
#### 标准答案
这个项目的需求讨论应先从业务本体出发：先用本项目 `PROJECT_GUIDE` 建立业务同频，再明确本轮到底是在改制度、改实现、补验证还是修运维面，然后再决定是否进入 foundation 的 run/session 工程主线。run 级需求收敛必须至少回答：这轮变化对应总纲/中央银行/一期策略的哪一层，影响哪些实现模块和验证面，哪些内容明确不做。
#### 必查文件
- `docs/PROJECT_GUIDE.md`
- `docs/WORKFLOW.md`
- foundation 仓 `docs/WORKFLOW.md`
- foundation 仓 `AGENTS.md`
#### 查找线索
- 先判断需求属于制度层、实现层还是验证层。
- 再决定是否进入最小 task 拆分。
#### 高质量追问模板
- 这次需求是在修总纲制度、中央银行规则，还是在补当前实现/验证？
- 它影响趋势、鲨鱼、风控、状态同步、执行桥接还是 replay 面？
- 哪些属于本轮必须做，哪些明确不做？
- 如果现在直接动代码，最可能漏掉哪条制度边界或验证面？
#### 自我梳理输出骨架
- `run_goal`: 本轮 run 真正要解决的问题
- `layer`: 制度层 / 实现层 / 验证层 / 运维层
- `scope`: 本轮纳入范围
- `non_goals`: 本轮明确不做
- `impacted_modules`: 受影响模块与验证面
- `acceptance`: 如何判断可以进入 task 拆分
#### 主线意义
- 这题负责守住“讨论先于执行”。
- 常见漂移是把业务构想、制度设计和代码修复混成一个问题。

### Q10. 项目实施流程是什么，需要哪些角色协作，如何保证角色独立思考，目前实现到了什么程度？
#### 为什么问这题
这题用来区分“多角色讨论能力”和“单一实现能力”，避免只靠一个视角拍脑袋出方案。
#### 标准答案
这个项目在工程上可以承接 foundation 的多角色实施流程，但角色讨论必须建立在本项目业务宪法之上，而不是先跑工程流程再回头补业务理解。更合理的分工是：`run-main` 负责把总纲、中央银行设计、一期范围和本轮 run 目标收敛清楚；`dev` 负责实现和局部技术决策；`test` 独立看 replay、一致性、风险门和回归面；`arch` 只在制度/结构变更较大时介入。独立性不是靠口头要求，而是靠 session 隔离、证据回写和 run-main 的最终裁决。当前实现层面，本项目已经具备真实交易运行骨架；但业务阶段判断必须再更明确：一期优先做中央银行总控下的确定性策略试点、模拟盘/实盘接通、执行数据分析与反哺优化，二期再把 AI 策略实验室能力补全。
#### 必查文件
- `docs/WORKFLOW.md`
- foundation 仓 `AGENTS.md`
- foundation 仓 `docs/WORKFLOW.md`
#### 查找线索
- 看本项目 WORKFLOW 的研发主线。
- 看 foundation 的角色线程与 summary 规则。
#### 高质量追问模板
- 这轮 task 只需要 `dev/test` 还是需要 `arch`？
- 哪些判断必须由 run-main 拍板，哪些应由 test 独立给出？
- 当前业务仓已经实现的部分，哪些适合继续自动化，哪些仍需 owner 人工确认？
#### 自我梳理输出骨架
- `role_plan`: 本轮需要哪些角色
- `role_responsibilities`: 各角色边界
- `verification_axes`: 测试需要覆盖的功能/流程/数据/非功能面
- `current_capability_gap`: 本项目已经实现到哪层，foundation 承接还差什么
#### 主线意义
- 这题防止把“角色协作”说成空口号。
- 常见漂移是只讲业务模块，不讲工程协作方式。

### Q11. 项目中的核心对象、关键状态和交付单元分别是什么，它们的生命周期是怎样的？
#### 为什么问这题
这题负责统一名词系统，避免 agent 在 task、run、project 这些层级上混乱。
#### 标准答案
在业务系统里，核心对象至少包括：`Treasury / Growth / Gamble` 三账本语义，`MainController` 组合入口，`DataSynchronizer` 事实同步器，`AccountState` 业务态账本，`RiskManager` 中央银行闸门，`TrendEngine / SharkEngine` 策略引擎，`TinyOMS` 执行边界，以及交易所桥接与契约层。关键状态包括：中央银行四态 `NORMAL / DEFENSIVE / FROZEN / REBUILD`，账户/持仓事实状态，策略权限状态，以及回放/验证状态。交付单元在工程上当然可以沿用 foundation 的 `project / run / task / PR / evidence` 分层，但这不是本题主体；本题主体是先把业务对象和业务状态链理解清楚，再把工程交付单元放上去。
#### 必查文件
- `docs/ENTITIES.md`
- `docs/WORKFLOW.md`
- `account_state.py`
- `advanced_risk.py`
- `contracts.py`
- foundation 仓 `docs/ENTITIES.md`
#### 查找线索
- 先看本项目对象字典。
- 再看关键实现和 foundation 的工程对象定义。
#### 高质量追问模板
- 这次讨论的是业务对象，还是工程对象？
- 哪些状态属于事实账本，哪些属于审批状态，哪些属于 task/run 工程状态？
- 这次要沉淀到 owner docs、run summary 还是 task summary？
#### 自我梳理输出骨架
- `business_objects`: 本项目核心业务对象
- `engineering_objects`: foundation 承接的工程对象
- `state_layers`: 事实态 / 闸门态 / 工程态
- `delivery_unit`: 当前更适合落到哪一层
#### 主线意义
- 这题负责名词统一。
- 常见漂移是把业务实体、状态机和工程交付单元混成一层。

### Q12. 我们在项目的准备工作做好后，我们一个需求讨论方向，从流程的哪一步开始？
#### 为什么问这题
这题确认“准备完成后做什么”，避免准备完成后还直接跳到写代码。
#### 标准答案
对本项目来说，准备工作做好后，如果同频已经稳定，就应先在业务层判断本轮需求属于制度、实现、验证还是运维，并且确保它已经回到本项目 `PROJECT_GUIDE` 与总纲约束之下；然后再进入 foundation 的 `run(appserverclient)` 主线，把方向拆成最小 task。也就是说，foundation 是工程承接层，不是需求定义起点。
#### 必查文件
- `docs/PROJECT_GUIDE.md`
- `docs/WORKFLOW.md`
- foundation 仓 `docs/WORKFLOW.md`
- foundation 仓 `AGENTS.md`
#### 查找线索
- 看本项目主线是否已经同频。
- 再看 foundation 的 run/session 主线从哪一步接上。
#### 高质量追问模板
- 当前这轮问题在本项目里属于制度层、实现层还是验证层？
- run 方向是否已经清楚到可以拆 task？
- 如果现在不该进实现，缺的是哪条边界或哪类证据？
#### 自我梳理输出骨架
- `direction_layer`: 当前问题所在层
- `run_ready`: 是否已具备 run 收敛前提
- `missing_boundaries`: 还缺哪些边界
- `first_task_candidate`: 第一块最小 task 候选
- `why_not_code_yet`: 如果还不能进实现，阻塞是什么
#### 标准化 Markdown 草稿模板
当 AI 读完客户给的杂乱材料后，先输出一版标准化 Markdown 草稿，再进入 run 方向收敛与 task 拆分；这一步是协议层草稿，不是机器真相源。
```md
# Run Intake Draft

## 1. Background
- 业务背景：
- 当前痛点：
- 为什么现在要做：

## 2. Run Goal
- 本轮 run 要解决的问题：
- 期望产出：

## 3. Scope
- 明确纳入范围：
- 涉及模块/流程/数据：
- 外部系统/依赖：

## 4. Non-Goals
- 本轮明确不做：

## 5. Impacted Modules
- 模块：
- 数据面：
- 角色面：

## 6. Risks And Abnormal Flows
- 已知风险：
- 异常流：
- 仍不清楚的边界：

## 7. Non-Functional Constraints
- 性能：
- 稳定性：
- 安全/审计：
- 环境/部署：

## 8. Acceptance
- 如何判断 run 已收敛到可以拆 task：
- 必要验证面：

## 9. Role Plan
- run-main：
- dev：
- test：
- arch（如需要）：

## 10. Task Candidates
- 候选 task 1：
- 候选 task 2：
- 为什么它们是最小切片：

## 11. Open Questions
- 还需要用户或 owner 明确什么：

## 12. Summary Target
- 当前应先形成：
  - thread summary / task summary / run summary
- 暂不进入实现的原因：
```
#### 主线意义
- 这题负责接上岗后的下一步。
- 常见漂移是把环境准备或 baseline 学习误当成“可以直接改代码”。

### Q13. 项目的分支与交付管理规则是什么，当前是否满足需求？
#### 为什么问这题
这题用于校准交付纪律，避免“本地能跑就行”而没有分支/PR 约束。
#### 标准答案
本项目默认沿用 foundation 的交付主线：一轮 task 对应一条分支和一组证据，通过 `gitclient` 统一处理 commit、PR、merge、rollback 和 sync main。当前需求也应继续按这个规则执行，因为业务仓不应该自行发明另一套交付体系。对本项目来说，额外要求是：如果业务制度、阅读顺序、同频课程或关键对象边界变了，owner docs 必须一起更新，不能只交代码。
#### 必查文件
- foundation 仓 `AGENTS.md`
- foundation 仓 `docs/WORKFLOW.md`
- `AGENTS.md`
- `docs/WORKFLOW.md`
#### 查找线索
- 看 foundation 的 PR discipline。
- 看本项目对 owner docs 更新的要求。
#### 主线意义
- 这题负责交付边界。
- 常见漂移是业务仓只顾代码，不顾证据、文档和可回滚交付。

### Q14. 每次做完任务，你必须要做什么事情？
#### 为什么问这题
这题是执行闭环问题，用来确认 agent 知道“写完代码不是结束”。
#### 标准答案
每次做完任务，必须做四件事：验证、更新证据、同步必要 owner docs、再通过 foundation 的 `gitclient` 做提交/PR/回滚。对本项目尤其要注意：只要制度认知、阅读顺序、对象边界或当前阶段判断变了，就必须更新本项目 owner docs，而不是让聊天记录替代正式文档。
#### 必查文件
- foundation 仓 `AGENTS.md`
- foundation 仓 `docs/WORKFLOW.md`
- `AGENTS.md`
- `docs/WORKFLOW.md`
- `docs/PROJECT_GUIDE.md`
#### 查找线索
- 看 foundation 的 evidence gate 和 docs freshness gate。
- 看本项目 owner docs 是否已成为正式真相源。
#### 主线意义
- 这题负责把“完成”定义清楚。
- 常见漂移是把“代码写完”误当“任务完成”。

### Q15. 如果目标体验是高质量、低噪音、强自动化，当前最需要优先优化什么？
#### 为什么问这题
这题用来防止局部最优。项目是基建，就必须优先优化通用流程，而不是只修某一个具体命令。
#### 标准答案
对本项目来说，当前最需要优先优化的不是继续扩策略种类，也不是抢先做完整 AI lab，而是先把一期业务闭环收稳。也就是说，优先级应放在：中央银行闸门是否真不可绕过、状态同步是否真以事实为准、确定性趋势/鲨鱼试点是否已打通模拟盘/实盘、执行与 replay 是否可复现、数据分析与策略反哺是否已经形成稳定闭环、owner docs 是否真的能先于代码建立同频。只有这些稳定后，再谈扩展 A 类现金流系统、三账本运行细节和二期的 `AI策略创作 -> backtesting/极限电池 -> replay仿真一致性` 实验室能力。
#### 必查文件
- `docs/总纲清单（可复制）.md`
- `docs/中央银行设计.md`
- `test_integration.py`
- `test_regression.py`
- `replay_runner.py`
#### 查找线索
- 看总纲的研发闭环。
- 看中央银行设计的冻结/重建逻辑。
- 看当前测试与 replay 面是否足够支撑制度。
#### 主线意义
- 这题负责产品视角。
- 常见漂移是继续堆功能，而不是先收稳制度和验证。

### Q16. 这个项目中 AI/工具系统的正确打开方式是什么，当前用到了哪些能力，你能列出来吗？
#### 为什么问这题
这题是技能题，确认 agent 不是只知道项目流程，还知道 Codex CLI 这个执行器该怎么正确使用。
#### 标准答案
这个项目里，AI/工具系统的正确打开方式是“双层协作”：本项目 owner docs 负责业务同频与制度约束，foundation 只负责自动化研发 OS。具体能力上，本项目提供 `PROJECT_GUIDE / AGENTS / WORKFLOW / ENTITIES / FILE_INDEX / TOOLS_METHOD_FLOW_MAP / PROJECT_BOOTSTRAP_PROTOCOL / FOUNDATION_BRIDGE` 这套业务与承接说明；foundation 提供 `init / learnbaseline / fork-current / role-turn / summarize / refresh-baseline / gitclient` 这套运行链。正确方式不是跳过文档直接让工具跑，而是先按本项目文档进入，再用 foundation 工具推进工程流。
#### 必查文件
- `AGENTS.md`
- `docs/WORKFLOW.md`
- `docs/PROJECT_GUIDE.md`
- foundation 仓 `AGENTS.md`
- foundation 仓 `docs/WORKFLOW.md`
#### 查找线索
- 先看本项目 7 份 owner docs。
- 再看 foundation 的主流程与工具边界。
#### 主线意义
- 这题负责技能上岗。
- 常见漂移是只会用工具，不会先按业务文档同频。

### Q17. 根据最新的 session，你现在做的东西是否偏离了我们现在最重要的任务，你是否认为我们偏离了主线，为什么，接下来我们应该怎么做？
#### 为什么问这题
这题是最终回拉题。它不问知识点，而是判断 agent 能不能把当前执行重新拉回最重要的方向。
#### 标准答案
对这个项目来说，只要当前动作没有帮助我们更准确地区分“终局制度 / 一期业务闭环 / 二期 lab 能力 / 当前实现”，就有偏离主线的风险。现在最重要的任务不是继续堆新功能，也不是围着某个局部命令打转，而是先把本项目 owner docs，尤其是 `docs/PROJECT_GUIDE.md`，收成真正稳定的同频核心；然后围绕一期正确主线推进：中央银行总控、确定性策略试点、模拟盘/实盘接通、数据分析与执行数据反哺优化。二期的 AI 实验室能力当然重要，但它不是当前一期主线。foundation 在这里只是工程承接工具链，不应抢业务主线的位置。凡是会把项目重新拉回“只是一个趋势/鲨鱼 bot”叙事，或者把二期 lab 提前冒充成一期主线的动作，都算偏离主线。
#### 必查文件
- `docs/PROJECT_GUIDE.md`
- `AGENTS.md`
- `docs/WORKFLOW.md`
- `docs/FILE_INDEX.md`
- foundation 仓 `tools/project_config.json`
- foundation 仓 `reports/<RUN_ID>/summary.md`
- foundation 仓 `reports/<RUN_ID>/decision.md`
#### 查找线索
- 先看本项目 owner docs 是否已经统一。
- 再看 foundation 当前 run 是否在推动正确方向。
#### 主线意义
- 这题就是主线回拉器。
- 常见漂移是被单个命令、单个 bug 或单个模块拖走，忘了先同频、后自动化。
