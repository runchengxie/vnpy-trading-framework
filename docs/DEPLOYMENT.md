# VN.py Trading Framework 部署指南

本指南详细说明如何在不同环境中部署和配置VN.py交易框架。

## 目录

- [系统要求](#系统要求)
- [快速安装](#快速安装)
- [详细安装步骤](#详细安装步骤)
- [环境配置](#环境配置)
- [交易接口配置](#交易接口配置)
- [生产环境部署](#生产环境部署)
- [Docker部署](#docker部署)
- [云服务器部署](#云服务器部署)
- [监控和维护](#监控和维护)
- [故障排除](#故障排除)

## 系统要求

### 最低要求
- **操作系统**: Windows 10+, macOS 10.14+, Ubuntu 18.04+
- **Python**: 3.8 或更高版本
- **内存**: 4GB RAM
- **存储**: 10GB 可用空间
- **网络**: 稳定的互联网连接

### 推荐配置
- **操作系统**: Windows 11, macOS 12+, Ubuntu 20.04+
- **Python**: 3.9 或 3.10
- **内存**: 8GB+ RAM
- **存储**: 50GB+ SSD
- **网络**: 低延迟网络连接
- **CPU**: 4核心或更多

## 快速安装

### 1. 克隆项目
```bash
git clone <repository-url>
cd vnpy-trading-framework
```

### 2. 运行安装脚本
```bash
python install.py
```

### 3. 测试安装
```bash
python test_framework.py
```

### 4. 快速开始
```bash
python quick_start.py
```

## 详细安装步骤

### 1. Python环境准备

#### Windows
```powershell
# 下载并安装Python 3.9+
# 从 https://python.org 下载

# 验证安装
python --version
pip --version
```

#### macOS
```bash
# 使用Homebrew安装
brew install python@3.9

# 或使用pyenv
brew install pyenv
pyenv install 3.9.16
pyenv global 3.9.16
```

#### Ubuntu/Debian
```bash
# 更新包列表
sudo apt update

# 安装Python 3.9
sudo apt install python3.9 python3.9-pip python3.9-venv

# 设置默认Python版本
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.9 1
```

### 2. 虚拟环境设置（推荐）

```bash
# 创建虚拟环境
python -m venv vnpy_env

# 激活虚拟环境
# Windows
vnpy_env\Scripts\activate

# macOS/Linux
source vnpy_env/bin/activate

# 升级pip
pip install --upgrade pip
```

### 3. 安装依赖包

```bash
# 安装核心依赖
pip install -r requirements_vnpy.txt

# 如果网络较慢，使用国内镜像
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements_vnpy.txt
```

### 4. 验证安装

```bash
# 运行测试脚本
python test_framework.py

# 检查策略导入
python -c "from strategies.cta_ema_adx_strategy import EmaAdxStrategy; print('策略导入成功')"
```

## 环境配置

### 1. 环境变量设置

创建 `.env` 文件：
```bash
# 数据库配置
DATABASE_URL=sqlite:///vnpy_data.db

# 日志级别
LOG_LEVEL=INFO

# 时区设置
TIMEZONE=Asia/Shanghai

# API配置目录
CONFIG_DIR=./config

# 结果输出目录
RESULTS_DIR=./results
```

### 2. 日志配置

编辑 `config/logging.json`：
```json
{
    "version": 1,
    "disable_existing_loggers": false,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        }
    },
    "handlers": {
        "default": {
            "level": "INFO",
            "formatter": "standard",
            "class": "logging.StreamHandler"
        },
        "file": {
            "level": "DEBUG",
            "formatter": "standard",
            "class": "logging.FileHandler",
            "filename": "logs/vnpy.log",
            "mode": "a"
        }
    },
    "loggers": {
        "": {
            "handlers": ["default", "file"],
            "level": "DEBUG",
            "propagate": false
        }
    }
}
```

## 交易接口配置

### 1. Alpaca配置

编辑 `config/live_trading_config.json`：
```json
{
    "gateways": {
        "alpaca": {
            "key_id": "YOUR_ALPACA_KEY_ID",
            "secret_key": "YOUR_ALPACA_SECRET_KEY",
            "paper": true,
            "proxy_host": "",
            "proxy_port": 0
        }
    }
}
```

### 2. Interactive Brokers配置

```json
{
    "gateways": {
        "ib": {
            "host": "127.0.0.1",
            "port": 7497,
            "client_id": 1,
            "account": "YOUR_IB_ACCOUNT"
        }
    }
}
```

### 3. Binance配置

```json
{
    "gateways": {
        "binance": {
            "api_key": "YOUR_BINANCE_API_KEY",
            "secret_key": "YOUR_BINANCE_SECRET_KEY",
            "proxy_host": "",
            "proxy_port": 0,
            "testnet": true
        }
    }
}
```

## 生产环境部署

### 1. 服务器配置

```bash
# 创建专用用户
sudo useradd -m -s /bin/bash vnpy
sudo usermod -aG sudo vnpy

# 切换到vnpy用户
sudo su - vnpy

# 创建项目目录
mkdir -p /home/vnpy/trading
cd /home/vnpy/trading
```

### 2. 系统服务配置

创建 `/etc/systemd/system/vnpy-trading.service`：
```ini
[Unit]
Description=VN.py Trading Framework
After=network.target

[Service]
Type=simple
User=vnpy
Group=vnpy
WorkingDirectory=/home/vnpy/trading
Environment=PATH=/home/vnpy/trading/vnpy_env/bin
ExecStart=/home/vnpy/trading/vnpy_env/bin/python scripts/run_live_trading.py --mode live
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable vnpy-trading
sudo systemctl start vnpy-trading
```

### 3. 反向代理配置（Nginx）

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## Docker部署

### 1. Dockerfile

```dockerfile
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements文件
COPY requirements_vnpy.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements_vnpy.txt

# 复制项目文件
COPY . .

# 创建必要目录
RUN mkdir -p logs results data

# 设置环境变量
ENV PYTHONPATH=/app
ENV LOG_LEVEL=INFO

# 暴露端口
EXPOSE 8080

# 启动命令
CMD ["python", "scripts/run_live_trading.py", "--mode", "paper"]
```

### 2. docker-compose.yml

```yaml
version: '3.8'

services:
  vnpy-trading:
    build: .
    container_name: vnpy-trading
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
      - ./results:/app/results
      - ./data:/app/data
    environment:
      - LOG_LEVEL=INFO
      - TIMEZONE=Asia/Shanghai
    networks:
      - vnpy-network

  redis:
    image: redis:alpine
    container_name: vnpy-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    networks:
      - vnpy-network

networks:
  vnpy-network:
    driver: bridge
```

### 3. 构建和运行

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f vnpy-trading

# 停止服务
docker-compose down
```

## 云服务器部署

### 1. AWS EC2部署

```bash
# 启动EC2实例（推荐t3.medium或更高配置）
# 选择Ubuntu 20.04 LTS AMI

# 连接到实例
ssh -i your-key.pem ubuntu@your-ec2-ip

# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# 部署应用
git clone <your-repo>
cd vnpy-trading-framework
docker-compose up -d
```

### 2. 阿里云ECS部署

```bash
# 购买ECS实例（推荐2核4GB或更高配置）
# 选择Ubuntu 20.04镜像

# 配置安全组
# 开放端口：22(SSH), 80(HTTP), 443(HTTPS), 8080(应用)

# 部署步骤同AWS EC2
```

### 3. 腾讯云CVM部署

```bash
# 购买CVM实例
# 配置防火墙规则
# 部署步骤同上
```

## 监控和维护

### 1. 系统监控

```bash
# 安装监控工具
sudo apt install htop iotop nethogs

# 监控脚本
#!/bin/bash
# monitor.sh
while true; do
    echo "=== $(date) ==="
    echo "CPU使用率:"
    top -bn1 | grep "Cpu(s)" | awk '{print $2}'
    
    echo "内存使用率:"
    free -h
    
    echo "磁盘使用率:"
    df -h
    
    echo "网络连接:"
    netstat -an | grep :8080
    
    sleep 60
done
```

### 2. 日志轮转

创建 `/etc/logrotate.d/vnpy`：
```
/home/vnpy/trading/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 vnpy vnpy
    postrotate
        systemctl reload vnpy-trading
    endscript
}
```

### 3. 备份策略

```bash
#!/bin/bash
# backup.sh
BACKUP_DIR="/backup/vnpy"
DATE=$(date +%Y%m%d_%H%M%S)

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份配置文件
tar -czf $BACKUP_DIR/config_$DATE.tar.gz /home/vnpy/trading/config/

# 备份数据库
cp /home/vnpy/trading/vnpy_data.db $BACKUP_DIR/database_$DATE.db

# 备份结果文件
tar -czf $BACKUP_DIR/results_$DATE.tar.gz /home/vnpy/trading/results/

# 删除30天前的备份
find $BACKUP_DIR -name "*" -mtime +30 -delete
```

## 故障排除

### 1. 常见问题

#### 依赖安装失败
```bash
# 问题：pip安装失败
# 解决：使用国内镜像源
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements_vnpy.txt

# 问题：编译错误
# 解决：安装编译工具
sudo apt install build-essential python3-dev
```

#### 策略导入失败
```bash
# 问题：ModuleNotFoundError
# 解决：检查Python路径
export PYTHONPATH=$PYTHONPATH:/path/to/vnpy-trading-framework

# 或在代码中添加
import sys
sys.path.append('/path/to/vnpy-trading-framework')
```

#### 交易接口连接失败
```bash
# 问题：API连接超时
# 解决：检查网络和防火墙设置
# 检查API密钥是否正确
# 确认交易时间段
```

### 2. 调试技巧

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 检查策略状态
from vnpy_ctastrategy import CtaEngine
engine = CtaEngine(main_engine, event_engine)
print(engine.get_all_strategy_class_names())

# 测试数据连接
from vnpy.trader.database import get_database
db = get_database()
print(db.get_bar_overview())
```

### 3. 性能优化

```python
# 数据库优化
# 使用更快的数据库（PostgreSQL, ClickHouse）
# 添加索引
# 定期清理历史数据

# 策略优化
# 减少不必要的计算
# 使用向量化操作
# 优化数据结构

# 系统优化
# 增加内存
# 使用SSD存储
# 优化网络连接
```

### 4. 安全建议

```bash
# 1. 使用防火墙
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 8080

# 2. 定期更新系统
sudo apt update && sudo apt upgrade

# 3. 使用强密码和密钥认证
# 4. 定期备份重要数据
# 5. 监控异常活动
# 6. 使用HTTPS加密通信
```

## 联系支持

如果遇到问题，可以通过以下方式获取帮助：

1. **查看文档**: 阅读README.md和相关文档
2. **运行测试**: 使用test_framework.py诊断问题
3. **检查日志**: 查看logs/目录下的日志文件
4. **社区支持**: 访问VN.py官方社区
5. **GitHub Issues**: 在项目仓库提交问题

---

**免责声明**: 本框架仅供学习和研究使用。实盘交易存在风险，请谨慎使用并充分测试。