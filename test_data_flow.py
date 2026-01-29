# test_data_flow.py
import asyncio
import sys
import os
import time

# 参考 martin.py，解决项目内模块导入问题
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from ccxt_utils import ExchangeTrader
# 假设我们将新写的两个模块放在项目根目录
from data_synchronizer import DataSynchronizer
from account_state import AccountState

async def main():
    print("🧪 数据底座集成测试开始...\n")
    
    
     # 配置代理（按需修改，无代理可注释）
    PROXY_URL = "http://127.0.0.1:7890"

    # 核心修改：Bitget 模拟盘 API 信息移到测试块中（仅用于测试，类本身无耦合）
    BITGET_SANDBOX_API = {
        "apiKey": "bg_43cbd60d1aa3b5edfbbc176c7f15a029",
        "secret": "443ea49362654b1c75d20e64306005a7c4fe975a6dea90f053bbc8dff8fe9959",
        "passphrase": "17717677953"
    }

    # ==================== 1. 初始化 ====================
    print("1. 初始化交易接口与数据模块...")
    try:
        # TODO: 请替换为你的真实配置，建议使用模拟盘！
        trader = ExchangeTrader(
            exchange_id='bitget',
            api_key=BITGET_SANDBOX_API["apiKey"],  # 传入测试块中的 API
            secret=BITGET_SANDBOX_API["secret"],    # 传入测试块中的 API
            passphrase=BITGET_SANDBOX_API["passphrase"],  # 传入测试块中的 API
            sandbox=True,  # 开启模拟盘
            proxy_url=PROXY_URL,
            default_trade_type="swap"  # 可改为 "spot" 测试现货
        )
        print("   ✅ ExchangeTrader 初始化成功")
    except Exception as e:
        print(f"   ❌ 交易接口初始化失败: {e}")
        return

    # TODO: 可替换为你想要测试的交易对，需与后续WS订阅匹配
    test_symbol = "BTC/USDT:USDT"
    data_sync = DataSynchronizer(trader, test_symbol)
    acc_state = AccountState(data_sync)
    print("   ✅ 数据同步器 & 账户状态 初始化成功")

    # ==================== 2. 测试REST强制同步 ====================
    print("\n2. 测试REST API强制同步（获取账户真实状态）...")
    sync_ok = await data_sync.force_rest_sync()
    if not sync_ok:
        print("   ❌ REST同步失败，测试终止。请检查网络或API权限。")
        return
    print("   ✅ REST同步成功")

    # ==================== 3. 测试数据清洗与转换 ====================
    print("\n3. 测试业务数据转换 (AccountState.update)...")
    acc_state.update()

    if acc_state.account:
        print(f"   ✅ 账户数据就绪。钱包余额: {acc_state.account.wallet_balance:.2f} USDT")
    else:
        print("   ❌ 账户数据为空")
        return

    pos_count = len(acc_state.positions)
    print(f"   ✅ 持仓数据就绪。共有 {pos_count} 个方向的持仓。")

    # ==================== 4. 测试对风控层的输出 ====================
    print("\n4. 验证给中央风控银行 (RiskManager) 的数据格式...")
    risk_snapshot = acc_state.get_risk_snapshot()
    if risk_snapshot:
        print("   ✅ 风控快照生成成功，包含以下关键字段:")
        for key, value in risk_snapshot.items():
            if key != 'timestamp':
                print(f"      - {key}: {value}")
    else:
        print("   ❌ 风控快照为空")

    # ==================== 5. 测试模拟WS更新 ====================
    print("\n5. 模拟WebSocket推送更新（测试状态实时性）...")
    # 注意：这里模拟的数据结构需要和你实际收到的Bitget WS格式一致
    mock_ws_data = [
        {
            'instId': 'BTCUSDT',  # 需与 clean_symbol 匹配
            'holdSide': 'long',
            'total': '0.001',
            'openPriceAvg': '60000',
            'unrealizedPL': '15.0',
            'leverage': '3',
            'marginSize': '20.0'
        }
    ]
    print(f"   注入模拟数据: {mock_ws_data[0]['holdSide']} 仓, 数量 {mock_ws_data[0]['total']}")
    data_sync.update_from_ws_position(mock_ws_data)
    acc_state.update()

    updated_pos = acc_state.positions.get('long')
    if updated_pos and updated_pos.size == 0.001:
        print(f"   ✅ WS更新成功！最新持仓均价: {updated_pos.entry_price}")
    else:
        print("   ⚠️  模拟更新后数据未达预期，请检查 `update_from_ws_position` 解析逻辑。")

    # ==================== 6. 总结 ====================
    print("\n" + "="*60)
    print("🎉 核心数据流测试完成！")
    print("="*60)
    print("\n【下一步行动建议】")
    print("1. 对照测试输出，检查各环节 ✅/❌ 状态。")
    print("2. 根据Bitget WebSocket实际返回格式，微调 `data_synchronizer.py` 中的 `update_from_ws_position` 函数。")
    print("3. 将测试成功的 `AccountState.get_risk_snapshot()` 输出，用于驱动你的 `advanced_risk.py` 风控银行。")
    print("4. 在实际策略循环中，定时调用 `data_sync.force_rest_sync()` 以确保状态同步。")

if __name__ == "__main__":
    asyncio.run(main())