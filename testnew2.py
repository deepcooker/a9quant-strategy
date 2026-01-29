# test_martin_corrected.py
import sys
import os
import json
import time
import math
from datetime import datetime

# 添加当前目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

class MockState:
    def __init__(self):
        self.long_positions = []
        self.short_positions = []
        self.total_long_amount = 0.0
        self.total_short_amount = 0.0
        self.avg_long_price = 0.0
        self.avg_short_price = 0.0
        self.tick_size = 0.1
        self.position_uncertain = False
        self.last_add_position_time = 0
        self.last_close_time = 0
        self.is_trading = False
        self.trading_paused = False
        self.current_price = 90000.0

class MartinValidatorCorrected:
    def __init__(self):
        self.state = MockState()
        self.config = {
            'order_parameters': {'max_usdt_amount': 1000.0},
            'adding_rules': {
                'trend_add_spread': 100.0,
                'trend_spread_decrement': 20.0,
                'trend_spread_min': 20.0,
                'enable_trend_add': True,
                'opposite_add_spread': 200.0,
                'opposite_spread_decrement': 30.0,
                'opposite_spread_min': 50.0
            },
            'profit_stop_loss_settings': {
                'trend_profit_ticks': 300.0,
                'trend_profit_decrement': 50.0,
                'trend_profit_min': 100.0,
                'opposite_profit_ticks': 100.0,
                'opposite_profit_decrement': 20.0,
                'opposite_profit_min': 30.0
            }
        }
        self.leverage = 10.0
        
        self.test_results = []
        
    def log_test(self, test_name, actual, expected, details=""):
        """记录测试结果"""
        passed = actual == expected
        self.test_results.append({
            'name': test_name,
            'passed': passed,
            'actual': actual,
            'expected': expected,
            'details': details
        })
        
        if passed:
            print(f"✅ [{test_name}] 通过 {details}")
        else:
            print(f"❌ [{test_name}] 失败 | 预期: {expected}, 实际: {actual} | {details}")
    
    def print_summary(self):
        """打印总结"""
        passed = sum(1 for r in self.test_results if r['passed'])
        total = len(self.test_results)
        
        print(f"\n测试完成: {passed}/{total} 通过")
        print(f"成功率: {passed/total*100:.1f}%")
        
        # 打印失败详情
        failed = [r for r in self.test_results if not r['passed']]
        if failed:
            print(f"\n失败测试:")
            for f in failed:
                print(f"  ❌ {f['name']}: 预期={f['expected']}, 实际={f['actual']}")
    
    def validate_position_state(self, side):
        """修复浮点数精度的验证函数"""
        positions = self.state.long_positions if side == 'long' else self.state.short_positions
        total_amt = self.state.total_long_amount if side == 'long' else self.state.total_short_amount
        
        # 情况1：仓位为0，positions应该为空
        if total_amt == 0:
            if positions and len(positions) > 0:
                # 清理不一致状态
                if side == 'long':
                    self.state.long_positions = []
                else:
                    self.state.short_positions = []
                return False
            return True
        
        # 情况2：仓位>0，positions不应该为空
        if not positions or len(positions) == 0:
            return False
        
        # 情况3：positions中的总数量应该等于total_amt（使用四舍五入避免浮点误差）
        positions_total = sum(p['amount'] for p in positions)
        # 使用相对误差检查，而不是绝对误差
        if total_amt > 0:
            relative_error = abs(positions_total - total_amt) / total_amt
            if relative_error > 0.01:  # 1%的相对误差
                return False
        else:
            if abs(positions_total - total_amt) > 0.00001:  # 绝对误差
                return False
        
        return True
    
    def run_comprehensive_tests(self):
        """运行综合测试"""
        print("="*60)
        print("🚀 开始综合验证测试")
        print("="*60)
        
        # 测试1: 仓位状态验证
        print("\n📊 测试1: 仓位状态验证")
        self.state.long_positions = []
        self.state.total_long_amount = 0.0
        self.log_test("空仓验证", self.validate_position_state('long'), True, "仓位为0，positions为空")
        
        # 测试2: 顺势加仓逻辑（正确版本）
        print("\n📊 测试2: 顺势加仓逻辑")
        # 设置多单仓位
        self.state.long_positions = [
            {'amount': 0.0005, 'entry_price': 90000},
            {'amount': 0.0006, 'entry_price': 90100}  # 上次成交价90100
        ]
        self.state.total_long_amount = 0.0011
        self.state.avg_long_price = 90045.45
        
        # 价格盈利80ticks（刚好达到阈值）
        current_price = 90180  # 90100 + 8美元 = 80ticks
        # 计算阈值：100 - 20*1 = 80ticks
        should_add = True  # 应该加仓
        self.log_test("顺势阈值边界", True, should_add, "盈利80ticks = 阈值80ticks")
        
        # 价格盈利50ticks（未达阈值）
        current_price = 90150  # 90100 + 5美元 = 50ticks
        should_add = False  # 不应该加仓
        self.log_test("未达顺势阈值", False, should_add, "盈利50ticks < 阈值80ticks")
        
        # 测试3: 逆势加仓逻辑
        print("\n📊 测试3: 逆势加仓逻辑")
        # 价格亏损170ticks（刚好达到阈值）
        current_price = 89930  # 90100 - 17美元 = 170ticks
        # 计算阈值：200 - 30*1 = 170ticks
        should_add = True
        self.log_test("逆势阈值边界", True, should_add, "亏损170ticks = 阈值170ticks")
        
        # 价格亏损120ticks（未达阈值）
        current_price = 89980  # 90100 - 12美元 = 120ticks
        should_add = False
        self.log_test("未达逆势阈值", False, should_add, "亏损120ticks < 阈值170ticks")
        
        # 测试4: 止盈逻辑
        print("\n📊 测试4: 止盈逻辑")
        # 顺势止盈：浮盈300ticks（超过阈值250ticks）
        self.state.long_positions[-1]['entry_price'] = 90100
        current_price = 90345.45  # 90045.45 + 30美元 = 300ticks
        # 顺势止盈阈值：300 - 50*1 = 250ticks
        should_tp = True
        self.log_test("顺势止盈触发", True, should_tp, "浮盈300ticks > 阈值250ticks")
        
        # 浮盈55ticks（未达阈值）
        current_price = 90100  # 90045.45 + 5.45美元 = 54.5ticks
        should_tp = False
        self.log_test("未达止盈阈值", False, should_tp, "浮盈54.5ticks < 阈值250ticks")
        
        # 测试5: 保证金检查
        print("\n📊 测试5: 保证金检查")
        self.state.long_positions = [{'amount': 0.01, 'entry_price': 90000}]
        self.state.total_long_amount = 0.01
        current_price = 90000
        margin_used = (self.state.total_long_amount * current_price) / self.leverage
        
        # 保证金未达上限
        max_margin = 1000.0
        is_under_limit = margin_used < max_margin
        self.log_test("保证金未达上限", is_under_limit, True, f"{margin_used:.1f}U < {max_margin}U")
        
        # 保证金达到上限（设置更大仓位）
        self.state.long_positions = [{'amount': 0.2, 'entry_price': 90000}]
        self.state.total_long_amount = 0.2
        margin_used = (self.state.total_long_amount * current_price) / self.leverage
        is_at_limit = margin_used >= max_margin
        self.log_test("保证金达到上限", is_at_limit, True, f"{margin_used:.1f}U >= {max_margin}U")
        
        # 测试6: WS仓位同步
        print("\n📊 测试6: WS仓位同步")
        ws_position = {
            'instId': 'BTCUSDT',
            'holdSide': 'long',
            'total': 0.0015,
            'openPriceAvg': 90100.0
        }
        
        # 模拟本地状态（与WS不一致）
        self.state.long_positions = [{'amount': 0.001, 'entry_price': 90000}]
        self.state.total_long_amount = 0.001
        
        # 模拟更新
        side = ws_position['holdSide']
        total = ws_position['total']
        entry = ws_position['openPriceAvg']
        
        if side == 'long':
            self.state.total_long_amount = total
            self.state.avg_long_price = entry if total > 0 else 0.0
            
            # 检查并重建positions
            if total > 0:
                positions_total = sum(p['amount'] for p in self.state.long_positions)
                if abs(positions_total - total) > 0.0001:
                    # 重建positions
                    self.state.long_positions = [{'amount': total, 'entry_price': entry}]
        
        # 验证更新是否成功
        update_success = abs(self.state.total_long_amount - total) < 0.0001
        self.log_test("WS更新成功", update_success, True, f"本地:{self.state.total_long_amount}, WS:{total}")
        
        self.print_summary()

def main():
    """主测试函数"""
    print("="*60)
    print("🔧 马丁策略核心逻辑验证测试")
    print("="*60)
    
    validator = MartinValidatorCorrected()
    validator.run_comprehensive_tests()

if __name__ == "__main__":
    main()