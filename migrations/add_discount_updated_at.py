"""
添加discount_updated_at列的数据库迁移脚本
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
        cursor.execute("PRAGMA table_info(products)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if "discount_updated_at" not in columns:
            # 先添加新列，初始值为NULL
            cursor.execute("""
                ALTER TABLE products 
                ADD COLUMN discount_updated_at TIMESTAMP
            """)
            print("成功添加discount_updated_at列")
        else:
            print("discount_updated_at列已存在")
        
        # 无论列是新增还是已存在，都将discount_updated_at设置为与created_at相同的值
        print("正在将discount_updated_at更新为对应的created_at值...")
        cursor.execute("""
            UPDATE products
            SET discount_updated_at = created_at
            WHERE created_at IS NOT NULL
        """)
        print(f"已将{cursor.rowcount}条记录的discount_updated_at设为created_at值")
        
        # 对于没有created_at值的记录，使用2025-03-31作为基准时间（表示从未更新过）
        cursor.execute("""
            UPDATE products
            SET discount_updated_at = '2025-03-31T00:00:00+00:00'
            WHERE created_at IS NULL OR discount_updated_at IS NULL
        """)
        print(f"已将{cursor.rowcount}条没有created_at的记录设置为基准时间")
        
        # 提交更改
        conn.commit()
        print("数据库迁移完成")
        
    except Exception as e:
        print(f"迁移失败: {str(e)}")
        conn.rollback()
        raise
    
    finally:
        # 关闭连接
        conn.close()

if __name__ == "__main__":
    migrate() 