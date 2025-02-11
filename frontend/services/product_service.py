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
        selected_filters: Optional[Dict[str, List[str]]] = None,
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
                "sort_by": sort_by,
                "sort_order": sort_order
            }
            
            # 添加数据来源筛选 - 使用api_provider参数
            if source_filter != "all":
                if source_filter == "pa-api":
                    params["api_provider"] = "pa-api"
                elif source_filter == "cj":
                    params["api_provider"] = "cj-api"
            
            # 添加佣金筛选
            if min_commission is not None and min_commission > 0:
                if source_filter == "all":
                    # 当选择全部来源且设置了佣金时，使用cj-api
                    params["api_provider"] = "cj-api"
                    params["min_commission"] = min_commission
                elif source_filter == "cj":
                    params["min_commission"] = min_commission
            
            # 添加筛选参数
            if selected_filters:
                if selected_filters.get("browse_node_ids"):
                    params["browse_node_ids"] = selected_filters["browse_node_ids"]
                if selected_filters.get("bindings"):
                    params["bindings"] = selected_filters["bindings"]
                if selected_filters.get("product_groups"):
                    params["product_groups"] = selected_filters["product_groups"]
            
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

    def get_product_stats(self) -> Dict:
        """获取商品统计信息"""
        try:
            response = requests.get(f"{self.api_base_url}/api/products/stats")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"获取商品统计信息失败: {str(e)}")
            return {
                "total_products": 0,
                "min_price": 0,
                "max_price": 0,
                "avg_price": 0,
                "min_discount": 0,
                "max_discount": 0,
                "avg_discount": 0,
                "prime_products": 0,
                "last_update": None
            }

    def get_coupon_stats(self) -> Dict:
        """获取优惠券统计信息"""
        try:
            response = requests.get(f"{self.api_base_url}/api/coupons/stats")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"获取优惠券统计信息失败: {str(e)}")
            return {
                "total_coupons": 0,
                "percentage_coupons": 0,
                "fixed_coupons": 0,
                "min_value": 0,
                "max_value": 0,
                "avg_value": 0,
                "median_value": 0
            } 