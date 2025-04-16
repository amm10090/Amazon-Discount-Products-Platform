#!/bin/bash

# 多线程优惠券抓取器启动脚本

# 进入项目根目录
cd "$(dirname "$0")/.."

# 默认参数
THREADS=4
BATCH_SIZE=100
MIN_DELAY=1.0
MAX_DELAY=3.0
HEADLESS=true
DEBUG=false
LOG_TO_CONSOLE=true

# 解析命令行参数
while [[ $# -gt 0 ]]; do
  case $1 in
    --threads=*)
      THREADS="${1#*=}"
      shift
      ;;
    --batch-size=*)
      BATCH_SIZE="${1#*=}"
      shift
      ;;
    --min-delay=*)
      MIN_DELAY="${1#*=}"
      shift
      ;;
    --max-delay=*)
      MAX_DELAY="${1#*=}"
      shift
      ;;
    --asin=*)
      ASIN="${1#*=}"
      shift
      ;;
    --asin-list=*)
      ASIN_LIST="${1#*=}"
      shift
      ;;
    --no-headless)
      HEADLESS=false
      shift
      ;;
    --debug)
      DEBUG=true
      shift
      ;;
    --verbose)
      VERBOSE=true
      shift
      ;;
    --no-log-console)
      LOG_TO_CONSOLE=false
      shift
      ;;
    *)
      echo "未知参数: $1"
      exit 1
      ;;
  esac
done

# 构建命令参数
CMD="python -m src.core.discount_scraper_mt --threads=$THREADS --batch-size=$BATCH_SIZE --min-delay=$MIN_DELAY --max-delay=$MAX_DELAY"

# 添加可选参数
if [ "$HEADLESS" = false ]; then
  CMD="$CMD --no-headless"
fi

if [ "$DEBUG" = true ]; then
  CMD="$CMD --debug"
fi

if [ "$VERBOSE" = true ]; then
  CMD="$CMD --verbose"
fi

if [ "$LOG_TO_CONSOLE" = true ]; then
  CMD="$CMD --log-to-console"
fi

if [ -n "$ASIN" ]; then
  CMD="$CMD --asin=$ASIN"
fi

if [ -n "$ASIN_LIST" ]; then
  CMD="$CMD --asin-list=$ASIN_LIST"
fi

# 输出运行信息
echo "启动多线程优惠券抓取器"
echo "线程数: $THREADS"
echo "批量大小: $BATCH_SIZE"
echo "请求延迟: $MIN_DELAY-$MAX_DELAY 秒"
echo "无头模式: $HEADLESS"
echo "调试模式: $DEBUG"
echo "控制台日志: $LOG_TO_CONSOLE"

# 运行命令
echo "执行命令: $CMD"
eval "$CMD" 