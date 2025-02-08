"""
Amazon产品广告API客户端模块

该模块提供了与Amazon Product Advertising API (PA-API) 5.0版本交互的异步客户端实现。
主要功能：
1. 异步获取Amazon商品信息
2. 支持商品信息的本地缓存
3. 实现AWS签名V4认证
4. 提供重试机制
5. 支持批量商品查询

技术特点：
- 使用aiohttp进行异步HTTP请求
- 实现异步上下文管理器
- 使用HMAC-SHA256进行AWS认证签名
- 支持商品信息的JSON格式化存储
"""

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
from src.utils.cache_manager import CacheManager, cache_decorator
from src.utils.api_retry import with_retry
import logging

logger = logging.getLogger(__name__)

class AmazonProductAPI:
    """
    Amazon Product Advertising API客户端类
    
    该类提供了与Amazon PA-API交互的主要功能，包括：
    - 异步获取商品信息
    - 本地缓存管理
    - AWS签名认证
    - 会话管理
    
    属性:
        access_key: Amazon PA-API访问密钥
        secret_key: Amazon PA-API密钥
        partner_tag: Amazon Associates合作伙伴标签
        marketplace: 目标市场域名
        host: API主机地址
        region: AWS区域
        service: 服务名称
        cache_manager: 缓存管理器实例
    """
    
    def __init__(self, access_key: str, secret_key: str, partner_tag: str, marketplace: str = "www.amazon.com", config_path: str = "config/cache_config.yaml"):
        """
        初始化Amazon Product API客户端
        
        Args:
            access_key: Amazon PA-API访问密钥
            secret_key: Amazon PA-API密钥
            partner_tag: Amazon Associates合作伙伴标签
            marketplace: 目标市场（默认为美国）
            config_path: 缓存配置文件路径
        """
        self.access_key = access_key
        self.secret_key = secret_key
        self.partner_tag = partner_tag
        self.marketplace = marketplace
        self.host = "webservices.amazon.com"
        self.region = "us-east-1"
        self.service = "ProductAdvertisingAPI"
        self.cache_manager = CacheManager(config_path)
        
    async def __aenter__(self):
        """
        异步上下文管理器入口
        
        Returns:
            self: 当前实例
        """
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        异步上下文管理器退出
        
        Args:
            exc_type: 异常类型
            exc_val: 异常值
            exc_tb: 异常回溯
        """
        pass  # 不再需要关闭session，因为每个请求都会创建和关闭自己的session

    def _sign(self, key: bytes, msg: str) -> bytes:
        """
        计算HMAC-SHA256签名
        
        Args:
            key: 密钥字节串
            msg: 待签名消息
            
        Returns:
            bytes: HMAC-SHA256签名结果
        """
        return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()
    
    def _get_signature_key(self, date_stamp: str) -> bytes:
        """
        生成AWS签名密钥
        
        使用AWS签名版本4算法生成签名密钥
        
        Args:
            date_stamp: 日期字符串（YYYYMMDD格式）
            
        Returns:
            bytes: 签名密钥
        """
        k_date = self._sign(f'AWS4{self.secret_key}'.encode('utf-8'), date_stamp)
        k_region = self._sign(k_date, self.region)
        k_service = self._sign(k_region, self.service)
        k_signing = self._sign(k_service, 'aws4_request')
        return k_signing
        
    def _get_authorization_header(self, amz_date: str, date_stamp: str, canonical_request: str) -> str:
        """
        生成Authorization头
        
        根据AWS签名版本4规范生成授权头
        
        Args:
            amz_date: AWS格式的日期时间
            date_stamp: 日期字符串
            canonical_request: 规范化请求字符串
            
        Returns:
            str: 授权头字符串
        """
        algorithm = 'AWS4-HMAC-SHA256'
        credential_scope = f'{date_stamp}/{self.region}/{self.service}/aws4_request'
        string_to_sign = f'{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()}'
        
        signing_key = self._get_signature_key(date_stamp)
        signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
        
        return (f'{algorithm} Credential={self.access_key}/{credential_scope}, '
                f'SignedHeaders=content-encoding;host;x-amz-date;x-amz-target, '
                f'Signature={signature}')

    def _extract_offer_from_item(self, item: Dict) -> List[ProductOffer]:
        """
        从商品数据中提取优惠信息
        
        解析API返回的商品数据，提取价格、折扣、Prime资格等信息
        
        Args:
            item: 商品数据字典
            
        Returns:
            List[ProductOffer]: 商品优惠信息列表
        """
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
            is_amazon_fulfilled = False
            is_free_shipping_eligible = False
            if 'DeliveryInfo' in listing:
                delivery_info = listing['DeliveryInfo']
                is_prime = delivery_info.get('IsPrimeEligible', False)
                is_amazon_fulfilled = delivery_info.get('IsAmazonFulfilled', False)
                is_free_shipping_eligible = delivery_info.get('IsFreeShippingEligible', False)
            
            # 创建优惠对象
            product_offer = ProductOffer(
                condition=listing.get('Condition', {}).get('Value', 'New'),
                price=listing.get('Price', {}).get('Amount', 0.0),
                currency=listing.get('Price', {}).get('Currency', 'USD'),
                savings=savings_amount,
                savings_percentage=savings_percentage,
                is_prime=is_prime,
                is_amazon_fulfilled=is_amazon_fulfilled,
                is_free_shipping_eligible=is_free_shipping_eligible,
                availability=listing.get('Availability', {}).get('Message', 'Unknown'),
                merchant_name=listing.get('MerchantInfo', {}).get('Name', 'Amazon'),
                is_buybox_winner=listing.get('IsBuyBoxWinner', False),
                deal_type=listing.get('Promotions', [{}])[0].get('Type') if listing.get('Promotions') else None
            )
            offers.append(product_offer)
            
        return offers

    @cache_decorator(cache_type="products")
    async def get_products_by_asins(self, asins: List[str]) -> List[ProductInfo]:
        """
        通过ASIN列表异步获取商品信息，支持缓存和重试机制
        
        该方法会首先检查本地缓存，对于未缓存的商品才会请求API
        
        Args:
            asins: ASIN列表（最多10个）
            
        Returns:
            List[ProductInfo]: 商品信息列表
            
        Raises:
            ValueError: 当ASIN数量超过10个时
            Exception: API请求失败时
        """
        if not asins:
            return []
            
        # 确保ASIN数量不超过10个
        if len(asins) > 10:
            raise ValueError("一次最多只能查询10个ASIN")
        
        products = []
        uncached_asins = []
        
        # 首先检查缓存
        logger.info(f"开始检查商品缓存: ASINs={asins}")
        for asin in asins:
            cached_data = self.cache_manager.get(asin, "products")
            if cached_data:
                try:
                    # 从缓存创建ProductInfo对象
                    product = ProductInfo(**cached_data)
                    products.append(product)
                    logger.debug(f"成功从缓存加载商品: ASIN={asin}")
                except Exception as e:
                    logger.error(f"从缓存创建ProductInfo对象失败: {str(e)}, ASIN={asin}")
                    uncached_asins.append(asin)
            else:
                logger.debug(f"商品未缓存: ASIN={asin}")
                uncached_asins.append(asin)
                
        # 如果所有商品都在缓存中，直接返回
        if not uncached_asins:
            logger.info(f"所有商品均命中缓存: ASINs={asins}")
            return products
            
        logger.info(f"开始从API获取未缓存商品: ASINs={uncached_asins}")
        session = None
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
                    # 分类信息
                    "ItemInfo.Classifications",
                    "ItemInfo.ProductInfo",
                    "BrowseNodeInfo.BrowseNodes",
                    "BrowseNodeInfo.WebsiteSalesRank",
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
            
            session = aiohttp.ClientSession()
            async with session.post(url, headers=headers, data=payload_json) as response:
                response.raise_for_status()
                response_data = await response.json()
            
            if 'ItemsResult' in response_data and 'Items' in response_data['ItemsResult']:
                for item in response_data['ItemsResult']['Items']:
                    try:
                        # 提取商品信息
                        offers = self._extract_offer_from_item(item)
                        main_image = None
                        if 'Images' in item and 'Primary' in item['Images']:
                            main_image = item['Images']['Primary'].get('Large', {}).get('URL')
                        
                        brand = None
                        if ('ItemInfo' in item and 'ByLineInfo' in item['ItemInfo'] and 
                            'Brand' in item['ItemInfo']['ByLineInfo']):
                            brand = item['ItemInfo']['ByLineInfo']['Brand'].get('DisplayValue')
                        
                        # 提取分类信息
                        binding = None
                        product_group = None
                        categories = []
                        browse_nodes = []
                        
                        if 'ItemInfo' in item:
                            # 获取绑定类型
                            if 'Classifications' in item['ItemInfo']:
                                binding = item['ItemInfo']['Classifications'].get('Binding', {}).get('DisplayValue')
                                product_group = item['ItemInfo']['Classifications'].get('ProductGroup', {}).get('DisplayValue')
                        
                        # 获取浏览节点信息
                        if 'BrowseNodeInfo' in item and 'BrowseNodes' in item['BrowseNodeInfo']:
                            for node in item['BrowseNodeInfo']['BrowseNodes']:
                                # 添加类别路径
                                if 'Ancestor' in node:
                                    category_path = []
                                    for ancestor in node['Ancestor']:
                                        if 'ContextFreeName' in ancestor:
                                            category_path.append(ancestor['ContextFreeName'])
                                    if category_path:
                                        categories.append(' > '.join(category_path))
                                
                                # 添加浏览节点信息
                                browse_nodes.append({
                                    'id': node.get('Id'),
                                    'name': node.get('ContextFreeName'),
                                    'is_root': node.get('IsRoot', False)
                                })
                        
                        # 创建商品信息对象
                        product = ProductInfo(
                            asin=item['ASIN'],
                            title=item.get('ItemInfo', {}).get('Title', {}).get('DisplayValue', ''),
                            url=item.get('DetailPageURL', ''),
                            brand=brand,
                            main_image=main_image,
                            offers=offers,
                            timestamp=datetime.utcnow(),
                            binding=binding,
                            product_group=product_group,
                            categories=categories,
                            browse_nodes=browse_nodes
                        )
                        
                        # 缓存商品信息
                        try:
                            self.cache_manager.set(item['ASIN'], product.dict(), "products")
                            logger.debug(f"成功缓存商品信息: ASIN={item['ASIN']}")
                        except Exception as e:
                            logger.error(f"缓存商品信息失败: {str(e)}, ASIN={item['ASIN']}")
                            
                        products.append(product)
                    except Exception as e:
                        logger.error(f"处理商品信息失败: {str(e)}, ASIN={item.get('ASIN', 'unknown')}")
                        continue
                    
            logger.info(f"成功获取并处理商品信息: 总数={len(products)}")
                    
        except Exception as e:
            logger.error(f"获取商品信息时出错: {str(e)}")
            raise
        finally:
            # 确保session被关闭
            if session:
                await session.close()
            
        return products

    async def save_products_info(self, products: List[ProductInfo], output_file: str):
        """
        异步保存商品信息到文件
        
        Args:
            products: 商品信息列表
            output_file: 输出文件路径
            
        Raises:
            Exception: 文件操作失败时
        """
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump([p.dict() for p in products], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存商品信息时出错: {str(e)}")
            raise

    def clear_expired_cache(self):
        """
        清理过期缓存
        
        调用缓存管理器清理过期的缓存数据
        """
        self.cache_manager.clear_expired()
        
    def clear_all_cache(self):
        """
        清理所有缓存
        
        调用缓存管理器清理所有缓存数据
        """
        self.cache_manager.clear_all()

async def main():
    """
    异步主函数示例
    
    展示如何使用AmazonProductAPI类的基本用法：
    1. 从环境变量获取API凭证
    2. 创建API客户端实例
    3. 获取测试商品信息
    4. 保存结果到文件
    """
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