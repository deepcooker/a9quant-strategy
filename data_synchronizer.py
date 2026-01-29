# data_synchronizer.py
import asyncio
import time
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from threading import Lock

logger = logging.getLogger('DataSync')

@dataclass
class RawPosition:
    """交易所原始持仓数据容器"""
    symbol: str
    side: str  # 'long' / 'short'
    size: float  # 持仓数量(币)
    entry_price: float
    unrealized_pnl: float
    leverage: float
    margin: float  # 占用保证金
    timestamp: float  # 数据更新时间

@dataclass
class RawAccount:
    """交易所原始账户数据容器"""
    equity: float  # 权益 (余额 + 未实现盈亏)
    wallet_balance: float  # 钱包余额 (已实现部分)
    available_balance: float  # 可用余额
    margin_ratio: float  # 保证金率
    timestamp: float

class DataSynchronizer:
    """
    数据同步器：负责与交易所实时同步，维护原始数据。
    采用『WS推送为主，REST定时/事件触发校准为辅』的策略。
    """
    def __init__(self, trader, symbol: str):
        self.trader = trader
        self.symbol = symbol
        self.clean_symbol = symbol.replace('/', '').split(':')[0]  # 用于匹配WS数据
        
        # 核心状态存储（使用锁保证线程安全）
        self._lock = Lock()
        self._raw_positions: Dict[str, RawPosition] = {}  # key: side
        self._raw_account: Optional[RawAccount] = None
        
        # 同步控制标志
        self.position_uncertain = False
        self.last_rest_sync = 0.0
        self.sync_interval = 60.0  # REST强制同步间隔(秒)

    def update_from_ws_position(self, data: Dict[str, Any]):
        """
        处理WebSocket持仓推送。
        注意：Bitget WS可能只推送变动的仓位，未推送方向可能为空或需保留。
        """
        with self._lock:
            for pos_data in data:
                if pos_data.get('instId') != self.clean_symbol:
                    continue
                    
                side = pos_data.get('holdSide', '').lower()
                if side not in ['long', 'short']:
                    continue
                
                # 解析原始数据
                raw_pos = RawPosition(
                    symbol=self.symbol,
                    side=side,
                    size=float(pos_data.get('total', 0)),
                    entry_price=float(pos_data.get('openPriceAvg', 0)),
                    unrealized_pnl=float(pos_data.get('unrealizedPL', 0)),
                    leverage=float(pos_data.get('leverage', 1)),
                    margin=float(pos_data.get('marginSize', 0)),
                    timestamp=time.time()
                )
                self._raw_positions[side] = raw_pos
                
            # 收到WS推送，解除仓位不确定状态
            self.position_uncertain = False
            logger.debug(f"WS持仓更新: long={self._raw_positions.get('long', RawPosition)}")

    def update_from_ws_account(self, data: Dict[str, Any]):
        """处理WebSocket账户推送"""
        with self._lock:
            # 这里需要根据Bitget WS账户推送的实际格式解析
            # 示例格式，请根据实际推送调整
            if data.get('marginCoin') == 'USDT':
                self._raw_account = RawAccount(
                    equity=float(data.get('accountEquity', 0)),
                    wallet_balance=float(data.get('available', 0)) + float(data.get('locked', 0)),
                    available_balance=float(data.get('available', 0)),
                    margin_ratio=float(data.get('crossedRiskRate', 0)),
                    timestamp=time.time()
                )

    async def force_rest_sync(self):
        """
        强制执行REST API同步，获取绝对真实数据。
        在启动、下单后、定时或状态不一致时调用。
        """
        logger.info("🔄 执行REST强制同步...")
        try:
            # 同步持仓
            positions = await asyncio.to_thread(
                self.trader.exchange.fetch_positions, 
                [self.symbol]
            )
            
            new_raw_positions = {}
            for p in positions:
                side = p.get('side', '').lower()
                if side in ['long', 'short'] and float(p.get('contracts', 0)) > 0:
                    new_raw_positions[side] = RawPosition(
                        symbol=self.symbol,
                        side=side,
                        size=float(p.get('contracts', 0)),
                        entry_price=float(p.get('entryPrice', 0)),
                        unrealized_pnl=float(p.get('unrealizedPnl', 0)),
                        leverage=float(p.get('leverage', 1)),
                        margin=float(p.get('initialMargin', 0)),
                        timestamp=time.time()
                    )
            
            # 同步账户
            balance = await asyncio.to_thread(
                self.trader.exchange.fetch_balance, 
                {'type': 'swap'}
            )
            usdt = balance.get('USDT', {})
            
            with self._lock:
                self._raw_positions = new_raw_positions
                self._raw_account = RawAccount(
                    equity=float(usdt.get('total', 0)),
                    wallet_balance=float(usdt.get('free', 0)) + float(usdt.get('used', 0)),
                    available_balance=float(usdt.get('free', 0)),
                    margin_ratio=0.0,  # 可能需要单独计算
                    timestamp=time.time()
                )
                self.position_uncertain = False
                self.last_rest_sync = time.time()
                
            logger.info("✅ REST同步完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ REST同步失败: {e}")
            return False

    def get_snapshot(self) -> Dict[str, Any]:
        """获取当前数据快照（线程安全）"""
        with self._lock:
            return {
                'positions': {k: v.__dict__ for k, v in self._raw_positions.items()},
                'account': self._raw_account.__dict__ if self._raw_account else None,
                'position_uncertain': self.position_uncertain,
                'timestamp': time.time()
            }