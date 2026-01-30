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