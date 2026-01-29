import math

# ========== 模拟 ExchangeTrader 类（让代码可独立运行） ==========
class MockExchange:
    def __init__(self):
        # 模拟 bitget 交易所 BTC/USDT:USDT 的精度参数
        self.markets = {
            'BTC/USDT:USDT': {
                'precision': {
                    'price': '0.01',      # tick_size (价格最小变动单位)
                    'amount': '0.0001'    # amount_precision (数量最小变动精度)
                },
                'limits': {
                    'amount': {'min': '0.0001'},  # min_amount (最小下单数量)
                    'cost': {'min': '5.0'}        # min_notional (最小名义价值)
                }
            }
        }
    
    def market(self, symbol):
        return self.markets.get(symbol, {})

class ExchangeTrader:
    def __init__(self, exchange_id='bitget', api_key='', secret='', passphrase='', sandbox=False):
        self.exchange = MockExchange()  # 模拟交易所实例

# ========== mock / 简化 state ==========
class MockState:
    def __init__(self):
        self.tick_size = None
        self.amount_precision = None
        self.min_amount = None
        self.min_notional = None

        self.total_long_amount = 0.0
        self.total_short_amount = 0.0

# ========== mock strategy ==========
class MockStrategy:
    def __init__(self, exchange, symbol):
        self.trader = exchange
        self.symbol = symbol
        self.leverage = 10

        self.state = MockState()

        self.order_params = {
            "initial_usdt_amount": 5.0,
            "max_usdt_amount": 80.0,
            "add_multiplier": 1.1,
        }

    # ===== 注入 market 精度 =====
    def load_market_precision(self):
        market = self.trader.exchange.market(self.symbol)

        self.state.tick_size = float(market['precision']['price'])
        self.state.amount_precision = float(market['precision']['amount'])
        self.state.min_amount = float(market['limits']['amount']['min'])
        self.state.min_notional = float(market['limits']['cost']['min'])

        print("📏 Precision Injected")
        print(f" tick_size       = {self.state.tick_size}")
        print(f" amount_precision= {self.state.amount_precision}")
        print(f" min_amount      = {self.state.min_amount}")
        print(f" min_notional    = {self.state.min_notional}")

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
        initial_usdt = self.order_params["initial_usdt_amount"]
        max_total_margin = self.order_params["max_usdt_amount"]
        add_multiplier = self.order_params["add_multiplier"]

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

# ========== 测试入口 ==========
if __name__ == "__main__":
    # 1. 初始化交易所和策略
    exchange = ExchangeTrader(
        exchange_id='bitget',
        api_key='test_key',
        secret='test_secret',
        passphrase='test_pass',
        sandbox=False
    )
    symbol = 'BTC/USDT:USDT'
    s = MockStrategy(exchange, symbol)

    # 2. 注入交易所精度参数
    s.load_market_precision()

    # 3. 测试价格（模拟 BTC 价格 90000 USDT）
    test_price = 90000.0
    print("\n=== 测试参数 ===")
    print(f"测试价格 = {test_price} USDT")
    print(f"杠杆 = {s.leverage}x")
    print(f"初始保证金 = {s.order_params['initial_usdt_amount']} USDT")
    print(f"最大总保证金 = {s.order_params['max_usdt_amount']} USDT")
    print(f"加仓系数 = {s.order_params['add_multiplier']}\n")

    # 4. 测试不同层数的下单量
    print("=== 测试不同加仓层数的下单数量 ===")
    for order_index in range(10):
        amt = s.calculate_order_amount(order_index, test_price, 'long')
        print(f"  层数 {order_index:02d} → 下单数量 = {amt} BTC")
        
        # 核心断言（验证逻辑正确性）
        if amt > 0:
            # 断言1：数量不超过 0.01 BTC（防止下单量过大）
            assert amt < 0.01, f"❌ 层数 {order_index} 下单量过大：{amt} ≥ 0.01"
            # 断言2：精度符合 4 位小数（0.0001 精度）
            assert round(amt, 4) == amt, f"❌ 层数 {order_index} 精度错误：{amt}"
            # 断言3：数量是 amount_precision 的整数倍
            assert abs((amt / s.state.amount_precision) - round(amt / s.state.amount_precision)) < 1e-9, \
                f"❌ 层数 {order_index} 数量不符合精度要求：{amt}"

    # 5. 测试持仓接近上限的情况
    print("\n=== 测试持仓接近保证金上限 ===")
    # 模拟已用 79 USDT 保证金（接近 80 上限）
    s.state.total_long_amount = (79 * s.leverage) / test_price
    amt = s.calculate_order_amount(1, test_price, 'long')
    print(f"  已用保证金≈79 USDT → 下单数量 = {amt} BTC")
    assert amt == 0.0, "❌ 保证金上限校验失败"

    # 6. 测试价格≤0的情况
    print("\n=== 测试价格≤0 ===")
    amt = s.calculate_order_amount(0, 0, 'long')
    print(f"  价格=0 → 下单数量 = {amt} BTC")
    assert amt == 0.0, "❌ 价格≤0 校验失败"

    print("\n✅ 所有测试通过！")