# main_controller.py
import asyncio
import time
import logging
from data_synchronizer import DataSynchronizer
from account_state import AccountState
from advanced_risk import RiskManager
from ccxt_utils import ExchangeTrader
from trend_engine import TrendEngine
from shark_engine import SharkEngine

logger = logging.getLogger('MainCtrl')

class MainController:
    def __init__(self, config):
        self.config = config
        self.running = False
        
        # === 模块初始化流水线 ===
        logger.info("正在初始化系统模块...")
        # 1. 交易接口
        self.trader = ExchangeTrader(**config['exchange'])
        print(self.trader )
        # 2. 数据底座
        self.data_sync = DataSynchronizer(self.trader, config['symbol'])
        print(self.data_sync )
        self.account_state = AccountState(self.data_sync)
        print(self.account_state )
        # 3. 风控银行 (注入AccountState)
        self.risk_manager = RiskManager(
            initial_capital=config['risk']['initial_capital'],
            account_state=self.account_state # 关键连接！
        )
        # 4. 策略引擎 (注入风控实例)
        self.trend_engine = TrendEngine(self.risk_manager)
        self.shark_engine = SharkEngine(self.risk_manager)
        
        logger.info("✅ 所有模块初始化完毕。")
    
    async def run(self):
        """主运行循环"""
        self.running = True
        logger.info("🚀 主控制器启动。")
        
        # 启动时进行一次全量同步
        await self.data_sync.force_rest_sync()
        self.account_state.update()
        self.risk_manager.update_from_account_state()
        
        while self.running:
            try:
                # 1. 同步最新账户数据
                self.account_state.update()
                # 2. 更新风控状态
                self.risk_manager.update_from_account_state()
                
                # 3. 获取市场数据 (这里需要你从base_bitget_ws.py接收ticker)
                #    假设我们有一个 `current_market_data` 变量存放最新行情
                market_data = self.get_latest_market_data()
                
                if market_data:
                    # 4. 驱动策略引擎思考 (传入市场数据和账户快照)
                    trend_signal = self.trend_engine.on_tick({
                        **market_data,
                        'account_snapshot': self.account_state.get_strategy_snapshot('trend')
                    })
                    
                    shark_signal = self.shark_engine.on_tick({
                        **market_data,
                        'account_snapshot': self.account_state.get_strategy_snapshot('shark')
                    })
                    
                    # 5. 处理交易信号 (下一阶段实现)
                    await self.process_signals(trend_signal, shark_signal)
                
                # 6. 定时强制REST同步，例如每5分钟一次
                if time.time() - self.data_sync.last_rest_sync > 300:
                    await self.data_sync.force_rest_sync()
                
                # 控制循环频率
                await asyncio.sleep(0.5) # 例如2Hz
                
            except Exception as e:
                logger.error(f"主循环发生错误: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    def get_latest_market_data(self):
        """需要你整合：从base_bitget_ws.py的on_public_ticker回调中获取最新行情"""
        # 暂时返回None，你需要在这里实现一个线程安全的队列或状态共享
        # 例如：return self.market_data_queue.get_nowait()
        return None
    
    async def process_signals(self, trend_signal, shark_signal):
        """处理策略信号：风控审批 -> 下单 -> 状态同步 (下一阶段核心)"""
        # 这里将是第三阶段的内容
        pass
    
    async def shutdown(self):
        """优雅关闭"""
        self.running = False
        logger.info("🛑 主控制器关闭。")