# tiny_oms.py
import time
import asyncio
import logging
import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, Tuple

from contracts import TradeIntent

logger = logging.getLogger("TinyOMS")

def resolve_trade_mode(live_trading_config: bool, env_allow: Optional[str]) -> Tuple[bool, str]:
    """Determine dry-run mode and provide a human-readable reason."""
    env_enabled = str(env_allow).lower() == "true"
    if live_trading_config and env_enabled:
        return False, "live_trading=true and ALLOW_LIVE_TRADING=true"
    if not live_trading_config and not env_enabled:
        return True, "live_trading=false and ALLOW_LIVE_TRADING!=true"
    if not live_trading_config:
        return True, "live_trading=false"
    return True, "ALLOW_LIVE_TRADING!=true"

class OrderStatus(str, Enum):
    NEW = "NEW"
    SENT = "SENT"
    ACK = "ACK"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    FAILED = "FAILED"


@dataclass
class OrderRecord:
    client_oid: str
    decision_id: str
    symbol: str
    engine: str
    side: str
    pos_side: str
    trade_side: str
    size: float
    status: OrderStatus = OrderStatus.NEW
    exchange_order_id: Optional[str] = None
    last_update: float = 0.0
    raw: Optional[Dict[str, Any]] = None
    trace_id: Optional[str] = None

class TinyOMS:
    def __init__(self, trader, symbol: str, data_sync=None, product_type: str = "USDT-FUTURES", dry_run: bool = True):  # v1.3
        self.trader = trader
        self.symbol = symbol
        self.data_sync = data_sync  # v1.3
        self.product_type = product_type
        self.dry_run = dry_run
        self.orders: Dict[str, OrderRecord] = {}
        self._decision_index: Dict[str, str] = {}

    def _gen_client_oid(self, engine: str, action: str) -> str:
        return f"{engine.lower()}_{action.lower()}_{int(time.time()*1000)}"

    def _build_decision_id(self, intent: TradeIntent) -> str:
        base = "|".join(
            [
                intent.trace_id or "no-trace",
                self.symbol,
                intent.engine,
                intent.action,
                intent.trade_side,
                intent.pos_side,
                f"{float(intent.size):.8f}",
            ]
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]

    async def place_intent(self, intent: TradeIntent) -> str:
        engine = intent.engine
        action = intent.action
        trade_side = intent.trade_side   # open/close
        pos_side = intent.pos_side       # long/short
        size = float(intent.size)
        margin_mode = intent.margin_mode or "crossed"
        trace_id = intent.trace_id or intent.risk_request.trace_id
        decision_id = intent.decision_id or self._build_decision_id(intent)

        # open long=>buy; open short=>sell; close long=>sell; close short=>buy
        if trade_side == "open":
            side = "buy" if pos_side == "long" else "sell"
        else:
            side = "sell" if pos_side == "long" else "buy"

        if decision_id in self._decision_index:
            existing = self._decision_index[decision_id]
            logger.info(f"[OMS] event=oms trace_id={trace_id} symbol={self.symbol} status=IDEMPOTENT decision_id={decision_id}")
            return existing

        client_oid = intent.client_oid or self._gen_client_oid(engine, action)
        if client_oid in self.orders and self.orders[client_oid].status not in (
            OrderStatus.FAILED,
            OrderStatus.CANCELED,
            OrderStatus.FILLED,
        ):
            logger.warning(f"[OMS] 幂等命中，跳过重复下单: {client_oid}")
            return client_oid

        rec = OrderRecord(
            client_oid=client_oid,
            decision_id=decision_id,
            symbol=self.symbol,
            engine=engine,
            side=side,
            pos_side=pos_side,
            trade_side=trade_side,
            size=size,
            status=OrderStatus.SENT,
            last_update=time.time(),
            trace_id=trace_id,
        )
        self.orders[client_oid] = rec
        self._decision_index[decision_id] = client_oid

        # 下单前：标记 pending（无回报风险开始计时）v1.3
        if self.data_sync:
            self.data_sync.mark_order_sent()

        if not self.dry_run and self.data_sync and not self.data_sync.is_private_ready():
            rec.status = OrderStatus.FAILED
            rec.last_update = time.time()
            if self.data_sync:
                self.data_sync.report_execution_event(False, f"order_channel_unhealthy clientOid={client_oid}")
            logger.warning(f"[OMS] event=oms trace_id={trace_id} symbol={self.symbol} status=FAILED reason=private_channel_unhealthy")
            return client_oid

        if self.dry_run:
            self.on_order_update(client_oid, "ack")
            self.on_order_update(client_oid, "filled")
            if self.data_sync:
                self.data_sync.pending_order_flag = False
                self.data_sync.pending_order_since_ts = 0.0
                self.data_sync.report_execution_event(True, f"dry_run_filled clientOid={client_oid}")
            logger.info(f"[OMS] event=oms trace_id={trace_id} symbol={self.symbol} status=FILLED")
            return client_oid

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
            logger.info(f"[OMS] event=oms trace_id={trace_id} symbol={self.symbol} status=SEND")

            try:  # v1.3
                resp = await asyncio.to_thread(
                    self.trader.exchange.private_mix_post_v2_mix_order_place_order,
                    req
                )
                rec.raw = resp
                rec.last_update = time.time()

                if str(resp.get("code")) == "00000":
                    data = resp.get("data") or {}
                    rec.exchange_order_id = data.get("orderId") or data.get("order_id")
                    rec.status = OrderStatus.ACK
                else:
                    rec.status = OrderStatus.FAILED
                    # v1.4 上报拒单闭环事件
                    if self.data_sync:
                        self.data_sync.report_execution_event(False, f"order_rejected clientOid={client_oid}")
                    raise RuntimeError(f"Bitget place_order failed: {resp}")
            except Exception as e:  # v1.3
                # 失败也算“有结果”，解除pending v1.3
                if self.data_sync:
                    self.data_sync.pending_order_flag = False
                    self.data_sync.pending_order_since_ts = 0.0
                    # v1.4 上报异常闭环事件
                    self.data_sync.report_execution_event(False, f"order_exception clientOid={client_oid} err={str(e)[:50]}")
                logger.error(f"下单失败: {e}")
                raise e  # 保持原有异常抛出逻辑
        else:
            try:  # v1.3
                order = await asyncio.to_thread(
                    self.trader.exchange.create_market_order,
                    self.symbol, side, size, None, {}
                )
                rec.exchange_order_id = order.get("id")
                rec.status = OrderStatus.ACK
                rec.raw = order
            except Exception as e:
                # v1.4 上报异常闭环事件
                if self.data_sync:
                    self.data_sync.pending_order_flag = False
                    self.data_sync.pending_order_since_ts = 0.0
                    self.data_sync.report_execution_event(False, f"order_exception clientOid={client_oid} err={str(e)[:50]}")
                raise e

    # ===== v1.4 新增订单状态更新方法（补充订单终态上报逻辑，需确保原有代码中调用此方法）=====
    def on_order_update(self, client_oid: str, st: str):
        """处理订单状态更新，上报执行闭环事件"""
        if client_oid not in self.orders:
            return
        rec = self.orders[client_oid]
        st = st.lower()
        # v1.4 订单终态上报闭环结果
        if st in ("ack", "accepted"):
            rec.status = OrderStatus.ACK
            if self.data_sync:
                self.data_sync.report_execution_event(True, f"order_ack clientOid={client_oid}")

        elif st in ("filled", "full_fill", "success"):
            rec.status = OrderStatus.FILLED
            if self.data_sync:
                self.data_sync.report_execution_event(True, f"order_filled clientOid={client_oid}")

        elif st in ("partial", "partial_fill", "partially_filled"):
            rec.status = OrderStatus.PARTIAL
            if self.data_sync:
                self.data_sync.report_execution_event(True, f"order_partial clientOid={client_oid}")

        elif st in ("canceled", "cancelled"):
            rec.status = OrderStatus.CANCELED
            if self.data_sync:
                self.data_sync.report_execution_event(False, f"order_canceled clientOid={client_oid}")

        elif st in ("rejected", "reject", "fail", "failed"):
            rec.status = OrderStatus.FAILED
            if self.data_sync:
                self.data_sync.report_execution_event(False, f"order_rejected clientOid={client_oid}")
        rec.last_update = time.time()

    # ===== v1.4 新增无回报超时检查方法 =====
    def check_no_report_timeout(self, timeout_s: int = 30):
        """在主循环里定期调用：发单后长时间无回报，判定为失败闭环。"""
        if not self.data_sync:
            return
        now = time.time()
        if self.data_sync.pending_order_flag and (now - self.data_sync.pending_order_since_ts > timeout_s):
            self.data_sync.report_execution_event(False, f"order_no_report_timeout>{timeout_s}s")
