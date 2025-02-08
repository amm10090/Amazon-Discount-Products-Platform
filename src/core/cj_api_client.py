import os
import aiohttp
import json
from typing import List, Dict, Optional, Any
from datetime import datetime
from dotenv import load_dotenv
import sys
from pathlib import Path
import asyncio

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from models.database import Product

# 加载环境变量
load_dotenv()

class CJAPIClient:
    """CJ API客户端类"""
    
    def __init__(self):
        """初始化CJ API客户端"""
        self.base_url = os.getenv("CJ_API_BASE_URL", "https://cj.partnerboost.com/api")
        self.pid = os.getenv("CJ_PID")
        self.cid = os.getenv("CJ_CID")
        
        if not all([self.pid, self.cid]):
            raise ValueError("缺少必要的CJ API凭证配置")
            
        self.headers = {
            "Request-Source": "cj",
            "Content-Type": "application/json"
        }
        
    async def _make_request(
        self, 
        endpoint: str, 
        method: str = "POST", 
        data: Optional[Dict] = None,
        max_retries: int = 3,
        timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=30)
    ) -> Dict:
        """发送API请求
        
        Args:
            endpoint: API端点
            method: 请求方法
            data: 请求数据
            max_retries: 最大重试次数
            timeout: 请求超时设置
            
        Returns:
            Dict: API响应数据
        """
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.request(
                        method=method,
                        url=url,
                        headers=self.headers,
                        json=data
                    ) as response:
                        response_data = await response.json()
                        
                        if response.status != 200:
                            raise Exception(f"API请求失败: {response_data.get('message', '未知错误')}")
                            
                        return response_data
                            
            except aiohttp.ClientError as e:
                if attempt == max_retries - 1:  # 最后一次重试
                    raise Exception(f"请求发送失败: {str(e)}")
                else:
                    # 等待一段时间后重试
                    await asyncio.sleep(1 * (attempt + 1))  # 递增等待时间
                    continue
                
    async def get_products(
        self,
        asins: Optional[List[str]] = None,
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        cursor: str = "",
        limit: int = 50,
        country_code: str = "US",
        brand_id: int = 0,
        is_featured_product: int = 2,
        is_amazon_choice: int = 2,
        have_coupon: int = 2,
        discount_min: int = 0
    ) -> Dict[str, Any]:
        """获取产品信息
        
        Args:
            asins: ASIN列表
            category: 商品类别
            subcategory: 商品子类别
            cursor: 分页游标
            limit: 每页数量，最大50
            country_code: 国家代码
            brand_id: 品牌ID
            is_featured_product: 是否精选商品(0:否, 1:是, 2:全部)
            is_amazon_choice: 是否亚马逊之选(0:否, 1:是, 2:全部)
            have_coupon: 是否有优惠券(0:否, 1:是, 2:全部)
            discount_min: 最低折扣率
            
        Returns:
            Dict[str, Any]: 产品信息
        """
        data = {
            "pid": self.pid,
            "cid": self.cid,
            "cursor": cursor,
            "limit": min(limit, 50),  # 确保不超过50
            "country_code": country_code,
            "brand_id": brand_id,
            "asins": ",".join(asins) if asins else "",
            "category": category or "",
            "subcategory": subcategory or "",
            "is_featured_product": is_featured_product,
            "is_amazon_choice": is_amazon_choice,
            "have_coupon": have_coupon,
            "discount_min": discount_min
        }
        
        return await self._make_request("/get_products", "POST", data)
        
    async def generate_product_link(
        self, 
        asin: str,
        max_retries: int = 3,
        timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=30)
    ) -> str:
        """生成商品推广链接
        
        Args:
            asin: 商品ASIN
            max_retries: 最大重试次数
            timeout: 请求超时设置
            
        Returns:
            str: 推广链接
            
        Raises:
            Exception: 当API请求失败或响应格式不正确时抛出
        """
        data = {
            "pid": self.pid,
            "cid": self.cid,
            "asins": asin,  # 直接使用asin字符串，而不是列表
            "country_code": "US"  # 默认使用美国站
        }
        
        response = await self._make_request(
            "/generate_product_link", 
            "POST", 
            data,
            max_retries=max_retries,
            timeout=timeout
        )
        
        if not response:
            raise Exception("API返回空响应")
            
        if response.get("code") != 0:
            raise Exception(f"生成链接失败: {response.get('message', '未知错误')}")
            
        # 获取第一个商品的链接
        if not response.get("data") or not response["data"]:
            raise Exception(f"响应中缺少数据: {response}")
            
        if not isinstance(response["data"], list) or not response["data"]:
            raise Exception(f"响应数据格式错误: {response}")
            
        product_data = response["data"][0]
        if not product_data.get("link"):
            raise Exception(f"响应中缺少链接: {response}")
            
        return product_data["link"]
        
    async def check_products_availability(self, asins: List[str]) -> Dict[str, bool]:
        """检查多个商品在CJ平台的可用性
        
        Args:
            asins: ASIN列表
            
        Returns:
            Dict[str, bool]: 商品可用性字典，key为ASIN，value为是否可用
        """
        # 由于API限制每次最多查询50个ASIN，需要分批处理
        result = {}
        
        for i in range(0, len(asins), 50):
            batch_asins = asins[i:i+50]
            response = await self.get_products(asins=batch_asins)
            
            # 解析响应数据
            available_asins = {
                item["asin"]: True 
                for item in response.get("data", {}).get("list", [])
            }
            
            # 更新结果字典
            for asin in batch_asins:
                result[asin] = available_asins.get(asin, False)
                
        return result
        
    async def get_product_details(self, asin: str) -> Optional[Dict]:
        """获取单个商品的详细信息
        
        Args:
            asin: 商品ASIN
            
        Returns:
            Optional[Dict]: 商品详细信息，如果不存在则返回None
        """
        response = await self.get_products(asins=[asin])
        products = response.get("data", {}).get("list", [])
        
        return products[0] if products else None 