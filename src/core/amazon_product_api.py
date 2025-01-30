from typing import List, Dict
import os
import asyncio
from datetime import datetime
import json
import aiohttp
import hmac
import hashlib
from datetime import datetime
import urllib.parse
from models.product import ProductInfo, ProductOffer
from models.cache_manager import CacheManager

class AmazonProductAPI:
    def __init__(self, access_key: str, secret_key: str, partner_tag: str, marketplace: str = "www.amazon.com", cache_dir: str = "cache"):
        """
        初始化Amazon Product API客户端
        
        Args:
            access_key: Amazon PA-API访问密钥
            secret_key: Amazon PA-API密钥
            partner_tag: Amazon Associates合作伙伴标签
            marketplace: 目标市场（默认为美国）
            cache_dir: 缓存目录路径
        """
        self.access_key = access_key
        self.secret_key = secret_key
        self.partner_tag = partner_tag
        self.marketplace = marketplace
        self.host = "webservices.amazon.com"
        self.region = "us-east-1"
        self.service = "ProductAdvertisingAPI"
        self.cache_manager = CacheManager(cache_dir)
        self._session = None
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self._session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self._session:
            await self._session.close()
            self._session = None
        
    def _sign(self, key: bytes, msg: str) -> bytes:
        """计算HMAC-SHA256签名"""
        return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()
    
    def _get_signature_key(self, date_stamp: str) -> bytes:
        """生成AWS签名密钥"""
        k_date = self._sign(f'AWS4{self.secret_key}'.encode('utf-8'), date_stamp)
        k_region = self._sign(k_date, self.region)
        k_service = self._sign(k_region, self.service)
        k_signing = self._sign(k_service, 'aws4_request')
        return k_signing
        
    def _get_authorization_header(self, amz_date: str, date_stamp: str, canonical_request: str) -> str:
        """生成Authorization头"""
        algorithm = 'AWS4-HMAC-SHA256'
        credential_scope = f'{date_stamp}/{self.region}/{self.service}/aws4_request'
        string_to_sign = f'{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()}'
        
        signing_key = self._get_signature_key(date_stamp)
        signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
        
        return (f'{algorithm} Credential={self.access_key}/{credential_scope}, '
                f'SignedHeaders=content-encoding;host;x-amz-date;x-amz-target, '
                f'Signature={signature}')

    def _extract_offer_from_item(self, item: Dict) -> List[ProductOffer]:
        """从商品数据中提取优惠信息"""
        offers = []
        
        if 'Offers' not in item or 'Listings' not in item['Offers']:
            return offers
            
        for listing in item['Offers']['Listings']:
            # 计算折扣信息
            savings_amount = None
            savings_percentage = None
            
            if 'Price' in listing:
                price_info = listing['Price']
                if 'SavingBasis' in listing:
                    saving_basis = listing['SavingBasis']
                    original_price = saving_basis.get('Amount', 0.0)
                    current_price = price_info.get('Amount', 0.0)
                    if original_price and current_price and original_price > current_price:
                        savings_amount = original_price - current_price
                        savings_percentage = int((savings_amount / original_price) * 100)
            
            # 获取Prime资格信息
            is_prime = False
            if 'ProgramEligibility' in listing:
                program = listing['ProgramEligibility']
                is_prime = program.get('IsPrimeEligible', False)
            
            # 创建优惠对象
            product_offer = ProductOffer(
                condition=listing.get('Condition', {}).get('Value', 'New'),
                price=listing.get('Price', {}).get('Amount', 0.0),
                currency=listing.get('Price', {}).get('Currency', 'USD'),
                savings=savings_amount,
                savings_percentage=savings_percentage,
                is_prime=is_prime,
                availability=listing.get('Availability', {}).get('Message', 'Unknown'),
                merchant_name=listing.get('MerchantInfo', {}).get('Name', 'Amazon'),
                is_buybox_winner=listing.get('IsBuyBoxWinner', False),
                deal_type=listing.get('Promotions', [{}])[0].get('Type') if listing.get('Promotions') else None
            )
            offers.append(product_offer)
            
        return offers

    async def get_products_by_asins(self, asins: List[str]) -> List[ProductInfo]:
        """
        通过ASIN列表异步获取商品信息，支持缓存
        
        Args:
            asins: ASIN列表（最多10个）
            
        Returns:
            List[ProductInfo]: 商品信息列表
        """
        if not asins:
            return []
            
        # 确保ASIN数量不超过10个
        if len(asins) > 10:
            raise ValueError("一次最多只能查询10个ASIN")
        
        products = []
        uncached_asins = []
        
        # 首先检查缓存
        for asin in asins:
            cached_data = self.cache_manager.get(asin)
            if cached_data:
                # 从缓存创建ProductInfo对象
                product = ProductInfo(**cached_data)
                products.append(product)
            else:
                uncached_asins.append(asin)
                
        # 如果所有商品都在缓存中，直接返回
        if not uncached_asins:
            return products
            
        try:
            # 准备请求数据
            payload = {
                "ItemIds": uncached_asins,
                "Resources": [
                    # Offers资源
                    "Offers.Listings.Availability.MaxOrderQuantity",
                    "Offers.Listings.Availability.Message",
                    "Offers.Listings.Availability.MinOrderQuantity",
                    "Offers.Listings.Availability.Type",
                    "Offers.Listings.Condition",
                    "Offers.Listings.Condition.ConditionNote",
                    "Offers.Listings.Condition.SubCondition",
                    "Offers.Listings.DeliveryInfo.IsAmazonFulfilled",
                    "Offers.Listings.DeliveryInfo.IsFreeShippingEligible",
                    "Offers.Listings.DeliveryInfo.IsPrimeEligible",
                    "Offers.Listings.DeliveryInfo.ShippingCharges",
                    "Offers.Listings.IsBuyBoxWinner",
                    "Offers.Listings.LoyaltyPoints.Points",
                    "Offers.Listings.MerchantInfo",
                    "Offers.Listings.Price",
                    "Offers.Listings.ProgramEligibility.IsPrimeExclusive",
                    "Offers.Listings.ProgramEligibility.IsPrimePantry",
                    "Offers.Listings.Promotions",
                    "Offers.Listings.SavingBasis",
                    "Offers.Summaries.HighestPrice",
                    "Offers.Summaries.LowestPrice",
                    "Offers.Summaries.OfferCount",
                    # 商品基本信息
                    "ItemInfo.Title",
                    "ItemInfo.ByLineInfo",
                    "ItemInfo.Features",
                    # 图片信息
                    "Images.Primary.Small",
                    "Images.Primary.Medium",
                    "Images.Primary.Large"
                ],
                "PartnerTag": self.partner_tag,
                "PartnerType": "Associates",
                "Marketplace": self.marketplace
            }
            
            # 准备请求头
            amz_date = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
            date_stamp = datetime.utcnow().strftime('%Y%m%d')
            
            headers = {
                'Host': self.host,
                'Content-Type': 'application/json; charset=UTF-8',
                'X-Amz-Date': amz_date,
                'X-Amz-Target': 'com.amazon.paapi5.v1.ProductAdvertisingAPIv1.GetItems',
                'Content-Encoding': 'amz-1.0'
            }
            
            # 构建规范请求
            canonical_uri = '/paapi5/getitems'
            canonical_querystring = ''
            payload_json = json.dumps(payload)
            
            canonical_headers = (f'content-encoding:amz-1.0\n'
                               f'host:{self.host}\n'
                               f'x-amz-date:{amz_date}\n'
                               f'x-amz-target:com.amazon.paapi5.v1.ProductAdvertisingAPIv1.GetItems\n')
            
            canonical_request = (f'POST\n{canonical_uri}\n{canonical_querystring}\n'
                               f'{canonical_headers}\ncontent-encoding;host;x-amz-date;x-amz-target\n'
                               f'{hashlib.sha256(payload_json.encode("utf-8")).hexdigest()}')
            
            # 生成授权头
            headers['Authorization'] = self._get_authorization_header(amz_date, date_stamp, canonical_request)
            
            # 发送异步请求
            url = f'https://{self.host}{canonical_uri}'
            
            if not self._session:
                self._session = aiohttp.ClientSession()
                
            async with self._session.post(url, headers=headers, data=payload_json) as response:
                response.raise_for_status()
                response_data = await response.json()
            
            if 'ItemsResult' in response_data and 'Items' in response_data['ItemsResult']:
                for item in response_data['ItemsResult']['Items']:
                    # 提取商品信息
                    offers = self._extract_offer_from_item(item)
                    main_image = None
                    if 'Images' in item and 'Primary' in item['Images']:
                        main_image = item['Images']['Primary'].get('Large', {}).get('URL')
                    
                    brand = None
                    if ('ItemInfo' in item and 'ByLineInfo' in item['ItemInfo'] and 
                        'Brand' in item['ItemInfo']['ByLineInfo']):
                        brand = item['ItemInfo']['ByLineInfo']['Brand'].get('DisplayValue')
                    
                    # 创建商品信息对象
                    product = ProductInfo(
                        asin=item['ASIN'],
                        title=item.get('ItemInfo', {}).get('Title', {}).get('DisplayValue', ''),
                        url=item.get('DetailPageURL', ''),
                        brand=brand,
                        main_image=main_image,
                        offers=offers,
                        timestamp=datetime.utcnow()
                    )
                    
                    # 缓存商品信息
                    self.cache_manager.set(item['ASIN'], product.dict())
                    products.append(product)
                    
        except Exception as e:
            print(f"获取商品信息时出错: {str(e)}")
            raise
            
        return products

    async def save_products_info(self, products: List[ProductInfo], output_file: str):
        """异步保存商品信息到文件"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump([p.dict() for p in products], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存商品信息时出错: {str(e)}")
            raise

    def clear_expired_cache(self):
        """清理过期缓存"""
        self.cache_manager.clear_expired()

async def main():
    """异步主函数示例"""
    # 从环境变量获取凭证
    access_key = os.getenv("AMAZON_ACCESS_KEY")
    secret_key = os.getenv("AMAZON_SECRET_KEY")
    partner_tag = os.getenv("AMAZON_PARTNER_TAG")
    
    if not all([access_key, secret_key, partner_tag]):
        print("请设置必要的环境变量")
        return
        
    # 测试ASIN列表
    test_asins = ["B01NBKTPTS", "B00X4WHP5E", "B00FLYWNYQ"]
    
    async with AmazonProductAPI(access_key, secret_key, partner_tag) as api:
        products = await api.get_products_by_asins(test_asins)
        await api.save_products_info(products, "test_products.json")
        print(f"成功获取并保存了 {len(products)} 个商品信息")

if __name__ == "__main__":
    asyncio.run(main()) 