"""
产品服务模块，处理与API的交互
"""

import requests
from typing import Dict, List, Optional
import streamlit as st
from ..utils.cache_manager import cache_manager

class ProductService:
    def __init__(self, api_base_url: str):
        self.api_base_url = api_base_url

    def load_products(
        self,
        product_type: str = "all",
        page: int = 1,
        page_size: int = 20,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_discount: Optional[int] = None,
        prime_only: bool = False,
        sort_by: Optional[str] = None,
        sort_order: str = "desc",
        selected_categories: Optional[Dict[str, List[str]]] = None,
        source_filter: str = "all",
        min_commission: Optional[int] = None
    ) -> Dict:
        """加载商品数据"""
        try:
            # 构建请求参数
            params = {
                "page": page,
                "page_size": page_size,
                "min_price": min_price,
                "max_price": max_price,
                "min_discount": min_discount,
                "is_prime_only": prime_only,
                "product_type": product_type,
                "sort_by": sort_by,
                "sort_order": sort_order
            }
            
            # 添加数据来源筛选
            if source_filter != "all":
                params["source"] = source_filter
            
            # 添加佣金筛选
            if min_commission is not None and source_filter in ["all", "cj"]:
                params["min_commission"] = min_commission
            
            # 添加类别筛选参数
            if selected_categories:
                if selected_categories.get("main_categories"):
                    params["main_categories"] = selected_categories["main_categories"]
                if selected_categories.get("sub_categories"):
                    params["sub_categories"] = selected_categories["sub_categories"]
                if selected_categories.get("bindings"):
                    params["bindings"] = selected_categories["bindings"]
                if selected_categories.get("product_groups"):
                    params["product_groups"] = selected_categories["product_groups"]
            
            # 移除None值和空列表的参数
            params = {k: v for k, v in params.items() if (isinstance(v, list) and len(v) > 0) or (not isinstance(v, list) and v is not None)}
            
            # 根据商品类型选择不同的API端点
            if product_type == "discount":
                endpoint = "/api/products/discount"
            elif product_type == "coupon":
                endpoint = "/api/products/coupon"
            else:
                endpoint = "/api/products/list"
            
            # 发送请求
            response = requests.get(f"{self.api_base_url}{endpoint}", params=params)
            response.raise_for_status()
            
            data = response.json()
            if isinstance(data, dict):
                return data
            else:
                return {
                    "items": data,
                    "total": len(data),
                    "page": page,
                    "page_size": page_size
                }
            
        except Exception as e:
            st.error(f"加载商品列表失败: {str(e)}")
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

    def load_category_stats(self) -> Dict[str, Dict[str, int]]:
        """加载类别统计信息"""
        try:
            response = requests.get(f"{self.api_base_url}/api/categories/stats")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"加载类别统计信息失败: {str(e)}")
            return {
                "main_categories": {},
                "sub_categories": {},
                "bindings": {},
                "product_groups": {}
            }

    def delete_product(self, asin: str) -> bool:
        """删除商品"""
        try:
            response = requests.delete(f"{self.api_base_url}/api/products/{asin}")
            success = response.status_code == 200
            if success:
                # 清除相关缓存
                cache_manager.clear_cache()
            return success
        except Exception as e:
            st.error(f"删除失败: {str(e)}")
            return False

    def batch_delete_products(self, products: List[Dict]) -> Dict[str, int]:
        """批量删除商品"""
        try:
            asins = [product["asin"] for product in products]
            response = requests.post(
                f"{self.api_base_url}/api/products/batch-delete",
                json={"asins": asins}
            )
            
            if response.status_code == 200:
                result = response.json()
                # 清除相关缓存
                cache_manager.clear_cache()
                return result
            return {"success_count": 0, "fail_count": len(asins)}
        except Exception as e:
            st.error(f"删除失败: {str(e)}")
            return {"success_count": 0, "fail_count": len(asins)} 