# FILE_INDEX

## 1. 首轮阅读顺序
先文档，后代码。固定顺序如下：

1. `docs/总纲清单（可复制）.md`
   - 总纲宪法
   - 定义终局、三账本、下牌桌概率、研发闭环
2. `README.md`
   - 项目入口说明
   - 定义项目定位、文档链路、关键模块
3. `docs/中央银行设计.md`
   - 风控 / 现金流 / 权限核心
   - 定义四态状态机、中央银行权限、合法信息流
4. `docs/基于资管双向非对称对冲策略手册.md`
   - 一期落地细则
   - 定义趋势/鲨鱼规则与杠杆审批
5. `docs/梦想中的交易资管财富系统想法.md`
   - 原始想法来源
   - 定义三池结构与资金流动雏形
6. `docs/资管双向原始想法.md`
   - 原始策略直觉来源
   - 定义趋势让路、鲨鱼收割、非对称仓位语言

## 2. 实现阅读顺序
在文档顺序确认后，再读这些实现文件：

1. `main_controller.py`
   - 主入口与主循环
2. `data_synchronizer.py`
   - 状态同步与 SoT
3. `account_state.py`
   - 业务态账本
4. `advanced_risk.py`
   - 中央银行闸门
5. `trend_engine.py`
   - 趋势侧执行层
6. `shark_engine.py`
   - 鲨鱼侧执行层
7. `tiny_oms.py`
   - OMS 边界
8. `bitget_ws_bridge.py`
   - 交易所桥接层
9. `base_bitget_ws.py`
   - WS 底层连接
10. `ccxt_utils.py`
    - REST/CCXT 适配层
11. `contracts.py`
    - 跨模块契约
12. `config.json`
    - 当前运行假设
13. `test_integration.py`
    - 集成验证
14. `test_regression.py`
    - 回归验证
15. `replay_runner.py`
    - replay/仿真入口

## 3. Owner Docs
- `AGENTS.md`
  - 本项目硬规则与制度边界
- `docs/PROJECT_GUIDE.md`
  - 同频核心课程
- `docs/WORKFLOW.md`
  - 研发主线 + 业务运行主线
- `docs/ENTITIES.md`
  - 对象字典
- `docs/FILE_INDEX.md`
  - 阅读顺序与文件职责
- `docs/TOOLS_METHOD_FLOW_MAP.md`
  - 方法/流程/追读图
- `docs/PROJECT_BOOTSTRAP_PROTOCOL.md`
  - 新接手者如何先文档后代码
