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
    availability: str
    merchant_name: str
    is_buybox_winner: bool = False
    deal_type: Optional[str] = None
    coupon_type: Optional[str] = None      # 优惠券类型（percentage/fixed）
    coupon_value: Optional[float] = None   # 优惠券值（百分比或固定金额）
    
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
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        
    def dict(self, *args, **kwargs):
        """重写dict方法以支持datetime序列化"""
        d = super().dict(*args, **kwargs)
        d['timestamp'] = self.timestamp.isoformat()
        return d 