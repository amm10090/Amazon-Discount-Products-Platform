from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

class ProductOffer(BaseModel):
    """商品优惠信息模型"""
    condition: str
    price: float
    currency: str
    savings: Optional[float] = None
    savings_percentage: Optional[float] = None
    is_prime: bool = False
    availability: str
    merchant_name: str
    is_buybox_winner: bool = False
    deal_type: Optional[str] = None

class ProductInfo(BaseModel):
    """商品信息模型"""
    asin: str
    title: str
    url: str
    brand: Optional[str] = None
    main_image: Optional[str] = None
    offers: List[ProductOffer]
    timestamp: datetime = datetime.now() 