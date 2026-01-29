
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
import math
from collections import deque
from datetime import datetime
from typing import Dict, Optional, Union

# ==================== 基础导入 ====================
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
from .base_bitget_ws import BaseBitgetWsClient
from .proxy_utils import set_system_proxy
from .trade_record_utils import TradeRecordManager
from .risk_control_v2 import GlobalRiskController
from cctx_utils import ExchangeTrader

# 代理设置
set_system_proxy(enable=True)
os.environ["http_proxy"] = "http://127.0.0.1:7890"
os.environ["https_proxy"] = "http://127.0.0.1:7890"

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Martingale_Strategy")

# 安全转换函数
def safe_float(value: Union[str, int, float, None], default: float = 0.0) -> float:
    if value is None: return default
    try: return float(value)
    except: return default

def safe_int(value: Union[str, int, float, None], default: int = 0) -> int:
    if value is None: return default
    try: return int(value)
    except: return default

# 状态管理
class MartingaleState:
    def __init__(self):
        # 核心状态
        self.position = None
        self.closing_position = None
        self.last_close_time = 0  # 平仓时间戳（防御盾）
        self.is_trading = False
        
        # 市场状态
        self.current_price = 0.0
        self.last_price = 0.0
        self.tick_history = deque(maxlen=1000)
        self.daily_loss = 0.0
        self.daily_profit = 0.0
        self.today_date = datetime.now().date()
        
        # 双向持仓
        self.long_positions = []  # 存储每个仓位的详细信息
        self.short_positions = []  # 存储每个仓位的详细信息
        self.total_long_amount = 0.0
        self.total_short_amount = 0.0
        self.avg_long_price = 0.0
        self.avg_short_price = 0.0
        
        # 计数器
        self.long_order_count = 0
        self.short_order_count = 0
        self.trend_order_count = 0
        
        # 动态参数
        self.current_opposite_spread = 0.0
        self.current_opposite_profit = 0.0
        self.current_trend_spread = 0.0
        
        self.trading_paused = False
        
        # 精度
        self.tick_size = 0.0
        self.amount_precision = 1
        self.min_amount = 1
        self.min_notional = 5
        self.notional_buffer = 0.01
        
        # 风控
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
        
        # 合约基础
        self.contract_base = {
            "dynamic_tick_size": True,
            "manual_tick_size": 0.01,
            "points_to_tick": 100.0
        }
        
        self.position_mode = "dual" # 默认为双向，因为我们强制全仓对冲
        self.pos_side = "net"
        
        self.position_uncertain = False
        self.last_add_position_time = 0  # 上次加仓时间

# ==================== 策略主类 ====================
class MartingaleStrategy(BaseBitgetWsClient):
    def __init__(self, config_path='martin.json'):
        super().__init__()

        # 加载配置
        if not os.path.exists(config_path):
            base_path = os.path.dirname(os.path.abspath(__file__))
            # [热更新] 保存配置文件路径到 self.config_path
            self.config_path = os.path.join(base_path, 'martin.json')
        else:
            self.config_path = config_path # [热更新]

        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        # [热更新] 初始化文件修改时间记录
        try:
            self.last_config_mtime = os.path.getmtime(self.config_path)
        except:
            self.last_config_mtime = 0
        self.last_check_config_time = 0

        self.symbol = self.config['symbol']
        self.ws_symbol = self.symbol.split(':')[0].replace('/', '')
        self.product_type = 'USDT-FUTURES'
        self.leverage = safe_float(self.config.get('leverage'), 10.0)

        self.state = MartingaleState()

        # 参数加载
        self.contract_base = self.config.get('contract_base', {})
        self.state.contract_base['dynamic_tick_size'] = self.contract_base.get('dynamic_tick_size', True)
        self.state.contract_base['manual_tick_size'] = self.contract_base.get('manual_tick_size', 0.01)
        self.state.contract_base['points_to_tick'] = self.contract_base.get('points_to_tick', 100.0)

        self.basic = self.config.get('basic_trading_settings', {})
        self.order_params = self.config.get('order_parameters', {})
        self.adding_rules = self.config.get('adding_rules', {})
        self.psl = self.config.get('profit_stop_loss_settings', {})
        self.close_rules = self.config.get('close_rules', {})
        self.risk = self.config.get('risk_supplement', {})
        self.risk_control = self.config.get('risk_control', {})

        # 正确做法：只从配置读取，如果没有就是None
        self.state.current_opposite_spread = self.adding_rules.get('opposite_add_spread')  # ✅ 正确
        self.state.current_opposite_profit = self.psl.get('opposite_profit_ticks')  # ✅ 正确
        self.state.current_trend_spread = self.adding_rules.get('trend_add_spread')  # ✅ 正确

        # 记录管理器
        self.history_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'martingale_history.json')
        self.record_manager = TradeRecordManager(record_file=self.history_file, max_records=1000)
        
        self.is_sandbox = self.config.get('sandbox', False)
        
        if self.is_sandbox:
            self.public_ws_url = "wss://wspap.bitget.com/v2/ws/public"
            self.private_ws_url = "wss://wspap.bitget.com/v2/ws/private"
            logger.info("🔧 [环境切换] 已切换至 Bitget 模拟盘 WS 地址")

        # 交易所初始化
        self.trader = None
        try:
            self.trader = ExchangeTrader(
                exchange_id=self.config.get('exchange_id', 'bitget'),
                api_key=self.config.get('api', {}).get('apiKey', ''),
                secret=self.config.get('api', {}).get('secret', ''),
                passphrase=self.config.get('api', {}).get('password', ''), 
                sandbox=self.is_sandbox
            )
            # 生产环境代理 (如不需要请注释)
            self.trader.exchange.proxies = {'http': "http://127.0.0.1:7890", 'https': "http://127.0.0.1:7890"}
            self.trader.exchange.load_markets()
            
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
            logger.error(f"Trader初始化失败: {e}")

        # 风控初始化
        self.risk_controller = GlobalRiskController(self.risk_control)
        
        # 频率控制
        self.order_rate_limit = 10
        self.order_timestamps = deque(maxlen=self.order_rate_limit)
        self.last_order_time = 0.0
        self.order_cooldown = safe_float(self.config.get('order_cooldown_seconds', 20.0))
        self.add_position_cooldown = 2.0  # 加仓冷却时间，防止过快连续加仓
          
        # 在__init__方法末尾添加
        logger.info("=" * 60)
        logger.info("📊 策略参数验证")
        
        # 安全显示参数值，如果为None则显示"未配置"
        opposite_add_spread = self.state.current_opposite_spread
        trend_add_spread = self.state.current_trend_spread
        opposite_profit = self.state.current_opposite_profit
        trend_profit = self.psl.get('trend_profit_ticks')
        
        # 格式化显示
        def format_param(param):
            if param is None:
                return "未配置"
            try:
                value = float(param)
                return f"{value} ticks = ${value * 0.1:.1f}"
            except:
                return f"无效值: {param}"
        
        logger.info(f"   逆势加仓: {format_param(opposite_add_spread)}")
        logger.info(f"   顺势加仓: {format_param(trend_add_spread)}")
        logger.info(f"   逆势止盈: {format_param(opposite_profit)}")
        logger.info(f"   顺势止盈: {format_param(trend_profit)}")
        logger.info("=" * 60)

    def get_sign(self, timestamp):
        """签名生成"""
        api_secret = self.config.get('api', {}).get('secret', '')
        message = f"{timestamp}GET/user/verify"
        mac = hmac.new(bytes(api_secret, encoding='utf-8'), bytes(message, encoding='utf-8'), digestmod=hashlib.sha256)
        return base64.b64encode(mac.digest()).decode('utf-8')

    # [热更新] 检查配置并重载
    def _check_and_reload_config(self):
        """检查并热重载配置，不重启程序"""
        try:
            # 5秒检查一次
            if time.time() - self.last_check_config_time < 5.0:
                return
            self.last_check_config_time = time.time()

            if not os.path.exists(self.config_path): return
            
            # 获取当前文件修改时间
            mtime = os.path.getmtime(self.config_path)
            if mtime <= self.last_config_mtime:
                return

            # 加载新配置
            logger.info(f"🔄 检测到配置变动，正在热重载: {self.config_path}")
            with open(self.config_path, 'r', encoding='utf-8') as f:
                new_config = json.load(f)

            # 更新内存中的配置字典
            self.config = new_config
            self.basic = new_config.get('basic_trading_settings', {})
            self.order_params = new_config.get('order_parameters', {})
            self.adding_rules = new_config.get('adding_rules', {})
            self.psl = new_config.get('profit_stop_loss_settings', {})
            self.close_rules = new_config.get('close_rules', {})
            self.risk = new_config.get('risk_supplement', {})
            self.risk_control = new_config.get('risk_control', {})
            
            # 更新风控配置
            if self.risk_controller:
                self.risk_controller.config = self.risk_control 

            # 更新时间戳
            self.last_config_mtime = mtime
            logger.info("✅ 配置热重载完成！新参数已生效。")

        except Exception as e:
            logger.error(f"❌ 热重载配置失败: {e}")
            
    # ===== 修正：严格按交易所规则计算最小数量 =====
    def calculate_min_amount_by_notional(self, price):
        """
        计算满足交易所「名义价值最小要求」的最小数量
        规则：
        1. 价格≤0时，返回交易所的min_amount
        2. 先算满足min_notional的数量 = min_notional / price
        3. 按amount_precision向上取整（保证符合精度）
        4. 最终取「交易所min_amount」和「计算值」的最大值（满足双重规则）
        """
        if price <= 0:
            return self.state.min_amount

        # 修正1：去掉1.02，严格用交易所的min_notional
        amt_needed_for_notional = self.state.min_notional / price

        # 按精度向上取整（保证数量是precision的整数倍）
        if self.state.amount_precision > 0:
            amt_needed_for_notional = math.ceil(amt_needed_for_notional / self.state.amount_precision) * self.state.amount_precision

        # 最终最小数量：同时满足min_amount和min_notional的要求
        min_amt = max(self.state.min_amount, amt_needed_for_notional)

        return min_amt

    # ===== 修正：基于正确的最小数量计算下单量 =====
    def calculate_order_amount(self, order_index, price, side):
        """
        计算马丁加仓的下单数量
        核心逻辑：
        1. 校验价格有效性
        2. 计算已用保证金，判断是否超上限
        3. 计算本次可使用的保证金（马丁系数×初始金额，不超过剩余保证金）
        4. 换算成基础数量，保证不低于交易所最小数量
        5. 按精度处理后返回
        """
        if price <= 0:
            return 0.0

        # 读取参数（简化写法，和原逻辑一致）
        initial_usdt = self.order_params.get("initial_usdt_amount", 10.0)
        max_total_margin = self.order_params.get("max_usdt_amount", 1000.0)
        add_multiplier = self.order_params.get("add_multiplier", 1.5)

        # 读取当前持仓
        current_holding = self.state.total_long_amount if side == 'long' else self.state.total_short_amount

        # 已用保证金 = 持仓数量 × 价格 / 杠杆
        current_margin_used = (current_holding * price) / self.leverage
        if current_margin_used >= max_total_margin:
            return 0.0  # 保证金超上限，不下单

        # 剩余可使用的保证金
        remaining_margin = max_total_margin - current_margin_used
        # 马丁加仓的保证金（初始×系数^层数）
        next_margin = initial_usdt * (add_multiplier ** order_index)
        # 本次实际可用保证金（取加仓金额和剩余保证金的较小值）
        final_margin = min(next_margin, remaining_margin)

        # 保证金太小（<2U），不下单
        if final_margin < 2.0:
            return 0.0

        # 基础数量 = 保证金 × 杠杆 / 价格
        base_amount = (final_margin * self.leverage) / price

        # 最小数量：必须满足交易所规则
        min_amt = self.calculate_min_amount_by_notional(price)
        # 最终数量：不低于最小数量
        final_amt = max(base_amount, min_amt)

        # 精度处理（消除浮点数误差，保证是precision的整数倍）
        precision = self.state.amount_precision
        if precision > 0:
            scale = int(round(1 / precision))
            final_amt = int(final_amt * scale) / scale

        # 最终校验
        return final_amt if final_amt > 0 else 0.0

    # ------------------ 核心初始化逻辑 ------------------
    def sync_initialize(self):
        """初始化检查"""
        logger.info(">>> 账户环境核验...")
        if not self.trader: sys.exit(1)
        
        try:
            self.trader.exchange.load_markets()
            market = self.trader.exchange.market(self.symbol)
            
            # price 精度
            self.state.tick_size = float(market['precision']['price'])

            # amount 精度
            self.state.amount_precision = float(market['precision']['amount'])

            # 交易所最小数量
            self.state.min_amount = float(market['limits']['amount']['min'])

            # 最小名义价值
            self.state.min_notional = float(market['limits']['cost']['min'])

            logger.info(
                f"📏 精度注入完成 | tick价格精度={self.state.tick_size} "
                f"| 最小购买份数={self.state.amount_precision} "
                f"| 交易所最小数量={self.state.min_amount} "
                f"| 最小名义价值={self.state.min_notional}"
            )
            
            try:
                self.trader.exchange.set_position_mode(True, self.symbol)
                logger.info("✅ 已设置为双向持仓模式")
            except Exception: pass
            
            # 1. 检查逐仓
            positions = self.trader.exchange.fetch_positions([self.symbol])
            has_pos = False
            for pos in positions:
                if float(pos.get('contracts', 0)) > 0:
                    has_pos = True
                    mode = pos.get('info', {}).get('marginMode', '').lower()
                    if mode == 'isolated':
                        logger.critical("🚨 严重错误：账户持有【逐仓】持仓！请手动平仓并切换为全仓！")
                        sys.exit(1)

            # 2. 强制全仓
            if not has_pos:
                try: self.trader.exchange.set_margin_mode('crossed', self.symbol)
                except: pass

            # 3. 设置杠杆
            try: self.trader.exchange.set_leverage(self.leverage, self.symbol)
            except: pass

            # 4. 余额
            bal = self.trader.exchange.fetch_balance({'type': 'swap'})
            usdt = safe_float(bal.get('USDT', {}).get('free'), 0.0)
            self.state.daily_initial_balance = usdt
            logger.info(f"✅ 环境核验通过 | 余额: {usdt:.2f}U")
            
            # 5. 初始同步
            self._fetch_and_log_current_positions()

        except SystemExit: raise
        except Exception as e:
            logger.error(f"初始化失败: {e}")
            sys.exit(1)

    # ------------------ 绝对真理同步 ------------------
    def _fetch_and_log_current_positions(self):
        """强制同步交易所数据"""
        try:
            positions = self.trader.exchange.fetch_positions([self.symbol])
            real_long, real_short = None, None
            
            for pos in positions:
                side = pos.get('side', '').lower()
                amt = float(pos.get('contracts', 0))
                entry = float(pos.get('entryPrice', 0))
                if amt > 0:
                    if side == 'long': 
                        real_long = {'amount': amt, 'entry': entry}
                    elif side == 'short': 
                        real_short = {'amount': amt, 'entry': entry}

            if real_long:
                # 重置并重新构建仓位列表
                self.state.long_positions = [{'amount': real_long['amount'], 'entry_price': real_long['entry']}]
                self.state.total_long_amount = real_long['amount']
                self.state.avg_long_price = real_long['entry']
                self.state.long_order_count = 1
            else:
                self.state.long_positions = []
                self.state.total_long_amount = 0.0
                self.state.avg_long_price = 0.0
                self.state.long_order_count = 0

            if real_short:
                self.state.short_positions = [{'amount': real_short['amount'], 'entry_price': real_short['entry']}]
                self.state.total_short_amount = real_short['amount']
                self.state.avg_short_price = real_short['entry']
                self.state.short_order_count = 1
            else:
                self.state.short_positions = []
                self.state.total_short_amount = 0.0
                self.state.avg_short_price = 0.0
                self.state.short_order_count = 0
                
            # 🔓 小保险丝解除：REST 已确认真实仓位
            self.state.position_uncertain = False
                
        except Exception as e:
            logger.error(f"同步持仓失败: {e}")

    # ==================== 【新核心】浮亏风控 ====================
    async def check_floating_loss(self):
        """
        [核心风控] 实时计算浮动亏损。
        修正：只计算当前持仓的未实现盈亏，不包含 daily_loss
        """
        if not self.trader: return

        # 1. 获取配置
        loss_percent_limit = safe_float(self.close_rules.get('total_loss_percent'), 30.0)
        initial_balance = self.state.daily_initial_balance
        if loss_percent_limit <= 0 or initial_balance <= 0: return

        # 2. 计算浮盈亏
        current_floating_pnl = 0.0
        current_price = self.state.current_price
        if current_price <= 0: return

        # 多单浮盈亏
        if self.state.long_positions and self.state.total_long_amount > 0:
            current_floating_pnl += (current_price - self.state.avg_long_price) * self.state.total_long_amount
            
        # 空单浮盈亏
        if self.state.short_positions and self.state.total_short_amount > 0:
            current_floating_pnl += (self.state.avg_short_price - current_price) * self.state.total_short_amount

        # 3. 如果是盈利的，或者亏损很小，直接跳过
        if current_floating_pnl >= 0: return

        # 4. 判断是否触发
        loss_threshold = initial_balance * (loss_percent_limit / 100.0)
        
        if abs(current_floating_pnl) >= loss_threshold:
            logger.critical("="*40)
            logger.critical(f"🚨 [风控熔断] 触发浮亏止损！")
            logger.critical(f"📉 当前浮亏: {current_floating_pnl:.2f} U")
            logger.critical(f"💥 阈值: {loss_percent_limit}% ({loss_threshold:.2f} U)")
            logger.critical("🛑 正在强制清仓...")
            logger.critical("="*40)
            
            if self.state.long_positions: await self.close_position('long', '浮亏熔断')
            if self.state.short_positions: await self.close_position('short', '浮亏熔断')
            
            self.state.trading_paused = True

    # ==================== 【新核心】策略逻辑引擎 ====================
    async def process_strategy_logic(self):
        """
        整合后的策略主逻辑：
        1. 空仓直接补单 (Rule 7)
        2. 持仓判断加仓/止盈 (Rule 4, 5, 8)
        """
        if self.state.trading_paused: return
        price = self.state.current_price
        if price <= 0: return

        # 分别处理多空
        await self.process_single_side('long', price)
        await self.process_single_side('short', price)
        
        
        
    def validate_position_state(self, side):
        """验证仓位状态一致性"""
        positions = self.state.long_positions if side == 'long' else self.state.short_positions
        total_amt = self.state.total_long_amount if side == 'long' else self.state.total_short_amount

        # 情况1：仓位数量为0，positions应该为空
        if total_amt == 0:
            if positions and len(positions) > 0:
                logger.error(f"❌ {side}仓位数量为0但positions非空！清空positions")
                if side == 'long':
                    self.state.long_positions = []
                else:
                    self.state.short_positions = []
                return False
            return True

        # 情况2：仓位数量>0，positions不应该为空
        if not positions or len(positions) == 0:
            logger.error(f"❌ {side}仓位数量>0但positions为空！需要同步")
            return False

        # 情况3：positions中的总数量应该等于total_amt
        positions_total = sum(p['amount'] for p in positions)
        if abs(positions_total - total_amt) > 0.0001:
            logger.error(f"❌ {side}仓位数量不一致！positions={positions_total}, total={total_amt}")
            return False

        return True
        
    async def process_single_side(self, side, price):
        """
        修复核心问题：正确处理仓位状态，防止无限补首单
        """
        # 🔒 仓位状态不确定时，禁止操作
        if self.state.position_uncertain:
            logger.debug(f'仓位状态不确定，跳过{side}侧处理')
            return

        # 🕒 加仓冷却时间检查
        current_time = time.time()
        if current_time - self.state.last_add_position_time < self.add_position_cooldown:
            return

        # 获取仓位信息
        positions = self.state.long_positions if side == 'long' else self.state.short_positions
        total_amt = self.state.total_long_amount if side == 'long' else self.state.total_short_amount
        avg_price = self.state.avg_long_price if side == 'long' else self.state.avg_short_price

        # 🔍 新增：仓位状态一致性检查（修复核心问题）
        if not self.validate_position_state(side):
            logger.warning(f"⚠️ {side}仓位状态不一致，强制同步并跳过")
            await asyncio.to_thread(self._fetch_and_log_current_positions)
            return

        # --- A. 空仓补首单（只在确实空仓时执行）---
        if total_amt <= 0 or (not positions or len(positions) == 0):
            # 🚨 关键修复：空仓补首单需要严格的冷却检查
            if current_time - self.last_order_time < 3.0:  # 延长冷却到3秒
                return

            # 确保不是刚刚平仓
            if current_time - self.state.last_close_time < 2.0:
                return

            logger.info(f"🔄 {side} 空仓状态，准备补首单")
            amt = self.calculate_order_amount(0, price, side)
            if amt > 0:
                raw_side = 'buy' if side == 'long' else 'sell'
                await self.execute_order(raw_side, amt)
            return

        # --- B. 获取上一次成交价和持仓均价 ---
        try:
            # 🚨 修复：确保positions有数据
            if not positions or len(positions) == 0:
                logger.warning(f"⚠️ {side} positions列表为空，无法获取上次成交价")
                return
            last_entry = positions[-1]['entry_price']
        except (IndexError, KeyError) as e:
            logger.error(f"❌ 获取{side}上次成交价失败: {e}")
            return

        # 计算两种价差（Tick）
        if side == 'long':
            diff_vs_last = (price - last_entry) / self.state.tick_size
            diff_vs_avg = (price - avg_price) / self.state.tick_size
        else:
            diff_vs_last = (last_entry - price) / self.state.tick_size
            diff_vs_avg = (avg_price - price) / self.state.tick_size

        # 当前层数
        layer = len(positions) - 1
        logger.debug(f"🔍 {side} 状态检查 | 层数:{layer} | 持仓:{total_amt} | 均价:{avg_price} | 上次:{last_entry}")

        # ============================================================
        # 🔥 修正后的逻辑：先判断止盈，再判断加仓
        # ============================================================

        # --- D. 止盈逻辑 ---
        try:
            trend_profit_ticks = safe_float(self.psl.get('trend_profit_ticks'))
            trend_profit_decrement_raw = self.psl.get('trend_profit_decrement')
            trend_profit_min_raw = self.psl.get('trend_profit_min')

            opposite_profit_ticks = safe_float(self.psl.get('opposite_profit_ticks'))
            opposite_profit_decrement_raw = self.psl.get('opposite_profit_decrement')
            opposite_profit_min_raw = self.psl.get('opposite_profit_min')
        except Exception as e:
            logger.error(f"❌ 止盈参数读取失败: {e}")
            return

        # 🚨 修复：检查止盈参数有效性
        can_check_tp = True
        if diff_vs_last > 0:  # 顺势止盈
            if trend_profit_ticks is None or trend_profit_ticks <= 0:
                can_check_tp = False
        else:  # 逆势止盈
            if opposite_profit_ticks is None or opposite_profit_ticks <= 0:
                can_check_tp = False

        if can_check_tp:
            if diff_vs_last > 0:  # 相对于上次成交价盈利
                target_ticks = trend_profit_ticks
                if trend_profit_decrement_raw is not None:
                    trend_profit_decrement = safe_float(trend_profit_decrement_raw)
                    target_ticks = max(0, target_ticks - (layer * trend_profit_decrement))
                if trend_profit_min_raw is not None:
                    trend_profit_min = safe_float(trend_profit_min_raw)
                    target_ticks = max(trend_profit_min, target_ticks)
                tp_type = "顺势大止盈"
            else:  # 相对于上次成交价亏损
                target_ticks = opposite_profit_ticks
                if opposite_profit_decrement_raw is not None:
                    opposite_profit_decrement = safe_float(opposite_profit_decrement_raw)
                    target_ticks = max(0, target_ticks - (layer * opposite_profit_decrement))
                if opposite_profit_min_raw is not None:
                    opposite_profit_min = safe_float(opposite_profit_min_raw)
                    target_ticks = max(opposite_profit_min, target_ticks)
                tp_type = "逆势小止盈"

            # 判断是否止盈（使用相对于持仓均价的价差）
            if diff_vs_avg >= target_ticks:
                logger.info(f"💰 {side} {tp_type} | 持仓均价浮盈Tick:{diff_vs_avg:.0f} >= {target_ticks}")
                await self.close_position(side, tp_type)
                return

        # --- C. 加仓逻辑 ---
        # 检查是否达到最大保证金
        max_margin_raw = self.order_params.get('max_usdt_amount')
        if max_margin_raw is None:
            logger.error("❌ max_usdt_amount 配置缺失，跳过加仓判断")
            return

        max_margin = safe_float(max_margin_raw)
        if max_margin <= 0:
            logger.error(f"❌ max_usdt_amount 配置错误（{max_margin}），跳过加仓判断")
            return

        margin_used = (total_amt * price) / self.leverage
        if margin_used >= max_margin:
            logger.info(f"⛔ {side} 保证金已达上限: {margin_used:.2f}/{max_margin:.2f}U")
            return

        # 读取加仓参数
        try:
            trend_add_spread_raw = self.adding_rules.get('trend_add_spread')
            trend_spread_decrement_raw = self.adding_rules.get('trend_spread_decrement')
            trend_spread_min_raw = self.adding_rules.get('trend_spread_min')
            enable_trend_add = self.adding_rules.get('enable_trend_add', True)

            opposite_add_spread_raw = self.adding_rules.get('opposite_add_spread')
            opposite_spread_decrement_raw = self.adding_rules.get('opposite_spread_decrement')
            opposite_spread_min_raw = self.adding_rules.get('opposite_spread_min')
        except Exception as e:
            logger.error(f"❌ 加仓参数读取失败: {e}")
            return

        # 1. 顺势加仓（只在上次成交价基础上盈利时触发）
        if diff_vs_last > 0 and enable_trend_add and trend_add_spread_raw is not None:
            trend_add_spread = safe_float(trend_add_spread_raw)

            if trend_add_spread <= 0:
                logger.warning(f"⚠️ trend_add_spread 配置错误（{trend_add_spread}），跳过顺势加仓")
            else:
                trend_gap = trend_add_spread

                # 🚨 修复递减逻辑：递减后不能低于最小值
                if trend_spread_decrement_raw is not None:
                    trend_spread_decrement = safe_float(trend_spread_decrement_raw)
                    trend_gap = trend_gap - (layer * trend_spread_decrement)

                # 应用最小值限制
                if trend_spread_min_raw is not None:
                    trend_spread_min = safe_float(trend_spread_min_raw)
                    trend_gap = max(trend_spread_min, trend_gap)
                else:
                    # 如果没有最小值，确保至少有10个ticks
                    trend_gap = max(10, trend_gap)

                # 确保趋势加仓至少有合理的利润空间
                trend_gap = max(20, trend_gap)  # 至少20个ticks（2美元）

                logger.debug(f"🔍 {side} 顺势加仓检查 | 盈利Tick:{diff_vs_last:.0f} | 所需Tick:{trend_gap:.0f} | 层数:{layer}")

                if diff_vs_last >= trend_gap:
                    logger.info(f"🚀 {side} 顺势加仓 | 相对于上次成交价盈利Tick:{diff_vs_last:.0f} >= {trend_gap}")
                    amt = self.calculate_order_amount(layer + 1, price, side)
                    if amt > 0:
                        raw_side = 'buy' if side == 'long' else 'sell'
                        await self.execute_order(raw_side, amt)
                        self.state.last_add_position_time = time.time()
                    return

        # 2. 逆势补仓（只在上次成交价基础上亏损时触发）
        if diff_vs_last < 0 and opposite_add_spread_raw is not None:
            opposite_add_spread = safe_float(opposite_add_spread_raw)

            if opposite_add_spread <= 0:
                logger.warning(f"⚠️ opposite_add_spread 配置错误（{opposite_add_spread}），跳过逆势加仓")
            else:
                loss_ticks = abs(diff_vs_last)
                oppo_gap = opposite_add_spread

                if opposite_spread_decrement_raw is not None:
                    opposite_spread_decrement = safe_float(opposite_spread_decrement_raw)
                    oppo_gap = oppo_gap - (layer * opposite_spread_decrement)

                if opposite_spread_min_raw is not None:
                    opposite_spread_min = safe_float(opposite_spread_min_raw)
                    oppo_gap = max(opposite_spread_min, oppo_gap)
                else:
                    oppo_gap = max(10, oppo_gap)

                # 确保逆势加仓至少有合理的亏损空间
                oppo_gap = max(20, oppo_gap)  # 至少20个ticks

                logger.debug(f"🔍 {side} 逆势加仓检查 | 亏损Tick:{loss_ticks:.0f} | 所需Tick:{oppo_gap:.0f} | 层数:{layer}")

                if loss_ticks >= oppo_gap:
                    logger.info(f"🛡️ {side} 逆势补仓 | 相对于上次成交价亏损Tick:{loss_ticks:.0f} >= {oppo_gap}")
                    amt = self.calculate_order_amount(layer + 1, price, side)
                    if amt > 0:
                        raw_side = 'buy' if side == 'long' else 'sell'
                        await self.execute_order(raw_side, amt)
                        self.state.last_add_position_time = time.time()
                    return
    # ==================== 核心交易执行 ====================
    # 当前代码的问题：只更新了average_price，没有正确维护positions列表
    # 修复代码：
    '''
    async def execute_order(self, side, amount):
        """执行开仓 (直连 Bitget API)"""

        if self.state.position_uncertain:
            logger.error("❌ 仓位未确认，禁止 execute_order")
            return

        current_time = time.time()
        # 简单的频率限制
        if self.order_timestamps and len(self.order_timestamps) >= self.order_rate_limit:
            if current_time - self.order_timestamps[0] < 1.0: await asyncio.sleep(1.0)
        self.order_timestamps.append(current_time)

        if self.state.is_trading: return
        self.state.is_trading = True

        try:
            req_side = side 
            req_pos_side = 'long' if side == 'buy' else 'short'

            amt_str = self.trader.exchange.amount_to_precision(self.symbol, amount)
            clean_symbol = self.symbol.split(':')[0].replace('/', '')

            request = {
                'symbol': clean_symbol,
                'productType': self.product_type,
                'marginMode': 'crossed',
                'marginCoin': 'USDT',
                'size': amt_str,
                'side': req_side,
                'tradeSide': 'open',
                'orderType': 'market',
                'force': 'gtc',
                'posSide': req_pos_side,
                'clientOid': f"m_open_{int(time.time()*1000)}",
            }

            logger.info(f"📥 [原生开仓] {json.dumps(request)}")

            response = await asyncio.to_thread(
                self.trader.exchange.private_mix_post_v2_mix_order_place_order, 
                request
            )

            if response.get('code') != '00000':
                raise Exception(f"Bitget Error: {response}")

            self.last_order_time = current_time
            logger.info(f"✅ 开仓成功 (ID: {response['data'].get('orderId')})")

            # 🔒 小保险丝：下单成功后，直到再次看到真实仓位前，不允许继续加仓
            self.state.position_uncertain = True

            # ⚡️ 乐观更新：不等WS推送，直接写入本地状态
            fill_price = self.state.current_price 
            entry_amount = float(amt_str)
            entry = {'amount': entry_amount, 'entry_price': fill_price}

            if side == 'buy':
                # 计算新的加权均价
                if self.state.total_long_amount > 0:
                    old_total_value = self.state.total_long_amount * self.state.avg_long_price
                    new_total_value = entry_amount * fill_price
                    new_total_amount = self.state.total_long_amount + entry_amount
                    self.state.avg_long_price = (old_total_value + new_total_value) / new_total_amount
                else:
                    self.state.avg_long_price = fill_price

                # 添加到仓位列表
                self.state.long_positions.append(entry)
                self.state.total_long_amount += entry_amount

            else:  # side == 'sell'
                # 计算新的加权均价
                if self.state.total_short_amount > 0:
                    old_total_value = self.state.total_short_amount * self.state.avg_short_price
                    new_total_value = entry_amount * fill_price
                    new_total_amount = self.state.total_short_amount + entry_amount
                    self.state.avg_short_price = (old_total_value + new_total_value) / new_total_amount
                else:
                    self.state.avg_short_price = fill_price

                # 添加到仓位列表
                self.state.short_positions.append(entry)
                self.state.total_short_amount += entry_amount

            logger.info(f"📊 乐观更新完成 | 多单仓位数:{len(self.state.long_positions)} | 空单仓位数:{len(self.state.short_positions)}")

        except Exception as e:
            logger.error(f"❌ 开仓失败: {e}")
        finally:
            self.state.is_trading = False
    '''
    
    
    async def execute_order(self, side, amount):
        """执行开仓 (直连 Bitget API)"""

        if self.state.position_uncertain:
            logger.error("❌ 仓位未确认，禁止 execute_order")
            return

        current_time = time.time()
        # 简单的频率限制
        if self.order_timestamps and len(self.order_timestamps) >= self.order_rate_limit:
            if current_time - self.order_timestamps[0] < 1.0: await asyncio.sleep(1.0)
        self.order_timestamps.append(current_time)

        if self.state.is_trading: return
        self.state.is_trading = True

        try:
            req_side = side 
            req_pos_side = 'long' if side == 'buy' else 'short'

            amt_str = self.trader.exchange.amount_to_precision(self.symbol, amount)
            clean_symbol = self.symbol.split(':')[0].replace('/', '')

            request = {
                'symbol': clean_symbol,
                'productType': self.product_type,
                'marginMode': 'crossed',
                'marginCoin': 'USDT',
                'size': amt_str,
                'side': req_side,
                'tradeSide': 'open',
                'orderType': 'market',
                'force': 'gtc',
                'posSide': req_pos_side,
                'clientOid': f"m_open_{int(time.time()*1000)}",
            }

            logger.info(f"📥 [原生开仓] {json.dumps(request)}")

            response = await asyncio.to_thread(
                self.trader.exchange.private_mix_post_v2_mix_order_place_order, 
                request
            )

            if response.get('code') != '00000':
                raise Exception(f"Bitget Error: {response}")

            self.last_order_time = current_time
            logger.info(f"✅ 开仓成功 (ID: {response['data'].get('orderId')})")

            # 🔒 小保险丝：下单成功后，直到再次看到真实仓位前，不允许继续加仓
            self.state.position_uncertain = True

            # ⚡️ 乐观更新：不等WS推送，直接写入本地状态
            fill_price = self.state.current_price 
            entry_amount = float(amt_str)
            entry = {'amount': entry_amount, 'entry_price': fill_price}

            if side == 'buy':
                # 记录更新前状态
                old_total = self.state.total_long_amount
                old_avg = self.state.avg_long_price
                old_positions_count = len(self.state.long_positions)

                # 计算新的加权均价
                if self.state.total_long_amount > 0:
                    old_total_value = self.state.total_long_amount * self.state.avg_long_price
                    new_total_value = entry_amount * fill_price
                    new_total_amount = self.state.total_long_amount + entry_amount
                    self.state.avg_long_price = (old_total_value + new_total_value) / new_total_amount
                else:
                    self.state.avg_long_price = fill_price

                # 添加到仓位列表
                self.state.long_positions.append(entry)
                self.state.total_long_amount += entry_amount

                # 记录更新后状态
                logger.info(f"📈 多单乐观更新 | 数量:{old_total:.6f}→{self.state.total_long_amount:.6f} | "
                           f"均价:{old_avg:.2f}→{self.state.avg_long_price:.2f} | "
                           f"positions:{old_positions_count}→{len(self.state.long_positions)}")

            else:  # side == 'sell'
                # 记录更新前状态
                old_total = self.state.total_short_amount
                old_avg = self.state.avg_short_price
                old_positions_count = len(self.state.short_positions)

                # 计算新的加权均价
                if self.state.total_short_amount > 0:
                    old_total_value = self.state.total_short_amount * self.state.avg_short_price
                    new_total_value = entry_amount * fill_price
                    new_total_amount = self.state.total_short_amount + entry_amount
                    self.state.avg_short_price = (old_total_value + new_total_value) / new_total_amount
                else:
                    self.state.avg_short_price = fill_price

                # 添加到仓位列表
                self.state.short_positions.append(entry)
                self.state.total_short_amount += entry_amount

                # 记录更新后状态
                logger.info(f"📉 空单乐观更新 | 数量:{old_total:.6f}→{self.state.total_short_amount:.6f} | "
                           f"均价:{old_avg:.2f}→{self.state.avg_short_price:.2f} | "
                           f"positions:{old_positions_count}→{len(self.state.short_positions)}")

            logger.info(f"📊 乐观更新完成 | 多单仓位数:{len(self.state.long_positions)} | 空单仓位数:{len(self.state.short_positions)}")

        except Exception as e:
            logger.error(f"❌ 开仓失败: {e}")
        finally:
            self.state.is_trading = False

    
    
    
    async def close_position(self, side, reason):
        """
        平仓逻辑 (严格遵循用户提供的 Bitget 双向持仓特殊规则)
        规则：
        - 平多: side='buy', tradeSide='close', posSide='long'
        - 平空: side='sell', tradeSide='close', posSide='short'
        """
        current_time = time.time()
        if self.order_timestamps and len(self.order_timestamps) >= self.order_rate_limit:
            if current_time - self.order_timestamps[0] < 1.0: await asyncio.sleep(1.0)
        self.order_timestamps.append(current_time)

        if self.state.is_trading: return
        self.state.is_trading = True
        
        logger.info(f"🛡️ [请求平仓] {side} | 原因: {reason}")

        try:
            # 1. 获取当前持仓量
            amt = self.state.total_long_amount if side == 'long' else self.state.total_short_amount
            if amt <= 0: 
                # 本地无持仓，强制归零并退出
                if side == 'long': 
                    self.state.long_positions = []
                    self.state.long_order_count = 0
                else: 
                    self.state.short_positions = []
                    self.state.short_order_count = 0
                return

            # 2. 构造参数 (严格修正版)
            if side == 'long':
                # 平多规则: side=buy, tradeSide=close
                req_side = 'buy'
                req_pos_side = 'long'
                # ClientOid: m_close_pd_时间戳
                req_client_oid = f"m_close_pd_{int(time.time()*1000)}"
            else:
                # 平空规则: side=sell, tradeSide=close
                req_side = 'sell'
                req_pos_side = 'short'
                # ClientOid: m_close_pk_时间戳
                req_client_oid = f"m_close_pk_{int(time.time()*1000)}"
            
            amt_str = self.trader.exchange.amount_to_precision(self.symbol, amt)
            clean_symbol = self.symbol.split(':')[0].replace('/', '')

            request = {
                'symbol': clean_symbol,
                'productType': self.product_type,
                'marginMode': 'crossed',
                'marginCoin': 'USDT',
                'size': amt_str,
                'side': req_side,         # 修正点：平多buy / 平空sell
                'tradeSide': 'close',     # 固定 close
                'orderType': 'market',
                'force': 'gtc',
                'posSide': req_pos_side,
                'reduceOnly': 'YES', 
                'clientOid': req_client_oid,
            }

            self.state.last_close_time = time.time()
            logger.info(f"📤 [原生平仓] {json.dumps(request)}")
            
            response = await asyncio.to_thread(
                self.trader.exchange.private_mix_post_v2_mix_order_place_order, 
                request
            )
            
            # 3. 结果处理
            if response.get('code') != '00000':
                 # 容错：如果报仓位不存在(22002)，也视为平仓成功
                 if '22002' not in str(response): 
                    raise Exception(f"Bitget Error: {response}")
            
            logger.info(f"✅ 平仓成功")
            
            # 🔒 小保险丝：主动改变仓位后，等待下一次真实仓位确认
            self.state.position_uncertain = True
            
            # 4. 状态清零 (乐观更新)
            if side == 'long':
                self.state.long_positions = []
                self.state.total_long_amount = 0.0
                self.state.avg_long_price = 0.0
                self.state.long_order_count = 0
            else:
                self.state.short_positions = []
                self.state.total_short_amount = 0.0
                self.state.avg_short_price = 0.0
                self.state.short_order_count = 0

        except Exception as e:
            logger.error(f"❌ 平仓异常: {e}")
            # 异常兜底
            err_str = str(e).lower()
            if "param" in err_str or "position" in err_str or "side" in err_str:
                if side == 'long': 
                    self.state.total_long_amount = 0.0
                    self.state.long_order_count = 0
                else: 
                    self.state.total_short_amount = 0.0
                    self.state.short_order_count = 0
        finally:
            self.state.is_trading = False

    # ------------------ WS 回调 (带超级仪表盘) ------------------
    async def on_public_ticker(self, ticker_item, action):
        """
        修正适配：解析底层传回的字典数据，转换为 price 和 ts
        """
        try:
            # 1. 数据解析（这是新增的关键步骤）
            # BaseBitgetWsClient 传回来的是 {'lastPr': '...', 'ts': '...'}
            price = float(ticker_item.get('lastPr', 0.0))
            ts_ms = int(ticker_item.get('ts', time.time() * 1000))
        except Exception as e:
            logger.error(f"Ticker解析错误: {e}")
            return

        # ==================== 下面是原有的业务逻辑 ====================

        # 1. 配置热更新
        self._check_and_reload_config()

        self.state.current_price = price
        self.state.tick_history.append(price)
        
        # 2. 定期强制校准 (防止网络丢包) - 仅在非活跃期
        now = time.time()
        last_sync = getattr(self, 'last_rest_sync_time', 0)
        
        if (now - last_sync > 15.0) and \
           (now - self.last_order_time > 10.0) and \
           (now - self.state.last_close_time > 10.0):
            self.last_rest_sync_time = now
            asyncio.create_task(asyncio.to_thread(self._fetch_and_log_current_positions))

        # ==================== 🔥 超级仪表盘 (每3秒刷新) 🔥 ====================
        last_log = getattr(self, 'last_dashboard_time', 0)
        if now - last_log > 3.0:
            self.last_dashboard_time = now
            
            # --- 多单计算 ---
            if self.state.total_long_amount > 0 and len(self.state.long_positions) > 0:
                l_amt = self.state.total_long_amount
                l_avg = self.state.avg_long_price
                l_val = l_amt * price # 持仓总价值 (U)
                l_mar = l_val / self.leverage # 占用保证金
                l_pnl = (price - l_avg) * l_amt # 浮动盈亏 (U)
                l_ticks = (price - l_avg) / self.state.tick_size # 差距Tick
                
                # 状态判定
                if price >= l_avg:
                    l_status = "🚀顺势(盈利)" 
                else:
                    l_status = "🛡️逆势(被套)"
                
                l_icon = "🟢" if l_pnl >= 0 else "🔴"
                long_msg = (f"   [多] 持仓:{l_amt} ({l_val:.1f}U) | 均价:{l_avg:.2f} | "
                            f"保证金:{l_mar:.1f}U | {l_icon}盈亏:{l_pnl:+.2f}U ({l_ticks:+.0f} Ticks) | {l_status}")
            else:
                long_msg = "   [多] 💤 空仓等待中..."

            # --- 空单计算 ---
            if self.state.total_short_amount > 0 and len(self.state.short_positions) > 0:
                s_amt = self.state.total_short_amount
                s_avg = self.state.avg_short_price
                s_val = s_amt * price
                s_mar = s_val / self.leverage
                s_pnl = (s_avg - price) * s_amt # 空单下跌赚钱
                s_ticks = (s_avg - price) / self.state.tick_size # 正数代表赚钱
                
                # 状态判定
                if price <= s_avg:
                    s_status = "🚀顺势(盈利)"
                else:
                    s_status = "🛡️逆势(被套)"

                s_icon = "🟢" if s_pnl >= 0 else "🔴"
                short_msg = (f"   [空] 持仓:{s_amt} ({s_val:.1f}U) | 均价:{s_avg:.2f} | "
                             f"保证金:{s_mar:.1f}U | {s_icon}盈亏:{s_pnl:+.2f}U ({s_ticks:+.0f} Ticks) | {s_status}")
            else:
                short_msg = "   [空] 💤 空仓等待中..."

            # --- 打印看板 ---
            logger.info(f"-------- 📡 现价: {price:.2f} ------------------------")
            logger.info(long_msg)
            logger.info(short_msg)
            logger.info("-" * 60)
        
        # ==================== 核心策略逻辑 ====================
        if not self.state.trading_paused:
            # A. 检查风控
            await self.check_floating_loss()
            
            # B. 执行整合后的策略逻辑
            await self.process_strategy_logic()
    '''
    async def on_private_position(self, pos_data):
        try:
            if pos_data.get('instId') != self.ws_symbol: return

            side = pos_data.get('holdSide', '').lower()
            total = float(pos_data.get('total', 0.0))
            entry = float(pos_data.get('openPriceAvg', 0.0))

            if side == 'long':
                self.state.total_long_amount = total
                self.state.avg_long_price = entry if total > 0 else 0.0

                # 🚨 修复：如果WS仓位与本地positions不一致，重建positions
                if total > 0:
                    positions_total = sum(p['amount'] for p in self.state.long_positions) if self.state.long_positions else 0
                    if abs(positions_total - total) > 0.0001:
                        logger.warning(f"🔄 多单仓位不一致，重建positions | WS:{total} vs 本地:{positions_total}")
                        self.state.long_positions = [{'amount': total, 'entry_price': entry}]
                else:
                    self.state.long_positions = []

            elif side == 'short':
                self.state.total_short_amount = total
                self.state.avg_short_price = entry if total > 0 else 0.0

                # 🚨 修复：如果WS仓位与本地positions不一致，重建positions
                if total > 0:
                    positions_total = sum(p['amount'] for p in self.state.short_positions) if self.state.short_positions else 0
                    if abs(positions_total - total) > 0.0001:
                        logger.warning(f"🔄 空单仓位不一致，重建positions | WS:{total} vs 本地:{positions_total}")
                        self.state.short_positions = [{'amount': total, 'entry_price': entry}]
                else:
                    self.state.short_positions = []

            # 🔓 解除仓位不确定状态
            self.state.position_uncertain = False

        except Exception as e:
            logger.error(f"WS仓位更新失败: {e}")
    '''
            
            
    async def on_private_position(self, pos_data):
        try:
            if pos_data.get('instId') != self.ws_symbol: return

            side = pos_data.get('holdSide', '').lower()
            ws_total = float(pos_data.get('total', 0.0))  # WS推送的数量
            ws_entry = float(pos_data.get('openPriceAvg', 0.0))  # WS推送的均价

            # 获取本地状态
            if side == 'long':
                local_total = self.state.total_long_amount
                positions = self.state.long_positions
                positions_total = sum(p['amount'] for p in positions) if positions else 0
            else:
                local_total = self.state.total_short_amount
                positions = self.state.short_positions
                positions_total = sum(p['amount'] for p in positions) if positions else 0

            logger.info(f"🔍 [仓位分析] {side.upper()} | "
                       f"WS总仓:{ws_total:.6f} | 本地总仓:{local_total:.6f} | positions总和:{positions_total:.6f} | "
                       f"WS均价:{ws_entry:.2f} | 本地均价:{self.state.avg_long_price if side=='long' else self.state.avg_short_price:.2f}")

            # ==================== 关键修复：智能同步策略 ====================
            # 1. 如果仓位数量完全一致，跳过
            if abs(ws_total - local_total) < 0.0001:
                logger.info(f"✅ {side}仓位数量一致，跳过同步")
                self.state.position_uncertain = False
                return

            # 2. 如果positions总和与WS一致，只更新总仓和均价（不重建positions）
            if abs(ws_total - positions_total) < 0.0001:
                logger.info(f"🔄 {side}更新总仓和均价 | 数量:{ws_total:.6f} 均价:{ws_entry:.2f}")
                if side == 'long':
                    self.state.total_long_amount = ws_total
                    self.state.avg_long_price = ws_entry if ws_total > 0 else 0.0
                else:
                    self.state.total_short_amount = ws_total
                    self.state.avg_short_price = ws_entry if ws_total > 0 else 0.0
                self.state.position_uncertain = False
                return

            # 3. 如果本地positions为空或数量为0，用WS数据重建
            if not positions or positions_total == 0:
                logger.info(f"🔄 {side}重建positions（本地为空）| 数量:{ws_total:.6f}")
                if side == 'long':
                    self.state.total_long_amount = ws_total
                    self.state.avg_long_price = ws_entry if ws_total > 0 else 0.0
                    self.state.long_positions = [{'amount': ws_total, 'entry_price': ws_entry}] if ws_total > 0 else []
                else:
                    self.state.total_short_amount = ws_total
                    self.state.avg_short_price = ws_entry if ws_total > 0 else 0.0
                    self.state.short_positions = [{'amount': ws_total, 'entry_price': ws_entry}] if ws_total > 0 else []
                self.state.position_uncertain = False
                return

            # 4. 其他情况：保守更新，不重建positions
            logger.info(f"⚠️ {side}保守更新 | WS:{ws_total:.6f} ≠ 本地:{local_total:.6f} ≠ positions:{positions_total:.6f}")
            if side == 'long':
                # 只更新总仓，保留positions结构
                self.state.total_long_amount = ws_total
                # 如果均价变化大，更新均价但不重建positions
                if ws_total > 0 and abs(ws_entry - self.state.avg_long_price) > 1.0:
                    logger.info(f"💰 更新多单均价: {self.state.avg_long_price:.2f} → {ws_entry:.2f}")
                    self.state.avg_long_price = ws_entry
            else:
                self.state.total_short_amount = ws_total
                if ws_total > 0 and abs(ws_entry - self.state.avg_short_price) > 1.0:
                    logger.info(f"💰 更新空单均价: {self.state.avg_short_price:.2f} → {ws_entry:.2f}")
                    self.state.avg_short_price = ws_entry

            self.state.position_uncertain = False
            # ==================== 修复结束 ====================

        except Exception as e:
            logger.error(f"WS仓位更新失败: {e}")        
            
            
    async def run(self):
        if self.trader: self.sync_initialize()
        await asyncio.gather(
            self.connect_public_ws(self.product_type, self.ws_symbol),
            self.connect_private_ws(self.config, self.product_type)
        )
    
    # 占位符
    def update_consecutive_loss(self): pass
    def check_risk_before_open(self, s, p): return True
    def save_trade_record(self, r): pass
    async def on_private_order(self, d): pass
    async def on_private_account(self, d): pass

# ==================== 主入口 (无强平版) ====================
if __name__ == "__main__":
    config_file = sys.argv[1] if len(sys.argv) > 1 else 'martin.json'
    strategy = MartingaleStrategy(config_path=config_file)
    logger.info("🚀 策略启动 | 安全模式: ON")
    
    try:
        asyncio.run(strategy.run())
    except KeyboardInterrupt:
        logger.info("⏹️ 用户停止 (持仓保留)")
    except Exception as e:
        logger.critical(f"❌ 崩溃: {e} (持仓保留)")
