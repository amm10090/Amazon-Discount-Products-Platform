from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, JSON, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

# 创建数据库引擎
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./amazon_products.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # 允许多线程访问
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
    
    # 其他信息
    deal_type = Column(String(50))
    features = Column(JSON)  # 存储商品特性列表
    
    # 时间信息
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    timestamp = Column(DateTime, default=datetime.utcnow)  # 数据采集时间
    
    # 元数据
    source = Column(String(50))  # 数据来源：'crawler' 或 'pa-api'
    raw_data = Column(JSON)  # 存储原始API响应

    # 关联优惠信息
    offers = relationship("Offer", back_populates="product", cascade="all, delete-orphan")

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
    
    # Prime信息
    is_prime = Column(Boolean, default=False)
    deal_type = Column(String(50))
    
    # 关联商品
    product = relationship("Product", back_populates="offers")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# 创建数据库表
def init_db():
    Base.metadata.create_all(bind=engine)

# 获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 