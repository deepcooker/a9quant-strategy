# FOUNDATION_BRIDGE

## 一句话
`quant-factory-os` 是仓库名，`foundation` 是它在业务项目中的角色名。

不要把这两个概念混在一起：
- `quant-factory-os`
  - 指这个基建仓库本身
- `foundation`
  - 指这个仓库对外提供的能力角色：AI 研发团队 / 自动化研发执行基座

## 1. foundation 是什么
foundation 是研发执行层，不是业务逻辑层。

它负责的是：
- 项目同频学习
- session / task / run 组织
- 自动化研发执行
- 证据沉淀
- Git 交付与回滚流程

它不负责的是：
- 业务项目为什么存在
- 业务项目如何赚钱
- 业务项目的制度设计
- 业务项目的策略与运维判断

## 2. 为什么使用 foundation
我们当前采用的是：
- `Codex` + `foundation`

分工是：
- `Codex`
  - 更偏手工调试、即时接管、复杂问题定位
- `foundation`
  - 更偏自动化、减少人工接入、沉淀研发记忆

所以 foundation 不是替代 Codex，而是和 Codex 并用。

## 3. foundation 和业务项目的关系
业务项目有自己的文档、自己的真相、自己的业务主线。

foundation 只提供工程执行层。

正确关系是：
- 业务项目定义业务
- foundation 承接研发执行

错误关系是：
- 用 foundation 去解释业务项目的终局、策略、制度或商业逻辑

## 4. 当前真实状态
foundation 已经开始嵌入真实业务项目做试点接入。

但要明确：
- 这不代表主线自动化已经完全闭合
- 当前仍然是 `Codex 手工调试 + foundation 自动化` 一起推进
- 现阶段重点仍是把这套工程执行层打磨成熟

## 5. foundation 包含什么
### 5.1 主线文档
- `AGENTS.md`
- `docs/PROJECT_GUIDE.md`
- `docs/WORKFLOW.md`
- `docs/ENTITIES.md`
- `docs/FILE_INDEX.md`
- `docs/TOOLS_METHOD_FLOW_MAP.md`

### 5.2 常用命令
- `appserverclient`
- `taskclient`
- `gitclient`

补充：
- `init` 是预检，不是主流程

### 5.3 常见产物
- `TASKS/`
- `reports/`
- `chatlogs/`
- `tools/project_config.json`

这些内容默认属于工程执行层，不属于业务真相本体。

## 6. 业务项目如何接入
建议顺序：

1. 业务项目先准备自己的原始文档
- 总纲
- README
- 核心制度设计
- 当前阶段策略手册
- 原始想法来源

2. 先完成业务同频
- 先读业务项目自己的 `PROJECT_GUIDE`
- 先理解业务终局、当前阶段、核心制度、当前实现边界

3. 再接 foundation 主线
- `learnbaseline`
- `fork-current`
- role / task / run 推进
- summarize / refresh
- git 交付

## 7. 出现问题时怎么处理
- 业务理解有问题：
  - 回业务项目自己的文档修
- foundation 工具链有问题：
  - 回 `quant-factory-os` 修

一句话：
foundation 是业务项目的工程执行层，不是业务项目的业务宪法。
