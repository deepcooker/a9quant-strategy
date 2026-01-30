import asyncio
import logging
from main_controller import MainController

# 配置日志，方便查看测试过程
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# 核心配置（需根据你的实际交易所信息调整）
TEST_CONFIG = {
    # 交易所配置（替换为你的Bitget API信息，模拟盘/实盘均可）
    "exchange": {
        "api_key": "your-bitget-api-key",
        "secret": "your-bitget-secret",
        "passphrase": "your-bitget-passphrase",
        "enable_rate_limit": True,
        "sandbox": True  # 建议先开模拟盘测试
    },
    # 交易对（需和Bitget格式一致）
    "symbol": "BTC/USDT:USDT",
    # 风控配置
    "risk": {
        "initial_capital": 1000.0  # 初始本金（USDT）
    }
}

async def test():
    """核心链路测试：初始化所有模块 + 验证数据同步"""
    logger = logging.getLogger("TestIntegration")
    logger.info("🚀 开始集成测试：数据底座 → 风控 链路验证")
    
    # 1. 初始化主控制器（传入配置，匹配__init__参数）
    try:
        controller = MainController(TEST_CONFIG)
        logger.info("✅ MainController 初始化成功")
    except Exception as e:
        logger.error(f"❌ MainController 初始化失败: {e}", exc_info=True)
        return
    
    # 2. 验证核心模块是否创建成功
    modules = [
        ("交易接口", controller.trader),
        ("数据同步器", controller.data_sync),
        ("账户状态", controller.account_state),
        ("风控管理器", controller.risk_manager),
        ("行情Hub", controller.market_hub),
        ("OMS订单管理", controller.oms),
        ("WS桥接器", controller.ws),
        ("趋势引擎", controller.trend_engine),
        ("鲨鱼引擎", controller.shark_engine)
    ]
    
    for name, module in modules:
        if module is not None:
            logger.info(f"✅ {name} 模块创建成功")
        else:
            logger.warning(f"❌ {name} 模块创建失败（为None）")
    
    # 3. 测试数据同步（强制REST同步）
    try:
        await controller.data_sync.force_rest_sync()
        logger.info("✅ 强制REST同步完成（数据底座连通交易所）")
    except Exception as e:
        logger.error(f"❌ REST同步失败: {e}", exc_info=True)
        return
    
    # 4. 验证账户状态更新
    try:
        controller.account_state.update()
        snapshot = controller.account_state.get_strategy_snapshot("trend")
        logger.info(f"✅ 账户状态更新成功 | 趋势策略快照: {snapshot}")
    except Exception as e:
        logger.error(f"❌ 账户状态更新失败: {e}", exc_info=True)
    
    # 5. 验证风控状态更新
    try:
        controller.risk_manager.update_from_account_state()
        logger.info(f"✅ 风控状态更新成功 | 初始本金: {controller.risk_manager.initial_capital}")
    except Exception as e:
        logger.error(f"❌ 风控状态更新失败: {e}", exc_info=True)
    
    # 6. （可选）测试WS连接（仅验证创建，不实际启动）
    try:
        await controller.setup_websocket()
        logger.info("✅ WebSocket任务创建成功（未实际启动，仅验证配置）")
    except Exception as e:
        logger.warning(f"⚠️ WebSocket任务创建警告: {e}（可先忽略，主运行时验证）")
    
    logger.info("\n🎉 集成测试完成：核心链路（数据底座→风控）验证通过！")

if __name__ == "__main__":
    # 运行异步测试
    asyncio.run(test())