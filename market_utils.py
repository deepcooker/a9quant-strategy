# market_utils.py 最终修复版
import logging
from typing import Dict, Optional

logger = logging.getLogger("MarketUtils")

def get_tick_size(
    market: Dict,
    symbol: str,
    default_tick_size: float = 0.001
) -> float:
    """
    通用获取交易对最小变动单位（修复版）
    现在能够正确处理Bitget的precision.price=0.1的情况
    """
    try:
        # 1. 优先使用tickSize字段
        if 'tickSize' in market and market['tickSize'] is not None:
            tick_size = float(market['tickSize'])
            logger.info(f"✅ 获取到 {symbol} 的tickSize: {tick_size}")
            return tick_size

        # 2. 其次使用minPrice字段
        if 'minPrice' in market and market['minPrice'] is not None:
            tick_size = float(market['minPrice'])
            logger.info(f"✅ 获取到 {symbol} 的minPrice: {tick_size}")
            return tick_size

        # 3. 基于precision.price计算（修复的核心！）
        if 'precision' in market and 'price' in market['precision']:
            price_precision = market['precision']['price']
            logger.debug(f"[Debug] {symbol} 的price precision: {price_precision}, 类型: {type(price_precision)}")
            
            if price_precision is None:
                logger.warning(f"{symbol} price precision为空，使用默认值")
                return default_tick_size
                
            # 情况1：price_precision是整数（如5）→ 0.00001
            if isinstance(price_precision, int):
                tick_size = 10 ** -price_precision
                logger.info(f"✅ 通过整数precision计算出 {symbol} 的tick size: {tick_size}")
                return tick_size
                
            # 情况2：price_precision是浮点数（如0.1）→ 直接使用
            elif isinstance(price_precision, float):
                tick_size = price_precision
                logger.info(f"✅ 通过浮点数precision获取 {symbol} 的tick size: {tick_size}")
                return tick_size
                
            # 情况3：price_precision是字符串
            elif isinstance(price_precision, str):
                try:
                    # 尝试转为浮点数
                    tick_size = float(price_precision)
                    logger.info(f"✅ 通过字符串precision获取 {symbol} 的tick size: {tick_size}")
                    return tick_size
                except ValueError:
                    # 如果是整数字符串，如"5"
                    if price_precision.isdigit():
                        tick_size = 10 ** -int(price_precision)
                        logger.info(f"✅ 通过整数字符串precision计算出 {symbol} 的tick size: {tick_size}")
                        return tick_size
                    else:
                        logger.warning(f"无法解析的price precision字符串: {price_precision}")
                        return default_tick_size
            else:
                logger.warning(f"未知的price precision类型: {type(price_precision)}")
                return default_tick_size

        # 4. Bitget USDT合约的特殊处理（兜底）
        if symbol.endswith(':USDT') and 'bitget' in str(market).lower():
            tick_size = 0.1
            logger.info(f"✅ 使用Bitget USDT合约默认tick size: {tick_size}")
            return tick_size

        logger.warning(f"⚠️ 无法自动获取 {symbol} 的tick size，使用默认值 {default_tick_size}")
        return default_tick_size

    except Exception as e:
        logger.error(f"❌ 获取 {symbol} 的tick size异常: {e}")
        return default_tick_size


    
    
