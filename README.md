# OI Monitor

Binance Open Interest (OI) 异动监控服务 - 实时扫描 USDT 永续合约持仓量变化。

## 功能

- 每 5 分钟扫描所有 Binance USDT 永续交易对
- 检测持仓量变化超过 8% 的币种
- 提供 REST API 接口查询异动数据

## API 接口

### GET /coinpool

返回发生 OI 异动的币种列表。

```json
{
  "success": true,
  "data": {
    "coins": [{"pair": "BTCUSDT"}, {"pair": "ETHUSDT"}],
    "count": 2
  }
}
```

### GET /oitop

返回按 OI 变化幅度排序的币种列表。

```json
{
  "success": true,
  "data": {
    "positions": [{"symbol": "BTCUSDT"}],
    "count": 1,
    "exchange": "binance",
    "time_range": "5m"
  }
}
```

### GET /health

健康检查端点。

```json
{"status": "healthy"}
```

## 快速开始

### Docker 部署 (推荐)

```bash
docker pull ghcr.io/liang/oi:latest
docker run -d -p 8000:8000 --name oi-monitor ghcr.io/liang/oi:latest
```

### Docker Compose

```bash
git clone https://github.com/liang/oi.git
cd oi
docker-compose up -d
```

### 本地运行

```bash
git clone https://github.com/liang/oi.git
cd oi

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 运行
python main.py
```

服务启动后访问: http://localhost:8000

## 架构

```
┌─────────────────────────────────────┐
│         OI Monitor Service          │
├─────────────────────────────────────┤
│  Scheduler (5min interval)          │
│    └── 扫描所有 USDT 永续合约        │
│    └── 计算 OI 变化百分比            │
│    └── 过滤 >= 8% 阈值               │
├─────────────────────────────────────┤
│  FastAPI REST API                   │
│    └── GET /coinpool                │
│    └── GET /oitop                   │
│    └── GET /health                  │
└─────────────────────────────────────┘
              │
              ▼
       Binance Futures API
```

## 发布版本

```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

GitHub Actions 会自动构建并推送 Docker 镜像到 GHCR。

## License

MIT License - 详见 [LICENSE](LICENSE)
