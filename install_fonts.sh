#!/bin/bash
#
# 此脚本用于安装中文字体，解决matplotlib中文显示问题
#

echo "开始安装中文字体..."

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then
  echo "请使用root权限运行此脚本"
  exit 1
fi

# 安装文泉驿字体
apt-get update
apt-get install -y fonts-wqy-microhei fonts-wqy-zenhei

# 安装思源字体
apt-get install -y fonts-noto-cjk

# 清除字体缓存
fc-cache -fv

echo "字体安装完成！"
echo "请重启应用程序以应用新字体。" 