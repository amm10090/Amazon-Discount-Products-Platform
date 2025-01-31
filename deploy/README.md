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
[program:amazon_platform]
directory=/path/to/your/project
command=/path/to/your/venv/bin/python run.py
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/amazon_platform.err.log
stdout_logfile=/var/log/supervisor/amazon_platform.out.log
environment=CONFIG_PATH="/path/to/your/project/config/production.yaml"

user=your_user  # 运行服务的用户
numprocs=1
process_name=%(program_name)s_%(process_num)02d
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
## 4.1更新和重启服务
# 重新加载supervisor配置
sudo supervisorctl reread

# 更新配置
sudo supervisorctl update

# 重启所有服务
sudo supervisorctl restart amazon_platform:*

# 检查状态
sudo supervisorctl status
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

## 使用 Supervisor 部署

### 1. 安装 Supervisor

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install supervisor

# CentOS/RHEL
sudo yum install supervisor
sudo systemctl enable supervisord
sudo systemctl start supervisord
```

### 2. 创建 Supervisor 配置文件

在 `/etc/supervisor/conf.d/` 目录下创建配置文件：

```bash
sudo nano /etc/supervisor/conf.d/amazon_platform.conf
```

配置文件内容：

```ini
[program:amazon_platform]
directory=/path/to/your/project
command=/path/to/your/venv/bin/python run.py
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/amazon_platform.err.log
stdout_logfile=/var/log/supervisor/amazon_platform.out.log
environment=CONFIG_PATH="/path/to/your/project/config/production.yaml"

user=your_user  # 运行服务的用户
numprocs=1
process_name=%(program_name)s_%(process_num)02d
```

### 3. 创建日志目录

```bash
sudo mkdir -p /var/log/supervisor
sudo chown -R your_user:your_user /var/log/supervisor
```

### 4. 更新 Supervisor 配置

```bash
# 重新加载配置
sudo supervisorctl reread

# 更新配置
sudo supervisorctl update

# 启动服务
sudo supervisorctl start amazon_platform:*
```

### 5. 查看服务状态

```bash
# 查看所有服务状态
sudo supervisorctl status

# 查看特定服务状态
sudo supervisorctl status amazon_platform:*
```

### 6. 常用管理命令

```bash
# 启动服务
sudo supervisorctl start amazon_platform:*

# 停止服务
sudo supervisorctl stop amazon_platform:*

# 重启服务
sudo supervisorctl restart amazon_platform:*

# 查看日志
sudo tail -f /var/log/supervisor/amazon_platform.out.log
sudo tail -f /var/log/supervisor/amazon_platform.err.log
```

### 7. 注意事项

1. 确保配置文件中的路径都是绝对路径
2. 确保运行服务的用户有足够的权限
3. 确保环境变量正确设置
4. 建议在生产环境使用虚拟环境
5. 定期检查日志文件大小，必要时进行日志轮转

### 8. 日志轮转配置

创建日志轮转配置文件：

```bash
sudo nano /etc/logrotate.d/supervisor
```

添加以下内容：

```
/var/log/supervisor/*.log {
    weekly
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    copytruncate
}
```

### 9. 故障排查

1. 检查服务状态：
```bash
sudo supervisorctl status
```

2. 检查日志文件：
```bash
sudo tail -f /var/log/supervisor/amazon_platform.out.log
sudo tail -f /var/log/supervisor/amazon_platform.err.log
```

3. 检查 Supervisor 系统日志：
```bash
sudo tail -f /var/log/supervisor/supervisord.log
```

4. 常见问题解决：

- 如果服务无法启动，检查：
  - 配置文件路径是否正确
  - 用户权限是否足够
  - 虚拟环境路径是否正确
  - 项目依赖是否安装完整

- 如果服务频繁重启：
  - 检查错误日志
  - 确认内存使用情况
  - 检查磁盘空间

### 10. 生产环境配置建议

1. 内存管理：
```ini
[program:amazon_platform]
# ... 其他配置 ...
stopasgroup=true
killasgroup=true
```

2. 环境变量设置：
```ini
environment=CONFIG_PATH="/path/to/your/project/config/production.yaml",PYTHONPATH="/path/to/your/project"
```

3. 启动重试设置：
```ini
startretries=3
startsecs=10
```

4. 进程控制：
```ini
stopwaitsecs=60
stopsignal=TERM
``` 