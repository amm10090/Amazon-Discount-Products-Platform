"""
数据库模型定义模块

本模块定义了应用程序的所有数据库模型，使用SQLAlchemy ORM框架。
主要包含以下模型：
- Product: 产品基本信息
- Offer: 产品优惠信息
- CouponHistory: 优惠券历史记录
- ProductVariant: 产品变体关系
"""

import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, JSON, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from pathlib import Path

# 确保数据存储目录存在
data_dir = Path(__file__).parent.parent / "data" / "db"
data_dir.mkdir(parents=True, exist_ok=True)

# 数据库连接配置
# 支持通过环境变量自定义数据库路径，方便在不同环境中部署
if "PRODUCTS_DB_PATH" in os.environ:
    db_file = os.environ["PRODUCTS_DB_PATH"]
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_file}"
else:
    # 默认使用项目目录下的数据库文件
    db_file = data_dir / "amazon_products.db"
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_file}"

# 创建数据库引擎，配置SQLite特定参数
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite线程安全配置
    pool_pre_ping=True,  # 自动检查连接有效性
    pool_recycle=3600,  # 连接池回收时间
)

# 创建会话工厂，用于管理数据库会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# SQLAlchemy模型基类
Base = declarative_base()

class Product(Base):
    """
    产品数据模型
    存储从亚马逊采集的商品基本信息、价格信息、状态等
    
    关联关系：
    - offers: 一对多关系，关联商品的优惠信息
    - coupons: 一对多关系，关联商品的优惠券历史
    - variants: 一对多关系，关联商品的变体信息
    """
    __tablename__ = "products"

    # 基本信息
    id = Column(Integer, primary_key=True, index=True)
    asin = Column(String(10), unique=True, index=True)  # 亚马逊商品唯一标识符
    title = Column(String(500))  # 商品标题
    url = Column(String(1000))  # 商品链接
    brand = Column(String(200))  # 品牌名称
    main_image = Column(String(1000))  # 主图链接
    
    # CJ特有信息
    cj_url = Column(String(1000))  # CJ推广链接
    
    # 价格信息
    current_price = Column(Float)  # 当前价格
    original_price = Column(Float)  # 原始价格
    currency = Column(String(10))  # 货币单位
    savings_amount = Column(Float)  # 节省金额
    savings_percentage = Column(Integer)  # 折扣百分比
    
    # Prime会员信息
    is_prime = Column(Boolean)  # 是否Prime商品
    is_prime_exclusive = Column(Boolean)  # 是否Prime会员专享
    
    # 商品状态
    condition = Column(String(50))  # 商品状态(新品/二手等)
    availability = Column(String(200))  # 库存状态
    merchant_name = Column(String(200))  # 卖家名称
    is_buybox_winner = Column(Boolean)  # 是否为购买框优胜者
    
    # 分类信息
    binding = Column(String(100))  # 商品绑定类型(如Kindle/平装书等)
    product_group = Column(String(100))  # 商品分组
    categories = Column(JSON)  # 商品分类路径，JSON数组格式
    browse_nodes = Column(JSON)  # 亚马逊浏览节点信息
    
    # 其他信息
    deal_type = Column(String(50))  # 优惠类型
    features = Column(JSON)  # 商品特性列表
    
    # 时间信息，用于追踪记录的生命周期
    created_at = Column(DateTime, default=datetime.utcnow)  # 记录创建时间
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # 记录更新时间
    timestamp = Column(DateTime, default=datetime.utcnow)  # 数据采集时间
    
    # 元数据
    source = Column(String(50))  # 数据来源：bestseller/coupon/cj
    api_provider = Column(String(50))  # API提供者：pa-api/cj-api
    raw_data = Column(JSON)  # 原始API响应数据，用于数据追溯

    # 关联关系定义
    offers = relationship("Offer", back_populates="product", cascade="all, delete-orphan")
    coupons = relationship("CouponHistory", back_populates="product", cascade="all, delete-orphan")
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")

    def __repr__(self):
        """对象的字符串表示"""
        return f"<Product(asin={self.asin}, title={self.title})>"

class Offer(Base):
    """
    商品优惠信息表
    记录商品的价格优惠、促销、Prime特权等信息
    
    关联关系：
    - product: 多对一关系，关联到商品基本信息
    """
    __tablename__ = "offers"
    
    # 主键和外键
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(10), ForeignKey("products.asin", ondelete="CASCADE"))
    
    # 价格信息
    price = Column(Float)  # 优惠价格
    currency = Column(String(10))  # 货币单位
    savings = Column(Float)  # 节省金额
    savings_percentage = Column(Integer)  # 折扣百分比
    
    # 优惠券信息
    coupon_type = Column(String(50))  # 优惠券类型：percentage(百分比)/fixed(固定金额)
    coupon_value = Column(Float)  # 优惠券面值
    
    # CJ特有信息
    commission = Column(String(50))  # CJ佣金信息
    
    # 商品状态
    condition = Column(String(50))  # 商品状态
    availability = Column(String(200))  # 库存状态
    merchant_name = Column(String(200))  # 卖家名称
    is_buybox_winner = Column(Boolean, default=False)  # 是否为购买框优胜者
    
    # Prime和配送信息
    is_prime = Column(Boolean, default=False)  # 是否Prime商品
    is_amazon_fulfilled = Column(Boolean, default=False)  # 是否由亚马逊配送
    is_free_shipping_eligible = Column(Boolean, default=False)  # 是否符合免运费条件
    deal_type = Column(String(50))  # 优惠类型
    
    # 关联商品
    product = relationship("Product", back_populates="offers")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)  # 记录创建时间
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # 记录更新时间

class CouponHistory(Base):
    """
    优惠券历史记录表
    记录商品优惠券的历史变化，用于分析优惠券趋势
    
    关联关系：
    - product: 多对一关系，关联到商品基本信息
    """
    __tablename__ = "coupon_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(10), ForeignKey("products.asin", ondelete="CASCADE"))
    
    # 优惠券信息
    coupon_type = Column(String(50))  # 优惠券类型：percentage(百分比)/fixed(固定金额)
    coupon_value = Column(Float)  # 优惠券面值
    
    # 时间信息
    created_at = Column(DateTime, default=datetime.utcnow)  # 记录创建时间
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # 记录更新时间
    
    # 关联商品
    product = relationship("Product", back_populates="coupons")
    
    def __repr__(self):
        """对象的字符串表示"""
        return f"<CouponHistory(product_id={self.product_id}, type={self.coupon_type}, value={self.coupon_value})>"

class ProductVariant(Base):
    """
    产品变体关系表
    记录商品的不同变体信息，如颜色、尺寸等
    
    关联关系：
    - product: 多对一关系，关联到商品基本信息
    """
    __tablename__ = "product_variants"
    
    id = Column(Integer, primary_key=True)
    parent_asin = Column(String(10), index=True)  # 父商品ASIN
    variant_asin = Column(String(10), ForeignKey("products.asin"), index=True)  # 变体商品ASIN
    variant_attributes = Column(JSON)  # 变体特有属性，如颜色、尺寸等
    created_at = Column(DateTime, default=datetime.utcnow)  # 记录创建时间
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # 记录更新时间

    # 关联到主商品表
    product = relationship("Product", back_populates="variants")

def init_db():
    """
    初始化数据库
    创建所有定义的数据表
    """
    Base.metadata.create_all(bind=engine)
    print("数据库初始化完成")

def get_db():
    """
    获取数据库会话的生成器函数
    
    用法:
    with get_db() as db:
        # 使用db进行数据库操作
    
    确保在操作完成后自动关闭会话
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 