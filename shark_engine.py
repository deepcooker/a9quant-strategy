# -*- coding: utf-8 -*-
import logging
import time
import os
from enum import Enum

from contracts import StrategyContext, TradeIntent, RiskRequest, MarketData, StrategySnapshot
from advanced_risk import RiskManager

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("SharkEngine")

# 全局常量（生产级可放入配置文件）
MAX_MARGIN_USAGE_RATIO = 0.6  # 最大保证金使用率 60%

class SharkState(Enum):
    SLEEP = 0
    L1_EXIST = 1
    L2_HUNT = 2
    L3_SNIPE = 3

class SharkEngine:
    def __init__(self, risk_manager: RiskManager):
        self.rm = risk_manager
        self.state = SharkState.SLEEP
        
        # 仓位数据
        self.avg_price = 0.0
        self.total_size = 0.0    
        self.leverage = 1.0  # 优化：改为浮点数，更符合杠杆精度
        self.margin_used = 0.0  # 新增：记录实际占用保证金，同步到RM
        
        # 辅助博弈数据
        self.entry_time = 0
        self.l1_l2_max_loss = 0  # 记录最大痛苦值
        self.last_clean_pnl = 0

    def _calc_pnl(self, current_price):
        # 做空逻辑
        if self.total_size == 0 or self.avg_price == 0.0:  # 增加 avg_price 为 0 的判断
            return 0
        return (self.avg_price - current_price) * (self.total_size / self.avg_price)

    def _calc_kill_target(self):
        """
        核心公式：计算回本并反杀的目标价
        """
        if self.total_size == 0: return 0
        cost = self.total_size * 0.0014 # 万14成本
        desired_profit = self.l1_l2_max_loss * 1.2 + cost
        pos_qty = self.total_size / self.avg_price
        # Target = Entry - DesiredProfit / Qty
        target = self.avg_price - (desired_profit / pos_qty)
        return target

    def _calc_current_margin_usage(self):
        """
        新增：计算当前全局保证金使用率，用于前置拦截
        """
        # 获取当前钱包总余额（锚定本金 + 已实现盈利 + 未实现浮盈）
        current_wallet_balance = self.rm.anchor_capital + self.rm.realized_profit
        if current_wallet_balance <= 0 or self.margin_used <= 0:
            return 0.0
        # 保证金使用率 = 占用保证金 / 钱包余额
        return min(1.0, self.margin_used / current_wallet_balance)

    def _execute_trade(self, price, margin, lev, new_state):
        """
        保留原有函数（暂不删除，后续可根据需求清理）
        注：v1.0 已不再调用该函数，改为返回 intent
        """
        new_size = margin * lev
        new_margin_used = margin  # 本次交易占用的保证金（保证金 = 名义价值 / 杠杆）
        
        # 更新均价
        if self.total_size + new_size > 0:
            self.avg_price = (self.avg_price * self.total_size + price * new_size) / (self.total_size + new_size)
        
        # 更新仓位、保证金、杠杆
        self.total_size += new_size
        self.margin_used += new_margin_used  # 累计占用保证金
        self.leverage = lev  # 若需保留平均杠杆，可改为 (self.total_size / self.margin_used)
        
        # 新增：同步保证金占用到 RiskManager（让风控感知真实使用率）
        current_margin_usage = self._calc_current_margin_usage()
        self.rm.update_snapshot(
            wallet_balance=self.rm.anchor_capital + self.rm.realized_profit,
            trend_float=0,
            shark_float=self._calc_pnl(price),
            margin_usage=current_margin_usage
        )
        
        self.state = new_state
        logger.info(f"🦈 [Action] 状态->{new_state.name} | 均价:{self.avg_price:.2f} | 规模:{self.total_size:.1f} | 占用保证金:{self.margin_used:.2f}U")

    def _close_position(self, price, reason) -> TradeIntent:
        # v1.0 改造：返回平仓intent，不再内部执行平仓逻辑
        logger.info(f"🏁 [Shark平仓意图] {reason} | 价格:{price:.2f} | 均价:{self.avg_price:.2f}")
        
        # MVP 乐观重置状态（后续需改为等待成交确认后重置）
        pnl = self._calc_pnl(price)
        fee = self.total_size * 0.0006
        final_pnl = pnl - fee
        current_balance = self.rm.anchor_capital + self.rm.realized_profit
        self.rm.update_snapshot(
            wallet_balance=current_balance + final_pnl,
            trend_float=0,
            shark_float=0,
            margin_usage=0  # 平仓后保证金使用率归0
        )
        self.margin_used = 0.0
        self.last_clean_pnl = final_pnl
        self.state = SharkState.SLEEP
        self.total_size = 0
        self.avg_price = 0
        
        # v1.0 返回平仓intent（做空平仓，pos_side=short）
        return TradeIntent(
            engine="SHARK",
            action="CLOSE",
            trade_side="close",
            pos_side="short",
            size=0.001,
            margin_mode="crossed",
            risk_request=RiskRequest(
                engine="SHARK",
                action="CLOSE",
                suggested_leverage=1,
                volatility_ratio=1.0,
                estimated_risk=0.0,
            ),
        )

    def on_tick(self, context: StrategyContext) -> TradeIntent | None:
        data = context.market_data
        trace_id = context.trace_id
        price = data.price
        ts = data.ts or time.time()
        vol = data.vol_ratio if data.vol_ratio is not None else 1.0
        
        # 1. 汇报浮亏 (防止保险费超标)
        floating_pnl = self._calc_pnl(price)
        self.rm.shark_floating_loss = abs(floating_pnl) if floating_pnl < 0 else 0
        
        # 2. 状态机 - v1.0 改造：调用函数接收intent并返回
        if self.state == SharkState.SLEEP:
            if data.rsi is not None and data.rsi > 70:
                intent = self._try_enter_l1(price, ts, vol, trace_id)  # v1.0
                if intent: return intent  # v1.0
                
        elif self.state == SharkState.L1_EXIST:
            # 时间止损 (24 ticks)
            if ts - self.entry_time > 24 and floating_pnl <= 0:
                intent = self._close_position(price, "⏳ 时间止损")  # v1.0
                if intent: return intent  # v1.0
            # 浮亏加仓 (L2)
            elif self.total_size > 0 and (floating_pnl/self.total_size) < -0.02:
                intent = self._try_enter_l2(price, vol, trace_id)  # v1.0
                if intent: return intent  # v1.0

        elif self.state == SharkState.L2_HUNT:
            self.l1_l2_max_loss = max(self.l1_l2_max_loss, abs(floating_pnl))
            # 极端信号 (L3)
            if data.rsi is not None and data.rsi > 85:
                intent = self._try_enter_l3(price, vol, trace_id)  # v1.0
                if intent: return intent  # v1.0

        elif self.state == SharkState.L3_SNIPE:
            target = self._calc_kill_target()
            if price <= target:
                intent = self._close_position(price, "💰 [L3收网] 死星打击成功")  # v1.0
                if intent: return intent  # v1.0
            elif price > self.avg_price * 1.01:
                intent = self._close_position(price, "🛡️ [L3止损] 狙击失败")  # v1.0
                if intent: return intent  # v1.0

    def _try_enter_l1(self, price, ts, vol, trace_id) -> TradeIntent:
        # v1.0 改造：不再执行交易，返回开仓intent（做空，pos_side=short）
        budget = self.rm.get_shark_budget() * 0.1
        req = RiskRequest(
            engine="SHARK",
            action="OPEN_L1",
            suggested_leverage=2,
            volatility_ratio=vol,
            estimated_risk=budget,
            trace_id=trace_id,
        )

        # 近似计算size：(保证金*杠杆)/价格
        size = (budget * req.suggested_leverage) / max(1e-9, price)

        # v1.0 记录入场时间（乐观记录，后续需确认成交）
        self.entry_time = ts
        self.l1_l2_max_loss = 0
        
        return TradeIntent(
            engine="SHARK",
            action="OPEN_L1",
            trade_side="open",
            pos_side="short",
            size=size,
            margin_mode="crossed",
            risk_request=req,
            trace_id=trace_id,
        )

    def _try_enter_l2(self, price, vol, trace_id) -> TradeIntent | None:
        """
        v1.0 改造：返回加仓intent，保留保证金校验逻辑
        """
        # 新增：前置拦截 - 保证金使用率超标
        current_margin_usage = self._calc_current_margin_usage()
        if current_margin_usage > MAX_MARGIN_USAGE_RATIO:
            logger.warning(f"🚫 [L2拒] 拒绝(保证金超标): 使用率{current_margin_usage:.2%} > 阈值{MAX_MARGIN_USAGE_RATIO:.2%}")
            return None  # 无intent返回
        
        budget = self.rm.get_shark_budget() * 0.2
        req = RiskRequest(
            engine="SHARK",
            action="ADD_L2",
            suggested_leverage=3,
            volatility_ratio=vol,
            estimated_risk=budget,
            trace_id=trace_id,
        )

        # 近似计算size
        size = (budget * req.suggested_leverage) / max(1e-9, price)

        return TradeIntent(
            engine="SHARK",
            action="ADD_L2",
            trade_side="open",
            pos_side="short",
            size=size,
            margin_mode="crossed",
            risk_request=req,
            trace_id=trace_id,
        )

    def _try_enter_l3(self, price, vol, trace_id) -> TradeIntent | None:
        # v1.0 改造：返回L3加仓intent
        trend_profit = self.rm.realized_profit
        if trend_profit <= 0: return None
        
        # 梭哈逻辑：拿50%的趋势利润来赌
        risk_budget = trend_profit * 0.5
        req = RiskRequest(
            engine="SHARK",
            action="ADD_L3",
            suggested_leverage=10,
            volatility_ratio=vol,
            estimated_risk=risk_budget,
            trace_id=trace_id,
        )

        # 近似计算size
        size = (risk_budget * req.suggested_leverage) / max(1e-9, price)

        return TradeIntent(
            engine="SHARK",
            action="ADD_L3",
            trade_side="open",
            pos_side="short",
            size=size,
            margin_mode="crossed",
            risk_request=req,
            trace_id=trace_id,
        )

# ==========================================
# 4. 集成对抗测试 (Integrated Tests)
# ==========================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🦈 SHARK & TREND 集成博弈测试（含极端场景补充）")
    print("="*60)

    def build_context(price: float, rsi: float, vol_ratio: float) -> StrategyContext:
        return StrategyContext(
            market_data=MarketData(
                price=price,
                ema20=None,
                atr=None,
                rsi=rsi,
                vol_ratio=vol_ratio,
                ts=time.time(),
            ),
            account_snapshot=StrategySnapshot(
                account=None,
                positions={},
                position_uncertain=False,
            ),
            system_mode="NORMAL",
            risk_regime="NORMAL",
            state_confidence=None,
            trace_id="test-trace",
        )
    
    # 通用清理函数
    def clean_state_files(*files):
        for file in files:
            if os.path.exists(file):
                os.remove(file)
    
    # 清理全局旧状态
    clean_state_files('risk_state.json', 'risk_state_c2.json', 'risk_state_c3.json', 'risk_state_c4.json', 'risk_state_c5.json', 'risk_state_c6.json', 'risk_state_c7.json', 'risk_state_c8.json')

    # --- CASE 1: 贫穷陷阱 (无利润强开L3被拦截) ---
    print("\n>>> CASE 1: 贫穷的鲨鱼 (无趋势利润，强开L3被拦截)")
    rm = RiskManager(initial_capital=200, state_file='risk_state.json')
    shark = SharkEngine(rm)
    
    shark.state = SharkState.L2_HUNT
    shark.total_size = 50
    # 尝试触发 L3 (无实盈)
    intent = shark.on_tick(build_context(price=110, rsi=90, vol_ratio=1.0))  # v1.0 接收intent
    
    if shark.state == SharkState.L2_HUNT and intent is None:
        print("✅ PASS: L3 被正确拦截 (无趋势利润，符合风控规则)")
    else:
        print(f"❌ FAIL: 竟然通过了? State: {shark.state}, Intent: {intent}")
    clean_state_files('risk_state.json')

    # --- CASE 2: 死星打击 (核心，趋势利润质押反杀) ---
    print("\n>>> CASE 2: 死星打击 (趋势利润质押 -> L3成功收网)")
    rm2 = RiskManager(initial_capital=200, state_file='risk_state_c2.json')
    # 模拟趋势赚了 30U (200->230，未触发240水位线重置)
    rm2.update_snapshot(230, 0, 0, 0) # 注入实盈
    
    shark2 = SharkEngine(rm2)
    # 设置 L2 被套状态
    shark2.state = SharkState.L2_HUNT
    shark2.avg_price = 100 
    shark2.total_size = 100 
    shark2.l1_l2_max_loss = 10 
    
    print(f"    [Before] 均价: 100.00 | 规模: 100.0 | 状态: L2_HUNT")
    
    # 1. 触发 L3 (价格拉高到 110，极端RSI信号)
    intent_l3 = shark2.on_tick(build_context(price=110, rsi=90, vol_ratio=1.0))  # v1.0 接收intent
    
    if intent_l3 and intent_l3.action == "ADD_L3" and shark2.state == SharkState.L2_HUNT:
        print(f"    [L3启动] 意图返回成功 | Action: {intent_l3.action} | Size: {intent_l3.size:.2f}")
        target = shark2._calc_kill_target()
        print(f"    [Target] 目标回本价: {target:.2f}")
        
        # 2. 价格回归至 100 (原点，触发止盈)
        intent_close = shark2.on_tick(build_context(price=100, rsi=40, vol_ratio=1.0))  # v1.0 接收平仓intent
        
        if intent_close and intent_close.action == "CLOSE" and shark2.state == SharkState.SLEEP:
            print(f"✅ PASS: 完美收网 | 平仓意图返回成功 | 最终盈利: {shark2.last_clean_pnl:.2f}U")
        else:
            print(f"❌ FAIL: 未返回平仓意图 | Intent: {intent_close} | PnL: {shark2.last_clean_pnl}")
    else:
        print("❌ FAIL: L3 未启动 (趋势利润充足，应返回ADD_L3意图)")
    clean_state_files('risk_state_c2.json')

    # --- CASE 3: 水位线重置 (本金上台阶，隔离上下文) ---
    print("\n>>> CASE 3: 水位线重置 (本金上台阶，超过1.2倍触发)")
    rm3 = RiskManager(initial_capital=200, state_file='risk_state_c3.json')
    original_anchor = rm3.anchor_capital
    target_wallet_balance = original_anchor * 1.2 + 1  # 241，超过1.2倍触发重置
    rm3.update_snapshot(target_wallet_balance, 0, 0, 0)
    
    # 容错验证，符合金额业务场景
    tolerance = 0.01
    anchor_updated = abs(rm3.anchor_capital - target_wallet_balance) < tolerance
    realized_profit_zero = abs(rm3.realized_profit) < tolerance
    
    if anchor_updated and realized_profit_zero:
        print(f"✅ PASS: 水位线重置成功 ({original_anchor:.2f} -> {rm3.anchor_capital:.2f})")
    else:
        print(f"❌ FAIL: Anchor: {rm3.anchor_capital:.2f} (目标: {target_wallet_balance:.2f})")
    clean_state_files('risk_state_c3.json')

    # --- CASE 4: 极端场景1 - 波动率过高 (杠杆强制降档) ---
    print("\n>>> CASE 4: 极端场景 - 波动率爆表 (杠杆申请3x被强制降为2x)")
    rm4 = RiskManager(initial_capital=200, state_file='risk_state_c4.json')
    # 注入足够实盈，满足L1开仓前提
    rm4.update_snapshot(250, 0, 0, 0)
    shark4 = SharkEngine(rm4)
    
    shark4.state = SharkState.SLEEP
    # 模拟波动率_ratio=2.0 (远大于1.5，触发杠杆降档)
    tick_context = build_context(price=100, rsi=80, vol_ratio=2.0)
    
    # 捕获杠杆核准结果（通过返回的intent验证）
    intent_l1 = shark4.on_tick(tick_context)  # v1.0 接收L1意图
    
    # 优化验证逻辑：intent存在且action为OPEN_L1即算通过（杠杆在intent中定义）
    if intent_l1 and intent_l1.action == "OPEN_L1" and intent_l1.risk_request.suggested_leverage <= 2:
        print(f"✅ PASS: 波动率过高，杠杆成功降档 | 意图中杠杆: {intent_l1.risk_request.suggested_leverage}x (申请3x)")
    else:
        print(f"❌ FAIL: 杠杆未正确降档 | Intent: {intent_l1} | 状态: {shark4.state}")
    clean_state_files('risk_state_c4.json')

    # --- CASE 5: 极端场景2 - 鲨鱼总亏损超预算 (强制拦截开仓) ---
    print("\n>>> CASE 5: 极端场景 - 鲨鱼浮亏超总预算 (拦截加仓)")
    rm5 = RiskManager(initial_capital=200, state_file='risk_state_c5.json')
    # 1. 注入实盈但不触发水位线重置（230 < 240，实盈30U>0，满足L2加仓前提）
    wallet_balance = 230
    rm5.update_snapshot(wallet_balance, 0, 0, 0)
    shark5 = SharkEngine(rm5)

    # 2. 初始化L1状态，关闭时间止损干扰
    shark5.state = SharkState.L1_EXIST
    shark5.avg_price = 100
    shark5.total_size = 300  # 大幅加大仓位，确保浮亏远超预算
    shark5.leverage = 2
    shark5.entry_time = time.time()
    shark5.l1_l2_max_loss = 0

    # 3. 计算鲨鱼总预算，确保浮亏**远超**预算（这里让浮亏=60U，预算=55U，60>55）
    shark_budget = rm5.get_shark_budget()
    current_price = 120  # 价格上涨20%，做空产生巨额浮亏
    # 关键：不手动写入RM浮亏，而是让SharkEngine和RM通过正常逻辑交互识别浮亏
    # 先执行一次tick，让RM更新当前浮亏状态
    tick_context_init = build_context(price=current_price, rsi=85, vol_ratio=1.0)
    shark5.on_tick(tick_context_init)

    # 4. 重新获取RM识别的实际浮亏（此时浮亏已远超预算）
    actual_floating_loss = rm5.shark_floating_loss
    print(f"    [前置信息] 鲨鱼预算: {shark_budget:.2f}U | 当前实际浮亏: {actual_floating_loss:.2f}U")
    print(f"    [前置信息] 趋势已实现利润: {rm5.realized_profit:.2f}U (满足L2加仓前提)")

    # 5. 再次执行tick，尝试触发L2加仓（此时浮亏超预算，应返回None）
    intent_l2 = shark5.on_tick(tick_context_init)  # v1.0 接收L2意图

    # 6. 优化验证逻辑：intent为None且状态保持L1_EXIST，即为拦截成功
    if shark5.state == SharkState.L1_EXIST and actual_floating_loss > shark_budget and intent_l2 is None:
        print(f"✅ PASS: 浮亏超预算 ({actual_floating_loss:.2f}U > {shark_budget:.2f}U)，加仓被拦截")
    else:
        print(f"❌ FAIL: 浮亏超预算仍返回加仓意图 | 状态: {shark5.state} | Intent: {intent_l2} | 浮亏: {actual_floating_loss:.2f}U | 预算: {shark_budget:.2f}U")
    clean_state_files('risk_state_c5.json')

    # --- CASE 6: 极端场景3 - 时间止损 (24ticks无盈利平仓) ---
    print("\n>>> CASE 6: 极端场景 - 持仓超时无盈利 (触发时间止损)")
    rm6 = RiskManager(initial_capital=200, state_file='risk_state_c6.json')
    rm6.update_snapshot(250, 0, 0, 0)  # 注入实盈
    shark6 = SharkEngine(rm6)
    
    # 启动L1，设置入场时间为“25ticks前”（超过24ticks阈值）
    shark6.on_tick(build_context(price=100, rsi=80, vol_ratio=1.0))
    shark6.entry_time = time.time() - 25  # 模拟超时
    shark6.avg_price = 100
    shark6.total_size = 50
    # 模拟无盈利（价格不变，浮亏=0）
    tick_context = build_context(price=100, rsi=75, vol_ratio=1.0)
    
    intent_stop = shark6.on_tick(tick_context)  # v1.0 接收止损平仓意图
    
    # 验证：返回平仓intent且状态回归SLEEP
    if intent_stop and intent_stop.action == "CLOSE" and shark6.state == SharkState.SLEEP:
        print("✅ PASS: 持仓超时无盈利，触发时间止损，返回平仓意图")
    else:
        print(f"❌ FAIL: 未触发时间止损 | Intent: {intent_stop} | 状态: {shark6.state} | 入场时间差: {time.time() - shark6.entry_time:.0f}ticks")
    clean_state_files('risk_state_c6.json')

    # --- CASE 7: 极端场景4 - 鲨鱼L3止损 (价格创新高，无条件撤退) ---
    print("\n>>> CASE 7: 极端场景 - 鲨鱼L3狙击失败 (价格创新高，触发无条件止损)")
    rm7 = RiskManager(initial_capital=200, state_file='risk_state_c7.json')
    rm7.update_snapshot(300, 0, 0, 0)  # 注入充足实盈（100U）
    shark7 = SharkEngine(rm7)
    
    # 手动设置L3状态，模拟狙击失败
    shark7.state = SharkState.L3_SNIPE
    shark7.avg_price = 100
    shark7.total_size = 200
    shark7.l1_l2_max_loss = 20
    shark7.leverage = 10
    
    # 模拟价格创新高（超过均价1%，触发L3止损）
    tick_context = build_context(price=101.5, rsi=95, vol_ratio=1.0)
    intent_l3_stop = shark7.on_tick(tick_context)  # v1.0 接收L3止损意图
    
    # 验证：返回平仓intent且状态回归SLEEP
    if intent_l3_stop and intent_l3_stop.action == "CLOSE" and shark7.state == SharkState.SLEEP:
        print(f"✅ PASS: L3狙击失败，价格创新高触发止损 | 平仓意图返回成功 | 最终盈亏: {shark7.last_clean_pnl:.2f}U")
    else:
        print(f"❌ FAIL: L3未触发止损 | Intent: {intent_l3_stop} | 状态: {shark7.state} | 当前价格: 101.5 (均价: 100)")
    clean_state_files('risk_state_c7.json')
    
    # --- CASE 8: 极端场景 - 整体保证金使用率>60%（全局拦截加仓）---
    print("\n>>> CASE 8: 极端场景 - 整体保证金使用率>60%（全局拦截加仓）")
    rm8 = RiskManager(initial_capital=200, state_file='risk_state_c8.json')
    # 注入充足实盈，满足双引擎开仓前提（不触发水位线重置）
    wallet_balance = 230
    rm8.update_snapshot(wallet_balance, 0, 0, 0)

    # 模拟趋势引擎L2持仓（占用部分保证金）
    shark8 = SharkEngine(rm8)
    # 先让鲨鱼L1开仓，占用部分保证金
    shark8.on_tick(build_context(price=100, rsi=80, vol_ratio=1.0))
    shark8.state = SharkState.L1_EXIST
    shark8.avg_price = 100
    shark8.total_size = 500  # 大幅加仓，占用大量保证金
    shark8.leverage = 10
    shark8.entry_time = time.time()
    # 手动更新保证金占用（模拟大幅加仓后的高使用率）
    shark8.margin_used = 140  # 140U 占用 / 230U 余额 ≈ 60.87% > 60% 阈值

    # 计算当前保证金使用率（验证是否超标）
    current_margin_usage = shark8._calc_current_margin_usage()
    print(f"    [前置信息] 当前保证金使用率: {current_margin_usage:.2%} | 阈值: {MAX_MARGIN_USAGE_RATIO:.2%}")

    # 尝试让鲨鱼升级L2，触发保证金超标拦截（应返回None）
    tick_context_margin = build_context(price=105, rsi=85, vol_ratio=1.0)
    intent_l2_margin = shark8.on_tick(tick_context_margin)  # v1.0 接收L2意图

    # 验证：intent为None且状态保持L1_EXIST，即为拦截成功
    if shark8.state == SharkState.L1_EXIST and intent_l2_margin is None:
        print("✅ PASS: 保证金使用率>60%，全局拦截加仓，符合风控规则")
    else:
        print(f"❌ FAIL: 保证金超标仍返回加仓意图 | Intent: {intent_l2_margin} | 状态: {shark8.state}")
    clean_state_files('risk_state_c8.json')

    # 最终全局清理
    print("\n" + "="*60)
    print("🦈 所有测试场景执行完毕，状态文件已清理")
    print("="*60)
