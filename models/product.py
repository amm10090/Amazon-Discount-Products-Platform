from typing import List, Optional
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
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ProductInfo(BaseModel):
    """商品信息模型"""
    asin: str
    title: str
    url: str
    brand: Optional[str] = None
    main_image: Optional[str] = None
    offers: List[ProductOffer] = []
    timestamp: datetime
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        
    def dict(self, *args, **kwargs):
        """重写dict方法以支持datetime序列化"""
        d = super().dict(*args, **kwargs)
        d['timestamp'] = self.timestamp.isoformat()
        return d 