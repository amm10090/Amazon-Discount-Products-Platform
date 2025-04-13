#!/bin/bash
# 设置定时清理任务的crontab配置

# 获取当前脚本所在目录的绝对路径
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 设置Python解释器和脚本路径
PYTHON_PATH="$(which python3)"
DAILY_CLEANUP_SCRIPT="$SCRIPT_DIR/scheduled_cleanup.py"
FULL_CLEANUP_SCRIPT="$SCRIPT_DIR/remove_products_without_discount.py"

# 设置日志目录
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

# 检查脚本是否存在
if [ ! -f "$DAILY_CLEANUP_SCRIPT" ]; then
    echo "错误: 清理脚本 $DAILY_CLEANUP_SCRIPT 不存在!"
    exit 1
fi

if [ ! -f "$FULL_CLEANUP_SCRIPT" ]; then
    echo "错误: 清理脚本 $FULL_CLEANUP_SCRIPT 不存在!"
    exit 1
fi

# 设置crontab条目
# 1. 每天凌晨3点运行定时清理脚本，执行默认策略
DAILY_CRON="0 3 * * * cd $PROJECT_ROOT && $PYTHON_PATH $DAILY_CLEANUP_SCRIPT >> $LOG_DIR/daily_cleanup_\$(date +\%Y\%m\%d).log 2>&1"

# 2. 每周一凌晨4点运行，执行价格低的无优惠商品清理
WEEKLY_LOW_PRICE_CRON="0 4 * * 1 cd $PROJECT_ROOT && $PYTHON_PATH $DAILY_CLEANUP_SCRIPT --strategies '低价无优惠商品' >> $LOG_DIR/weekly_low_price_cleanup_\$(date +\%Y\%m\%d).log 2>&1"

# 3. 每月1号凌晨5点运行，执行完整清理，对所有无优惠商品进行处理
MONTHLY_FULL_CRON="0 5 1 * * cd $PROJECT_ROOT && $PYTHON_PATH $FULL_CLEANUP_SCRIPT --min-days-old 30 --yes >> $LOG_DIR/monthly_full_cleanup_\$(date +\%Y\%m\%d).log 2>&1"

# 临时文件用于存储当前的crontab
TEMP_CRONTAB=$(mktemp)

# 导出当前的crontab
crontab -l > "$TEMP_CRONTAB" 2>/dev/null

# 检查是否已存在相同的任务，如果不存在则添加
if ! grep -q "$DAILY_CLEANUP_SCRIPT" "$TEMP_CRONTAB"; then
    echo "# 每天凌晨3点运行Amazon商品清理" >> "$TEMP_CRONTAB"
    echo "$DAILY_CRON" >> "$TEMP_CRONTAB"
    echo "" >> "$TEMP_CRONTAB"
fi

if ! grep -q "低价无优惠商品" "$TEMP_CRONTAB"; then
    echo "# 每周一凌晨4点清理低价无优惠商品" >> "$TEMP_CRONTAB"
    echo "$WEEKLY_LOW_PRICE_CRON" >> "$TEMP_CRONTAB"
    echo "" >> "$TEMP_CRONTAB"
fi

if ! grep -q "monthly_full_cleanup" "$TEMP_CRONTAB"; then
    echo "# 每月1号凌晨5点运行完整清理" >> "$TEMP_CRONTAB"
    echo "$MONTHLY_FULL_CRON" >> "$TEMP_CRONTAB"
    echo "" >> "$TEMP_CRONTAB"
fi

# 更新crontab
crontab "$TEMP_CRONTAB"
rm "$TEMP_CRONTAB"

echo "已成功设置以下定时清理任务:"
echo "1. 每天凌晨3点 - 运行定时清理脚本，执行默认策略"
echo "2. 每周一凌晨4点 - 清理低价无优惠商品"
echo "3. 每月1号凌晨5点 - 执行完整清理，处理所有30天前的无优惠商品"
echo ""
echo "以下是当前的crontab配置:"
crontab -l | grep -E "cleanup|clean"
echo ""
echo "日志文件将保存在: $LOG_DIR 目录"

# 为脚本添加执行权限
chmod +x "$DAILY_CLEANUP_SCRIPT"
chmod +x "$FULL_CLEANUP_SCRIPT"
chmod +x "$0"

echo "脚本执行权限已设置"
echo "设置完成!" 