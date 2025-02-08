import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, JSON, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from pathlib import Path

# 确保data/db目录存在
data_dir = Path(__file__).parent.parent / "data" / "db"
data_dir.mkdir(parents=True, exist_ok=True)

# 优先使用环境变量中的数据库路径
if "PRODUCTS_DB_PATH" in os.environ:
    db_file = os.environ["PRODUCTS_DB_PATH"]
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_file}"
else:
    # 默认路径
    db_file = data_dir / "amazon_products.db"
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_file}"

# 创建数据库引擎
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite特定配置
    pool_pre_ping=True,  # 自动检查连接是否有效
    pool_recycle=3600,  # 每小时回收连接
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 声明基类
Base = declarative_base()

class Product(Base):
    """产品数据模型"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    asin = Column(String(10), unique=True, index=True)
    title = Column(String(500))
    url = Column(String(1000))
    brand = Column(String(200))
    main_image = Column(String(1000))
    
    # 价格信息
    current_price = Column(Float)
    original_price = Column(Float)
    currency = Column(String(10))
    savings_amount = Column(Float)
    savings_percentage = Column(Integer)
    
    # Prime信息
    is_prime = Column(Boolean)
    is_prime_exclusive = Column(Boolean)
    
    # 商品状态
    condition = Column(String(50))
    availability = Column(String(200))
    merchant_name = Column(String(200))
    is_buybox_winner = Column(Boolean)
    
    # 分类信息
    binding = Column(String(100))  # 商品绑定类型
    product_group = Column(String(100))  # 商品分组
    categories = Column(JSON)  # 商品类别列表
    browse_nodes = Column(JSON)  # 商品浏览节点信息
    
    # CJ相关字段
    cj_product_id = Column(String(100))  # CJ商品ID
    cj_commission = Column(Float)  # CJ佣金比例
    cj_discount_code = Column(String(100))  # CJ优惠码
    cj_coupon = Column(String(100))  # CJ优惠券
    cj_url = Column(String(1000))  # CJ推广链接
    cj_parent_asin = Column(String(10))  # CJ父ASIN
    cj_variant_asin = Column(String(10))  # CJ变体ASIN
    cj_rating = Column(Float)  # CJ商品评分
    cj_reviews = Column(Integer)  # CJ商品评论数
    cj_brand_id = Column(Integer)  # CJ品牌ID
    cj_brand_name = Column(String(200))  # CJ品牌名称
    cj_is_featured = Column(Boolean)  # 是否CJ精选商品
    cj_is_amazon_choice = Column(Boolean)  # 是否亚马逊之选
    cj_update_time = Column(DateTime)  # CJ数据更新时间
    
    # 其他信息
    deal_type = Column(String(50))
    features = Column(JSON)  # 存储商品特性列表
    
    # 时间信息
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    timestamp = Column(DateTime, default=datetime.utcnow)  # 数据采集时间
    
    # 元数据
    source = Column(String(50))  # 数据来源渠道：bestseller/coupon/cj
    api_provider = Column(String(50))  # API提供者：pa-api/cj-api等
    raw_data = Column(JSON)  # 存储原始API响应

    # 关联优惠信息
    offers = relationship("Offer", back_populates="product", cascade="all, delete-orphan")
    coupons = relationship("CouponHistory", back_populates="product", cascade="all, delete-orphan")
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Product(asin={self.asin}, title={self.title})>"

class Offer(Base):
    """商品优惠信息表"""
    __tablename__ = "offers"
    
    # 主键和外键
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(10), ForeignKey("products.asin", ondelete="CASCADE"))
    
    # 价格信息
    price = Column(Float)
    currency = Column(String(10))
    savings = Column(Float)
    savings_percentage = Column(Integer)
    
    # 优惠券信息
    coupon_type = Column(String(50))      # 优惠券类型（percentage/fixed）
    coupon_value = Column(Float)          # 优惠券值（百分比或固定金额）
    
    # 商品状态
    condition = Column(String(50))
    availability = Column(String(200))
    merchant_name = Column(String(200))
    is_buybox_winner = Column(Boolean, default=False)
    
    # Prime和配送信息
    is_prime = Column(Boolean, default=False)
    is_amazon_fulfilled = Column(Boolean, default=False)  # 是否由亚马逊配送
    is_free_shipping_eligible = Column(Boolean, default=False)  # 是否符合免运费资格
    deal_type = Column(String(50))
    
    # 关联商品
    product = relationship("Product", back_populates="offers")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class CouponHistory(Base):
    """优惠券历史记录表"""
    __tablename__ = "coupon_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(10), ForeignKey("products.asin", ondelete="CASCADE"))
    
    # 优惠券信息
    coupon_type = Column(String(50))      # 优惠券类型（percentage/fixed）
    coupon_value = Column(Float)          # 优惠券值（百分比或固定金额）
    
    # 时间信息
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联商品
    product = relationship("Product", back_populates="coupons")
    
    def __repr__(self):
        return f"<CouponHistory(product_id={self.product_id}, type={self.coupon_type}, value={self.coupon_value})>"

class ProductVariant(Base):
    """产品变体关系表"""
    __tablename__ = "product_variants"
    
    id = Column(Integer, primary_key=True)
    parent_asin = Column(String(10), index=True)  # 父ASIN
    variant_asin = Column(String(10), ForeignKey("products.asin"), index=True)  # 变体ASIN
    variant_attributes = Column(JSON)  # 变体特有属性(如颜色、尺寸等)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联到主商品表
    product = relationship("Product", back_populates="variants")

def init_db():
    """初始化数据库，创建所有表"""
    # 初始化主数据库
    Base.metadata.create_all(bind=engine)
    
    # 初始化CJ数据库
    Base.metadata.create_all(bind=cj_engine)
    
    print("数据库初始化完成：主数据库和CJ数据库已创建")

# 获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 获取CJ数据库会话
def get_cj_db():
    db = CJSessionLocal()
    try:
        yield db
    finally:
        db.close()

# 优先使用环境变量中的数据库路径
if "CJ_PRODUCTS_DB_PATH" in os.environ:
    cj_db_file = os.environ["CJ_PRODUCTS_DB_PATH"]
    CJ_DATABASE_URL = f"sqlite:///{cj_db_file}"
else:
    # 默认路径
    cj_db_file = data_dir / "cj_products.db"
    CJ_DATABASE_URL = f"sqlite:///{cj_db_file}"

# 创建CJ数据库引擎
cj_engine = create_engine(
    CJ_DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite特定配置
    pool_pre_ping=True,  # 自动检查连接是否有效
    pool_recycle=3600,  # 每小时回收连接
)

# 创建CJ会话工厂
CJSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cj_engine)

class CJProduct(Base):
    """CJ商品数据模型"""
    __tablename__ = "cj_products"

    id = Column(Integer, primary_key=True, index=True)
    asin = Column(String(10), unique=True, index=True)
    product_id = Column(String(100), unique=True)  # CJ商品ID
    product_name = Column(String(500))  # 商品名称
    brand_name = Column(String(200))  # 品牌名称
    brand_id = Column(Integer)  # 品牌ID
    
    # 图片和链接
    image = Column(String(1000))  # 商品图片
    url = Column(String(1000))  # 商品链接
    affiliate_url = Column(String(1000))  # 推广链接
    
    # 价格信息
    original_price = Column(Float)  # 原价
    discount_price = Column(Float)  # 折扣价
    commission = Column(Float)  # 佣金比例
    
    # 折扣信息
    discount_code = Column(String(100))  # 折扣码
    coupon = Column(String(100))  # 优惠券
    
    # 商品关系
    parent_asin = Column(String(10), index=True)  # 父ASIN
    is_parent = Column(Boolean, default=False)  # 是否为父商品
    
    # 评分信息
    rating = Column(Float)  # 商品评分
    reviews = Column(Integer)  # 评论数量
    
    # 分类信息
    category = Column(String(200))  # 主分类
    subcategory = Column(String(200))  # 子分类
    
    # 商品状态
    is_featured_product = Column(Boolean, default=False)  # 是否精选商品
    is_amazon_choice = Column(Boolean, default=False)  # 是否亚马逊之选
    
    # 时间信息
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    update_time = Column(DateTime)  # CJ平台更新时间
    
    # 原始数据
    raw_data = Column(JSON)  # 存储原始API响应

    # 变体关系
    variants = relationship("CJProductVariant", back_populates="parent", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CJProduct(asin={self.asin}, name={self.product_name})>"

class CJProductVariant(Base):
    """CJ商品变体关系表"""
    __tablename__ = "cj_product_variants"
    
    id = Column(Integer, primary_key=True)
    parent_asin = Column(String(10), ForeignKey("cj_products.asin", ondelete="CASCADE"), index=True)
    variant_asin = Column(String(10), index=True)
    
    # 变体特有属性
    product_name = Column(String(500))
    image = Column(String(1000))
    url = Column(String(1000))
    affiliate_url = Column(String(1000))
    original_price = Column(Float)
    discount_price = Column(Float)
    discount_code = Column(String(100))
    coupon = Column(String(100))
    
    # 变体属性(如颜色、尺寸等)
    variant_attributes = Column(JSON)
    
    # 时间信息
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联到父商品
    parent = relationship("CJProduct", back_populates="variants")

    def __repr__(self):
        return f"<CJProductVariant(parent_asin={self.parent_asin}, variant_asin={self.variant_asin})>" 