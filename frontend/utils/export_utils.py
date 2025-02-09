"""
导出工具模块
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from typing import List, Dict
from frontend.i18n.language import get_text

def handle_export(
    products: List[Dict],
    key_suffix: str = ""
):
    """处理数据导出
    
    Args:
        products: 商品列表
        key_suffix: 状态键后缀
    """
    st.markdown("---")
    st.subheader(get_text("export_data"))
    
    export_format = st.selectbox(
        get_text("export_format"),
        options=["CSV", "JSON", "Excel"],
        index=0,
        key=f"export_format_{key_suffix}"
    )
    
    if st.button(
        get_text("export_button"),
        key=f"export_{key_suffix}"
    ):
        if products:
            try:
                df = pd.DataFrame(products)
                
                # 根据选择的格式导出
                if export_format == "CSV":
                    csv = df.to_csv(index=False)
                    st.download_button(
                        get_text("save") + " CSV",
                        csv,
                        f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        "text/csv",
                        key=f"download_csv_{key_suffix}"
                    )
                
                elif export_format == "JSON":
                    json_str = df.to_json(orient="records", force_ascii=False)
                    st.download_button(
                        get_text("save") + " JSON",
                        json_str,
                        f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        "application/json",
                        key=f"download_json_{key_suffix}"
                    )
                
                else:  # Excel
                    excel_buffer = pd.ExcelWriter(
                        f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        engine="openpyxl"
                    )
                    df.to_excel(excel_buffer, index=False)
                    excel_buffer.save()
                    
                    with open(excel_buffer.path, "rb") as f:
                        st.download_button(
                            get_text("save") + " Excel",
                            f,
                            f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"download_excel_{key_suffix}"
                        )
                
                st.success(get_text("export_success"))
                
            except Exception as e:
                st.error(f"{get_text('export_failed')}: {str(e)}")
        else:
            st.warning(get_text("no_data")) 