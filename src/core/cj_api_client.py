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
from src.utils.log_config import get_logger, log_function_call

# 加载环境变量
load_dotenv()

class CJAPIClient:
    """CJ API客户端类"""
    
    def __init__(self):
        """初始化CJ API客户端"""
        self.base_url = os.getenv("CJ_API_BASE_URL", "https://cj.partnerboost.com/api")
        self.pid = os.getenv("CJ_PID")
        self.cid = os.getenv("CJ_CID")
        self.logger = get_logger("CJAPIClient")
        
        if not all([self.pid, self.cid]):
            self.logger.error("缺少必要的CJ API凭证配置")
            raise ValueError("缺少必要的CJ API凭证配置")
            
        self.headers = {
            "Request-Source": "cj",
            "Content-Type": "application/json"
        }
        
        self.logger.debug(f"CJ API客户端初始化完成，基础URL: {self.base_url}")
        
    @log_function_call
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
                self.logger.debug(f"发送 {method} 请求到 {endpoint}，尝试 {attempt+1}/{max_retries}")
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.request(
                        method=method,
                        url=url,
                        headers=self.headers,
                        json=data
                    ) as response:
                        response_data = await response.json()
                        
                        if response.status != 200:
                            error_msg = f"API请求失败: {response_data.get('message', '未知错误')}"
                            self.logger.error(f"{error_msg}，状态码: {response.status}")
                            raise Exception(error_msg)
                            
                        self.logger.debug(f"请求成功: {endpoint}")
                        return response_data
                            
            except aiohttp.ClientError as e:
                if attempt == max_retries - 1:  # 最后一次重试
                    self.logger.error(f"请求发送失败: {str(e)}，已达最大重试次数")
                    raise Exception(f"请求发送失败: {str(e)}")
                else:
                    wait_time = 1 * (attempt + 1)
                    self.logger.warning(f"请求失败: {str(e)}，{wait_time}秒后重试...")
                    # 等待一段时间后重试
                    await asyncio.sleep(wait_time)  # 递增等待时间
                    continue
                
    @log_function_call
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
        
        self.logger.info(f"获取商品信息，类别: {category or '全部'}，优惠券筛选: {have_coupon}，总数: {limit}")
        # 记录完整的游标信息用于调试
        self.logger.debug(f"请求使用的游标参数: [{cursor[:50]}{'...' if len(cursor) > 50 else ''}]")
        return await self._make_request("/get_products", "POST", data)
        
    @log_function_call
    async def generate_product_link(
        self, 
        asin: str,
        max_retries: int = 5,
        timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=45)
    ) -> str:
        """生成商品推广链接
        
        Args:
            asin: 商品ASIN
            max_retries: 最大重试次数
            timeout: 请求超时设置
            
        Returns:
            str: 推广链接，如果失败则返回基于ASIN构建的默认链接
        """
        data = {
            "pid": self.pid,
            "cid": self.cid,
            "asins": asin,
            "country_code": "US"  # 默认使用美国站
        }
        
        self.logger.info(f"为商品 {asin} 生成推广链接")
        
        # 默认推广链接，如果API调用失败将返回此链接
        default_link = f"https://www.amazon.com/dp/{asin}?tag=default"
        
        # 创建重试计数器
        retries = 0
        last_error = None
        
        while retries < max_retries:
            try:
                response = await self._make_request(
                    "/generate_product_link", 
                    "POST", 
                    data,
                    max_retries=1,  # 这里使用1是因为我们自己实现了重试
                    timeout=timeout
                )
                
                if not response:
                    self.logger.error(f"第{retries+1}次尝试: API返回空响应")
                    retries += 1
                    await asyncio.sleep(1 * (retries + 1))  # 指数退避
                    continue
                    
                if response.get("code") != 0:
                    error_msg = f"第{retries+1}次尝试: 生成链接失败: {response.get('message', '未知错误')}"
                    self.logger.error(f"{error_msg}，ASIN: {asin}")
                    last_error = Exception(error_msg)
                    retries += 1
                    await asyncio.sleep(1 * (retries + 1))
                    continue
                    
                # 获取第一个商品的链接
                if not response.get("data") or not response["data"]:
                    error_msg = f"第{retries+1}次尝试: 响应中缺少数据"
                    self.logger.error(f"{error_msg}，ASIN: {asin}")
                    last_error = Exception(error_msg)
                    retries += 1
                    await asyncio.sleep(1 * (retries + 1))
                    continue
                    
                if not isinstance(response["data"], list) or not response["data"]:
                    error_msg = f"第{retries+1}次尝试: 响应数据格式错误"
                    self.logger.error(f"{error_msg}，ASIN: {asin}")
                    last_error = Exception(error_msg)
                    retries += 1
                    await asyncio.sleep(1 * (retries + 1))
                    continue
                    
                product_data = response["data"][0]
                if not product_data.get("link"):
                    error_msg = f"第{retries+1}次尝试: 响应中缺少链接"
                    self.logger.error(f"{error_msg}，ASIN: {asin}")
                    last_error = Exception(error_msg)
                    retries += 1
                    await asyncio.sleep(1 * (retries + 1))
                    continue
                    
                link = product_data["link"]
                self.logger.info(f"成功生成推广链接，ASIN: {asin}, 链接: {link[:30]}...")
                return link
                
            except Exception as e:
                retries += 1
                last_error = e
                await_time = 1 * (retries + 1)
                self.logger.error(f"第{retries}次尝试失败: {str(e)}，{await_time}秒后重试...")
                await asyncio.sleep(await_time)
        
        # 如果所有重试都失败了
        error_msg = f"生成推广链接失败，已重试{max_retries}次: {str(last_error)}"
        self.logger.error(f"{error_msg}，ASIN: {asin}，返回默认链接")
        return default_link
        
    @log_function_call
    async def batch_generate_product_links(
        self, 
        asins: List[str],
        max_retries: int = 5,  # 增加默认重试次数
        timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=45)  # 增加超时时间
    ) -> Dict[str, str]:
        """批量生成商品推广链接
        
        Args:
            asins: 商品ASIN列表，最多10个
            max_retries: 最大重试次数
            timeout: 请求超时设置
            
        Returns:
            Dict[str, str]: 推广链接字典，key为ASIN，value为推广链接
            
        Raises:
            ValueError: 当ASIN列表为空或超过10个时抛出
            Exception: 当API请求失败或响应格式不正确时抛出
        """
        if not asins:
            raise ValueError("ASIN列表不能为空")
        
        if len(asins) > 10:
            raise ValueError("一次最多只能生成10个推广链接")
        
        data = {
            "pid": self.pid,
            "cid": self.cid,
            "asins": ",".join(asins),
            "country_code": "US"  # 默认使用美国站
        }
        
        self.logger.info(f"批量生成推广链接，ASIN数量: {len(asins)}, ASINs: {asins}")
        
        # 创建重试计数器
        retries = 0
        last_error = None
        
        while retries < max_retries:
            try:
                response = await self._make_request(
                    "/generate_product_link", 
                    "POST", 
                    data,
                    max_retries=1,  # 这里使用1是因为我们自己已经实现了重试逻辑
                    timeout=timeout
                )
                
                if not response:
                    self.logger.error(f"第{retries+1}次尝试: API返回空响应")
                    retries += 1
                    await asyncio.sleep(1 * (retries + 1))  # 指数退避
                    continue
                    
                if response.get("code") != 0:
                    error_msg = f"第{retries+1}次尝试: 生成链接失败: {response.get('message', '未知错误')}"
                    self.logger.error(error_msg)
                    last_error = Exception(error_msg)
                    retries += 1
                    await asyncio.sleep(1 * (retries + 1))
                    continue
                
                # 获取所有商品的链接并映射到ASIN
                if not response.get("data") or not isinstance(response["data"], list):
                    error_msg = f"第{retries+1}次尝试: 响应数据格式错误: {response}"
                    self.logger.error(error_msg)
                    last_error = Exception(error_msg)
                    retries += 1
                    await asyncio.sleep(1 * (retries + 1))
                    continue
                
                result = {}
                for product_data in response["data"]:
                    if not product_data.get("asin") or not product_data.get("link"):
                        self.logger.warning(f"响应中缺少ASIN或链接: {product_data}")
                        continue
                    
                    asin = product_data["asin"]
                    link = product_data["link"]
                    result[asin] = link
                
                # 检查是否所有ASIN都有返回结果
                missing_asins = [asin for asin in asins if asin not in result]
                if missing_asins:
                    self.logger.warning(f"以下ASIN未能获取到推广链接: {missing_asins}")
                    
                    # 如果一个结果都没有获取到，可能是有问题，尝试重试
                    if not result and retries < max_retries - 1:
                        self.logger.warning(f"第{retries+1}次尝试没有获取到任何推广链接，将重试")
                        retries += 1
                        await asyncio.sleep(1 * (retries + 1))
                        continue
                
                self.logger.info(f"成功生成 {len(result)}/{len(asins)} 个推广链接")
                return result
                
            except Exception as e:
                retries += 1
                last_error = e
                await_time = 1 * (retries + 1)
                self.logger.error(f"第{retries}次尝试失败: {str(e)}，{await_time}秒后重试...")
                await asyncio.sleep(await_time)
        
        # 如果所有重试都失败了
        error_msg = f"批量生成推广链接失败，已重试{max_retries}次: {str(last_error)}"
        self.logger.error(error_msg)
        return {}
        
    @log_function_call
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
            self.logger.debug(f"批量检查商品可用性，批次: {i//50+1}，商品数: {len(batch_asins)}")
            
            response = await self.get_products(asins=batch_asins)
            
            if response.get("code") != 0:
                self.logger.error(f"检查商品可用性失败: {response.get('message', '未知错误')}")
                raise Exception(f"检查商品可用性失败: {response.get('message', '未知错误')}")
                
            # 初始化所有ASIN为不可用
            for asin in batch_asins:
                result[asin] = False
                
            # 设置API返回的ASIN为可用
            if response.get("data") and response["data"].get("list"):
                for product in response["data"]["list"]:
                    if product.get("asin"):
                        result[product["asin"]] = True
                        
            await asyncio.sleep(0.5)  # 避免API限流
        
        available_count = sum(1 for available in result.values() if available)
        self.logger.info(f"商品可用性检查完成，总数: {len(asins)}，可用: {available_count}，不可用: {len(asins) - available_count}")
        return result
        
    @log_function_call
    async def get_product_details(self, asin: str) -> Optional[Dict]:
        """获取单个商品的详细信息
        
        Args:
            asin: 商品ASIN
            
        Returns:
            Optional[Dict]: 商品详细信息，如果商品不存在则返回None
        """
        self.logger.debug(f"获取商品详情，ASIN: {asin}")
        response = await self.get_products(asins=[asin])
        
        if response.get("code") != 0:
            self.logger.error(f"获取商品详情失败: {response.get('message', '未知错误')}")
            return None
            
        if not response.get("data") or not response["data"].get("list"):
            self.logger.warning(f"商品不存在或不可用，ASIN: {asin}")
            return None
            
        products = response["data"]["list"]
        if not products:
            self.logger.warning(f"商品不存在，ASIN: {asin}")
            return None
            
        return products[0] 