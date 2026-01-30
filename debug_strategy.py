# debug_strategy.py
import asyncio
import time
from market_data_hub import MarketDataHub
from data_synchronizer import DataSynchronizer
from account_state import AccountState
from ccxt_utils import ExchangeTrader
from advanced_risk import RiskManager
from trend_engine import TrendEngine

async def main():
    # 1. 初始化核心模块
    trader = ExchangeTrader(exchange_id='bitget', api_key='bg_43cbd60d1aa3b5edfbbc176c7f15a029', secret='443ea49362654b1c75d20e64306005a7c4fe975a6dea90f053bbc8dff8fe9959', passphrase='17717677953', proxy_url='http://127.0.0.1:7890',sandbox=True)
    data_sync = DataSynchronizer(trader, "BTC/USDT:USDT")
    account_state = AccountState(data_sync)
    risk_manager = RiskManager(initial_capital=200, account_state=account_state)
    trend_engine = TrendEngine(risk_manager)
    
    # 2. 等待一些K线数据
    print("等待K线数据累积（约1分钟）...")
    await asyncio.sleep(65)
    
    # 3. 手动触发一次同步和策略检查
    await data_sync.force_rest_sync()
    account_state.update()
    risk_manager.update_from_account_state()
    
    # 4. 模拟一个市场数据（替换为从你的hub获取的真实数据）
    market_data = {
        'price': 50000,
        'ema20': 49000,
        'atr': 500,
        'rsi': 65,  # 故意设为低于70
        'vol_ratio': 1.0
    }
    
    # 5. 调用策略引擎，观察输出
    snapshot = account_state.get_strategy_snapshot('trend')
    test_data = {**market_data, **snapshot}
    
    intent = trend_engine.on_tick(test_data)
    if intent:
        print("⚠️ 策略产生了意图:", intent)
    else:
        print("✅ 策略未产生意图 (符合预期，因为RSI=65<70)")
    
    # 6. 测试一个应该触发的条件
    test_data['rsi'] = 75
    intent2 = trend_engine.on_tick(test_data)
    if intent2:
        print("✅ 策略在RSI=75时正确产生意图:", intent2.get('action'))
    else:
        print("❌ 策略在RSI=75时未触发，需要检查条件")

asyncio.run(main())