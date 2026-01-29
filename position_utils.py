# position_utils.py
import logging
import math

# 初始化日志器，归属"PositionUtils"模块，便于日志溯源
logger = logging.getLogger("PositionUtils")


def calculate_break_even_points(
    entry_price: float,
    position_size: float,
    open_fee_usdt: float,
    tick_size: float,
    slippage_ticks: int = 1
) -> float:
    """
    通用保本点计算（完全复用原有策略逻辑）
    核心作用：计算持仓保本所需的最小价格变动幅度（含手续费+滑点成本）
    
    :param entry_price: 开仓均价（USD/币）
    :param position_size: 持仓数量（币）
    :param open_fee_usdt: 开仓手续费（USDT，单边）
    :param tick_size: 交易对最小价格变动单位（如0.001）
    :param slippage_ticks: 预估滑点对应的最小变动单位数，默认1个tick
    :return: 保本所需的价格变动幅度（USD/币），即价格变动≥此值才盈利
    """
    # 防护逻辑：持仓量/最小变动单位无效时，返回默认保本幅度（10个tick）
    if position_size <= 0 or tick_size <= 0: 
        return tick_size * 10

    # 总成本计算：双边手续费（开仓+平仓）
    total_fee_usdt = open_fee_usdt * 2 
    # 单位持仓的手续费成本（USDT/币）
    fee_cost_per_unit = total_fee_usdt / position_size
    # 手续费成本对应的最小变动单位数（便于和滑点合并计算）
    fee_ticks_float = fee_cost_per_unit / tick_size
    # 滑点成本：预估滑点对应的USD金额（1个tick * 最小变动单位）
    slippage_cost = slippage_ticks * tick_size
    
    # 总保本成本：手续费成本 + 滑点成本（USD/币）
    raw_dist = fee_cost_per_unit + slippage_cost
    # 向上取整到最近的tick数（确保覆盖所有成本，避免保本计算不足）
    final_ticks = math.ceil(raw_dist / tick_size)
    # 最终保本幅度：取整后的tick数 * 最小变动单位（USD/币）
    final_dist = final_ticks * tick_size

    # 日志输出：保本计算明细（便于复盘成本构成）
    logger.info(
        f"🎯 [保本精算] 仓位:{position_size} | 开仓价:{entry_price:.5f} | "
        f"💰双边费估:{total_fee_usdt:.4f}U (单边{open_fee_usdt:.4f}) | "
        f"📉每币成本:{fee_cost_per_unit:.5f}U (≈{fee_ticks_float:.1f} ticks) | "
        f"🌊预设滑点:{slippage_ticks} ticks | "
        f"👉 最终保本需: {final_ticks} ticks ({final_dist:.5f} U)"
    )
    return final_dist


def calculate_position_size(
    price: float,
    current_balance: float,
    position_ratio: float,
    leverage: float,
    market: dict,
    safety_margin: float = 0.98,
    min_amount_threshold: float = 6.0
) -> float:
    """
    通用仓位大小计算（完全复用原有策略逻辑）
    核心作用：根据账户余额、风控参数、杠杆计算可开仓的最大数量（含风控防护）
    
    :param price: 当前市场价格（USD/币）
    :param current_balance: 账户可用余额（USDT）
    :param position_ratio: 风控仓位比例（0~1，如0.1表示用10%余额开仓）
    :param leverage: 开仓杠杆倍数（如10倍、20倍）
    :param market: 交易所市场数据字典（ccxt返回，含最小开仓量等规则）
    :param safety_margin: 安全边际系数（默认0.98，预留2%余额避免爆仓）
    :param min_amount_threshold: 最小开仓金额阈值（USD，默认6USDT，低于则强制调整）
    :return: 最终可开仓数量（币），满足交易所规则+风控要求
    """
    # 1. 基础保证金计算：可用余额 * 风控比例（仅用指定比例的余额开仓）
    margin = current_balance * position_ratio
    # 2. 安全边际调整：预留部分余额，避免因价格波动触发爆仓
    margin = margin * safety_margin
    
    # 3. 交易所规则获取：最小开仓数量（币）
    min_amount = market['limits']['amount']['min']
    # 4. 理论开仓数量：保证金 * 杠杆 / 当前价格（杠杆放大可开仓数量）
    raw_amount = (margin * leverage) / price
    # 5. 规则校验1：确保开仓量≥交易所最小要求
    final_amount = max(raw_amount, min_amount)
    
    # 6. 规则校验2：确保开仓金额≥最小阈值（避免小额开仓手续费占比过高）
    if final_amount * price < min_amount_threshold:
         final_amount = min_amount_threshold / price

    return final_amount