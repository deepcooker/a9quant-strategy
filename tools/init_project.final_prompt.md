[固定模板段]

init-project: 接下来请你对一个尚未接入基座的新项目执行首轮初始化理解。

目标：
- 基于项目已有文档和现有实现，完成首轮 17 问初始化理解
- 先学习、再补证据、再更新状态，不允许直接跳到写结论
- 当前阶段不要直接反写 owner docs

硬规则：
- 你面对的是“未初始化项目”，只有在首轮接入完成后，项目才允许进入 baseline 主线
- 输入材料不是最终真相，必须结合现有实现确认项目已经做到哪里
- 不允许把我们自己的 owner docs 当成原始输入材料
- 如果证据不够，必须明确提出“下一批必读文件”，不能假装已经理解完整
- 当前阶段默认是 `xhigh` 的 plan/gating 阶段
- 先产出 17 问完成度、缺口和下一步引导；不要直接产出 owner docs 正文

默认读取顺序：
1. 先读项目根目录的 `README.md`，把它当作 guide / 材料理解说明
2. 再读原始 docs 材料（`docs/**/*.md|txt|doc|docx`），但排除以下 owner docs 目标文件：
   - `AGENTS.md`
   - `docs/PROJECT_GUIDE.md`
   - `docs/WORKFLOW.md`
   - `docs/ENTITIES.md`
   - `docs/FILE_INDEX.md`
   - `docs/TOOLS_METHOD_FLOW_MAP.md`
   - `docs/PROJECT_BOOTSTRAP_PROTOCOL.md`
3. 从 README 和原始 docs 中提取显式线索：
   - 明确提到的文件名
   - 模块名
   - 主流程入口
   - 关键对象/状态
   - 已实现 / 未实现描述
4. 结合程序提供的“轻量仓库探测结果”做第一轮判断
5. 如果本轮还有 session 级补充执行指令，必须先吸收它对文档优先级、阅读顺序、owner 关注点和阶段边界的修正
6. 输出“下一批必读文件”
7. 读取这些文件后，再判断 17 问目前能完成到哪一步

对“轻量仓库探测结果”的理解：
- 它只是仓库现状摘要，不等于代码已被完整阅读
- 它通常包含：
  - 根目录文件摘要
  - 候选主入口文件
  - 候选测试文件
  - 候选配置/契约/状态文件
  - README 提到但实际不存在的文件对照

对 `must_read_next` 的要求：
- 必须是相对 `project_root` 的文件路径列表
- 只能指向仓库内真实存在的文件
- 只允许这些类型：
  - `*.py`
  - `*.md`
  - `*.txt`
  - `*.json`
  - `*.doc`
  - `*.docx`
- 默认最多 8 个
- 不能为空；如果为空，则只能在 17 问已经基本成立、允许继续进入写入前判断时出现
- 不允许包含 owner docs 目标文件：
  - `AGENTS.md`
  - `docs/PROJECT_GUIDE.md`
  - `docs/WORKFLOW.md`
  - `docs/ENTITIES.md`
  - `docs/FILE_INDEX.md`
  - `docs/TOOLS_METHOD_FLOW_MAP.md`
  - `docs/PROJECT_BOOTSTRAP_PROTOCOL.md`
- 若候选超过上限，优先顺序应为：
  - 主入口
  - 状态/契约
  - 配置
  - 测试
  - 其他补充文件

你当前只需要输出第一阶段结果：

第一阶段：17 问理解与补证据规划（JSON）
- 先用 `README + docs + 轻量仓库探测 + 已补读文件` 去填充 17 问
- 先判断当前证据是否足够让 17 问基本成立
- 输出必须回答：
  - 17 问里已经答稳了哪些
  - 哪些问题仍不清楚
  - 需要客户继续补什么
  - 你当前对文档优先级的理解是什么
  - 你当前对整个项目的理解是什么
  - 当前是否已经具备进入下一步的前提
- 第一阶段最小输出字段：
  - `session_execution_instruction`
  - `answered_questions`
  - `unclear_questions`
  - `customer_followups`
  - `document_priority_understanding`
  - `current_project_understanding`
  - `ready_for_doc_write`
- 第一阶段允许同时携带内部辅助字段：
  - `explicit_refs`
  - `light_repo_findings`
  - `implementation_gaps`
  - `must_read_next`
- 字段含义：
  - `session_execution_instruction`：本轮补充执行指令的标准化理解，用来约束当前 session 的阅读顺序与 owner 关注点
  - `answered_questions`：当前已经基本答稳的问题编号与简要结论
  - `unclear_questions`：当前仍缺证据、答不稳的问题编号与缺口说明
  - `customer_followups`：需要客户继续补充的内容，必须翻译成客户能回答的话
  - `document_priority_understanding`：当前对 `README/docs` 等材料角色和优先级的理解
  - `current_project_understanding`：当前对项目定位、阶段、亮点、风险和下一步的高层理解
  - `ready_for_doc_write`：当前是否已具备进入下一步的基本前提；即使为 `true`，也不代表必须立刻完成初始化

输出要求：
- 先给阶段一结果，禁止跳过
- 如果证据不足，必须明确 `ready_for_doc_write = false`
- 如果证据足够，可以把 `ready_for_doc_write` 置为 `true`，但仍应允许继续在同一 session 上人工纠偏和补充
- 如果用户给了额外的一句话执行指令，必须把它吸收到 `session_execution_instruction` 中，而不是忽略
- 所有结论必须可追溯到文档或实现证据
- 不要输出闲聊，不要复述用户问题

[本轮补充执行指令段]

你好

[动态项目上下文段]

- project_root: /root/a9quant-strategy
- readme_guide: ["README.md"]
- raw_docs_read: ["docs/中央银行设计.md", "docs/基于资管双向非对称对冲策略手册.md", "docs/总纲清单（可复制）.md", "docs/梦想中的交易资管财富系统想法.md", "docs/资管双向原始想法.md"]
- owner_docs_targets: ["AGENTS.md", "docs/PROJECT_GUIDE.md", "docs/WORKFLOW.md", "docs/ENTITIES.md", "docs/FILE_INDEX.md", "docs/TOOLS_METHOD_FLOW_MAP.md"]

### light_repo_findings
```json
{
  "project_root": "/root/a9quant-strategy",
  "top_level_files": [
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "account_state.py",
    "advanced_risk.py",
    "base_bitget_ws.py",
    "bitget_ws_bridge.py",
    "ccxt_utils.py",
    "config.json",
    "contracts.py",
    "data_synchronizer.py",
    "debug_strategy.py",
    "main_controller.py",
    "market_data_hub.py",
    "market_utils.py",
    "martin.json",
    "martin.py",
    "mysqldbpoolnew.py",
    "position_utils.py",
    "proxy_utils.py"
  ],
  "docs_files": [
    "docs/中央银行设计.md",
    "docs/基于资管双向非对称对冲策略手册.md",
    "docs/总纲清单（可复制）.md",
    "docs/梦想中的交易资管财富系统想法.md",
    "docs/资管双向原始想法.md"
  ],
  "entry_candidates": [
    "main_controller.py",
    "tools/appserverclient.py"
  ],
  "test_candidates": [
    "test_data_flow.py",
    "test_dry_run_flow.py",
    "test_integration.py",
    "test_regression.py"
  ],
  "config_candidates": [
    "config.json",
    "martin.json",
    "tools/project_config.json",
    "tools/project_config.template.json"
  ],
  "state_or_contract_candidates": [
    "account_state.py",
    "contracts.py",
    "tools/result_schema.py"
  ],
  "readme_refs_missing_in_repo": []
}
```

### explicit_refs
```json
{
  "files": [
    "ccxt_utils.py",
    "advanced_risk.py",
    "trend_engine.py",
    "shark_engine.py",
    "base_bitget_ws.py",
    "bitget_ws_bridge.py",
    "market_data_hub.py",
    "tiny_oms.py",
    "data_synchronizer.py",
    "main_controller.py",
    "martin.py",
    "martin.json",
    "market_utils.py",
    "position_utils.py"
  ],
  "modules": [
    "# a9量化-交易资管财富系统（以终为始）",
    "本项目源于“梦想中的交易资管财富系统”顶层愿景，目标是构建一套**机构级量化交易基座**，核心方向是从“现金流型资管系统（A类）”逐步演进为“中央银行式资管+无风险套利系统”，而“鲨鱼引擎+趋势引擎”仅作为第二类策略系统（B类）中的一组核心策略。第一阶段落地聚焦“资管双向非对称对冲”策略，基于Bitget交易所完成模块化、高稳定性、可扩展的底层架构搭建（Bitget仅作为第一个落地验证的交易所，后续可基于`ccxt_utils.py`的通用接口扩展至Binance、OKX等主流交易所），而非单一策略脚本的开发。",
    "## 一、核心设计文档（演进逻辑：愿景→落地想法→需求分析→架构设计）",
    "以下4份MD文档构成项目从“顶层愿景”到“可落地架构”的完整逻辑链，是理解项目核心思想的关键：",
    "### 0. 梦想中的交易资管财富系统想法.md",
    "定位**：项目的**顶层愿景文档**，定义了整个系统的终极目标、核心策略分类、交易哲学与分阶段实现路径。",
    "交易哲学（系统设计的第一性原则）：",
    "3. 模块化与抽象化：拒绝“一次性策略脚本”，以机构级模块化架构为核心，保证策略/交易所/风控规则的可替换性；",
    "4. 以终为始：所有第一阶段的开发都围绕终局系统的架构准则设计，避免重构成本，每一个模块都为后续三类策略融合预留扩展空间。",
    "终局系统核心策略分类（三类核心盈利模式）：",
    "1. **现金流型（Market Neutral / Carry / Spread）**：核心是创造稳定、低波动的现金流，聚焦市场中性、基差套利、持仓收益（Carry）、价差交易（Spread）等无风险/低风险策略，是整个资管系统的“压舱石”；",
    "2. **方向性 Alpha（趋势 / 主力 / 因子）**：通过捕捉市场趋势、主力资金动向、量化因子等获取超额收益，“鲨鱼引擎+趋势引擎”属于此类，是系统的“收益增强模块”；"
  ],
  "objects": [
    "接口适配层：各模块间的标准化交互格式（信号、订单指令、状态反馈）。",
    "稳定性：WS断连自动重连、订单执行失败重试、核心状态不丢失；",
    "定位**：项目的**当前核心架构设计文档**，是第一阶段及后续演进的唯一架构准则，系统的数据流设计、核心状态定义、模块交互规则均在此文档中持续更新。",
    "状态管理：统一核心状态（仓位、订单、行情）的存储与同步规则，避免模块间状态不一致。",
    "3. 状态数据流：交易所 → `bitget_ws_bridge.py` → `data_synchronizer.py` → 全局状态池 → 各模块查询。",
    "核心状态定义（持续更新）：",
    "行情状态：K线、ticker、波动率等（存储于`market_data_hub.py`）；",
    "订单状态：订单ID、状态、成交金额等（存储于`tiny_oms.py`）；",
    "账户状态：仓位、资产、盈亏等（存储于`data_synchronizer.py`的全局状态池）；",
    "风险状态：单日回撤、仓位比例、订单失败率等（存储于`advanced_risk.py`）。",
    "| 订单创建与跟踪 | `create_order()`（创建订单）、`track_order_status()`（跟踪订单状态） | tiny_oms.py |",
    "| 状态同步 | `sync_account_state()`（同步账户状态）、`sync_order_state()`（同步订单状态） | data_synchronizer.py |"
  ],
  "flows": [
    "## 一、核心设计文档（演进逻辑：愿景→落地想法→需求分析→架构设计）",
    "落地约束：明确第一阶段仅围绕Bitget交易所（首个落地交易所），完成“趋势识别→风险控制→订单执行”的核心链路，不涉及A类现金流系统和第三类凸性赌注策略。",
    "抽象化原则：定义通用接口（如策略引擎→风险层的指令接口、风险层→基础设施层的订单接口），保证模块解耦与替换性（如后续替换交易所、新增现金流/凸性赌注策略引擎）。",
    "1. 行情数据流：`base_bitget_ws.py`/`ccxt_utils.py` → `market_data_hub.py` → `trend_engine.py`/`shark_engine.py`；",
    "2. 指令数据流：`shark_engine.py` → `advanced_risk.py` → `tiny_oms.py` → `bitget_ws_bridge.py` → 交易所；",
    "3. 状态数据流：交易所 → `bitget_ws_bridge.py` → `data_synchronizer.py` → 全局状态池 → 各模块查询。",
    "模块初始化：按顺序初始化所有模块（基础设施层→数据层→监管层→执行层），保证模块启动顺序与依赖关系；",
    "流程调度：触发“行情接收→趋势识别→策略决策→风险校验→订单执行→状态同步”的全链路流程；",
    "3. 开发“指令校验接口”，定义鲨鱼引擎→风险层的指令格式；",
    "1. 打通“行情→趋势引擎→鲨鱼引擎→风险层→桥接层→交易所”的全链路；",
    "系统仅存在4种状态，各状态有**硬行为定义**，流转触发条件明确，99%系统缺失的**REBUILD态**是避免反复死亡的关键，默认状态为NORMAL，流转逻辑为：**NORMAL→DEFENSIVE→FROZEN→REBUILD→NORMAL**",
    "### （1）3条立即冻结红线（任意触发→直接进入FROZEN）"
  ]
}
```

### current_init_project_session
```json
{
  "thread_id": "",
  "thread_path": "",
  "status": "",
  "answered_questions": [],
  "unclear_questions": [],
  "must_read_next": [],
  "implementation_gaps": []
}
```

### current_phase1_payload
```json
{
  "answered_questions": [],
  "unclear_questions": [
    "Q1: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q2: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q3: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q4: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q5: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q6: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q7: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q8: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q9: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q10: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q11: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q12: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q13: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q14: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q15: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q16: 等待 xhigh plan init session 基于通用模板与证据继续理解。",
    "Q17: 等待 xhigh plan init session 基于通用模板与证据继续理解。"
  ],
  "customer_followups": [
    "请先按本轮补充执行指令校正文档优先级、阅读顺序和 owner 关注点。",
    "请继续补读这些关键实现文件：ccxt_utils.py, advanced_risk.py, trend_engine.py, shark_engine.py, base_bitget_ws.py, bitget_ws_bridge.py, market_data_hub.py, tiny_oms.py"
  ],
  "document_priority_understanding": "README 作为 guide 优先阅读；当前已读取 5 份 docs 原始材料，并已生成下一批受控补读线索。",
  "current_project_understanding": "当前只完成了初始化 intake；下一步应在同一 init-project session 中按通用模板继续理解 17 问，并逐步更新状态。",
  "ready_for_doc_write": false,
  "implementation_gaps": [
    "key implementation files still need to be read before initialization can move forward"
  ],
  "must_read_next": [
    "ccxt_utils.py",
    "advanced_risk.py",
    "trend_engine.py",
    "shark_engine.py",
    "base_bitget_ws.py",
    "bitget_ws_bridge.py",
    "market_data_hub.py",
    "tiny_oms.py"
  ]
}
```

[最终输出约束段]

- 请只输出 JSON。
- 不要输出闲聊。
- 不要直接反写 owner docs。
- 如果当前证据不足，`ready_for_doc_write` 必须为 false。
- 所有结论必须可追溯到文档或实现证据。
