from typing import List, Optional, Dict
from datetime import datetime
from pydantic import BaseModel

class ProductOffer(BaseModel):
    """商品优惠信息模型"""
    condition: str
    price: float
    currency: str
    savings: Optional[float] = None
    savings_percentage: Optional[int] = None
    is_prime: bool = False
    is_amazon_fulfilled: bool = False  # 是否由亚马逊配送
    is_free_shipping_eligible: bool = False  # 是否符合免运费资格
    availability: str
    merchant_name: str
    is_buybox_winner: bool = False
    deal_type: Optional[str] = None
    coupon_type: Optional[str] = None      # 优惠券类型（percentage/fixed）
    coupon_value: Optional[float] = None   # 优惠券值（百分比或固定金额）
    coupon_history: Optional[List[Dict]] = None  # 优惠券历史记录
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        
    def dict(self, *args, **kwargs):
        """重写dict方法以支持datetime序列化"""
        d = super().dict(*args, **kwargs)
        if 'coupon_type' in d and d['coupon_type'] is None:
            del d['coupon_type']
        if 'coupon_value' in d and d['coupon_value'] is None:
            del d['coupon_value']
        return d

class ProductInfo(BaseModel):
    """商品信息模型"""
    asin: str
    title: str
    url: str
    brand: Optional[str] = None
    main_image: Optional[str] = None
    offers: List[ProductOffer] = []
    timestamp: datetime
    coupon_info: Optional[Dict] = None
    binding: Optional[str] = None  # 商品绑定类型
    product_group: Optional[str] = None  # 商品分组
    categories: Optional[List[str]] = []  # 商品类别列表
    browse_nodes: Optional[List[Dict]] = []  # 商品浏览节点信息
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        
    def dict(self, *args, **kwargs):
        """重写dict方法以支持datetime序列化"""
        d = super().dict(*args, **kwargs)
        d['timestamp'] = self.timestamp.isoformat()
        return d

    def to_cache_dict(self) -> dict:
        """
        转换为可缓存的字典格式
        
        Returns:
            dict: 可序列化的字典
        """
        return {
            "asin": self.asin,
            "title": self.title,
            "url": self.url,
            "brand": self.brand,
            "main_image": self.main_image,
            "offers": [offer.dict() for offer in self.offers],
            "timestamp": self.timestamp.isoformat()
        } 