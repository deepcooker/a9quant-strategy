好，继续把“没写完”的部分补齐，而且这次我按你真实代码来写——函数名、字段名、WS 钩子名都对上你现在的文件。

下面你照着做，就能把系统闭环跑起来（WS 行情 → 引擎出意图 → 风控审批 → OMS 下单 → WS 回报/REST 校准 → AccountState/Risk 刷新）。

⸻

1) 先解决你现在的真实阻塞点：MainController 没有行情、没有下单通路

你现在 main_controller.py 的两个空洞：
	•	get_latest_market_data() 永远 None（策略永远不跑）
	•	process_signals() 是 pass（即使有信号也不会执行）

而你 base_bitget_ws.py 已经把钩子打好了：
	•	on_public_ticker(ticker, action)
	•	on_public_candle(candle_data, channel, action)
	•	on_private_order/order/position/account

所以我们要新增 3 个文件，然后改 main_controller.py。

⸻

2) 新增 3 个文件（直接放同级目录）

2.1 market_data_hub.py（行情缓存 + 指标）

让 TrendEngine 的 required_fields（price/ema20/atr/rsi/vol_ratio）真的有值。

# market_data_hub.py
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock

@dataclass
class Candle:
    ts: float
    o: float
    h: float
    l: float
    c: float
    v: float

class MarketDataHub:
    def __init__(self, max_candles: int = 500):
        self._lock = Lock()
        self._candles = deque(maxlen=max_candles)
        self._latest_price = None
        self._latest_ts = 0.0

        self._ema20 = None
        self._atr14 = None
        self._rsi14 = None
        self._vol_ratio = None

    def update_ticker(self, ticker_item: dict):
        last = ticker_item.get("lastPr") or ticker_item.get("last") or ticker_item.get("close")
        if last is None:
            return
        with self._lock:
            self._latest_price = float(last)
            self._latest_ts = time.time()

    def update_candles(self, candle_rows: list):
        parsed = []
        for row in candle_rows:
            if not row or len(row) < 6:
                continue
            ts_raw = float(row[0])
            ts = ts_raw / 1000.0 if ts_raw > 1e12 else ts_raw
            parsed.append(Candle(ts, float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])))

        if not parsed:
            return

        with self._lock:
            existing_ts = {c.ts for c in self._candles}
            for c in parsed:
                if c.ts not in existing_ts:
                    self._candles.append(c)

            self._latest_price = self._candles[-1].c
            self._latest_ts = time.time()
            self._recalc_indicators()

    def _recalc_indicators(self):
        closes = [c.c for c in self._candles]
        highs  = [c.h for c in self._candles]
        lows   = [c.l for c in self._candles]
        vols   = [c.v for c in self._candles]

        # EMA20
        if len(closes) >= 20:
            k = 2 / (20 + 1)
            ema = closes[0]
            for x in closes[1:]:
                ema = x * k + ema * (1 - k)
            self._ema20 = ema

        # ATR14
        if len(closes) >= 15:
            trs = []
            for i in range(1, len(closes)):
                tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
                trs.append(tr)
            self._atr14 = sum(trs[-14:]) / 14

        # RSI14
        if len(closes) >= 15:
            gains, losses = [], []
            for i in range(1, len(closes)):
                chg = closes[i] - closes[i-1]
                gains.append(max(chg, 0))
                losses.append(max(-chg, 0))
            avg_gain = sum(gains[-14:]) / 14
            avg_loss = sum(losses[-14:]) / 14
            self._rsi14 = 100.0 if avg_loss == 0 else (100 - (100 / (1 + (avg_gain / avg_loss))))

        # vol_ratio：当前量 / 近20均量
        if len(vols) >= 20:
            avgv = sum(vols[-20:]) / 20
            self._vol_ratio = (vols[-1] / avgv) if avgv > 0 else 1.0

    def get_latest(self):
        with self._lock:
            if self._latest_price is None:
                return None
            return {
                "price": self._latest_price,
                "ema20": self._ema20,
                "atr": self._atr14,
                "rsi": self._rsi14,
                "vol_ratio": self._vol_ratio,
                "ts": self._latest_ts
            }


⸻

2.2 tiny_oms.py（最小 OMS：幂等 + 下单 + WS回报更新）

先做到能下单 + 能吃回报就行，状态机后面再精炼。

# tiny_oms.py
import time
import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

logger = logging.getLogger("TinyOMS")

@dataclass
class OrderRecord:
    client_oid: str
    symbol: str
    engine: str
    side: str
    pos_side: str
    trade_side: str
    size: float
    status: str = "NEW"
    exchange_order_id: Optional[str] = None
    last_update: float = 0.0
    raw: Optional[Dict[str, Any]] = None

class TinyOMS:
    def __init__(self, trader, symbol: str, product_type: str = "USDT-FUTURES"):
        self.trader = trader
        self.symbol = symbol
        self.product_type = product_type
        self.orders: Dict[str, OrderRecord] = {}

    def _gen_client_oid(self, engine: str, action: str) -> str:
        return f"{engine.lower()}_{action.lower()}_{int(time.time()*1000)}"

    async def place_intent(self, intent: Dict[str, Any]) -> str:
        engine = intent["engine"]
        action = intent["action"]
        trade_side = intent["trade_side"]   # open/close
        pos_side = intent["pos_side"]       # long/short
        size = float(intent["size"])
        margin_mode = intent.get("marginMode", "crossed")

        # open long=>buy; open short=>sell; close long=>sell; close short=>buy
        if trade_side == "open":
            side = "buy" if pos_side == "long" else "sell"
        else:
            side = "sell" if pos_side == "long" else "buy"

        client_oid = intent.get("clientOid") or self._gen_client_oid(engine, action)
        if client_oid in self.orders and self.orders[client_oid].status not in ("REJECTED", "CANCELED", "FILLED"):
            logger.warning(f"[OMS] 幂等命中，跳过重复下单: {client_oid}")
            return client_oid

        rec = OrderRecord(
            client_oid=client_oid,
            symbol=self.symbol,
            engine=engine,
            side=side,
            pos_side=pos_side,
            trade_side=trade_side,
            size=size,
            status="SENT",
            last_update=time.time(),
        )
        self.orders[client_oid] = rec

        # Bitget：优先用原生端点（和你 martin 思路一致，更稳）
        if self.trader.exchange_id == "bitget":
            clean_symbol = self.symbol.replace("/", "").split(":")[0]
            req = {
                "symbol": clean_symbol,
                "productType": self.product_type,
                "marginMode": margin_mode,
                "marginCoin": "USDT",
                "size": str(size),
                "side": side,
                "tradeSide": trade_side,
                "orderType": "market",
                "force": "gtc",
                "posSide": pos_side,
                "clientOid": client_oid,
            }
            logger.info(f"[OMS] Bitget native place: {req}")

            resp = await asyncio.to_thread(
                self.trader.exchange.private_mix_post_v2_mix_order_place_order,
                req
            )
            rec.raw = resp
            rec.last_update = time.time()

            if str(resp.get("code")) == "00000":
                data = resp.get("data") or {}
                rec.exchange_order_id = data.get("orderId") or data.get("order_id")
                rec.status = "ACK"
            else:
                rec.status = "REJECTED"
                raise RuntimeError(f"Bitget place_order failed: {resp}")

        else:
            order = await asyncio.to_thread(
                self.trader.exchange.create_market_order,
                self.symbol, side, size, None, {}
            )
            rec.exchange_order_id = order.get("id")
            rec.status = "ACK"
            rec.raw = order
            rec.last_update = time.time()

        return client_oid

    def on_order_update(self, order_data: Dict[str, Any]):
        # 兼容字段
        client_oid = order_data.get("clientOid") or order_data.get("clientOrderId")
        if not client_oid:
            return
        rec = self.orders.get(client_oid)
        if not rec:
            return

        rec.raw = order_data
        rec.last_update = time.time()

        st = (order_data.get("state") or order_data.get("status") or "").lower()
        if st in ("filled", "full_fill", "success"):
            rec.status = "FILLED"
        elif st in ("canceled", "cancelled"):
            rec.status = "CANCELED"
        elif st in ("partial_fill", "partially_filled"):
            rec.status = "PARTIAL"
        else:
            rec.status = "ACK"


⸻

2.3 bitget_ws_bridge.py（继承你的 BaseBitgetWsClient）

关键点：你 connect_private_ws() 需要 config['api']['apiKey'] 这种结构，而且还要求 get_sign() 必须实现。我们在桥里解决掉。

# bitget_ws_bridge.py
import logging
from base_bitget_ws import BaseBitgetWsClient

logger = logging.getLogger("BitgetWSBridge")

class BitgetWSBridge(BaseBitgetWsClient):
    def __init__(self, api_key: str, secret: str, passphrase: str, market_hub, data_sync, oms):
        super().__init__()
        self.api_key = api_key
        self.secret = secret
        self.passphrase = passphrase

        self.market_hub = market_hub
        self.data_sync = data_sync
        self.oms = oms

    def get_sign(self, timestamp: str) -> str:
        return self.generate_sign(timestamp, self.secret)

    def build_private_ws_config(self):
        # 满足 base_bitget_ws.connect_private_ws 的 config 结构
        return {
            "api": {
                "apiKey": self.api_key,
                "password": self.passphrase,
            }
        }

    async def on_public_ticker(self, ticker: dict, action: str):
        self.market_hub.update_ticker(ticker)

    async def on_public_candle(self, candle_data: list, channel: str, action: str):
        self.market_hub.update_candles(candle_data)

    async def on_private_order(self, order_data: dict):
        self.oms.on_order_update(order_data)

    async def on_private_position(self, pos_data: dict):
        # DataSynchronizer.update_from_ws_position 需要 list
        self.data_sync.update_from_ws_position([pos_data])

    async def on_private_account(self, account_data: dict):
        self.data_sync.update_from_ws_account(account_data)


⸻

3) 改 main_controller.py（补全 WS + market_data + process_signals）

这是你现在真正要跑起来的心脏文件。按你现有结构做最小改动：
	•	初始化 MarketDataHub / TinyOMS / BitgetWSBridge
	•	启动 connect_public_ws() + connect_private_ws()
	•	get_latest_market_data() 从 hub 取数据（指标不齐先返回 None）
	•	process_signals()：风控审批 → OMS下单 → REST校准

把你当前 main_controller.py 改成下面这样（你可以直接覆盖整个文件）：

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


⸻

4) 现在最关键：改 TrendEngine / SharkEngine ——从“内部记账执行”改成“返回 intent”

你现在两个引擎都在自己 approve_action() + _execute_trade()，这会导致：
	•	Controller/OMS 没机会统一幂等/对账
	•	引擎会“以为成交了”，但交易所可能没成交

先做 MVP：引擎仍然可以计算止损与状态，但交易动作必须返回 intent。

4.1 TrendEngine 改法（最小改动，改 4 个点）

改动点在你 trend_engine.py 里这些函数：
	•	on_tick()：要把 _try_open_l1/_try_open_l2/_try_open_l3/_close_position 的返回值往上 return
	•	_try_open_l1/_try_open_l2/_try_open_l3：不再调用 approve_action() 和 _execute_trade()，而是返回 intent
	•	_close_position：也返回平仓 intent（先按市价 close long）

A) 改 on_tick()：把函数调用改成接收并 return
把这些行：

self._try_open_l1(data)
...
self._try_open_l2(data)
...
self._try_open_l3(data)

改成：

intent = self._try_open_l1(data)
if intent: return intent
...
intent = self._try_open_l2(data)
if intent: return intent
...
intent = self._try_open_l3(data)
if intent: return intent

并且止损处：

if price <= self.stop_loss:
    self._close_position(price, "触及止损")
    return

改成：

if price <= self.stop_loss:
    intent = self._close_position(price, "触及止损")
    return intent

B) 改 _try_open_l1/_try_open_l2/_try_open_l3：返回 intent
以 _try_open_l1 为例（你原来 170~178 行附近），改成：

def _try_open_l1(self, data):
    trend_total_capital = self.rm.initial_capital * self.rm.trend_allocation
    req_capital = trend_total_capital * 0.3

    risk_request = {
        'engine': 'TREND',
        'action': 'OPEN_L1',
        'suggested_leverage': 3,
        'volatility_ratio': data['vol_ratio'],
        'estimated_risk': req_capital * 0.1
    }

    # 这里不 approve，不 execute，只返回意图
    # size MVP：用 (保证金*杠杆)/price 近似，后面再按 Bitget 合约单位精化
    suggested_lev = risk_request["suggested_leverage"]
    size = (req_capital * suggested_lev) / max(1e-9, data["price"])

    return {
        "engine": "TREND",
        "action": "OPEN_L1",
        "trade_side": "open",
        "pos_side": "long",
        "size": size,
        "marginMode": "crossed",
        "risk_request": risk_request
    }

L2 / L3 同理：
	•	action 改成 ADD_L2、ADD_L3
	•	suggested_lev 分别 5、10
	•	size 同样用近似

C) 改 _close_position：返回平仓 intent（先 MVP 市价平多）
你的 _close_position() 现在是内部算 PnL+重置。MVP 先让它返回一个 intent：

def _close_position(self, price, reason):
    logger.info(f"💥 [平仓意图] {reason} | 价格:{price:.2f} | 入场价:{self.entry_price:.2f}")

    # 注意：这里先不重置状态（因为真实成交还没确认）
    # MVP 可以先重置；更严谨是等 OMS/对账确认成交后再重置
    # 为了先跑通闭环，这里先走“乐观重置”
    self.state = TrendState.EMPTY
    self.entry_price = 0.0
    self.position_size = 0.0
    self.margin_used = 0.0
    self.avg_leverage = 1.0
    self.stop_loss = 0.0
    self.unrealized_pnl = 0.0

    return {
        "engine": "TREND",
        "action": "CLOSE",
        "trade_side": "close",
        "pos_side": "long",
        "size": 0.001,  # MVP：先给个最小值；后面要用 AccountState 的真实持仓数量
        "marginMode": "crossed",
        "risk_request": {
            "engine": "TREND",
            "action": "CLOSE",
            "suggested_leverage": 1,
            "volatility_ratio": 1.0,
            "estimated_risk": 0.0
        }
    }

⚠️ 这里有个你后面必改的点：平仓 size 必须来自真实持仓（AccountState/交易所仓位）。
MVP 先跑通链路，下一步我会让 controller 从 account_snapshot 取真实 size 塞进 intent。

⸻

4.2 SharkEngine 改法（同套路）

你 shark_engine.py 里改这些函数：
	•	on_tick()：把 _try_enter_l1/l2/l3/_close_position 的动作返回 intent
	•	_try_enter_l1/l2/l3：不再 approve + execute，而是返回 intent（pos_side=short）
	•	_close_position：返回 close short intent

例如 _try_enter_l1 改成：

def _try_enter_l1(self, price, ts, vol):
    budget = self.rm.get_shark_budget() * 0.1
    req = {'engine': 'SHARK', 'action': 'OPEN_L1', 'suggested_leverage': 2, 'volatility_ratio': vol, 'estimated_risk': budget}

    size = (budget * req["suggested_leverage"]) / max(1e-9, price)

    return {
        "engine": "SHARK",
        "action": "OPEN_L1",
        "trade_side": "open",
        "pos_side": "short",
        "size": size,
        "marginMode": "crossed",
        "risk_request": req
    }

然后在 on_tick() 里：

if self.state == SharkState.SLEEP:
    if data['rsi'] > 70:
        intent = self._try_enter_l1(price, ts, vol)
        if intent: return intent

L2/L3 同理。_close_position 返回 close short intent。

⸻

5) 你现在就能跑起来的验收标准（必须出现这三类现象）
	1.	WS 公共频道连上，并且 candle1m snapshot/update 在刷
	2.	过 20 根 candle 后，TrendEngine 不再报 “行情数据缺字段”，on_tick 开始返回 intent
	3.	MainController 日志里出现：

	•	✅ OMS提交: ... intent=...
	•	随后 DataSynchronizer.force_rest_sync() 更新仓位/账户（position_uncertain 解除）

⸻

6) 下一步我会继续补齐的“最后一块”（你说要机构级必须有）

你现在跑通后，下一步我会把 MVP 变成真正可控的机构执行：
	•	平仓 size 从 AccountState 的真实仓位取值
	•	引擎状态切换从“乐观执行”改成“等待成交确认”
	•	OMS 增加 reconcile()：断线/重启后用 REST 把订单状态补齐
	•	把 risk_request 与 approved_leverage 严格绑定：size = margin * lev / price

但这些都建立在你先跑通当前闭环。

⸻

你现在按上面做完（新增3文件 + 改 main_controller + 改 trend/shark 返回 intent），如果你愿意，我下一条就直接给你一个“最小补丁版”——让平仓 size 自动从 account_snapshot 推导，不再写死 0.001，并且把趋势/鲨鱼的订单方向、posSide、tradeSide 完整对齐 Bitget 双向规则。
