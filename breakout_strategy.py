import asyncio
import json
import sys
import time
import logging
import os
import hmac
import hashlib
import base64
import ssl
from collections import deque
from decimal import Decimal
from typing import Dict, Optional
from datetime import datetime

# 修复导入问题：添加当前目录到sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# 确保 BaseBitgetWsClient 是你修改过支持 candle_channels 的版本
from .base_bitget_ws import BaseBitgetWsClient 
from .proxy_utils import set_system_proxy
from .trade_record_utils import TradeRecordManager
from .market_utils import get_tick_size
from .risk_control_v2 import GlobalRiskController
from .position_utils import calculate_position_size, calculate_break_even_points
from cctx_utils import ExchangeTrader

# 1. 通用代理配置
set_system_proxy(enable=True)

try:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(current_dir))))
    sys.path.append("/root/policy")
except ImportError:
    print("⚠️ 警告: 未找到 cctx_utils，部分功能可能受限")
    ExchangeTrader = None

# ================= 配置日志 =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BreakoutStrategy")

# 辅助函数：时间戳格式化 (精确到毫秒)
def format_ts(ts):
    return datetime.fromtimestamp(int(ts) / 1000).strftime('%H:%M:%S.%f')[:-3]

# ================= 状态管理 =================
class StrategyState:
    def __init__(self):
        self.tick_history = deque()
        self.current_price = 0.0
        self.last_price = 0.0
        
        # --- K线本地缓存 ---
        # 结构: [ ..., 前2根(已结), 前1根(已结), 当前根(未结) ]
        self.kline_cache = [] 
        
        # 信号冷却锁
        self.last_signal_time = 0  # 上一次信号触发时间
        
        # 持仓与移动止损状态
        self.position = None 
        self.closing_position = None 
        self.highest_price = 0.0
        self.lowest_price = 0.0 
        self.dynamic_stop_price = 0.0
        self.last_close_time = 0
        self.initial_balance = 0.0
        self.current_balance = 0.0
        self.is_trading = False 
        self.is_warmup_done = False # 冷启动预热标志
        self.is_stopping = False  # 【新增】正在停止标志

        # 分析字段
        self.trade_start_time = 0
        self.trigger_price = 0.0 

        # 风控指标状态
        self.risk_metrics = {
            "consecutive_loss": 0,
            "daily_drawdown": "0.0",
            "current_position_count": 0,
            "volatility": "0.0",
            "single_symbol_position_count": 0,
            "total_exposure_ratio": "0.0"
        }
        self.daily_initial_balance = 0.0
        self.trade_pnl_history = []

# ================= 核心策略类 =================
class BreakoutStrategy(BaseBitgetWsClient):        
    def __init__(self, config_path='breakout_config.json'):
        # 初始化WS基类
        super().__init__()
        
        # [热更新] 1. 路径处理与保存
        if not os.path.exists(config_path):
            base_path = os.path.dirname(os.path.abspath(__file__))
            self.config_path = os.path.join(base_path, 'breakout_config.json') 
        else:
            self.config_path = config_path

        # [热更新] 2. 初始加载配置
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)

        # [热更新] 3. 初始化文件修改时间记录
        try:
            self.last_config_mtime = os.path.getmtime(self.config_path)
        except:
            self.last_config_mtime = 0
        self.last_check_config_time = 0
        
        # 【稳定性补丁】记录上一次被风控拦截的时间
        self.last_risk_block_time = 0
        
        self.symbol = self.config['symbol'] 
        self.ws_symbol = self.symbol.split(':')[0].replace('/', '')
        self.product_type = 'USDT-FUTURES'
        
        # 读取策略配置的周期 (默认 candle1m)
        self.target_period = self.config.get('strategy', {}).get('period', 'candle1m')
        
        # 判断是否模拟盘
        self.is_sandbox = self.config.get('sandbox', False)
        
        if self.is_sandbox:
            self.public_ws_url = "wss://wspap.bitget.com/v2/ws/public"
            self.private_ws_url = "wss://wspap.bitget.com/v2/ws/private"
            logger.info("🔧 [环境切换] 已切换至 Bitget 模拟盘 WS 地址")
        
        self.state = StrategyState()
        self.history_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'breakout_history.json') 
        
        self.record_manager = TradeRecordManager(
            record_file=self.history_file,
            max_records=1000
        )
        
        self.trader = None
        if ExchangeTrader:
            try:
                # 初始化 REST 客户端
                self.trader = ExchangeTrader(
                    exchange_id=self.config.get('exchange_id', 'bitget'),
                    api_key=self.config['api']['apiKey'],
                    secret=self.config['api']['secret'],
                    passphrase=self.config['api']['password'], 
                    sandbox=self.is_sandbox
                )
                self.trader.exchange.proxies = {
                    'http': "http://127.0.0.1:7890",
                    'https': "http://127.0.0.1:7890"
                }
                
                # 【模拟盘核心修复】注入请求头
                if self.is_sandbox:
                    logger.warning("⚠️⚠️⚠️ 当前处于【模拟盘/Sandbox】模式 ⚠️⚠️⚠️")
                    if not hasattr(self.trader.exchange, 'headers') or not self.trader.exchange.headers:
                        self.trader.exchange.headers = {}
                    self.trader.exchange.headers['paptrading'] = '1'
                    logger.info("🔧 [模拟盘] 已注入请求头: paptrading=1")
                else:
                    logger.info("💰 当前处于【实盘/Live】模式")

            except Exception as e:
                logger.error(f"ExchangeTrader初始化失败: {e}")

        # 获取tick_size
        self.tick_size = self.get_tick_size()

        # 初始化风控控制器
        self.risk_controller = None
        if GlobalRiskController:
            risk_config = self.config.get('risk_control', {})
            self.risk_controller = GlobalRiskController({
                "max_consecutive_loss": risk_config.get('max_consecutive_loss', 5),
                "daily_max_drawdown": risk_config.get('daily_max_drawdown', "2.0"),
                "max_position_count": risk_config.get('max_position_count', 5),
                "single_position_max_risk": risk_config.get('single_position_max_risk', "0.5"),
                "single_symbol_max_position": risk_config.get('single_symbol_max_position', 2),
                "total_exposure_max_ratio": risk_config.get('total_exposure_max_ratio', "10.0"),
                "cool_down_seconds": risk_config.get('cool_down_seconds', 1800)
            })
            logger.info("✅ 风控控制器初始化完成")
        else:
            logger.warning("⚠️ 风控模块未加载，将跳过部分风控校验")

    # ------------------- [热更新] 核心逻辑 -------------------
    def _check_and_reload_config(self):
        try:
            if time.time() - self.last_check_config_time < 5.0: return
            self.last_check_config_time = time.time()

            if not os.path.exists(self.config_path): return
            
            mtime = os.path.getmtime(self.config_path)
            if mtime <= self.last_config_mtime: return

            logger.info(f"🔄 检测到配置变动，正在热重载: {self.config_path}")
            with open(self.config_path, 'r', encoding='utf-8') as f:
                new_config = json.load(f)

            self.config = new_config
            
            old_period = self.target_period
            self.target_period = self.config.get('strategy', {}).get('period', self.target_period)
            if old_period != self.target_period:
                logger.info(f"⚠️ 策略周期已变更: {old_period} -> {self.target_period} (注意: 需要重启程序才能订阅新频道)")
            
            if self.risk_controller:
                self.risk_controller.config = self.config.get('risk_control', {})
                logger.info("🛡️ 风控参数已实时更新")

            self.last_config_mtime = mtime
            logger.info("✅ 配置热重载完成！")

        except Exception as e:
            logger.error(f"❌ 热重载配置失败: {e}")

    # ------------------- 必须实现的方法 -------------------
    def get_sign(self, timestamp):
        return self.generate_sign(timestamp, self.config['api']['secret'])
    
    def get_tick_size(self):
        try:
            if self.trader:
                market = self.trader.exchange.market(self.symbol)
                return get_tick_size(market=market, symbol=self.symbol, default_tick_size=0.001)
            return 0.5 
        except Exception:
            return 0.5

    def sync_initialize(self):
        """同步初始化"""
        logger.info(">>> 阶段一：REST 环境初始化...")
        if not self.trader: return
        try:
            self.trader.exchange.load_markets()
            try:
                self.trader.exchange.set_position_mode(False, self.symbol)
                logger.info("✅ 已设置为单向持仓模式")
            except Exception: pass

            if self.config.get('leverage'):
                try:
                    self.trader.exchange.set_leverage(self.config['leverage'], self.symbol)
                    logger.info(f"杠杆已设置: {self.config['leverage']}x")
                except Exception: pass

            balance = self.trader.exchange.fetch_balance({'type': 'swap'})
            usdt_free = float(balance['USDT']['free'])
            self.state.initial_balance = usdt_free
            self.state.current_balance = usdt_free
            self.state.daily_initial_balance = usdt_free
            logger.info(f"初始可用余额: {usdt_free:.2f} USDT")

            try:
                self.trader.exchange.cancel_all_orders(self.symbol)
            except Exception: pass

        except Exception as e:
            logger.error(f"初始化失败: {e}")
            sys.exit(1)
            

    # ------------------- K线数据处理 -------------------
    async def on_public_candle(self, candle_data: list, channel: str, action: str):
        try:
            if channel != self.target_period: return

            if action == 'snapshot':
                sorted_data = sorted(candle_data, key=lambda x: int(x[0]))
                self.state.kline_cache = sorted_data[-5:]
                
                logger.info(f"✅ [K线初始化] 历史K线已构建 (最近{len(self.state.kline_cache)}根)")
                for i, k in enumerate(self.state.kline_cache):
                    status = "已结" if i < len(self.state.kline_cache)-1 else "未结"
                    logger.info(f"   📜 [{status}] TS:{format_ts(k[0])} | O:{k[1]} H:{k[2]} L:{k[3]} C:{k[4]}")
                return

            if action == 'update' and candle_data:
                new_k = candle_data[0]
                new_ts = int(new_k[0])
                
                if not self.state.kline_cache:
                    self.state.kline_cache.append(new_k)
                    return

                last_k = self.state.kline_cache[-1]
                last_ts = int(last_k[0])

                if new_ts == last_ts:
                    self.state.kline_cache[-1] = new_k

                elif new_ts > last_ts:
                    logger.info("=" * 60)
                    logger.info(f"🔒 [K线封板] {format_ts(last_ts)} 最终收盘: {last_k[4]}")
                    
                    closed_k = self.state.kline_cache[-1]
                    logger.info(f"📊 [基准更新] 上一根已结: TS:{format_ts(closed_k[0])} H:{closed_k[2]} L:{closed_k[3]}")

                    self.state.kline_cache.append(new_k)
                    logger.info(f"🆕 [新线开始] {format_ts(new_ts)} 开盘: {new_k[1]}")
                    
                    # 预热完成
                    if not self.state.is_warmup_done:
                        self.state.is_warmup_done = True
                        logger.info(f"🔥 [预热完成] 已完整观测一根K线，策略正式接管！")
                    
                    if len(self.state.kline_cache) > 5:
                        self.state.kline_cache.pop(0)
                    logger.info("=" * 60)

        except Exception as e:
            logger.error(f"K线数据处理异常: {e}")

    # ------------------- 行情处理与交易逻辑 -------------------
    async def on_public_ticker(self, ticker: dict, action: str):
        local_ms = time.time() * 1000
        server_ms = float(ticker.get('ts'))
        latency = local_ms - server_ms
        price = float(ticker.get('lastPr'))
        await self.process_ticker(price, latency)
    
    async def process_ticker(self, price, latency):
        self._check_and_reload_config()

        if time.time() - self.last_risk_block_time < 60:
            return

        if time.time() - self.state.last_signal_time < 1.0:
            return

        if self.state.is_trading:
            return
        
        # 【新增】如果正在停止中，绝不处理任何逻辑
        if self.state.is_stopping:
            return

        self.state.current_price = price
        if price != self.state.last_price:
            self.state.tick_history.append(time.time())
            self.state.last_price = price

        if len(self.state.kline_cache) < 2:
            if int(time.time()) % 10 == 0:
                logger.info(f"⏳ 等待K线数据 (缓存:{len(self.state.kline_cache)}/2)...")
            return

        last_closed_k = self.state.kline_cache[-2]
        prev_high = float(last_closed_k[2])
        prev_low = float(last_closed_k[3])
        k_ts_str = format_ts(last_closed_k[0])

        if int(time.time() * 10) % 200 == 0:
            pos_str = f"{self.state.position['side']}" if self.state.position else "空仓"
            logger.info(f"👀 监控中 | 延迟:{latency:.1f}ms | 现价:{price} | 突破区间: [{prev_low} - {prev_high}] | 持仓:{pos_str}")
            
        if not self.state.is_warmup_done:
            if int(time.time() * 10) % 50 == 0:
                logger.info(f"⏳ [预热中] 等待当前K线封板... 现价:{price}")
            return

        # --- 策略核心逻辑 ---
        if not self.state.position:
            if price > prev_high:
                if self.check_risk_before_open('buy', price):
                    self.state.last_signal_time = time.time()
                    logger.info(f"📈 [信号触发] 现价{price} > 前高{prev_high} (K线:{k_ts_str}) -> 🚀 开多")
                    await self.execute_market_entry('buy', price)
            
            elif price < prev_low:
                if self.check_risk_before_open('sell', price):
                    self.state.last_signal_time = time.time()
                    logger.info(f"📉 [信号触发] 现价{price} < 前低{prev_low} (K线:{k_ts_str}) -> 🚀 开空")
                    await self.execute_market_entry('sell', price)

        elif self.state.position['side'] == 'long':
            self.state.highest_price = max(self.state.highest_price, price)
            if price < prev_low:
                self.state.last_signal_time = time.time()
                logger.warning(f"🛑 [反转信号] 现价{price} < 前低{prev_low} -> 多单平仓")
                await self.execute_market_close(reason='breakout_reverse')

        elif self.state.position['side'] == 'short':
            self.state.lowest_price = min(self.state.lowest_price, price)
            if price > prev_high:
                self.state.last_signal_time = time.time()
                logger.warning(f"🛑 [反转信号] 现价{price} > 前高{prev_high} -> 空单平仓")
                await self.execute_market_close(reason='breakout_reverse')

    # ------------------- 风控与交易执行 -------------------
    def check_risk_before_open(self, side, price):
        if time.time() - self.last_risk_block_time < 60: return False
        if not self.risk_controller: return True
        self.update_risk_metrics()
        
        position_data = {
            "symbol": self.symbol,
            "size": self.calculate_position_size(price),
            "open_price": price
        }
        
        risk_result = self.risk_controller.check_risk(
            risk_metrics=self.state.risk_metrics,
            position_data=position_data,
            position_id=f"{self.symbol}_{side}_{int(time.time())}"
        )
        
        if risk_result["triggered"]:
            self.last_risk_block_time = time.time()
            logger.error(f"🚫 开仓被风控拦截 | 原因: {risk_result['reason']} | ⏸️ 暂停开仓检测 60秒...")
            return False
        return True

    def update_risk_metrics(self):
        if not self.state: return
        self.state.risk_metrics["current_position_count"] = 1 if self.state.position else 0
        self.state.risk_metrics["single_symbol_position_count"] = self.state.risk_metrics["current_position_count"]
        
        if self.is_sandbox:
            self.state.risk_metrics["daily_drawdown"] = "0.0"
        elif self.state.daily_initial_balance > 0:
            drawdown = (self.state.daily_initial_balance - self.state.current_balance) / self.state.daily_initial_balance * 100
            self.state.risk_metrics["daily_drawdown"] = f"{drawdown:.2f}"
        self.update_consecutive_loss()

    def update_consecutive_loss(self):
        consecutive_loss = 0
        for record in reversed(self.state.trade_pnl_history[-10:]):
            if record["net_pnl"] < 0: consecutive_loss += 1
            else: break
        self.state.risk_metrics["consecutive_loss"] = consecutive_loss

    async def execute_market_entry(self, raw_side, price):
        """市价开仓"""
        if self.state.is_stopping:
            logger.warning("🛑 策略正在停止，拒绝开仓请求")
            return
        
        if self.state.is_trading: return
        self.state.is_trading = True
        try:
            std_side = 'long' if raw_side.lower() == 'buy' else 'short'
            amount = self.calculate_position_size(price)
            if amount <= 0:
                logger.error("❌ 计算下单量为0，取消开仓")
                return

            amount_str = self.trader.exchange.amount_to_precision(self.symbol, amount)
            
            logger.info(f"🔫 突破策略开仓: {std_side} ({raw_side}) 数量:{amount_str}")
            
            # 乐观更新 (防止重复开单)
            self.state.position = {
                'side': std_side, 
                'amount': float(amount_str), 
                'entry': price, 
                'fee': 0.0
            }
            self.state.highest_price = price
            self.state.lowest_price = price
            self.state.trade_start_time = time.time()
            self.state.trigger_price = price 
            
            sl_ticks = int(self.config['risk']['min_stop_loss_ticks'])
            sl_dist = sl_ticks * self.tick_size
            self.state.dynamic_stop_price = price - sl_dist if std_side == 'long' else price + sl_dist

            params = {'reduceOnly': False, 'posSide': 'net'}
            await asyncio.to_thread(
                self.trader.exchange.create_market_order,
                self.symbol, raw_side, amount_str, None, params
            )
            
        except Exception as e:
            logger.error(f"开仓失败: {e}")
            self.state.position = None 
            if "Insufficient balance" in str(e):
                logger.warning("💰 余额不足，暂停策略开仓 60 秒...")
                await asyncio.sleep(60) 
        finally:
            self.state.is_trading = False

    async def execute_market_close(self, reason='signal'):
        """市价平仓"""
        if self.state.is_trading: return
        self.state.is_trading = True
        self.state.last_signal_time = time.time()

        try:
            pos = self.state.position
            if not pos: 
                self.state.is_trading = False
                return
            
            self.state.closing_position = pos.copy()
            self.state.closing_position['highest'] = self.state.highest_price
            self.state.closing_position['lowest'] = self.state.lowest_price
            self.state.closing_position['start_time'] = self.state.trade_start_time
            self.state.closing_position['trigger_price'] = self.state.trigger_price
            self.state.closing_position['close_reason'] = reason
            if 'break_even_points' in pos:
                self.state.closing_position['break_even_points'] = pos['break_even_points']
            
            side = pos['side']
            amt = pos['amount']
            close_side = 'sell' if side == 'long' else 'buy'
            amt_str = self.trader.exchange.amount_to_precision(self.symbol, amt)
            
            logger.info(f"💨 突破策略平仓: {close_side} 数量:{amt_str} 原因:{reason}")
            
            params = {'reduceOnly': True, 'posSide': 'net'}
            await asyncio.to_thread(
                self.trader.exchange.create_market_order,
                self.symbol, close_side, amt_str, None, params
            )
            
            self.state.position = None
            self.state.last_close_time = time.time()
            
        except Exception as e:
            err_str = str(e)
            if "22002" in err_str or "No position" in err_str:
                logger.warning(f"⚠️ [状态同步] 交易所提示无仓位 ({err_str})，强制清空本地持仓状态。")
                self.state.position = None
                self.state.closing_position = None 
                self.state.last_close_time = time.time()
            else:
                logger.error(f"❌ 平仓失败: {e}")
        finally:
            self.state.is_trading = False
            await asyncio.sleep(0.5)

    # ------------------- 辅助计算 -------------------
    def calculate_position_size(self, price):
        if not self.trader: return 0.001
        try:
            position_ratio = float(self.config['risk'].get('position_ratio', 0.1))
            leverage = float(self.config.get('leverage', 10))
            market = self.trader.exchange.market(self.symbol)
            
            amount = calculate_position_size(price, self.state.current_balance, position_ratio, leverage, market)
            
            min_amount = float(market.get('limits', {}).get('amount', {}).get('min', 0.001))
            if amount < min_amount:
                logger.warning(f"⚠️ 计算下单量 {amount} 小于最小限制 {min_amount}，尝试强制使用最小量")
                cost = min_amount * price / leverage
                if self.state.current_balance > cost * 1.05: 
                    return min_amount
                else:
                    logger.error(f"❌ 余额不足以开最小仓位! 需: {cost:.2f}U, 有: {self.state.current_balance:.2f}U")
                    return 0.0 
            
            return amount
        except Exception as e: 
            logger.error(f"仓位计算出错: {e}")
            return 0.001

    def calculate_break_even_points(self, entry_price, position_size, open_fee_usdt):
        slippage_ticks = int(self.config['risk'].get('slippage_ticks', 1))
        return calculate_break_even_points(
            entry_price=entry_price,
            position_size=position_size,
            open_fee_usdt=open_fee_usdt,
            tick_size=self.tick_size,
            slippage_ticks=slippage_ticks
        )
    
    def save_trade_record(self, record):
        self.record_manager.save_record(record)

    # ------------------- 私有WS回调 -------------------
    async def on_private_order(self, order_data):
        try:
            status = order_data.get('status', '')
            if status != 'filled': return

            fill_price = float(order_data.get('priceAvg', 0))
            side = order_data.get('side', '')

            fee = 0.0
            try:
                fee_details = order_data.get('feeDetail', [])
                if fee_details:
                    fee = float(fee_details[0].get('fee', '0'))
                else:
                    fee = float(order_data.get('fee', '0'))
            except Exception as e:
                logger.warning(f"[手续费] 提取失败: {e}")
            actual_fee = abs(fee)

            # 【核心修复】正确解析 reduceOnly
            # Bitget 可能返回 "YES"/"NO" 或者 boolean
            raw_reduce = order_data.get('reduceOnly', 'NO')
            is_close_order = str(raw_reduce).upper() == 'YES' or str(raw_reduce).lower() == 'true'
            
            # 【双重保险】如果本地有仓位，且订单方向与持仓相反，也视为平仓
            # 开多(long) -> 平仓必须是 sell
            # 开空(short) -> 平仓必须是 buy
            if not is_close_order and self.state.position:
                pos_side = self.state.position['side']
                if (pos_side == 'long' and side == 'sell') or \
                   (pos_side == 'short' and side == 'buy'):
                    is_close_order = True
                    # logger.info("⚠️ 根据方向判定为平仓 (reduceOnly未生效)")

            if is_close_order:
                if self.state.closing_position:
                    pos = self.state.closing_position
                    direction = pos['side']
                    entry_price = pos['entry']
                    amount = pos['amount']
                    
                    open_fee = pos.get('fee', 0.0)
                    total_fee = open_fee + actual_fee

                    start_time = pos.get('start_time', time.time())
                    duration = time.time() - start_time
                    
                    if direction == 'long':
                        price_diff = (fill_price - entry_price) * amount
                    else:
                        price_diff = (entry_price - fill_price) * amount
                    net_pnl = price_diff - total_fee

                    # 战报
                    logger.info("========================================")
                    logger.info(f"🏁 [突破策略战报] {'🙂 小赚' if net_pnl>=0 else '😢 亏损'} | 方向: {direction.upper()}")
                    logger.info(f"⏱️ 耗时: {duration:.1f}s | 余额: {self.state.current_balance:.4f} U")
                    logger.info(f"💰 净利: {net_pnl:+.4f} U (价差{price_diff:+.4f} - 费{total_fee:.4f})")
                    logger.info("========================================")

                    record = {
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "symbol": self.symbol,
                        "side": direction,
                        "duration": round(duration, 2),
                        "net_pnl": round(net_pnl, 6),
                        "total_fee": round(total_fee, 6),
                        "entry_price": entry_price,
                        "exit_price": fill_price,
                        "reason": pos.get('close_reason', 'unknown')
                    }
                    self.save_trade_record(record)
                    self.state.trade_pnl_history.append(record)
                    self.update_risk_metrics()
                    self.state.closing_position = None
                else:
                    logger.info(f"🛡️ [系统平仓] 检测到外部平仓: {side} @ {fill_price}")
                    self.state.position = None
                return

            # 开仓处理
            if self.state.position:
                self.state.position['entry'] = fill_price
                self.state.position['fee'] = actual_fee
                
                break_even_points = self.calculate_break_even_points(
                    fill_price, self.state.position['amount'], actual_fee
                )
                self.state.position['break_even_points'] = break_even_points
                
                logger.info(f"✅ 开仓成交确认 | 均价:{fill_price:.5f} | 保本点:{break_even_points:.6f}")
            else:
                # 状态补全 (WS比API快)
                logger.warning(f"⚡ [极速成交] WS推送快于API，补全状态")
                amt = float(order_data.get('size', 0))
                self.state.position = {
                    'side': 'long' if side == 'buy' else 'short',
                    'amount': amt,
                    'entry': fill_price,
                    'fee': actual_fee
                }
                self.state.trade_start_time = time.time()
                sl_ticks = int(self.config['risk']['min_stop_loss_ticks'])
                sl_dist = sl_ticks * self.tick_size
                if side == 'buy':
                    self.state.highest_price = fill_price
                    self.state.dynamic_stop_price = fill_price - sl_dist
                else:
                    self.state.lowest_price = fill_price
                    self.state.dynamic_stop_price = fill_price + sl_dist
                logger.info(f"✅ 状态补全完成: {side} {amt} @ {fill_price}")

        except Exception as e:
            logger.error(f"订单处理异常: {e}")

    async def on_private_position(self, pos_data):
        try:
            total = float(pos_data.get('total', 0))
            if total == 0:
                if self.state.position is not None:
                    logger.warning("⚠️ 检测到仓位已释放，重置本地状态")
                    self.state.position = None
                    self.state.closing_position = None
            else:
                # 中途接管
                if self.state.position is None:
                    if time.time() - self.state.last_close_time < 3.0: return
                    side = pos_data.get('holdSide', '')
                    entry = float(pos_data.get('openPriceAvg', 0))
                    logger.warning(f"🔄 检测到未知持仓 (启动接管): {side} {total} @ {entry}")
                    
                    self.state.position = {'side': side, 'amount': total, 'entry': entry, 'fee': 0.0}
                    sl_ticks = int(self.config['risk']['min_stop_loss_ticks'])
                    sl_dist = sl_ticks * self.tick_size
                    
                    if side == 'long':
                        self.state.highest_price = entry
                        self.state.dynamic_stop_price = entry - sl_dist
                    else:
                        self.state.lowest_price = entry
                        self.state.dynamic_stop_price = entry + sl_dist
                    logger.info(f"✅ 已接管持仓，当前止损线: {self.state.dynamic_stop_price}")
        except Exception as e:
            logger.error(f"仓位推送处理出错: {e}")

    async def on_private_account(self, account_data):
        try:
            coin_name = account_data.get('marginCoin', '')
            if coin_name != 'USDT': return

            available = float(account_data.get('available', 0))
            old_balance = self.state.current_balance
            self.state.current_balance = available
            
            if abs(old_balance - available) > 0.0001:
                logger.info(f"💰 [资金流] USDT余额更新: {old_balance:.4f} -> {available:.4f}")
                self.update_risk_metrics()
        except Exception as e:
            logger.error(f"账户余额处理异常: {e}")

    def shutdown(self):
        
        
        # 【核心修复】第一时间锁死策略，防止“回光返照”开单
        self.state.is_stopping = True
        
        
        logger.info("🚨 正在停止突破策略...")
        force_close = self.config.get('force_close_on_exit', True)
        
        if not force_close:
            logger.info("🛑 策略已停止 (持仓保留)")
            return

        logger.warning("⚠️ 配置要求退出时强平所有持仓...")
        if not self.trader: return
        
        try:
            positions = self.trader.exchange.fetch_positions([self.symbol])
            for pos in positions:
                amt = float(pos['contracts'])
                if amt > 0:
                    amt_str = self.trader.exchange.amount_to_precision(self.symbol, amt)
                    side = pos['side'] 
                    close_side = 'sell' if side == 'long' else 'buy'
                    self.trader.exchange.create_market_order(
                        self.symbol, close_side, amt_str, None, 
                        {'reduceOnly': True, 'posSide': 'net'}
                    )
                    logger.info(f"✅ 强平 {side} {amt_str} 成功")
        except Exception as e:
            logger.error(f"强平出错: {e}")

    # ------------------- 启动逻辑 -------------------
    async def run(self):
        self.sync_initialize()
        logger.info(f">>> 突破策略(BreakoutStrategy)启动: {self.symbol} | 周期: {self.target_period}")
        
        await asyncio.gather(
            self.connect_public_ws(
                self.product_type, 
                self.ws_symbol, 
                candle_channels=[self.target_period] 
            ),
            self.connect_private_ws(self.config, self.product_type)
        )

# ================= 主函数 =================
if __name__ == "__main__":
    s = BreakoutStrategy()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(s.run())
    except KeyboardInterrupt:
        print("\n\n")
        logger.info("🛑 收到停止指令 (Ctrl+C)")
        s.shutdown()
        loop.run_until_complete(asyncio.sleep(1.0))
        
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        
        try:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception: pass
            
        print("Safe Exit")
    except Exception as e:
        logger.error(f"❌ 异常崩溃: {e}")
        s.shutdown()
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
        except Exception: pass