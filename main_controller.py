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
        self.oms = TinyOMS(self.trader, config["symbol"], data_sync=self.data_sync, product_type="USDT-FUTURES")  # v1.3

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

        # ===== 现金流治理：策略注册表（可被中央银行冷酷关闭） ===== v1.3
        self.strategy_registry = {
            "trend": "ENABLED",
            "shark": "ENABLED",
        }

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
                # 1) 更新事实账本 v1.3
                self.account_state.update()
                self.risk_manager.update_from_account_state()

                # 2) 中央银行输出 policy（现金流主权）v1.3
                policy = self.risk_manager.evaluate_policy()

                # 3) 应用“冷酷关闭策略” v1.3
                for s in policy.disable_strategies:
                    if s in self.strategy_registry:
                        self.strategy_registry[s] = "DISABLED"

                # 4) 若系统冻结：直接跳过（这里不让任何策略跑）v1.3
                if policy.system_mode.value == "FROZEN":
                    logger.warning(f"🧊 FROZEN: {policy.reason}")
                    await asyncio.sleep(1.0)
                    continue

                # 5) 取行情（指标不足就跳过）v1.3
                market_data = self.get_latest_market_data()
                if not market_data:
                    await asyncio.sleep(0.5)
                    continue

                # 6) 只在策略 ENABLED 时才调用 on_tick v1.3
                trend_intent = None
                shark_intent = None

                if self.strategy_registry.get("trend") == "ENABLED":
                    trend_intent = self.trend_engine.on_tick({
                        **market_data,
                        "account_snapshot": self.account_state.get_strategy_snapshot("trend"),
                        "system_mode": policy.system_mode.value,
                        "risk_regime": policy.risk_regime.value,
                        "state_confidence": getattr(self.account_state, "state_confidence", None),
                    })

                if self.strategy_registry.get("shark") == "ENABLED":
                    shark_intent = self.shark_engine.on_tick({
                        **market_data,
                        "account_snapshot": self.account_state.get_strategy_snapshot("shark"),
                        "system_mode": policy.system_mode.value,
                        "risk_regime": policy.risk_regime.value,
                        "state_confidence": getattr(self.account_state, "state_confidence", None),
                    })

                # 7) DEFENSIVE：只允许 CLOSE/REDUCE intent 进入执行层 v1.3
                if policy.system_mode.value == "DEFENSIVE":
                    def _filter_defensive(intent):
                        if not intent:
                            return None
                        a = str(intent.get("action", "")).upper()
                        if ("CLOSE" in a) or ("REDUCE" in a) or ("STOP" in a):
                            return intent
                        return None
                    trend_intent = _filter_defensive(trend_intent)
                    shark_intent = _filter_defensive(shark_intent)

                # 8) 交给统一执行（内部会再走 approve_action 闸门）v1.3
                await self.process_signals(trend_intent, shark_intent)

                if time.time() - self.data_sync.last_rest_sync > 300:
                    await self.data_sync.force_rest_sync()

                # ===== v1.4 新增：无回报超时检查 =====
                self.oms.check_no_report_timeout(timeout_s=30)

                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"主循环发生错误: {e}", exc_info=True)
                await asyncio.sleep(3)

    def get_latest_market_data(self):
        md = self.market_hub.get_latest()
        if not md:
            return None
        # 指标未就绪，先不跑策略
        
        # 临时添加：打印指标值，观察是否异常
        logger.info(f"[DEBUG] 行情指标 -> price:{md['price']}, ema20:{md['ema20']}, rsi:{md['rsi']}, vol_ratio:{md['vol_ratio']}")
        
        
        
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

            # 下单后强制校准一次 v1.4 修改：对账结果纳入闭环证据
            ok = await self.data_sync.force_rest_sync()
            self.account_state.update()
            self.risk_manager.update_from_account_state()

            # ===== v1.4 新增：对账结果纳入闭环证据 =====
            # 对账成功 + position_uncertain解除：记一条“对账闭环成功”
            if ok and (not self.data_sync.position_uncertain):
                self.data_sync.report_execution_event(True, "rest_reconcile_ok")
            elif not ok:
                self.data_sync.report_execution_event(False, "rest_reconcile_fail")
            elif self.data_sync.position_uncertain:
                self.data_sync.report_execution_event(False, "rest_reconcile_uncertain")

    async def shutdown(self):
        self.running = False
        for t in self.ws_tasks:
            t.cancel()
        logger.info("🛑 主控制器关闭。")
        
        
# ========== 新增：程序入口 ==========
async def main():
    import json
    # 1. 加载配置文件
    with open("config.json", "r") as f:
        config = json.load(f)
    
    # 2. 初始化主控制器
    controller = MainController(config)
    
    try:
        # 3. 启动主循环
        await controller.run()
    except KeyboardInterrupt:
        # 4. 捕获Ctrl+C，优雅关闭
        await controller.shutdown()
        logger.info("👋 程序已手动终止")

# 启动异步程序
if __name__ == "__main__":
    # 配置日志（确保能看到输出）
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    asyncio.run(main())