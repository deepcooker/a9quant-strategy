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
