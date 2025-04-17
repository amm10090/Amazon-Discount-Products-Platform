#!/bin/bash

# 设置项目根目录环境变量供Supervisor使用
# 获取项目根目录的绝对路径
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# 创建Supervisor环境变量配置目录
sudo mkdir -p /etc/supervisor/conf.d/environment/

# 创建环境变量文件
cat > /tmp/project_env.conf << EOF
[supervisord]
environment=PROJECT_ROOT="$PROJECT_ROOT"
EOF

# 复制到Supervisor配置目录
sudo cp /tmp/project_env.conf /etc/supervisor/conf.d/environment/amazon_project_env.conf

# 清理临时文件
rm -f /tmp/project_env.conf

echo "已设置Supervisor环境变量: PROJECT_ROOT=$PROJECT_ROOT" 