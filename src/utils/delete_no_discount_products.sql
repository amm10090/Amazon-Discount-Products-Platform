-- 删除没有任何优惠信息的商品SQL脚本
-- 该脚本会删除既没有折扣、也没有优惠券、也没有促销标签的商品

-- 开始事务
BEGIN;

-- 步骤1: 创建临时表存储要删除的商品ASIN
CREATE TEMPORARY TABLE temp_products_to_delete AS
SELECT p.asin
FROM products p
LEFT JOIN offers o ON p.asin = o.product_id
WHERE
  -- 没有折扣
  (p.savings_amount IS NULL OR p.savings_amount <= 0)
  AND (p.savings_percentage IS NULL OR p.savings_percentage <= 0)
  -- 没有优惠券
  AND (o.coupon_type IS NULL OR o.coupon_type = '')
  AND (o.coupon_value IS NULL OR o.coupon_value <= 0)
  -- 没有促销标签
  AND (o.deal_badge IS NULL OR o.deal_badge = '');

-- 步骤2: 输出要删除的商品数量
SELECT COUNT(*) AS products_to_delete_count FROM temp_products_to_delete;

-- 步骤3: 删除关联的优惠信息
DELETE FROM offers
WHERE product_id IN (SELECT asin FROM temp_products_to_delete);

-- 步骤4: 删除商品记录
DELETE FROM products
WHERE asin IN (SELECT asin FROM temp_products_to_delete);

-- 步骤5: 提交事务 (如需执行，请移除下面的注释)
-- COMMIT;

-- 默认回滚事务，防止误操作
ROLLBACK;

-- 注意: 默认情况下此脚本会回滚所有操作，不会实际删除任何数据
-- 如需实际执行删除操作，请将ROLLBACK注释掉，并取消COMMIT的注释

-- 使用过滤条件的版本 (按创建时间、价格等过滤)
-- 取消下面注释可以使用带过滤条件的查询

/*
BEGIN;

-- 创建临时表存储要删除的商品ASIN (带过滤条件)
CREATE TEMPORARY TABLE temp_products_to_delete AS
SELECT p.asin
FROM products p
LEFT JOIN offers o ON p.asin = o.product_id
WHERE
  -- 没有折扣
  (p.savings_amount IS NULL OR p.savings_amount <= 0)
  AND (p.savings_percentage IS NULL OR p.savings_percentage <= 0)
  -- 没有优惠券
  AND (o.coupon_type IS NULL OR o.coupon_type = '')
  AND (o.coupon_value IS NULL OR o.coupon_value <= 0)
  -- 没有促销标签
  AND (o.deal_badge IS NULL OR o.deal_badge = '')
  
  -- 可选的过滤条件 (根据需要取消注释并修改)
  -- 创建时间过滤 (例如只删除30天前创建的商品)
  -- AND p.created_at < NOW() - INTERVAL '30 days'
  
  -- 价格过滤 (例如只删除价格在10-100范围的商品)
  -- AND (p.current_price >= 10 AND p.current_price <= 100)
  
  -- 结果限制 (例如最多删除1000个商品)
  -- LIMIT 1000
;

-- 删除关联的优惠信息
DELETE FROM offers
WHERE product_id IN (SELECT asin FROM temp_products_to_delete);

-- 删除商品记录
DELETE FROM products
WHERE asin IN (SELECT asin FROM temp_products_to_delete);

-- 查看删除结果
SELECT COUNT(*) AS deleted_count FROM temp_products_to_delete;

ROLLBACK; -- 默认回滚，改为COMMIT;来实际执行删除
*/ 