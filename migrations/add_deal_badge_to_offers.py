"""
为offers表添加deal_badge列的数据库迁移脚本
"""

import sqlite3
from datetime import datetime, UTC
import os
from pathlib import Path

def migrate():
    # 获取数据库文件路径
    data_dir = Path(__file__).parent.parent / "data" / "db"
    db_file = os.environ.get("PRODUCTS_DB_PATH", data_dir / "amazon_products.db")
    
    # 连接数据库
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    try:
        # 检查列是否已存在
        cursor.execute("PRAGMA table_info(offers)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if "deal_badge" not in columns:
            # 添加新列
            cursor.execute("""
                ALTER TABLE offers 
                ADD COLUMN deal_badge VARCHAR(200)
            """)
            print("成功添加deal_badge列")
        else:
            print("deal_badge列已存在")
        
        # 提交更改
        conn.commit()
        
    except Exception as e:
        print(f"迁移失败: {str(e)}")
        conn.rollback()
        raise
    
    finally:
        # 关闭连接
        conn.close()

if __name__ == "__main__":
    migrate() 