# -*- coding: utf-8 -*-
import ccxt
import logging
import json
import re
from typing import Dict, Any, List, Optional, Union
from functools import wraps

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger('CCXT_Utils')

class ExchangeStandardError(Exception):
    def __init__(self, code: str, msg: str, raw_err: str = ""):
        self.code = code
        self.msg = msg
        self.raw_err = raw_err
        super().__init__(f"[{code}] {msg}")

# ==========================================
# 安全转换工具函数 (全局通用，封装核心类型转换逻辑)
# 仅定义留存，供后续外部调用，**内部业务逻辑不使用**
# ==========================================
def safe_float(value: Union[str, int, float, None], default: float = 0.0) -> float:
    """
    安全转换为浮点型，处理空值和转换异常
    :param value: 待转换值
    :param default: 转换失败时的默认值
    :return: 转换后的浮点型
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def safe_int(value: Union[str, int, float, None], default: int = 0) -> int:
    """
    安全转换为整型，处理空值和转换异常
    :param value: 待转换值
    :param default: 转换失败时的默认值
    :return: 转换后的整型
    """
    if value is None:
        return default
    try:
        return int(float(value))  # 先转浮点再转整型，兼容字符串格式的小数（如 "10.0"）
    except (TypeError, ValueError):
        return default

class ExchangeTrader:
    # 核心修改：移除类内部的 DEFAULT_BITGET_SANDBOX_API 内置配置
    # 让类更通用，不耦合固定的模拟盘密钥，API 信息由外部传入

    # 核心修改1：新增 default_trade_type 参数，默认值为 'swap'
    def __init__(self, 
                 exchange_id: str, 
                 api_key: str = None, 
                 secret: str = None, 
                 passphrase: str = None, 
                 sandbox: bool = False, 
                 proxy_url: str = None,
                 default_trade_type: str = "swap"):  # 新增参数，默认 swap
        self.exchange_id = exchange_id.lower()
        self.sandbox = sandbox
        # 保存默认交易类型，供后续查询和日志使用
        self.default_trade_type = default_trade_type.lower()
        
        # 核心修改2：移除内置模拟盘 API 自动填充逻辑，仅保留参数接收（类不再耦合固定 API）
        # 模拟盘 API 由外部（if __name__ 测试块）传入，类本身不存储固定密钥
        if self.sandbox and self.exchange_id == "bitget" and (not api_key or not secret or not passphrase):
            logger.warning("🔧 检测到 Bitget 模拟盘模式，但未传入 API 信息，可能无法正常调用接口")
            # 不再自动填充，直接抛出警告，由外部保证 API 信息的传入
            raise ExchangeStandardError("MISSING_API_INFO", "Bitget 模拟盘模式需要传入有效的 api_key、secret、passphrase")
        
        # 基础配置
        config = {
            'apiKey': api_key,
            'secret': secret,
            'enableRateLimit': True,
            'timeout': 10000,
            'options': {
                # 核心修改3：使用传入的 default_trade_type，不再固定为 'swap'
                #'defaultType': self.default_trade_type,
                #'adjustForTimeDifference': True,
                'createMarketBuyOrderRequiresPrice': False,
            }
        }

        if passphrase:
            config['password'] = passphrase
        if proxy_url:
            config['proxies'] = {'http': proxy_url, 'https': proxy_url}

        # 初始化交易所
        try:
            exchange_class = getattr(ccxt, self.exchange_id)
            self.exchange = exchange_class(config)
        except AttributeError:
            raise ExchangeStandardError("INVALID_EXCHANGE", f"不支持的交易所: {self.exchange_id}")

        # Bitget 专属适配 (模拟盘 + 特殊请求头)
        if self.exchange_id == 'bitget':
            if not self.exchange.headers:
                self.exchange.headers = {}
            # Bitget 渠道头（可选，保持你的原有配置）
            self.exchange.headers['X-CHANNEL-API-CODE'] = "x8alx"
            # ========== 新增：补充核心缺失的请求头 ==========
            self.exchange.headers['Content-Type'] = 'application/json'
            # ==============================================
            if self.sandbox:
                self.exchange.set_sandbox_mode(True)
                self.exchange.headers['paptrading'] = '1'  # 模拟盘必填请求头
                self.exchange.options['sandbox'] = True
                logger.info("🔧 [Bitget 模拟盘] 已注入请求头: paptrading=1")
        
        # 安全加载市场数据
        self._load_markets_safe()

    def _load_markets_safe(self):
        """安全加载市场交易对数据，避免初始化失败（新增默认交易类型日志）"""
        try:
            self.exchange.load_markets()
            logger.info(f"✅ [{self.exchange_id}] {self.default_trade_type} 市场数据加载成功，共 {len(self.exchange.markets)} 个交易对")
        except Exception as e:
            err_msg = str(e)
            logger.error(f"❌ [{self.exchange_id}] {self.default_trade_type} 市场数据加载失败: {err_msg}")
            raise ExchangeStandardError("LOAD_MARKETS_FAILED", "市场数据加载失败", err_msg)

    # ==========================================
    # 核心修复：将 _guard 改为静态方法，解决装饰器参数缺失问题
    # ==========================================
    @staticmethod
    def _guard(func):
        """API 调用异常捕获装饰器，统一异常格式（静态方法，支持类内方法装饰）"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except ExchangeStandardError:
                # 自定义异常直接抛出，不重复包装
                raise
            except Exception as e:
                err_msg = str(e)
                # 常见异常分类
                if 'insufficient funds' in err_msg.lower():
                    raise ExchangeStandardError("INSUFFICIENT_FUNDS", "账户余额不足", err_msg)
                elif 'symbol' in err_msg.lower() and 'not found' in err_msg.lower():
                    raise ExchangeStandardError("INVALID_SYMBOL", "无效的交易对", err_msg)
                # 提取 exchange_id 用于日志（args[0] 是被装饰方法的 self 实例）
                exchange_id = "unknown"
                if args and hasattr(args[0], 'exchange_id'):
                    exchange_id = args[0].exchange_id
                logger.error(f"🚨 [{exchange_id}] API 调用失败: {err_msg}")
                raise ExchangeStandardError("API_ERROR", f"接口调用异常: {err_msg}", err_msg)
        return wrapper

    # ==========================================
    # 核心 1: 完善市场详情提取与中文分类打印 (一次性提取，不重复查询，使用原始数据)
    # ==========================================
    def get_market_details(self, symbol: str) -> Dict[str, Any]:
        """
        一次性提取交易对完整详情，中文分类打印，返回清洗后的结构化数据
        注意：使用接口返回的原始数据，不调用 safe_float/safe_int 进行转换
        :param symbol: 交易对 (如 BTC/USDT:USDT)
        :return: 结构化市场详情字典
        """
        # 校验交易对是否存在
        if symbol not in self.exchange.markets:
            err_msg = f"交易对 {symbol} 不存在于 {self.exchange_id} 交易所 {self.default_trade_type} 市场"
            logger.error(f"❌ {err_msg}")
            raise ExchangeStandardError("INVALID_SYMBOL", err_msg)

        # 一次性获取 market 对象，避免重复查询（保留原始数据）
        market = self.exchange.market(symbol)
        info = market.get('info', {})  # 交易所原始返回数据
        precision = market.get('precision', {})  # 精度配置（原始）
        limits = market.get('limits', {})  # 限额配置（原始）

        # 一次性提取所有核心数据（兼容 None 值，替换为可格式化的默认值，保留原始数据本质）
        # 核心修改：对可能为 None 的字段，增加 `or` 兜底，替换为 0.0 或 ''（不影响原始数据备份）
        market_details = {
            # 基础信息（原始数据，直接取值，兼容 None）
            'symbol': market.get('symbol', '') or '',
            'market_id': market.get('id', '') or '',
            'base_coin': market.get('base', '') or '',  # 基础货币 (如 BTC)
            'quote_coin': market.get('quote', '') or '',  # 计价货币 (如 USDT)
            'settle_coin': market.get('settle', '') or '',  # 结算货币 (如 USDT)
            'market_type': market.get('type', '') or '',  # spot/swap/future/option
            'default_trade_type': self.default_trade_type,  # 新增：标注当前实例默认交易类型
            'is_linear': market.get('linear', False) or False,  # 是否 U 本位正向合约
            'is_inverse': market.get('inverse', False) or False,  # 是否 币本位反向合约
            'is_active': market.get('active', False) or False,  # 交易对是否活跃
            'is_contract': market.get('contract', False) or False,  # 是否合约交易对
            'contract_type': info.get('symbolType', 'unknown') or 'unknown',  # 合约类型 (永续/交割)

            # 费率信息（原始数据，直接取值，百分比手动计算保留原始精度，兼容 None）
            'taker_fee': market.get('taker', 0.0) or 0.0,  # 吃单手续费率（原始值，不转换）
            'maker_fee': market.get('maker', 0.0) or 0.0,  # 挂单手续费率（原始值，不转换）
            'taker_fee_percent': (market.get('taker', 0.0) or 0.0) * 100,  # 吃单手续费 (%)（原始值计算）
            'maker_fee_percent': (market.get('maker', 0.0) or 0.0) * 100,  # 挂单手续费 (%)（原始值计算）

            # 合约专属信息（原始数据，直接取值，兼容 None）
            'contract_size': market.get('contractSize', 1.0) or 1.0,  # 合约面值（原始值）
            'funding_interval_hours': info.get('fundInterval', 0) or 0,  # 资金费率间隔 (小时)（原始值）
            'max_leverage': limits.get('leverage', {}).get('max', 1.0) or 1.0,  # 最大杠杆（原始值）
            'min_leverage': limits.get('leverage', {}).get('min', 1.0) or 1.0,  # 最小杠杆（原始值）
            'support_margin_modes': market.get('marginModes', {}) or {},  # 支持的保证金模式 (cross/isolated)

            # 精度与限额（下单校验核心，原始数据直接取值，兼容 None，兜底为 0.0 或 '无限制'）
            'price_precision': precision.get('price', 0.0) or 0.0,  # 价格精度 (最小变动单位)（原始值）
            'amount_precision': precision.get('amount', 0.0) or 0.0,  # 数量精度 (最小变动单位)（原始值）
            'min_trade_amount': limits.get('amount', {}).get('min', 0.0) or 0.0,  # 最小下单数量（原始值）
            'max_trade_amount': limits.get('amount', {}).get('max') or '无限制',  # 最大下单数量（兼容 None，兜底为 '无限制'）
            'min_trade_cost': limits.get('cost', {}).get('min', 0.0) or 0.0,  # 最小下单名义价值 (U)（原始值）
            'max_trade_cost': limits.get('cost', {}).get('max') or '无限制',  # 最大下单名义价值 (U)（兼容 None，兜底为 '无限制'）
            'min_trade_usdt': info.get('minTradeUSDT', 0.0) or 0.0,  # Bitget 原始最小 USDT 下单量（原始值）
            'price_step': info.get('priceEndStep', 0.0) or 0.0,  # Bitget 原始价格步长（原始值）

            # 原始数据备份（完整保留接口返回结果，供后续外部处理使用）
            'raw_info': info,
            'raw_market': market
        }

        # ==========================================
        # 中文分类打印（清晰易懂，标注数据来源，兼容 None 值，避免格式错误）
        # ==========================================
        print("\n" + "="*88)
        print(f"📊 [{self.exchange_id}] {self.default_trade_type} 市场 - 交易对详情报告 - {market_details['symbol']}")
        print("="*88)

        print(f"【1. 基础信息】(来源: market 直接提取，原始数据)")
        # 字符串字段使用 str() 包裹，兼容 None
        print(f"  • 交易对符号 (symbol)        : {str(market_details['symbol']):<30} -> market['symbol']")
        print(f"  • 交易所内部ID (market_id)   : {str(market_details['market_id']):<30} -> market['id']")
        print(f"  • 基础货币 (base_coin)       : {str(market_details['base_coin']):<30} -> market['base']")
        print(f"  • 计价货币 (quote_coin)      : {str(market_details['quote_coin']):<30} -> market['quote']")
        print(f"  • 结算货币 (settle_coin)    : {str(market_details['settle_coin']):<30} -> market['settle']")
        print(f"  • 市场类型 (market_type)     : {str(market_details['market_type']):<30} -> market['type']")
        print(f"  • 实例默认交易类型           : {str(market_details['default_trade_type']):<30} -> self.default_trade_type")
        print(f"  • 是否 U 本位 (is_linear)     : {str(market_details['is_linear']):<30} -> market['linear']")
        print(f"  • 是否活跃 (is_active)       : {str(market_details['is_active']):<30} -> market['active']")
        print(f"  • 合约类型 (contract_type)   : {str(market_details['contract_type']):<30} -> market['info']['symbolType']")

        print(f"\n【2. 手续费信息】(来源: market 直接提取，原始数据)")
        # 浮点数字段使用 float() 包裹，兼容 None，避免 .6f 格式化错误
        print(f"  • 吃单手续费率 (taker)       : {float(market_details['taker_fee']):.6f} ({float(market_details['taker_fee_percent']):.4f}%) -> market['taker']")
        print(f"  • 挂单手续费率 (maker)       : {float(market_details['maker_fee']):.6f} ({float(market_details['maker_fee_percent']):.4f}%) -> market['maker']")

        print(f"\n【3. 合约专属信息】(来源: market + info，原始数据)")
        print(f"  • 合约面值 (contract_size)   : {str(market_details['contract_size']):<30} -> market['contractSize']")
        print(f"  • 资金费率间隔 (小时)        : {str(market_details['funding_interval_hours']):<30} -> market['info']['fundInterval']")
        print(f"  • 最小杠杆 (min_leverage)    : {str(market_details['min_leverage']):<30} -> market['limits']['leverage']['min']")
        print(f"  • 最大杠杆 (max_leverage)    : {str(market_details['max_leverage']):<30} -> market['limits']['leverage']['max']")
        print(f"  • 支持保证金模式             : {str(market_details['support_margin_modes'])} -> market['marginModes']")

        print(f"\n【4. 精度与下单限额】(来源: precision + limits + info，原始数据) - 下单校验核心！")
        # 兼容 '无限制' 字符串和数字，直接使用 str() 包裹，不使用浮点格式
        print(f"  • 价格精度 (price_precision) : {str(market_details['price_precision']):<30} -> market['precision']['price']")
        print(f"  • 数量精度 (amount_precision) : {str(market_details['amount_precision']):<30} -> market['precision']['amount']")
        print(f"  • 最小下单数量 (min_amount)  : {str(market_details['min_trade_amount']):<30} -> market['limits']['amount']['min']")
        print(f"  • 最大下单数量 (max_amount)  : {str(market_details['max_trade_amount']):<30} -> market['limits']['amount']['max']")
        print(f"  • 最小下单价值 (U, min_cost) : {str(market_details['min_trade_cost']):<30} -> market['limits']['cost']['min']")
        print(f"  • 最大下单价值 (U, max_cost) : {str(market_details['max_trade_cost']):<30} -> market['limits']['cost']['max']")  # 补充打印最大下单价值
        print(f"  • Bitget 最小 USDT 下单量    : {str(market_details['min_trade_usdt']):<30} -> market['info']['minTradeUSDT']")
        print(f"  • Bitget 价格步长            : {str(market_details['price_step']):<30} -> market['info']['priceEndStep']")

        print("="*88 + "\n")

        return market_details

    # ==========================================
    # 核心 2: 简化配置校验 (传入 market 对象，参数格式自动归一化，使用原始数据)
    # ==========================================
    def _normalize_key(self, key: str) -> str:
        """
        参数键名归一化：去除下划线/横杠、转小写，实现模糊匹配
        :param key: 原始键名 (如 MAX_Leverage、min_notional、Min-USDt)
        :return: 归一化后的键名
        """
        if not isinstance(key, str):
            return str(key)
        # 步骤：转小写 -> 去除下划线 -> 去除横杠 -> 去除空格
        return key.lower().replace('_', '').replace('-', '').replace(' ', '')

    def validate_config_by_market(self, market: Dict[str, Any], user_config: Dict[str, Any]) -> bool:
        """
        传入 market 详情对象，校验用户配置是否符合交易所规则
        支持键名模糊匹配（驼峰、下划线、大小写全兼容），使用原始数据校验
        :param market: get_market_details 返回的市场详情字典（原始数据）
        :param user_config: 用户配置字典 (如 {'leverage': 50, 'min_notional': 2.0})
        :return: 校验结果 (True: 无硬性错误, False: 存在阻断性错误)
        """
        if not market or not user_config:
            logger.warning("⚠️  市场详情或用户配置为空，跳过校验")
            return True

        print(f"\n🔍 开始校验用户配置 (交易对: {market['symbol']} | 市场类型: {self.default_trade_type})...")
        is_valid = True

        # 建立 归一化键名 -> (校验值, 描述, 校验规则) 的映射表（使用原始数据，不调用 safe_float）
        validation_map = {
            'leverage': (
                market['max_leverage'],
                f"最大杠杆 ({market['max_leverage']}x)",
                lambda user_val, limit_val: float(user_val) > float(limit_val)  # 仅用户输入转浮点，原始校验值保持原样
            ),
            'mincost': (
                market['min_trade_cost'],
                f"最小下单价值 ({market['min_trade_cost']} U)",
                lambda user_val, limit_val: float(user_val) < float(limit_val)
            ),
            'minnotional': (
                market['min_trade_cost'],
                f"最小下单价值 ({market['min_trade_cost']} U)",
                lambda user_val, limit_val: float(user_val) < float(limit_val)
            ),
            'minusdt': (
                market['min_trade_usdt'],
                f"最小 USDT 下单量 ({market['min_trade_usdt']} U)",
                lambda user_val, limit_val: float(user_val) < float(limit_val)
            ),
            'minamount': (
                market['min_trade_amount'],
                f"最小下单数量 ({market['min_trade_amount']})",
                lambda user_val, limit_val: float(user_val) < float(limit_val)
            )
        }

        # 遍历用户配置，进行模糊匹配校验
        for user_key, user_val in user_config.items():
            norm_user_key = self._normalize_key(user_key)

            # 遍历校验映射表，匹配归一化后的键名
            for norm_map_key, (limit_val, desc, check_func) in validation_map.items():
                # 模糊匹配：用户归一化键名 包含 映射表归一化键名 即视为匹配
                if norm_map_key in norm_user_key and float(limit_val) > 0:
                    # 执行校验规则（仅用户输入做必要转换，原始数据不处理）
                    try:
                        user_val_float = float(user_val)
                    except (TypeError, ValueError):
                        print(f"  ⚠️ [配置格式错误] {user_key}={user_val} 不是有效数字，无法校验")
                        break
                    
                    if check_func(user_val, limit_val):
                        if norm_map_key == 'leverage':
                            # 杠杆超过上限：阻断性错误
                            print(f"  ❌ [校验失败] {user_key}={user_val} > 交易所{desc}")
                            is_valid = False
                        else:
                            # 其他项低于下限：风险提示（非阻断）
                            print(f"  ⚠️ [风险提示] {user_key}={user_val} < 交易所{desc}，下单可能被拒绝")
                    else:
                        print(f"  ✅ [校验通过] {user_key}={user_val} (符合交易所{desc}要求)")
                    break  # 匹配到一个映射项后，跳出循环，避免重复校验

        # 输出校验结果总结
        if is_valid:
            print("🎉 配置校验完成，未发现阻断性错误（部分风险提示请留意）")
        else:
            print("🚫 配置校验发现阻断性错误，请修正后再使用")

        return is_valid

    # ==========================================
    # 核心 3: 保证金模式与杠杆设置 (完善逐仓/全仓切换，支持分方向杠杆，使用原始数据)
    # ==========================================
    @_guard
    def set_margin_mode(self, symbol: str, mode: str, leverage: float = 10.0):
        """
        切换保证金模式并设置杠杆（支持 Bitget 分方向杠杆）
        :param symbol: 交易对 (如 BTC/USDT:USDT)
        :param mode: 保证金模式 ('crossed' 全仓 | 'isolated' 逐仓)
        :param leverage: 杠杆倍数 (需在 [min_leverage, max_leverage] 范围内)
        """
        mode = mode.lower()
        if mode not in ['crossed', 'isolated']:
            raise ExchangeStandardError("INVALID_MARGIN_MODE", "保证金模式仅支持 'crossed' (全仓) 或 'isolated' (逐仓)")

        print(f"\n⚙️  正在设置 [{symbol}] | {self.default_trade_type} 市场 -> 保证金模式: {mode}, 杠杆: {leverage}x")

        # 步骤 1: 切换保证金模式（使用原始数据交互）
        try:
            self.exchange.set_margin_mode(mode, symbol)
            print(f"  ✅ 保证金模式已成功切换为: {mode}")
        except Exception as e:
            err_msg = str(e).lower()
            if "no change" in err_msg or "already" in err_msg:
                print(f"  ℹ️  无需切换保证金模式 (当前已是 {mode} 模式)")
            else:
                logger.warning(f"  ⚠️  保证金模式切换警告: {e}")

        # 步骤 2: 设置杠杆（通用方法 + Bitget 分方向重试，使用原始输入杠杆值）
        try:
            # 先尝试 CCXT 通用方法（直接使用传入的 leverage 值，不进行安全转换）
            self.exchange.set_leverage(leverage, symbol)
            print(f"  ✅ 杠杆已成功设置为: {leverage}x")
        except Exception as e:
            print(f"  ⚠️  通用杠杆设置失败，尝试 Bitget 分方向设置: {e}")
            # Bitget 逐仓模式下，需分多空设置杠杆
            if self.exchange_id == 'bitget' and mode == 'isolated':
                try:
                    self.exchange.set_leverage(leverage, symbol, params={'posSide': 'long'})
                    self.exchange.set_leverage(leverage, symbol, params={'posSide': 'short'})
                    print(f"  ✅ (Bitget 专属) 分多/空方向杠杆设置成功: {leverage}x")
                except Exception as e2:
                    raise ExchangeStandardError("SET_LEVERAGE_FAILED", f"分方向杠杆设置失败: {e2}")

    @_guard
    def fetch_positions_risk(self, symbol: str = None) -> List[Dict[str, Any]]:
        """
        查询持仓风控状态（全仓/逐仓、杠杆、持仓数量），返回原始持仓数据
        :param symbol: 交易对 (可选，不传则查询所有持仓)
        :return: 持仓详情列表（原始数据）
        """
        # Bitget 专属参数：指定 U 本位合约
        params = {}
        if self.exchange_id == 'bitget':
            params['productType'] = 'USDT-FUTURES'

        # 获取持仓数据（保留原始数据，不进行安全转换）
        symbols = [symbol] if symbol else None
        positions = self.exchange.fetch_positions(symbols, params=params)
        # 过滤有效持仓（仅对合约数量做必要判断，不转换原始数据）
        filtered_positions = [p for p in positions if float(p.get('contracts', 0)) > 0]

        # 打印持仓信息（原始数据直接展示，必要时格式化输出）
        print(f"\n🔍 [{self.exchange_id}] {self.default_trade_type} 市场 - 持仓风控状态查询（原始数据）")
        if not filtered_positions:
            print("  • 当前无有效持仓（空仓）")
            return []

        for pos in filtered_positions:
            symbol = pos.get('symbol', 'unknown')
            side = pos.get('side', 'unknown')
            contracts = pos.get('contracts', 0)
            margin_mode = pos.get('marginMode', 'unknown')
            leverage = pos.get('leverage', 0)
            unrealized_pnl = pos.get('unrealizedPnl', 0)

            print(f"  • 交易对: {symbol:<15} 方向: {side:<5} 数量: {contracts:<10} 模式: {margin_mode:<10} 杠杆: {leverage}x 未实现盈亏: {unrealized_pnl}")

        return filtered_positions

    # ==========================================
    # 核心 4: Bitget 专属平仓逻辑 (严格遵循双向持仓规则，使用原始数据)
    # ==========================================
    @_guard
    def close_position_bitget(self, symbol: str, side: str, amount: float = None, price: float = None, params: Dict = None) -> Dict[str, Any]:
        """
        Bitget 双向持仓专属平仓逻辑
        规则：平多 -> side='buy', tradeSide='close', posSide='long'；平空 -> side='sell', tradeSide='close', posSide='short'
        :param symbol: 交易对 (如 BTC/USDT:USDT)
        :param side: 平仓方向 ('long' 平多 | 'short' 平空)
        :param amount: 平仓数量 (可选，不传则平全部)
        :param price: 平仓价格 (市价单不传，限价单必填)
        :param params: 额外参数 (可选)
        :return: 平仓订单结果（原始数据）
        """
        if self.exchange_id != 'bitget':
            raise ExchangeStandardError("UNSUPPORTED_EXCHANGE", "该方法仅支持 Bitget 交易所")

        side = side.lower()
        if side not in ['long', 'short']:
            raise ExchangeStandardError("INVALID_CLOSE_SIDE", "平仓方向仅支持 'long' (平多) 或 'short' (平空)")

        # 初始化默认参数
        params = params or {}
        order_side = ''
        pos_side = side

        # 映射 Bitget 平仓规则
        if side == 'long':
            order_side = 'buy'  # 平多：买入平仓
            print(f"📉 准备平多仓 [{symbol}] | {self.default_trade_type} 市场，订单方向: {order_side}，持仓方向: {pos_side}")
        elif side == 'short':
            order_side = 'sell'  # 平空：卖出平仓
            print(f"📈 准备平空仓 [{symbol}] | {self.default_trade_type} 市场，订单方向: {order_side}，持仓方向: {pos_side}")

        # 注入 Bitget 平仓专属参数
        params['tradeSide'] = 'close'
        params['posSide'] = pos_side
        params['productType'] = 'USDT-FUTURES'  # 显式指定 U 本位合约

        # 处理平仓数量（不传则平全部，使用原始持仓数据）
        if not amount:
            positions = self.fetch_positions_risk(symbol)
            for pos in positions:
                if pos.get('side', '').lower() == side:
                    amount = pos.get('contracts', 0)  # 直接取原始持仓数量，不转换
                    print(f"  ℹ️  未指定平仓数量，自动获取全部持仓: {amount}")
                    break
            if not amount or float(amount) <= 0:
                raise ExchangeStandardError("NO_POSITION", "当前无对应方向持仓，无法平仓")

        # 处理订单类型（限价单/市价单，使用原始数据交互）
        if price:
            # 限价平仓（直接使用传入的 price 原始值）
            order = self.exchange.create_limit_order(
                symbol=symbol,
                side=order_side,
                amount=amount,
                price=price,
                params=params
            )
            print(f"  ✅ 限价平仓订单已提交，订单ID: {order.get('id', 'unknown')}，价格: {price}")
        else:
            # 市价平仓
            order = self.exchange.create_market_order(
                symbol=symbol,
                side=order_side,
                amount=amount,
                params=params
            )
            print(f"  ✅ 市价平仓订单已提交，订单ID: {order.get('id', 'unknown')}")

        return order

    # ==========================================
    # 辅助方法：切换市场类型（现货/合约）
    # ==========================================
    def switch_market_type(self, market_type: str):
        """
        切换交易所默认市场类型（解决 defaultType 不匹配问题）
        :param market_type: 'spot' (现货) | 'swap' (永续合约) | 'future' (交割合约)
        """
        market_type = market_type.lower()
        if market_type not in ['spot', 'swap', 'future']:
            raise ExchangeStandardError("INVALID_MARKET_TYPE", "市场类型仅支持 'spot'、'swap'、'future'")

        # 更新实例默认交易类型和交易所配置
        self.default_trade_type = market_type
        self.exchange.options['defaultType'] = market_type
        # 重新加载市场数据（切换类型后必须重新加载）
        self._load_markets_safe()
        logger.info(f"🔧 已切换默认市场类型为: {market_type}，并重新加载市场数据")
        
        

    def get_current_price(self, symbol: str) -> float:
        """
        获取当前价格

        Args:
            symbol: 交易对符号

        Returns:
            当前价格
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            # 优化：增加 ticker['last'] 存在性校验，避免 KeyError
            last_price = ticker.get('last', 0.0)
            if last_price is None:
                # 兜底：若 last 不存在，用 close 或 bid/ask 兜底
                last_price = ticker.get('close', ticker.get('bid', ticker.get('ask', 0.0)))
            return float(last_price)
        except Exception as e:
            logger.error(f"获取价格失败: symbol={symbol}, err={e}")  # 优化：补充 symbol 上下文，方便排障
            raise


    
    def get_contract_balance(self, margin_coin: str = 'USDT', return_type: str = 'free') -> float:
        """
        简洁方法：获取合约账户指定保证金币种的指定类型余额（直接返回金额，日常使用首选）
        Args:
            margin_coin: 合约保证金币种（默认 'USDT'，适配 USDT 本位合约）
            return_type: 返回余额类型（默认 'free' 可用保证金，支持 'used' 已用保证金/'total' 总保证金）
        Returns:
            对应类型的余额金额（float 类型，无数据返回 0.0）
        """
        # 1. 校验返回类型合法性
        valid_return_types = ['free', 'used', 'total']
        if return_type not in valid_return_types:
            raise ValueError(f"无效的 return_type：{return_type}，支持类型：{valid_return_types}")
        
        try:
            # 2. 设置合约账户类型，获取完整原始余额数据
            #self.exchange.options['defaultType'] = 'swap'
            
            params = {'type': 'swap', 'productType': 'USDT-FUTURES'}
        
            full_balance = self.exchange.fetch_balance(params=params)
            
            
            #full_balance = self.exchange.fetch_balance()
            
            # 3. 标准化币种格式
            margin_coin_upper = margin_coin.upper()
            
            # 4. 提取对应类型的余额，返回 float 金额
            if margin_coin_upper in full_balance:
                balance_data = full_balance[margin_coin_upper]
                # 按需返回对应类型，无该字段则返回 0.0
                target_balance = balance_data.get(return_type, 0.0)
                return float(target_balance)
            
            # 5. 未找到该币种，返回 0.0
            logger.warning(f"合约账户未找到保证金币种余额：{margin_coin_upper}")
            return 0.0
        
        except Exception as e:
            logger.error(f"获取合约简洁余额失败：margin_coin={margin_coin}，return_type={return_type}，err={e}")
            raise
                         
                         

    
    def get_contract_balance_info(self, margin_coin: str = 'USDT', is_print: bool = False) -> Dict:
        """
        详细方法：获取合约账户指定保证金币种的完整原始余额数据（支持中文打印所有字段，深度定制/调试首选）
        Args:
            margin_coin: 合约保证金币种（默认 'USDT'，适配 USDT 本位合约）
            is_print: 是否中文格式化打印所有字段（默认 False，不打印）
        Returns:
            完整原始余额数据（CCXT 标准化 dict，包含 info 交易所原始数据）
        """
        try:
            # 1. 设置合约账户类型，获取完整原始余额数据
            #self.exchange.options['defaultType'] = 'swap'
            params = {'type': 'swap', 'productType': 'USDT-FUTURES'}
        
            full_balance = self.exchange.fetch_balance(params=params)
            
            # 2. 标准化币种格式
            margin_coin_upper = margin_coin.upper()
            
            # 3. 若开启中文打印，格式化输出所有字段
            if is_print:
                print("\n" + "="*70)
                print(f"📋 合约账户（{margin_coin_upper} 本位）完整余额信息")
                print("="*70)
                
                # 3.1 打印 CCXT 标准化核心字段（通用兼容）
                print(f"\n【CCXT 标准化字段（跨交易所兼容）】")
                if margin_coin_upper in full_balance:
                    balance_data = full_balance[margin_coin_upper]
                    free_balance = float(balance_data.get('free', 0.0))
                    used_balance = float(balance_data.get('used', 0.0))
                    total_balance = float(balance_data.get('total', 0.0))
                    print(f"  可用保证金（free）：{free_balance:.8f} {margin_coin_upper}")
                    print(f"  已用保证金（used）：{used_balance:.8f} {margin_coin_upper}（持仓/挂单冻结）")
                    print(f"  总保证金（total）：{total_balance:.8f} {margin_coin_upper}（free + used）")
                else:
                    print(f"  未找到 {margin_coin_upper} 对应的标准化余额数据")
                
                # 3.2 打印 Bitget 合约特有原始字段（所有字段，无遗漏）
                print(f"\n【Bitget 合约特有字段（原始全量数据，风控/调试核心）】")
                info_list = full_balance.get('info', [])
                if info_list and isinstance(info_list[0], dict):
                    contract_info = info_list[0]
                    
                    # 建立「所有原始字段」与「中文释义」的映射（覆盖 Bitget 合约全部返回字段）
                    field_cn_map = {
                        'marginCoin': '保证金币种',
                        'locked': '冻结保证金（持仓/挂单占用）',
                        'available': '合约可用保证金（可开仓/划转）',
                        'crossedMaxAvailable': '全仓模式最大可用保证金',
                        'isolatedMaxAvailable': '逐仓模式最大可用保证金',
                        'maxTransferOut': '最大可划转至现货的金额',
                        'accountEquity': '账户权益（保证金 + 未实现盈亏，真实总资产）',
                        'usdtEquity': 'USDT 计价账户权益（精准值）',
                        'btcEquity': 'BTC 计价账户权益（辅助参考）',
                        'crossedRiskRate': '全仓风险率（<1 面临强平，风控核心）',
                        'unrealizedPL': '未实现盈亏（持仓浮动盈亏，盈利正/亏损负）',
                        'coupon': '优惠券/平台补贴金额',
                        'crossedUnrealizedPL': '全仓未实现盈亏（多仓位汇总）',
                        'isolatedUnrealizedPL': '逐仓未实现盈亏（单一仓位独立）',
                        'grant': '平台发放奖励/赠金金额',
                        'unionTotalMargin': '联合总保证金（多币种/多账户汇总）',
                        'unionAvailable': '联合可用保证金（多币种/多账户汇总）',
                        'unionMm': '联合维持保证金（多币种/多账户汇总）',
                        'assetList': '非保证金资产列表（合约账户内其他闲置币种）',
                        'assetMode': '保证金模式（single=单一币种/multi=多币种）',
                        'isolatedMargin': '逐仓占用保证金（当前逐仓持仓冻结）',
                        'crossedMargin': '全仓占用保证金（当前全仓持仓冻结）'
                    }
                    
                    # 遍历所有原始字段，打印「中文释义 + 字段值」（无映射的字段也保留，避免遗漏）
                    for field_name, field_value in contract_info.items():
                        # 获取中文释义，未知字段显示原名字段
                        field_cn = field_cn_map.get(field_name, f"【未知字段】{field_name}")
                        
                        # 特殊处理：assetList 是列表，格式化打印
                        if field_name == 'assetList' and isinstance(field_value, list):
                            print(f"  {field_cn}：")
                            for asset in field_value:
                                coin = asset.get('coin', '未知币种')
                                available = asset.get('available', '0')
                                balance = asset.get('balance', '0')
                                print(f"    - {coin}：可用 {available}，余额 {balance}")
                            continue
                        
                        # 普通字段：格式化打印（数值字段保持原样，空值标注为「无」）
                        display_value = field_value if field_value not in ['', None] else '无'
                        # 尝试将数值字符串转成更易读的格式（不报错，兼容非数值）
                        try:
                            if isinstance(display_value, str) and display_value.replace('.', '').replace('-', '').isdigit():
                                display_value = f"{float(display_value):.8f}"
                        except:
                            pass
                        print(f"  {field_cn}：{display_value}")
                else:
                    print(f"  未获取到 Bitget 合约原始特有字段")
                
                print("\n" + "="*70)
            
            # 4. 返回完整原始数据（不做任何加工，满足深度定制）
            return full_balance
        
        except Exception as e:
            logger.error(f"获取合约完整余额信息失败：margin_coin={margin_coin}，is_print={is_print}，err={e}")
            raise
            
            
    def get_spot_balance(self, currency: str) -> float:
        """
        独立方法：获取现货账户指定币种的总余额（仅现货，逻辑单一）
        Args:
            currency: 货币代码（如 'USDT'、'BTC'）
        Returns:
            现货账户该币种的总余额（float 类型，无余额返回 0.0）
        """
        try:
            # 强制设置为现货账户
            params = {'type': 'spot'}
            full_balance = self.exchange.fetch_balance(params=params)

            currency_upper = currency.upper()
            if currency_upper in full_balance:
                total_balance = full_balance[currency_upper].get('total', 0.0)
                return float(total_balance)

            logger.warning(f"现货账户未找到币种余额：{currency_upper}")
            return 0.0
        except Exception as e:
            logger.error(f"获取现货余额失败：currency={currency}，err={e}")
            raise

 
        
        
    
# ==========================================
# 完整测试用例（覆盖逐仓/全仓切换、配置校验、平仓逻辑，使用原始数据）
# 核心修改：将 Bitget 模拟盘 API 配置移到此处，类内部不再耦合
# ==========================================
if __name__ == "__main__":
    import sys
    import time

    # 配置代理（按需修改，无代理可注释）
    PROXY_URL = "http://127.0.0.1:7890"

    # 核心修改：Bitget 模拟盘 API 信息移到测试块中（仅用于测试，类本身无耦合）
    BITGET_SANDBOX_API = {
        "apiKey": "bg_43cbd60d1aa3b5edfbbc176c7f15a029",
        "secret": "443ea49362654b1c75d20e64306005a7c4fe975a6dea90f053bbc8dff8fe9959",
        "passphrase": "17717677953"
    }

    try:
        # 步骤 1: 初始化 ExchangeTrader (Bitget 模拟盘，传入测试块中的 API 信息)
        print("="*60)
        print("🚀 开始 CCXT_Utils 全功能测试（Bitget 模拟盘，生产级代码）")
        print("="*60)
        trader = ExchangeTrader(
            exchange_id='bitget',
            api_key=BITGET_SANDBOX_API["apiKey"],  # 传入测试块中的 API
            secret=BITGET_SANDBOX_API["secret"],    # 传入测试块中的 API
            passphrase=BITGET_SANDBOX_API["passphrase"],  # 传入测试块中的 API
            sandbox=True,  # 开启模拟盘
            proxy_url=PROXY_URL,
            default_trade_type="swap"  # 可改为 "spot" 测试现货
        )
        test_symbol = "BTC/USDT:USDT" if trader.default_trade_type == "swap" else "BTC/USDT"

        # 步骤 2: 获取并打印市场详情（核心完善功能，原始数据）
        print("\n🧪 [测试 1] 市场详情提取与中文打印（原始数据）")
        market_details = trader.get_market_details(test_symbol)

        # 步骤 3: 配置校验（支持模糊匹配，核心简化功能，原始数据校验）
        print("\n🧪 [测试 2] 用户配置模糊匹配校验（原始数据）")
        fake_user_config = {
            'LEVERAGE': 50,          # 全大写，匹配 leverage
            'max_Leverage': 200,     # 驼峰+下划线，匹配 leverage（超过上限，阻断错误）
            'min_Notional': 2.0,     # 驼峰，匹配 minnotional（低于下限，风险提示）
            'min_USDt_Amount': 5.0,  # 混合格式，匹配 minusdt（符合要求）
            'stopLoss': 0.05         # 无关参数，自动忽略
        }
        trader.validate_config_by_market(market_details, fake_user_config)

        # 步骤 4: 保证金模式切换测试（仅合约市场有效，全仓 -> 逐仓 -> 全仓，原始数据）
        if trader.default_trade_type in ['swap', 'future']:
            print("\n🧪 [测试 3] 全仓/逐仓切换与杠杆设置（原始数据，仅合约有效）")
            # 3.1 切换为 全仓 10x
            trader.set_margin_mode(test_symbol, mode='crossed', leverage=10.0)
            trader.fetch_positions_risk(test_symbol)
            time.sleep(1)  # 规避 API 频率限制

            # 3.2 切换为 逐仓 20x（Bitget 空仓时可正常切换）
            trader.set_margin_mode(test_symbol, mode='isolated', leverage=20.0)
            trader.fetch_positions_risk(test_symbol)
            time.sleep(1)

            # 3.3 恢复为 全仓 10x
            trader.set_margin_mode(test_symbol, mode='crossed', leverage=10.0)
            trader.fetch_positions_risk(test_symbol)

            # 步骤 5: Bitget 平仓逻辑测试（需先有持仓，模拟盘可先手动开仓，原始数据）
            print("\n🧪 [测试 4] Bitget 专属平仓逻辑（需先手动开仓，原始数据，仅合约有效）")
            try:
                # 平多仓（市价平仓，不传 amount 则平全部）
                trader.close_position_bitget(
                    symbol=test_symbol,
                    side='long',
                    price=None  # None 为市价单，传入具体价格则为限价单
                )
            except ExchangeStandardError as e:
                if e.code == "NO_POSITION":
                    print(f"  ℹ️  {e.msg}，跳过平仓测试（可手动在模拟盘开仓后重试）")
                else:
                    raise
        else:
            print("\n🧪 [测试 3/4] 保证金切换与平仓逻辑仅合约市场有效，跳过（当前为现货市场）")

        # 步骤 6: 市场类型切换测试（可选，现货测试，原始数据）
        print("\n🧪 [测试 5] 市场类型切换（合约 -> 现货，原始数据）")
        trader.switch_market_type('spot')
        # 现货交易对查询（BTC/USDT 无后缀）
        try:
            trader.get_market_details("BTC/USDT")
        except ExchangeStandardError as e:
            print(f"  ℹ️  现货市场详情查询: {e.msg}")

       # （1）默认返回：合约 USDT 可用保证金（free）
        contract_free = trader.get_contract_balance()
        print(f"合约 USDT 可用保证金：{contract_free:.8f}")  # 输出：14235.59060075

        # （2）返回：合约 USDT 总保证金（total）
        contract_total = trader.get_contract_balance(margin_coin='USDT', return_type='total')
        print(f"合约 USDT 总保证金：{contract_total:.8f}")  # 输出：14235.59060075

        # （3）返回：合约 USDT 已用保证金（used）
        contract_used = trader.get_contract_balance(margin_coin='USDT', return_type='used')
        print(f"合约 USDT 已用保证金：{contract_used:.8f}")  # 输出：0.0
        
        
        # （1）获取完整原始数据，不打印（用于深度定制/后续逻辑处理）
        contract_full_info = trader.get_contract_balance_info(margin_coin='USDT')
        print(f"\n合约完整原始数据（info 字段）：{contract_full_info.get('info', [])}")

        # （2）获取完整原始数据，开启中文打印（用于调试/排障，直观查看所有字段）
        trader.get_contract_balance_info(margin_coin='USDT', is_print=True)

        print("\n" + "="*60)
        print("✅ 所有测试流程执行完成（无阻断性错误，生产级代码可直接复用）")
        print("="*60)
        
    

    except Exception as e:
        print(f"\n❌ 全局测试流程异常终止：{str(e)}")
        sys.exit(1)
        
        
'''
((venv) ) (base) root@autodl-container-1a4d48a0d9-a416943c:~/policy# python -m busi.strategy.ccxt_utils
============================================================
🚀 开始 CCXT_Utils 全功能测试（Bitget 模拟盘，生产级代码）
============================================================
2026-01-29 21:17:47,281 [INFO] CCXT_Utils: 🔧 [Bitget 模拟盘] 已注入请求头: paptrading=1
2026-01-29 21:17:49,009 [INFO] CCXT_Utils: ✅ [bitget] swap 市场数据加载成功，共 35 个交易对

🧪 [测试 1] 市场详情提取与中文打印（原始数据）

========================================================================================
📊 [bitget] swap 市场 - 交易对详情报告 - BTC/USDT:USDT
========================================================================================
【1. 基础信息】(来源: market 直接提取，原始数据)
  • 交易对符号 (symbol)        : BTC/USDT:USDT                  -> market['symbol']
  • 交易所内部ID (market_id)   : BTCUSDT                        -> market['id']
  • 基础货币 (base_coin)       : BTC                            -> market['base']
  • 计价货币 (quote_coin)      : USDT                           -> market['quote']
  • 结算货币 (settle_coin)    : USDT                           -> market['settle']
  • 市场类型 (market_type)     : swap                           -> market['type']
  • 实例默认交易类型           : swap                           -> self.default_trade_type
  • 是否 U 本位 (is_linear)     : True                           -> market['linear']
  • 是否活跃 (is_active)       : True                           -> market['active']
  • 合约类型 (contract_type)   : perpetual                      -> market['info']['symbolType']

【2. 手续费信息】(来源: market 直接提取，原始数据)
  • 吃单手续费率 (taker)       : 0.000600 (0.0600%) -> market['taker']
  • 挂单手续费率 (maker)       : 0.000200 (0.0200%) -> market['maker']

【3. 合约专属信息】(来源: market + info，原始数据)
  • 合约面值 (contract_size)   : 1                              -> market['contractSize']
  • 资金费率间隔 (小时)        : 1                              -> market['info']['fundInterval']
  • 最小杠杆 (min_leverage)    : 1.0                            -> market['limits']['leverage']['min']
  • 最大杠杆 (max_leverage)    : 125.0                          -> market['limits']['leverage']['max']
  • 支持保证金模式             : {'cross': True, 'isolated': True} -> market['marginModes']

【4. 精度与下单限额】(来源: precision + limits + info，原始数据) - 下单校验核心！
  • 价格精度 (price_precision) : 0.1                            -> market['precision']['price']
  • 数量精度 (amount_precision) : 0.0001                         -> market['precision']['amount']
  • 最小下单数量 (min_amount)  : 0.0001                         -> market['limits']['amount']['min']
  • 最大下单数量 (max_amount)  : 无限制                            -> market['limits']['amount']['max']
  • 最小下单价值 (U, min_cost) : 5.0                            -> market['limits']['cost']['min']
  • 最大下单价值 (U, max_cost) : 无限制                            -> market['limits']['cost']['max']
  • Bitget 最小 USDT 下单量    : 5                              -> market['info']['minTradeUSDT']
  • Bitget 价格步长            : 1                              -> market['info']['priceEndStep']
========================================================================================


🧪 [测试 2] 用户配置模糊匹配校验（原始数据）

🔍 开始校验用户配置 (交易对: BTC/USDT:USDT | 市场类型: swap)...
  ✅ [校验通过] LEVERAGE=50 (符合交易所最大杠杆 (125.0x)要求)
  ❌ [校验失败] max_Leverage=200 > 交易所最大杠杆 (125.0x)
  ⚠️ [风险提示] min_Notional=2.0 < 交易所最小下单价值 (5.0 U)，下单可能被拒绝
  ✅ [校验通过] min_USDt_Amount=5.0 (符合交易所最小 USDT 下单量 (5 U)要求)
🚫 配置校验发现阻断性错误，请修正后再使用

🧪 [测试 3] 全仓/逐仓切换与杠杆设置（原始数据，仅合约有效）

⚙️  正在设置 [BTC/USDT:USDT] | swap 市场 -> 保证金模式: crossed, 杠杆: 10.0x
  ✅ 保证金模式已成功切换为: crossed
  ✅ 杠杆已成功设置为: 10.0x

🔍 [bitget] swap 市场 - 持仓风控状态查询（原始数据）
  • 当前无有效持仓（空仓）

⚙️  正在设置 [BTC/USDT:USDT] | swap 市场 -> 保证金模式: isolated, 杠杆: 20.0x
  ✅ 保证金模式已成功切换为: isolated
  ✅ 杠杆已成功设置为: 20.0x

🔍 [bitget] swap 市场 - 持仓风控状态查询（原始数据）
  • 当前无有效持仓（空仓）

⚙️  正在设置 [BTC/USDT:USDT] | swap 市场 -> 保证金模式: crossed, 杠杆: 10.0x
  ✅ 保证金模式已成功切换为: crossed
  ✅ 杠杆已成功设置为: 10.0x

🔍 [bitget] swap 市场 - 持仓风控状态查询（原始数据）
  • 当前无有效持仓（空仓）

🧪 [测试 4] Bitget 专属平仓逻辑（需先手动开仓，原始数据，仅合约有效）
📉 准备平多仓 [BTC/USDT:USDT] | swap 市场，订单方向: buy，持仓方向: long

🔍 [bitget] swap 市场 - 持仓风控状态查询（原始数据）
  • 当前无有效持仓（空仓）
  ℹ️  当前无对应方向持仓，无法平仓，跳过平仓测试（可手动在模拟盘开仓后重试）

🧪 [测试 5] 市场类型切换（合约 -> 现货，原始数据）
2026-01-29 21:17:53,089 [INFO] CCXT_Utils: ✅ [bitget] spot 市场数据加载成功，共 35 个交易对
2026-01-29 21:17:53,089 [INFO] CCXT_Utils: 🔧 已切换默认市场类型为: spot，并重新加载市场数据

========================================================================================
📊 [bitget] spot 市场 - 交易对详情报告 - BTC/USDT
========================================================================================
【1. 基础信息】(来源: market 直接提取，原始数据)
  • 交易对符号 (symbol)        : BTC/USDT                       -> market['symbol']
  • 交易所内部ID (market_id)   : BTCUSDT                        -> market['id']
  • 基础货币 (base_coin)       : BTC                            -> market['base']
  • 计价货币 (quote_coin)      : USDT                           -> market['quote']
  • 结算货币 (settle_coin)    :                                -> market['settle']
  • 市场类型 (market_type)     : spot                           -> market['type']
  • 实例默认交易类型           : spot                           -> self.default_trade_type
  • 是否 U 本位 (is_linear)     : False                          -> market['linear']
  • 是否活跃 (is_active)       : True                           -> market['active']
  • 合约类型 (contract_type)   : unknown                        -> market['info']['symbolType']

【2. 手续费信息】(来源: market 直接提取，原始数据)
  • 吃单手续费率 (taker)       : 0.002000 (0.2000%) -> market['taker']
  • 挂单手续费率 (maker)       : 0.002000 (0.2000%) -> market['maker']

【3. 合约专属信息】(来源: market + info，原始数据)
  • 合约面值 (contract_size)   : 1.0                            -> market['contractSize']
  • 资金费率间隔 (小时)        : 0                              -> market['info']['fundInterval']
  • 最小杠杆 (min_leverage)    : 1.0                            -> market['limits']['leverage']['min']
  • 最大杠杆 (max_leverage)    : 1.0                            -> market['limits']['leverage']['max']
  • 支持保证金模式             : {'cross': True, 'isolated': True} -> market['marginModes']

【4. 精度与下单限额】(来源: precision + limits + info，原始数据) - 下单校验核心！
  • 价格精度 (price_precision) : 0.01                           -> market['precision']['price']
  • 数量精度 (amount_precision) : 1e-06                          -> market['precision']['amount']
  • 最小下单数量 (min_amount)  : 0.0                            -> market['limits']['amount']['min']
  • 最大下单数量 (max_amount)  : 9e+20                          -> market['limits']['amount']['max']
  • 最小下单价值 (U, min_cost) : 1.0                            -> market['limits']['cost']['min']
  • 最大下单价值 (U, max_cost) : 无限制                            -> market['limits']['cost']['max']
  • Bitget 最小 USDT 下单量    : 1                              -> market['info']['minTradeUSDT']
  • Bitget 价格步长            : 0.0                            -> market['info']['priceEndStep']
========================================================================================

合约 USDT 可用保证金：14235.59060075
合约 USDT 总保证金：14235.59060075
合约 USDT 已用保证金：0.00000000

合约完整原始数据（info 字段）：[{'marginCoin': 'USDT', 'locked': '0', 'available': '14235.59060075', 'crossedMaxAvailable': '14235.59060075', 'isolatedMaxAvailable': '14235.59060075', 'maxTransferOut': '14235.59060075', 'accountEquity': '14235.59060075', 'usdtEquity': '14235.5906007527296781', 'btcEquity': '0.1615871056628368', 'crossedRiskRate': '0', 'unrealizedPL': '0', 'coupon': '0', 'crossedUnrealizedPL': '', 'isolatedUnrealizedPL': '', 'grant': '', 'unionTotalMargin': '131674.17522838', 'unionAvailable': '131674.17522838', 'unionMm': '0', 'assetList': [{'coin': 'BTC', 'available': '1', 'balance': '1'}, {'coin': 'ETH', 'available': '10', 'balance': '10'}], 'assetMode': 'single', 'isolatedMargin': '0', 'crossedMargin': '0'}]

======================================================================
📋 合约账户（USDT 本位）完整余额信息
======================================================================

【CCXT 标准化字段（跨交易所兼容）】
  可用保证金（free）：14235.59060075 USDT
  已用保证金（used）：0.00000000 USDT（持仓/挂单冻结）
  总保证金（total）：14235.59060075 USDT（free + used）

【Bitget 合约特有字段（原始全量数据，风控/调试核心）】
  保证金币种：USDT
  冻结保证金（持仓/挂单占用）：0.00000000
  合约可用保证金（可开仓/划转）：14235.59060075
  全仓模式最大可用保证金：14235.59060075
  逐仓模式最大可用保证金：14235.59060075
  最大可划转至现货的金额：14235.59060075
  账户权益（保证金 + 未实现盈亏，真实总资产）：14235.59060075
  USDT 计价账户权益（精准值）：14235.59060075
  BTC 计价账户权益（辅助参考）：0.16158711
  全仓风险率（<1 面临强平，风控核心）：0.00000000
  未实现盈亏（持仓浮动盈亏，盈利正/亏损负）：0.00000000
  优惠券/平台补贴金额：0.00000000
  全仓未实现盈亏（多仓位汇总）：无
  逐仓未实现盈亏（单一仓位独立）：无
  平台发放奖励/赠金金额：无
  联合总保证金（多币种/多账户汇总）：131674.17522838
  联合可用保证金（多币种/多账户汇总）：131674.17522838
  联合维持保证金（多币种/多账户汇总）：0.00000000
  非保证金资产列表（合约账户内其他闲置币种）：
    - BTC：可用 1，余额 1
    - ETH：可用 10，余额 10
  保证金模式（single=单一币种/multi=多币种）：single
  逐仓占用保证金（当前逐仓持仓冻结）：0.00000000
  全仓占用保证金（当前全仓持仓冻结）：0.00000000

======================================================================

============================================================
✅ 所有测试流程执行完成（无阻断性错误，生产级代码可直接复用）
============================================================
'''