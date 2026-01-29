# account_state.py
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from .data_synchronizer import DataSynchronizer

logger = logging.getLogger('AccountState')

@dataclass
class Position:
    """清洗后的持仓业务对象"""
    side: str
    size: float
    entry_price: float
    unrealized_pnl: float
    leverage: float
    margin: float
    # 衍生计算字段
    notional_value: float = 0.0  # 名义价值
    
@dataclass  
class Account:
    """清洗后的账户业务对象"""
    equity: float
    wallet_balance: float  # 已实现余额
    available_balance: float
    margin_ratio: float
    # 衍生计算字段
    total_unrealized_pnl: float = 0.0
    used_margin: float = 0.0
    margin_usage: float = 0.0  # 保证金使用率

class AccountState:
    """
    账户状态管理器：负责数据清洗、业务计算和状态分发。
    它不关心数据来源，只关心数据本身的业务含义。
    """
    def __init__(self, data_sync: DataSynchronizer):
        self.data_sync = data_sync
        
        # 业务状态存储
        self.positions: Dict[str, Position] = {}
        self.account: Optional[Account] = None
        
        # 引擎仓位归属映射（核心：解决“钱是谁的”问题）
        # 默认映射：long->trend, short->shark，可根据策略状态动态调整
        self.position_ownership = {
            'long': 'trend',
            'short': 'shark'
        }
    
    def update(self):
        """从DataSynchronizer拉取快照并更新业务状态"""
        snapshot = self.data_sync.get_snapshot()
        
        # 1. 更新持仓
        self.positions = {}
        for side, raw_pos in snapshot.get('positions', {}).items():
            notional_value = raw_pos['size'] * raw_pos['entry_price'] if raw_pos['size'] > 0 else 0
            self.positions[side] = Position(
                side=side,
                size=raw_pos['size'],
                entry_price=raw_pos['entry_price'],
                unrealized_pnl=raw_pos['unrealized_pnl'],
                leverage=raw_pos['leverage'],
                margin=raw_pos['margin'],
                notional_value=notional_value
            )
        
        # 2. 更新账户
        raw_account = snapshot.get('account')
        if raw_account:
            # 计算衍生字段
            total_unrealized = sum(p.unrealized_pnl for p in self.positions.values())
            used_margin = sum(p.margin for p in self.positions.values())
            
            # 注意：wallet_balance可能需要根据交易所定义调整
            # 这里假设 raw_account['wallet_balance'] 是不含未实现盈亏的纯余额
            margin_usage = used_margin / raw_account['wallet_balance'] if raw_account['wallet_balance'] > 0 else 0
            
            self.account = Account(
                equity=raw_account['equity'],
                wallet_balance=raw_account['wallet_balance'],
                available_balance=raw_account['available_balance'],
                margin_ratio=raw_account['margin_ratio'],
                total_unrealized_pnl=total_unrealized,
                used_margin=used_margin,
                margin_usage=min(margin_usage, 1.0)  # 限制不超过100%
            )
    
    def get_risk_snapshot(self) -> Dict[str, Any]:
        """
        为风控管理器提供标准化数据。
        这是连接数据层和风控层的桥梁。
        """
        if not self.account:
            return {}
        
        # 根据仓位归属，分离趋势和鲨鱼的浮盈
        trend_float = 0.0
        shark_float = 0.0
        
        for side, pos in self.positions.items():
            owner = self.position_ownership.get(side)
            if owner == 'trend':
                trend_float += pos.unrealized_pnl
            elif owner == 'shark':
                shark_float += pos.unrealized_pnl
        
        return {
            'wallet_balance': self.account.wallet_balance,  # 净值余额（已实现）
            'trend_float': trend_float,
            'shark_float': shark_float,
            'margin_usage': self.account.margin_usage,
            'timestamp': time.time()
        }
    
    def get_strategy_snapshot(self, engine_name: str) -> Dict[str, Any]:
        """
        为策略引擎提供其关心的数据视图。
        例如，趋势引擎只看到long仓位和整体账户。
        """
        # 这里可以根据引擎名称过滤数据
        # 简单返回全部，由引擎自己处理
        return {
            'account': self.account.__dict__ if self.account else None,
            'positions': {k: v.__dict__ for k, v in self.positions.items()},
            'position_uncertain': self.data_sync.position_uncertain
        }
    
    def update_position_ownership(self, long_owner='trend', short_owner='shark'):
        """动态更新仓位所有权（用于策略切换）"""
        self.position_ownership = {
            'long': long_owner,
            'short': short_owner
        }
        logger.info(f"更新仓位归属: long->{long_owner}, short->{short_owner}")