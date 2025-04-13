# 商品数据清理工具

这个目录包含用于清理Amazon商品数据库中没有优惠的商品的脚本工具。这些工具可以帮助保持数据库中只存储有价值的折扣或优惠券商品。

## 功能说明

系统定义的"没有优惠的商品"是指同时满足以下条件的商品：

1. 没有优惠券历史记录（在`CouponHistory`表中没有记录）
2. 没有价格折扣（`savings_percentage`为0或NULL）
3. 在`Offer`表中没有任何优惠券信息

## 可用脚本

本目录包含以下脚本：

1. `remove_products_without_discount.py` - 单次运行的删除工具，支持多种过滤参数
2. `scheduled_cleanup.py` - 支持多策略的定时清理工具
3. `setup_cleanup_cron.sh` - 自动设置crontab定时任务的Shell脚本
4. `insert_test_products_without_discount.py` - 插入没有优惠的测试商品，用于测试清理功能

## 使用方法

### 单次手动删除

使用`remove_products_without_discount.py`脚本可以执行单次清理操作：

```bash
# 模拟运行，不实际删除，查看哪些商品会被删除
python remove_products_without_discount.py --dry-run

# 删除至少7天前创建的没有优惠的商品
python remove_products_without_discount.py --min-days-old 7

# 删除特定API来源的商品
python remove_products_without_discount.py --api-provider cj-api

# 限制价格范围
python remove_products_without_discount.py --min-price 10 --max-price 50

# 限制最多删除的商品数量
python remove_products_without_discount.py --limit 100

# 自动确认删除而不提示
python remove_products_without_discount.py --yes
```

### 使用策略化清理

`scheduled_cleanup.py`脚本支持根据预定义的策略执行清理：

```bash
# 列出所有可用的清理策略
python scheduled_cleanup.py --list

# 模拟运行所有策略但不实际删除
python scheduled_cleanup.py --dry-run

# 仅执行特定策略
python scheduled_cleanup.py --strategies "过期PA-API商品,低价无优惠商品"

# 实际执行所有策略
python scheduled_cleanup.py
```

### 设置定时任务

使用`setup_cleanup_cron.sh`脚本可以自动设置crontab定时任务：

```bash
# 添加执行权限
chmod +x setup_cleanup_cron.sh

# 运行脚本设置定时任务
./setup_cleanup_cron.sh
```

这将设置以下定时任务：

1. 每天凌晨3点 - 运行所有清理策略
2. 每周一凌晨4点 - 专门清理低价无优惠商品 
3. 每月1号凌晨5点 - 执行完整清理，处理所有30天前的无优惠商品

### 插入测试数据

使用`insert_test_products_without_discount.py`脚本可以向数据库插入没有优惠的测试商品，以便测试清理功能：

```bash
# 添加执行权限
chmod +x insert_test_products_without_discount.py

# 插入默认的所有测试商品（10个）
python insert_test_products_without_discount.py

# 插入指定数量的测试商品
python insert_test_products_without_discount.py --count 5

# 选择使用ORM方法创建商品
python insert_test_products_without_discount.py --method orm

# 选择使用Service方法创建商品
python insert_test_products_without_discount.py --method service

# 强制重新创建已存在的商品
python insert_test_products_without_discount.py --force

# 插入后检查商品是否符合"无优惠"条件
python insert_test_products_without_discount.py --check
```

测试商品包括不同价格范围、不同API提供商和不同创建时间的商品，可以用来全面测试清理功能的各种参数组合。

## 预定义策略说明

`scheduled_cleanup.py`中预定义了以下清理策略：

1. **过期PA-API商品** - 删除3天前创建的PA-API无优惠商品
2. **过期CJ-API商品** - 删除7天前创建的CJ-API无优惠商品
3. **低价无优惠商品** - 删除1天前创建的价格低于$10的无优惠商品
4. **高价无优惠商品** - 删除14天前创建的价格高于$100的无优惠商品

您可以在`scheduled_cleanup.py`文件中的`CLEANUP_STRATEGIES`变量中调整或添加新的策略。

## 日志

所有清理操作的日志都会保存在项目根目录下的`logs`文件夹中。定时任务会按日期生成单独的日志文件。

## 安全提示

- 首次使用时，建议使用`--dry-run`参数查看会删除的商品，确认无误后再执行实际删除
- 定期检查日志文件，确保清理任务正常执行
- 修改策略参数时应谨慎，建议先使用`--dry-run`测试新策略 