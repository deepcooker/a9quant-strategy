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