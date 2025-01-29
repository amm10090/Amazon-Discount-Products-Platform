# Amazon折扣商品平台部署指南

## 系统要求

- Ubuntu 20.04 LTS 或更高版本
- Python 3.8+
- 2GB+ RAM
- 10GB+ 磁盘空间

## 安装步骤

### 1. 安装系统依赖

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv git supervisor nginx
```

### 2. 克隆项目

```bash
git clone [项目仓库URL]
cd Amazon-Discount-Products-Platform
```

### 3. 创建并激活虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. 安装项目依赖

```bash
pip install -r requirements.txt
```

### 5. 配置Supervisor

创建supervisor配置文件：

```bash
sudo nano /etc/supervisor/conf.d/amazon_platform.conf
```

添加以下内容：

```ini
[program:amazon_platform]
directory=/path/to/project
command=/path/to/project/venv/bin/python run.py
user=ubuntu
autostart=true
autorestart=true
stderr_logfile=/var/log/amazon_platform/err.log
stdout_logfile=/var/log/amazon_platform/out.log
environment=PYTHONPATH="/path/to/project"

[supervisord]
logfile=/var/log/supervisor/supervisord.log
pidfile=/var/run/supervisord.pid
childlogdir=/var/log/supervisor
```

### 6. 创建日志目录

```bash
sudo mkdir -p /var/log/amazon_platform
sudo chown -R ubuntu:ubuntu /var/log/amazon_platform
```

### 7. 启动服务

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start amazon_platform
```

## 配置说明

1. 修改 `config/app.yaml` 配置文件：

```yaml
api:
  host: "0.0.0.0"  # 允许外部访问
  port: 8000
  reload: false    # 生产环境关闭热重载

frontend:
  host: "0.0.0.0"
  port: 8501
```

## 监控和维护

### 查看服务状态

```bash
sudo supervisorctl status amazon_platform
```

### 查看日志

```bash
tail -f /var/log/amazon_platform/out.log  # 标准输出
tail -f /var/log/amazon_platform/err.log  # 错误日志
```

### 重启服务

```bash
sudo supervisorctl restart amazon_platform
```

## 故障排除

1. 如果服务无法启动，检查日志文件
2. 确保所有配置文件权限正确
3. 验证虚拟环境和依赖安装是否完整

## 安全建议

1. 使用防火墙限制端口访问
2. 配置SSL证书
3. 定期更新依赖包
4. 设置适当的文件权限 