import asyncio
import json
import time
import logging
import ssl
# import websockets # v1.0: 移除原版直接导入，改为下方带容错的导入
import hmac
import hashlib
import base64
import os
from datetime import datetime

# ==================== v1.0: 引入代理库支持 ====================
try:
    import websockets
    from websockets_proxy import Proxy, proxy_connect
    HAS_PROXY_LIB = True
except ImportError:
    from websockets import connect as proxy_connect
    HAS_PROXY_LIB = False
# ============================================================

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BaseBitgetWS")

class BaseBitgetWsClient:
    """Bitget WS基础客户端（生产环境优化版 - 完整保留原逻辑）"""
    
    def __init__(self):
        # 初始化SSL上下文
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        # WS连接状态
        self.public_ws_url = "wss://ws.bitget.com/v2/ws/public"
        self.private_ws_url = "wss://ws.bitget.com/v2/ws/private"
        self.product_type: str = None
        self.ws_symbol: str = None

        # v1.0: 显式定义代理地址
        self.proxy_url = "http://127.0.0.1:7890"
        
        self.on_ticker_callback = None # 新增：ticker回调
        self.on_candle_callback = None # 新增：K线回调

    # ------------------- v1.0: 获取连接参数(含代理) -------------------
    def _get_connect_kwargs(self):
        """v1.0: 统一构建连接参数，自动注入代理"""
        kwargs = {
            "ssl": self.ssl_context,
            "open_timeout": 20,
            "ping_interval": None
        }
        if HAS_PROXY_LIB:
            # 显式注入代理，解决 websockets 忽略环境变量的问题
            kwargs["proxy"] = Proxy.from_url(self.proxy_url)
        return kwargs
        
    # ------------------- 独立心跳任务 -------------------
    async def _keep_alive(self, ws):
        """独立的心跳发送任务，每20秒发送一次 ping"""
        try:
            while True:
                await asyncio.sleep(20)
                await ws.send("ping")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"心跳发送失败: {repr(e)}") # v1.0: 使用repr防止格式化错误

    # ------------------- 公有WS方法 -------------------
    async def connect_public_ws(self, product_type: str, ws_symbol: str, candle_channels: list = None):
        """
        连接公共WS
        修改点：解析 action 字段，并透传完整数据给回调函数
        """
        self.product_type = product_type
        self.ws_symbol = ws_symbol
        logger.info(f"正在连接公共行情: {self.public_ws_url} (代理: {self.proxy_url})") # v1.0: 打印代理信息
        
        while True:
            try:
                # v1.0: 使用 proxy_connect 并注入参数
                async with proxy_connect(
                    self.public_ws_url, 
                    **self._get_connect_kwargs()
                ) as ws:
                    logger.info("✅ 公共频道连接成功")
                    
                    # 1. 订阅 Ticker
                    args = [{"instType": self.product_type, "channel": "ticker", "instId": self.ws_symbol}]
                    
                    # 2. 订阅 K线
                    if candle_channels:
                        for ch in candle_channels:
                            args.append({"instType": self.product_type, "channel": ch, "instId": self.ws_symbol})
                            logger.info(f"➕ 追加订阅K线: {ch}")

                    sub_msg = {"op": "subscribe", "args": args}
                    await ws.send(json.dumps(sub_msg))
                    await self.on_public_reconnect()

                    # 启动心跳
                    heartbeat_task = asyncio.create_task(self._keep_alive(ws))

                    try:
                        while True:
                            # 30秒看门狗超时
                            resp = await asyncio.wait_for(ws.recv(), timeout=30)
                            
                            if resp == 'pong': continue
                            if resp == 'ping': await ws.send("pong"); continue 
                            
                            data = json.loads(resp)
                            
                            # 【核心修改】提取 action (snapshot/update)
                            # 如果没有action字段(如订阅响应)，默认为unknown
                            action = data.get('action', 'unknown')

                            if 'data' in data and 'arg' in data:
                                channel = data.get('arg', {}).get('channel')
                                
                                # 1. 处理 Ticker
                                if channel == 'ticker':
                                    # Bitget Ticker data 是一个列表，通常只有一项
                                    if data['data']:
                                        ticker_item = data['data'][0]
                                        # 【修改】透传完整 item 和 action
                                        await self.on_public_ticker(ticker_item, action)
                                
                                # 2. 处理 Candle K线
                                elif channel and channel.startswith('candle'):
                                    # K线 data 是列表的列表，直接透传
                                    await self.on_public_candle(data['data'], channel, action)

                    except asyncio.TimeoutError:
                        logger.warning("公共WS接收超时(30s无数据)，准备重连...")
                        raise
                    finally:
                        heartbeat_task.cancel()

            except Exception as e:
                # v1.0: 使用 repr(e) 修复 TypeError: unsupported format string
                logger.error(f"公共 WS 断开: {repr(e)}，3秒后重连...")
                await self.on_public_disconnect()
                await asyncio.sleep(3)
    
    # ------------------- 私有WS方法 (完整保留) -------------------
    async def connect_private_ws(self, config: dict, product_type: str):
        self.product_type = product_type
        logger.info(f"正在连接私有频道: {self.private_ws_url} (代理: {self.proxy_url})") # v1.0
        
        while True:
            try:
                # v1.0: 使用 proxy_connect 并注入参数
                async with proxy_connect(
                    self.private_ws_url, 
                    **self._get_connect_kwargs()
                ) as ws:
                    logger.info("✅ 私有频道连接成功")
                    
                    ts = str(int(time.time() * 1000))
                    sign = self.get_sign(ts)
                    login_msg = {
                        "op": "login",
                        "args": [{
                            "apiKey": config['api']['apiKey'],
                            "passphrase": config['api']['password'],
                            "timestamp": ts,
                            "sign": sign
                        }]
                    }
                    await ws.send(json.dumps(login_msg))
                    await asyncio.sleep(1) 
                    
                    sub_msg = {
                        "op": "subscribe",
                        "args": [
                            {"instType": self.product_type, "channel": "orders", "instId": "default"},
                            {"instType": self.product_type, "channel": "positions", "instId": "default"},
                            {"instType": self.product_type, "channel": "account", "coin": "default"}
                        ]
                    }
                    await ws.send(json.dumps(sub_msg))
                    logger.info("✅ 已订阅 Orders & Positions & Account")
                    await self.on_private_reconnect()

                    heartbeat_task = asyncio.create_task(self._keep_alive(ws))

                    try:
                        while True:
                            resp = await asyncio.wait_for(ws.recv(), timeout=30)
                            
                            if resp == 'pong': continue
                            if resp == 'ping': await ws.send("pong"); continue
                            
                            data = json.loads(resp)
                            
                            # v1.0: 兼容 code 为 0(int) 或 '00000'(str) 的情况
                            is_login_success = data.get('event') == 'login' and \
                                              (str(data.get('code')) == '00000' or data.get('code') == 0)

                            if is_login_success:
                                logger.info("✅ 登录验证通过")
                                continue
                            elif data.get('event') == 'login': # v1.0: 显式打印登录失败
                                logger.error(f"❌ 登录失败: {data}")

                            if 'data' in data:
                                channel = data.get('arg', {}).get('channel')
                                if channel == 'orders':
                                    for order in data['data']:
                                        await self.on_private_order(order)
                                elif channel == 'positions':
                                    for pos in data['data']:
                                        await self.on_private_position(pos)
                                elif channel == 'account':
                                    for account in data['data']:
                                        await self.on_private_account(account)
                    except asyncio.TimeoutError:
                        logger.warning("私有WS接收超时，连接可能已断开")
                        raise
                    finally:
                        heartbeat_task.cancel()

            except Exception as e:
                # v1.0: 使用 repr(e) 修复 TypeError
                logger.error(f"私有 WS 异常: {repr(e)}, 3秒后重连...")
                await self.on_private_disconnect()
                await asyncio.sleep(3)
    
    # ------------------- 钩子方法 -------------------
    async def on_public_ticker(self, ticker: dict, action: str):
        pass

    async def on_public_candle(self, candle_data: list, channel: str, action: str):
        pass
    
    async def on_private_order(self, order_data: dict):
        pass
    
    async def on_private_position(self, pos_data: dict):
        pass
    
    async def on_private_account(self, account_data: dict):
        pass

    async def on_public_disconnect(self):
        pass

    async def on_private_disconnect(self):
        pass

    async def on_public_reconnect(self):
        pass

    async def on_private_reconnect(self):
        pass
    
    # ------------------- 签名方法 -------------------
    def generate_sign(self, timestamp: str, secret: str) -> str:
        message = f"{timestamp}GET/user/verify"
        mac = hmac.new(
            bytes(secret, encoding='utf-8'),
            bytes(message, encoding='utf-8'),
            digestmod=hashlib.sha256
        )
        d = mac.digest()
        return base64.b64encode(d).decode('utf-8')
    
    def get_sign(self, timestamp: str) -> str:
        raise NotImplementedError("子类必须实现get_sign方法")



# ==========================================
# 生产环境策略实现 (Main Block) - 最终修订版
# ==========================================
if __name__ == '__main__':
    # 1. 设置代理
    os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
    os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"
    
    # v1.0: 增加代理库检查提示
    if not HAS_PROXY_LIB:
        print("⚠️ 警告: 未检测到 websockets-proxy 库，将尝试直连 (可能失败)")
        print("👉 建议安装: pip install websockets-proxy")
        
    print(">>> 代理已配置: http://127.0.0.1:7890")

    # 辅助函数：时间戳(ms) 转 可读时间字符串 (精确到毫秒)
    def format_ts(ts):
        return datetime.fromtimestamp(int(ts) / 1000).strftime('%H:%M:%S.%f')[:-3]

    # 2. 定义具体的策略子类
    class MyStrategy(BaseBitgetWsClient):
        def __init__(self, api_key, secret, password):
            super().__init__()
            self.api_key = api_key
            self.secret = secret
            self.password = password
            
            # 【核心】本地K线缓存：仅保留最近5根
            # 结构：[ ..., 前2根(已结), 前1根(已结), 当前根(未结/跳动中) ]
            self.kline_cache = [] 

        def get_sign(self, timestamp: str) -> str:
            return self.generate_sign(timestamp, self.secret)

        # ------------------- Ticker 处理 (行情变动 & 策略触发) -------------------
        async def on_public_ticker(self, ticker: dict, action: str):
            """
            Ticker 推送频率高 (300ms)，用于计算延迟和触发信号
            """
            # 1. 延迟监控
            local_ms = time.time() * 1000
            server_ms = float(ticker.get('ts'))
            latency = local_ms - server_ms # 链路延迟
            
            ts_recv = format_ts(local_ms)   # 本地接收时间
            ts_data = format_ts(server_ms)  # 数据生成时间
            
            price = float(ticker.get('lastPr'))

            # 2. 打印 Ticker 核心数据 (带延迟监控)
            print(f"📊 [Ticker] Recv:{ts_recv} | Latency:{latency:.1f}ms | 现价:{price} | 24H额(U):{ticker.get('quoteVolume')}")

            # 3. 【策略立即执行】
            # 只要缓存里有至少2根数据（Snapshot回来就有5根了），就立刻对比
            # self.kline_cache[-1] 是当前正在跑的
            # self.kline_cache[-2] 是上一根彻底拿下的已结K线
            if len(self.kline_cache) >= 2:
                last_closed_k = self.kline_cache[-2] # 取倒数第二根(已结)
                
                # 获取已结K线的数据
                k_ts = format_ts(last_closed_k[0])
                k_high = float(last_closed_k[2])
                k_low = float(last_closed_k[3])
                k_close = float(last_closed_k[4])
                
                # --- 简单突破策略示例 ---
                if price > k_high:
                    print(f"🚀 [信号-多] Recv:{ts_recv} | 现价:{price} > 上根High:{k_high} (K线时间:{k_ts})")
                elif price < k_low:
                    print(f"📉 [信号-空] Recv:{ts_recv} | 现价:{price} < 上根Low:{k_low} (K线时间:{k_ts})")
                #elif int(local_ms) % 1000 < 300: 
                #    print(f"\r💓 [监控中] Ticker正常 | 延迟:{latency:.1f}ms | 现价:{price} (区间 {k_low} - {k_high})", end="", flush=True)

        # ------------------- K线 处理 (数据维护) -------------------
        async def on_public_candle(self, candle_data: list, channel: str, action: str):
            """
            维护 self.kline_cache，只存最近5根
            """
            # --- 场景 1: 刚连接，Snapshot (历史数据) ---
            if action == 'snapshot':
                # 按时间排序
                sorted_data = sorted(candle_data, key=lambda x: int(x[0]))
                
                # 只保留最后5根
                self.kline_cache = sorted_data[-5:]
                
                print(f"✅ [初始化] 历史K线加载完毕 (最近{len(self.kline_cache)}根)")
                for i, k in enumerate(self.kline_cache):
                    status = "已结" if i < len(self.kline_cache)-1 else "未结"
                    print(f"   📜 [{status}] TS:{format_ts(k[0])} | O:{k[1]} H:{k[2]} L:{k[3]} C:{k[4]} | Vol:{k[5]}")
                print("-" * 80)
                return

            # --- 场景 2: 实时 Update ---
            if action == 'update' and candle_data:
                new_k = candle_data[0]
                new_ts = int(new_k[0])
                recv_time = format_ts(time.time() * 1000)
                
                # 初始化防御
                if not self.kline_cache:
                    self.kline_cache.append(new_k)
                    return

                last_k = self.kline_cache[-1]
                last_ts = int(last_k[0])

                # 【情况A】时间戳相同 -> 当前K线还在变动 -> 覆盖
                if new_ts == last_ts:
                    self.kline_cache[-1] = new_k
                    # 打印秒级跳动 (包含接收时间，证明程序是活的)
                    #print(f"\r⏳ [{channel}] Recv:{recv_time} | TS:{format_ts(new_ts)} | C:{new_k[4]} H:{new_k[2]} L:{new_k[3]} V:{new_k[5]}", end="", flush=True)

                # 【情况B】时间戳变大 -> 新的一分钟 -> 封板结算
                elif new_ts > last_ts:
                    print() # 换行
                    print("=" * 100)
                    print(f"🔒 [K线封板] {format_ts(last_ts)} 最终收盘价: {last_k[4]}")
                    
                    # 此时 self.kline_cache[-1] 已经是【已结】的了，可以做复盘打印
                    closed_k = self.kline_cache[-1]
                    prev_1 = self.kline_cache[-2] if len(self.kline_cache) >= 2 else None
                    
                    print(f"📊 [K线回溯]")
                    print(f"   1. 刚结K线 [{format_ts(closed_k[0])}] O:{closed_k[1]} H:{closed_k[2]} L:{closed_k[3]} C:{closed_k[4]} V:{closed_k[5]}")
                    if prev_1:
                        print(f"   2. 上一根K [{format_ts(prev_1[0])}] O:{prev_1[1]} H:{prev_1[2]} L:{prev_1[3]} C:{prev_1[4]} V:{prev_1[5]}")

                    # 维护缓存：加入新的一根
                    self.kline_cache.append(new_k)
                    print(f"🆕 [新线开始] {format_ts(new_ts)} 开盘: {new_k[1]}")
                    
                    # 保持长度为 5
                    if len(self.kline_cache) > 5:
                        self.kline_cache.pop(0)
                        
                    print("=" * 100)

        async def on_private_account(self, account_data: dict):
            print(f"💰 [账户] {account_data}")

    # 3. 模拟配置
    api_config = {
        'api': {
            'apiKey': "bg_24eee43388a0e50dd197ce59158ddd15",
            'secret': "9905150389942a313afe7f29b1b09b41386fd7d8be1fe808aef609b15ab915b6",
            'password': "smartswaptest"
        }
    }

    async def main():
        client = MyStrategy(
            api_config['api']['apiKey'], 
            api_config['api']['secret'], 
            api_config['api']['password']
        )

        print(">>> 开始连接...")
        await asyncio.gather(
            client.connect_public_ws(
                product_type="USDT-FUTURES", 
                ws_symbol="BTCUSDT",
                candle_channels=["candle5m"] 
            ),
        )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("程序已停止")
