# Amazon折扣商品平台部署指南

## 1. 环境准备

### 系统要求
- Ubuntu 20.04 或更高版本
- Python 3.8+
- PostgreSQL（可选）
- Nginx
- pnpm（用于前端依赖管理）

### 安装系统依赖
```bash
# 更新系统包
sudo apt update
sudo apt upgrade -y

# 安装必要的系统依赖
sudo apt install -y python3-pip python3-dev build-essential libssl-dev libffi-dev python3-setuptools nginx postgresql postgresql-contrib

# 安装pnpm
curl -fsSL https://get.pnpm.io/install.sh | sh -
```

## 2. 项目部署

### 克隆项目
```bash
git clone [https://github.com/amm10090/Amazon-Discount-Products-Platform]
cd Amazon-Discount-Products-Platform
```

### 配置Python环境
```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装项目依赖
pip install -r requirements.txt
```

### 配置环境变量
```bash
# 复制环境变量模板
cp .env.example .env

# 编辑.env文件，填入必要的配置信息
# 包括：
# - Amazon PA-API 密钥
# - 数据库配置
# - 其他必要的API密钥
```

### 配置数据库
```bash
# 如果使用PostgreSQL，创建数据库和用户
sudo -u postgres psql
CREATE DATABASE amazon_discount;
CREATE USER amazon_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE amazon_discount TO amazon_user;
```

## 3. 服务配置

### 配置Supervisor
```bash
sudo apt install supervisor
sudo nano /etc/supervisor/conf.d/amazon_platform.conf
```

添加以下配置：
```ini
[group:amazon_platform]
programs=fastapi_server,streamlit_frontend,scheduler_server

; FastAPI服务
[program:fastapi_server]
directory=/root/Amazon-Discount-Products-Platform
command=/root/Amazon-Discount-Products-Platform/venv/bin/uvicorn amazon_crawler_api:app --host 0.0.0.0 --port 5001 --workers 4
user=root
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=10
startretries=3
redirect_stderr=true
stdout_logfile=/var/log/amazon_platform/fastapi.log
stdout_logfile_maxbytes=20MB
stdout_logfile_backups=10
stderr_logfile=/var/log/amazon_platform/fastapi_err.log
stderr_logfile_maxbytes=20MB
stderr_logfile_backups=10
environment=PYTHONPATH="/root/Amazon-Discount-Products-Platform",PATH="/root/Amazon-Discount-Products-Platform/venv/bin:%(ENV_PATH)s",CONFIG_PATH="/root/Amazon-Discount-Products-Platform/config/production.yaml"

; Streamlit前端服务
[program:streamlit_frontend]
directory=/root/Amazon-Discount-Products-Platform
command=/root/Amazon-Discount-Products-Platform/venv/bin/streamlit run frontend/main.py --server.port 5002 --server.address 0.0.0.0
user=root
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=10
startretries=3
redirect_stderr=true
stdout_logfile=/var/log/amazon_platform/streamlit.log
stdout_logfile_maxbytes=20MB
stdout_logfile_backups=10
stderr_logfile=/var/log/amazon_platform/streamlit_err.log
stderr_logfile_maxbytes=20MB
stderr_logfile_backups=10
environment=PYTHONPATH="/root/Amazon-Discount-Products-Platform",PATH="/root/Amazon-Discount-Products-Platform/venv/bin:%(ENV_PATH)s",CONFIG_PATH="/root/Amazon-Discount-Products-Platform/config/production.yaml"

; 调度器服务
[program:scheduler_server]
directory=/root/Amazon-Discount-Products-Platform
command=/root/Amazon-Discount-Products-Platform/venv/bin/python run.py --config config/production.yaml
user=root
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=10
startretries=3
redirect_stderr=true
stdout_logfile=/var/log/amazon_platform/scheduler.log
stdout_logfile_maxbytes=20MB
stdout_logfile_backups=10
stderr_logfile=/var/log/amazon_platform/scheduler_err.log
stderr_logfile_maxbytes=20MB
stderr_logfile_backups=10
environment=PYTHONPATH="/root/Amazon-Discount-Products-Platform",PATH="/root/Amazon-Discount-Products-Platform/venv/bin:%(ENV_PATH)s",CONFIG_PATH="/root/Amazon-Discount-Products-Platform/config/production.yaml"

[supervisord]
logfile=/var/log/supervisor/supervisord.log
logfile_maxbytes=50MB
logfile_backups=10
loglevel=info
pidfile=/var/run/supervisord.pid
nodaemon=false
minfds=1024
minprocs=200

; 内存监控
[eventlistener:memmon]
command=memmon -p fastapi_server=500MB streamlit_frontend=300MB scheduler_server=200MB
events=TICK_60 

```

### 配置Nginx
```bash
sudo nano /etc/nginx/sites-available/amazon_platform
```

添加以下配置：
```nginx
server {
    listen 80;
    server_name your_domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

```bash
# 启用站点配置
sudo ln -s /etc/nginx/sites-available/amazon_platform /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx
```

## 4. 启动服务

```bash
# 重启Supervisor服务
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart amazon_platform

# 检查服务状态
sudo supervisorctl status amazon_platform
```

## 5. 定时任务配置

配置爬虫和数据更新的定时任务：
```bash
# 编辑crontab
crontab -e

# 添加定时任务
0 */4 * * * /path/to/project/venv/bin/python /path/to/project/service_scheduler.py
```

## 6. 监控和日志

日志文件位置：
- 应用日志：`/path/to/project/logs/service.log`
- Supervisor日志：`/var/log/amazon_platform/`
- Nginx日志：`/var/log/nginx/`

## 7. 安全配置

1. 配置防火墙：
```bash
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

2. 设置SSL证书（推荐使用Let's Encrypt）：
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your_domain.com
```

## 8. 备份策略

1. 数据库备份：
```bash
# 创建备份脚本
mkdir -p /path/to/backups
pg_dump amazon_discount > /path/to/backups/backup_$(date +%Y%m%d).sql
```

2. 配置定时备份：
```bash
# 添加到crontab
0 0 * * * /path/to/backup_script.sh
```

## 9. 故障排除

常见问题及解决方案：

1. 服务无法启动
   - 检查日志文件
   - 验证环境变量配置
   - 确认端口是否被占用

2. 数据库连接问题
   - 检查数据库配置
   - 验证数据库服务状态
   - 确认防火墙设置

3. 爬虫任务失败
   - 检查网络连接
   - 验证API密钥有效性
   - 查看爬虫日志

## 10. 更新维护

1. 代码更新流程：
```bash
# 拉取最新代码
git pull

# 更新依赖
pip install -r requirements.txt

# 重启服务
sudo supervisorctl restart amazon_platform
```

2. 定期维护检查：
   - 监控系统资源使用
   - 检查日志文件大小
   - 清理临时文件
   - 更新SSL证书 