import asyncio
import aiohttp
from aiohttp.resolver import AsyncResolver
import time
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn

BASE_URL = "https://fapi.binance.com"
THRESHOLD = 8
CONCURRENCY = 20
aggregation_interval = 5  # 5m周期

# 最新结果存储位置（提供给 API）
coin_pool = []  # 候选池（发生 OI 异动的币）
oi_top = []     # 按 OI 异动排序

@asynccontextmanager
async def lifespan(app):
    # 启动时运行
    asyncio.create_task(scheduler())
    yield
    # 关闭时运行（如需清理可在此添加）

app = FastAPI(lifespan=lifespan)

def align_to_kline_period():
    current_time = datetime.now(timezone.utc)
    aligned_minute = (current_time.minute // aggregation_interval) * aggregation_interval
    return current_time.replace(minute=aligned_minute, second=0, microsecond=0)

async def wait_for_next_kline_period():
    aligned_time = align_to_kline_period()
    next_period_start = aligned_time + timedelta(minutes=aggregation_interval)
    wait_seconds = (next_period_start - datetime.now(timezone.utc)).total_seconds()
    if wait_seconds > 0:
        print(f"⏸ 等待 {wait_seconds:.2f} 秒 到下一个5m周期…")
        await asyncio.sleep(wait_seconds)

async def fetch_json(session, url, params=None):
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                print(f"❌ HTTP {resp.status}: {url}")
                return None
            return await resp.json()
    except Exception as e:
        print(f"❌ 请求失败: {url} - {type(e).__name__}: {e}")
        return None

async def get_usdtm_symbols(session):
    url = f"{BASE_URL}/fapi/v1/exchangeInfo"
    data = await fetch_json(session, url)
    if not data or "symbols" not in data:
        return []
    return [
        item["symbol"]
        for item in data["symbols"]
        if item.get("contractType") == "PERPETUAL"
        and item.get("quoteAsset") == "USDT"
        and item.get("status") == "TRADING"
    ]

async def get_oi_change(session, symbol):
    url = f"{BASE_URL}/futures/data/openInterestHist"
    params = {"symbol": symbol, "period": "5m", "limit": 2}
    data = await fetch_json(session, url, params)
    if not isinstance(data, list) or len(data) < 2:
        return None
    try:
        oi_old = float(data[0]["sumOpenInterestValue"])
        oi_now = float(data[1]["sumOpenInterestValue"])
        change = (oi_now - oi_old) / oi_old * 100
        return symbol, change, oi_now
    except:
        return None

async def run_scan():
    global coin_pool, oi_top

    # Windows DNS 兼容：使用 AsyncResolver 避免 DNS 超时
    resolver = AsyncResolver(nameservers=["8.8.8.8", "1.1.1.1"])
    connector = aiohttp.TCPConnector(resolver=resolver, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        symbols = await get_usdtm_symbols(session)
        if not symbols:
            print("⚠ 无法获取USDT永续交易对")
            return

        sem = asyncio.Semaphore(CONCURRENCY)
        tasks = []

        for s in symbols:
            async def task(sym=s):
                async with sem:
                    return await get_oi_change(session, sym)
            tasks.append(task())

        results = []
        for coro in asyncio.as_completed(tasks):
            r = await coro
            if r:
                results.append(r)

        spikes = [(sym, chg, oi) for sym, chg, oi in results if abs(chg) >= THRESHOLD]

        # 更新 API 数据
        # coin_pool = [sym for sym, chg, oi in spikes]
        # oi_top = [sym for sym, chg, oi in sorted(spikes, key=lambda x: abs(x[1]), reverse=True)]
        
        # 更新 API 数据（如果本轮无异动，则保留上一轮结果）
        if spikes:
            coin_pool = [sym for sym, chg, oi in spikes]
            oi_top = [sym for sym, chg, oi in sorted(spikes, key=lambda x: abs(x[1]), reverse=True)]
        else:
            print("ℹ 无 OI 异动 → 保留上一周期结果")

        # 更新 API 数据（若无异动 → 保留上一轮；若仍为空 → 使用默认 BTCUSDT）
        # if spikes:
            # coin_pool = [sym for sym, chg, oi in spikes]
            # oi_top = [sym for sym, chg, oi in sorted(spikes, key=lambda x: abs(x[1]), reverse=True)]
        # else:
            # print("ℹ 无 OI 异动 → 保留上一周期结果")
            # if not coin_pool:   # 上一周期也为空
                # coin_pool = ["BTCUSDT"]
            # if not oi_top:      # 上一周期也为空
                # oi_top = ["BTCUSDT"]

        # -------- 🔥 日志输出部分 --------
        print("--------------------------------------------------------------")
        print(f"🕒 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📌 扫描币种数量: {len(symbols)}")
        if not spikes:
            print("ℹ 本周期无 OI 异动")
        else:
            print(f"🔥 本周期发现 {len(spikes)} 个 OI 异动:")
            for sym, chg, oi in spikes[:20]:   # ← 使用 spikes，而不是 oi_top
            # for sym, chg, oi in oi_top[:20]:   # 最多显示前 20 条
                print(f"  {sym:<12} 变化率={chg:+.2f}%  当前OI=${oi:,.0f}")
        print("--------------------------------------------------------------\n")

async def scheduler():
    while True:
        await wait_for_next_kline_period()
        print("⏳ 扫描中…")
        start = time.time()
        await run_scan()
        print(f"⏱ 执行完毕，用时 {time.time() - start:.1f} 秒\n")

# -------------------- API 部分 --------------------

@app.get("/coinpool")
async def get_coin_pool():
    return {
        "success": True,
        "data": {
            "coins": [{"pair": sym} for sym in coin_pool],  # coin_pool = ["BTCUSDT", "DOGSUSDT", ...]
            "count": len(coin_pool)
        }
    }

@app.get("/oitop")
async def get_oi_top():
    return {
        "success": True,
        "data": {
            "positions": [{"symbol": sym} for sym in oi_top],  # oi_top = ["BTCUSDT", "DOGSUSDT", ...]
            "count": len(oi_top),
            "exchange": "binance",
            "time_range": "5m"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)

