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

from market_data_hub import MarketDataHub
from tiny_oms import TinyOMS
from bitget_ws_bridge import BitgetWSBridge

logger = logging.getLogger('MainCtrl')

class MainController:
    def __init__(self, config):
        self.config = config
        self.running = False
        self.ws_tasks = []

        logger.info("正在初始化系统模块...")

        self.trader = ExchangeTrader(**config['exchange'])
        self.data_sync = DataSynchronizer(self.trader, config['symbol'])
        self.account_state = AccountState(self.data_sync)

        self.risk_manager = RiskManager(
            initial_capital=config['risk']['initial_capital'],
            account_state=self.account_state
        )

        # 新增：行情 hub + OMS + WS bridge
        self.market_hub = MarketDataHub()
        self.oms = TinyOMS(self.trader, config["symbol"], product_type="USDT-FUTURES")

        self.ws = BitgetWSBridge(
            api_key=config["exchange"]["api_key"],
            secret=config["exchange"]["secret"],
            passphrase=config["exchange"]["passphrase"],
            market_hub=self.market_hub,
            data_sync=self.data_sync,
            oms=self.oms
        )

        self.trend_engine = TrendEngine(self.risk_manager)
        self.shark_engine = SharkEngine(self.risk_manager)

        logger.info("✅ 所有模块初始化完毕。")

    async def setup_websocket(self):
        # public: ticker + candle1m
        self.ws_tasks.append(asyncio.create_task(
            self.ws.connect_public_ws(
                product_type="USDT-FUTURES",
                ws_symbol=self.data_sync.clean_symbol,
                candle_channels=["candle1m"]
            )
        ))

        # private: orders/positions/account
        self.ws_tasks.append(asyncio.create_task(
            self.ws.connect_private_ws(
                config=self.ws.build_private_ws_config(),
                product_type="USDT-FUTURES"
            )
        ))

    async def run(self):
        self.running = True
        logger.info("🚀 主控制器启动。")

        await self.setup_websocket()

        await self.data_sync.force_rest_sync()
        self.account_state.update()
        self.risk_manager.update_from_account_state()

        while self.running:
            try:
                self.account_state.update()
                self.risk_manager.update_from_account_state()

                market_data = self.get_latest_market_data()
                if market_data:
                    trend_intent = self.trend_engine.on_tick({
                        **market_data,
                        "account_snapshot": self.account_state.get_strategy_snapshot("trend")
                    })
                    shark_intent = self.shark_engine.on_tick({
                        **market_data,
                        "account_snapshot": self.account_state.get_strategy_snapshot("shark")
                    })

                    await self.process_signals(trend_intent, shark_intent)

                if time.time() - self.data_sync.last_rest_sync > 300:
                    await self.data_sync.force_rest_sync()

                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"主循环发生错误: {e}", exc_info=True)
                await asyncio.sleep(3)

    def get_latest_market_data(self):
        md = self.market_hub.get_latest()
        if not md:
            return None
        # 指标未就绪，先不跑策略
        if md["ema20"] is None or md["atr"] is None or md["rsi"] is None or md["vol_ratio"] is None:
            return None
        return md

    async def process_signals(self, trend_intent, shark_intent):
        intents = []
        if trend_intent:
            intents.append(trend_intent)
        if shark_intent:
            intents.append(shark_intent)
        if not intents:
            return

        # 简单优先级：CLOSE/STOP > OPEN/ADD
        def score(x):
            a = (x.get("action") or "").upper()
            if "CLOSE" in a or "STOP" in a:
                return 100
            if "OPEN" in a:
                return 50
            if "ADD" in a:
                return 40
            return 10
        intents.sort(key=score, reverse=True)

        for intent in intents:
            risk_req = intent.get("risk_request")
            if risk_req:
                ok, lev, msg = self.risk_manager.approve_action(risk_req)
                if not ok:
                    logger.info(f"❌ 风控拒绝: {msg} | intent={intent}")
                    continue
                intent["approved_leverage"] = lev

            client_oid = await self.oms.place_intent(intent)
            logger.info(f"✅ OMS提交: {client_oid} intent={intent}")

            # 下单后强制校准一次
            await self.data_sync.force_rest_sync()
            self.account_state.update()
            self.risk_manager.update_from_account_state()

    async def shutdown(self):
        self.running = False
        for t in self.ws_tasks:
            t.cancel()
        logger.info("🛑 主控制器关闭。")