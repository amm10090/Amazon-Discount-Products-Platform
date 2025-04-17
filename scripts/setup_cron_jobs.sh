#!/usr/bin/env bash
# 设置优惠券抓取脚本的crontab定时任务

# 获取项目根目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# 确保日志目录存在
mkdir -p "$PROJECT_ROOT/logs"

# 临时crontab文件
TEMP_CRONTAB="/tmp/coupon_crontab_temp"

# 备份当前crontab
crontab -l > "$TEMP_CRONTAB" 2>/dev/null || echo "# 创建新的crontab文件" > "$TEMP_CRONTAB"

# 检查是否已经存在相关任务
if ! grep -q "discount_scraper_mt.py" "$TEMP_CRONTAB"; then
    echo "# 亚马逊折扣产品平台 - 优惠券抓取定时任务" >> "$TEMP_CRONTAB"
    # 每天凌晨2点执行常规更新
    echo "0 2 * * * cd $PROJECT_ROOT && $PROJECT_ROOT/venv/bin/python $PROJECT_ROOT/src/core/discount_scraper_mt.py --batch-size 100 --threads 4 --update-interval 24 --log-to-console >> $PROJECT_ROOT/logs/coupon_daily_cron.log 2>&1" >> "$TEMP_CRONTAB"
    # 每周日凌晨3点执行全量更新
    echo "0 3 * * 0 cd $PROJECT_ROOT && $PROJECT_ROOT/venv/bin/python $PROJECT_ROOT/src/core/discount_scraper_mt.py --batch-size 200 --threads 6 --force-update --log-to-console >> $PROJECT_ROOT/logs/coupon_weekly_cron.log 2>&1" >> "$TEMP_CRONTAB"
    
    # 安装新的crontab
    crontab "$TEMP_CRONTAB"
    echo "已成功添加优惠券抓取定时任务到crontab"
else
    echo "优惠券抓取定时任务已存在于crontab中，未做更改"
fi

# 清理临时文件
rm -f "$TEMP_CRONTAB"

echo "当前crontab配置:"
crontab -l | grep -A 3 "优惠券抓取定时任务" || echo "未找到优惠券抓取定时任务" 