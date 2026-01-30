# test_integration.py
import asyncio
from main_controller import MainController
import json

async def test():
    with open('config.json', 'r') as f:
        config = json.load(f)
    controller = MainController(config)
    # 测试初始化
    print("✅ 主控制器创建成功")
    # 测试一次手动更新
    await controller.data_sync.force_rest_sync()
    controller.account_state.update()
    controller.risk_manager.update_from_account_state()
    print("✅ 风控状态已更新:", controller.risk_manager.realized_profit)

asyncio.run(test())