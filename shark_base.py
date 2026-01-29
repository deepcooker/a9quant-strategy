import asyncio
import json
import logging
import sys
import os
import ccxt.async_support as ccxt  # 使用异步CCXT
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# 引入你的基础WS库
from base_bitget_ws import BaseBitgetWsClient

# 配置日志
logging.basicConfig(level=logging.INFO,format="%(asctime)s [%(levelname)s] %(message)s",handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("SharkBase")

# ==========================================
# 1. 状态容器 (数据与逻辑分离)
# ==========================================
@dataclass
class PositionData:
    """单方向仓位数据"""
    amount: float = 0.0      # 持仓数量 (个)
    entry_price: float = 0.0 # 持仓均价
    unrealized_pnl: float = 0.0 # 未实现盈亏

@dataclass
class StrategyState:
    """全局策略状态"""
    symbol: str = ""
    current_price: float = 0.0
    
    # 账户资金
    wallet_balance: float = 0.0  # 钱包余额
    available_balance: float = 0.0 # 可用余额
    
    # 双向持仓 (Long/Short)
    long_pos: PositionData = field(default_factory=PositionData)
    short_pos: PositionData = field(default_factory=PositionData)
    
    # 系统状态
    is_ready: bool = False  # 初始化是否完成

# ==========================================
# 2. 策略核心类
# ==========================================
class SharkStrategy(BaseBitgetWsClient):
    def __init__(self, config_path='config.json'):
        super().__init__()
        self.config = self._load_config(config_path)
        
        # 基础参数
        self.symbol = self.config['symbol']
        self.ws_symbol = self.symbol.split(':')[0].replace('/', '') # BTCUSDT
        self.leverage = self.config.get('leverage', 10)
        self.is_sandbox = self.config.get('sandbox', False)
        
        # 初始化状态容器
        self.state = StrategyState(symbol=self.symbol)
        
        # CCXT 交易所实例 (用于REST API操作)
        self.exchange: Optional[ccxt.bitget] = None

    def _load_config(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"配置文件加载失败: {e}")
            sys.exit(1)

    # ---------------------------------------------------
    # REST API 初始化 (环境准备)
    # ---------------------------------------------------
    async def init_exchange_rest(self):
        """初始化 CCXT 并检查交易环境 (双向持仓、全仓模式)"""
        logger.info("正在初始化 REST API 连接...")
        
        proxy_url = self.config.get('proxy')
        exchange_config = {
            'apiKey': self.config['api']['apiKey'],
            'secret': self.config['api']['secret'],
            'password': self.config['api']['password'],
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
        }
        
        if self.is_sandbox:
            self.exchange = ccxt.bitget(exchange_config)
            self.exchange.set_sandbox_mode(True)
            logger.warning("⚠️⚠️⚠️ 当前为模拟盘模式 (Sandbox) ⚠️⚠️⚠️")
        else:
            self.exchange = ccxt.bitget(exchange_config)

        if proxy_url:
            self.exchange.proxies = {'http': proxy_url, 'https': proxy_url}

        try:
            # 1. 检查连接
            await self.exchange.load_markets()
            market = self.exchange.market(self.symbol)
            logger.info(f"✅ 交易所连接成功 | 交易对: {self.symbol}")
            
            # 2. 设置双向持仓模式 (Hedge Mode)
            # Bitget API: set_position_mode(hedged=True)
            try:
                await self.exchange.set_position_mode(hedged=True, symbol=self.symbol)
                logger.info("✅ 已设置为双向持仓模式 (Hedge Mode)")
            except Exception as e:
                logger.info(f"设置持仓模式跳过 (可能已设置): {e}")

            # 3. 设置全仓模式 (Crossed)
            try:
                await self.exchange.set_margin_mode(marginMode='crossed', symbol=self.symbol)
                logger.info("✅ 已设置为全仓模式 (Cross Margin)")
            except Exception as e:
                logger.info(f"设置保证金模式跳过: {e}")

            # 4. 设置杠杆
            try:
                await self.exchange.set_leverage(self.leverage, symbol=self.symbol)
                logger.info(f"✅ 杠杆已设置为: {self.leverage}x")
            except Exception as e:
                logger.warning(f"设置杠杆失败: {e}")

            # 5. 初始资产同步
            await self.sync_rest_data()
            
            self.state.is_ready = True
            
        except Exception as e:
            logger.critical(f"❌ 环境初始化失败: {e}")
            await self.exchange.close()
            sys.exit(1)

    async def sync_rest_data(self):
        """通过 REST API 强制同步一次资金和持仓"""
        try:
            # 同步余额
            balance = await self.exchange.fetch_balance({'type': 'swap'})
            usdt = balance.get('USDT', {})
            self.state.wallet_balance = float(usdt.get('free', 0)) + float(usdt.get('used', 0))
            self.state.available_balance = float(usdt.get('free', 0))
            
            # 同步持仓
            positions = await self.exchange.fetch_positions([self.symbol])
            # 重置本地状态
            self.state.long_pos = PositionData()
            self.state.short_pos = PositionData()
            
            for pos in positions:
                side = pos['side'] # long / short
                contracts = float(pos['contracts'])
                entry_price = float(pos['entryPrice']) if pos['entryPrice'] else 0.0
                unrealized = float(pos['unrealizedPnl']) if pos['unrealizedPnl'] else 0.0
                
                if side == 'long' and contracts > 0:
                    self.state.long_pos = PositionData(contracts, entry_price, unrealized)
                elif side == 'short' and contracts > 0:
                    self.state.short_pos = PositionData(contracts, entry_price, unrealized)
            
            logger.info(f"💰 [REST同步] 余额:{self.state.wallet_balance:.2f}U | "
                        f"多单:{self.state.long_pos.amount} | 空单:{self.state.short_pos.amount}")
            
        except Exception as e:
            logger.error(f"REST数据同步出错: {e}")

    # ---------------------------------------------------
    # 必要的抽象方法实现 (来自 BaseBitgetWsClient)
    # ---------------------------------------------------
    def get_sign(self, timestamp: str) -> str:
        """实现父类的签名方法"""
        return self.generate_sign(timestamp, self.config['api']['secret'])

    # ---------------------------------------------------
    # WebSocket 回调处理 (实时更新状态)
    # ---------------------------------------------------
    async def on_public_ticker(self, ticker: dict, action: str):
        """处理公共行情 Ticker"""
        try:
            # 更新最新价格
            price = float(ticker.get('lastPr', 0))
            if price > 0:
                self.state.current_price = price
                # 可以在这里打印心跳，证明程序活着
                # print(f"\r💓 现价: {price}", end="", flush=True)
        except Exception:
            pass

    async def on_private_position(self, pos_data: dict):
        """处理私有仓位推送"""
        # 过滤非当前币种
        if pos_data.get('instId') != self.ws_symbol: return
        
        try:
            # Bitget 推送字段解析
            hold_side = pos_data.get('holdSide') # long / short
            total = float(pos_data.get('total', 0))
            avg_price = float(pos_data.get('openPriceAvg', 0))
            upl = float(pos_data.get('unrealizedPL', 0))
            
            logger.info(f"⚡ [WS推仓] {hold_side} | 数量:{total} | 均价:{avg_price}")
            
            if hold_side == 'long':
                self.state.long_pos.amount = total
                self.state.long_pos.entry_price = avg_price
                self.state.long_pos.unrealized_pnl = upl
            elif hold_side == 'short':
                self.state.short_pos.amount = total
                self.state.short_pos.entry_price = avg_price
                self.state.short_pos.unrealized_pnl = upl
                
        except Exception as e:
            logger.error(f"仓位解析错误: {e}")

    async def on_private_account(self, account_data: dict):
        """处理账户余额推送"""
        # 简单更新一下余额，实际逻辑可能更复杂
        # logger.info(f"💰 [WS资金] 更新: {account_data}")
        pass

    # ---------------------------------------------------
    # 仪表盘任务 (Dashboard)
    # ---------------------------------------------------
    async def dashboard_task(self):
        """每3秒打印一次当前状态"""
        while True:
            await asyncio.sleep(3)
            if not self.state.is_ready: continue
            
            p = self.state.current_price
            logger.info("-" * 60)
            logger.info(f"📊 [基座监控] 现价: {p}")
            
            # 多单展示
            l = self.state.long_pos
            l_val = l.amount * p
            logger.info(f"   🟢 [多单] 持仓: {l.amount} ({l_val:.1f}U) | 均价: {l.entry_price}")
            
            # 空单展示
            s = self.state.short_pos
            s_val = s.amount * p
            logger.info(f"   🔴 [空单] 持仓: {s.amount} ({s_val:.1f}U) | 均价: {s.entry_price}")
            
            logger.info(f"   💰 [资金] 余额: {self.state.wallet_balance:.2f} U")
            logger.info("-" * 60)

    # ---------------------------------------------------
    # 主运行入口
    # ---------------------------------------------------
    async def start(self):
        # 1. 初始化 REST API (环境检查)
        await self.init_exchange_rest()
        
        # 2. 启动 WS 连接 (父类方法)
        # 并行运行：公共WS、私有WS、仪表盘
        await asyncio.gather(
            self.connect_public_ws("USDT-FUTURES", self.ws_symbol, candle_channels=[]),
            self.connect_private_ws(self.config, "USDT-FUTURES"),
            self.dashboard_task()
        )

# ==========================================
# 运行脚本
# ==========================================
if __name__ == "__main__":
    strategy = SharkStrategy()
    try:
        asyncio.run(strategy.start())
    except KeyboardInterrupt:
        logger.info("程序停止")