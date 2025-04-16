"""
向coupon_history表添加expiration_date和terms字段的数据库迁移脚本

该脚本会检查字段是否存在，如果不存在则添加相应字段
"""

import os
import sqlite3
from pathlib import Path

# 获取项目根目录
project_root = Path(__file__).parent.parent
data_dir = project_root / "data" / "db"

# 确定数据库文件路径
if "PRODUCTS_DB_PATH" in os.environ:
    db_file = os.environ["PRODUCTS_DB_PATH"]
else:
    # 默认使用项目目录下的数据库文件
    db_file = data_dir / "amazon_products.db"

def run_migration():
    """执行迁移，添加新字段"""
    print(f"连接到数据库: {db_file}")
    
    # 连接到数据库
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    try:
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='coupon_history'")
        if not cursor.fetchone():
            print("错误: coupon_history表不存在!")
            return
        
        # 获取表的当前列信息
        cursor.execute("PRAGMA table_info(coupon_history)")
        columns = {row[1]: row for row in cursor.fetchall()}
        
        # 添加expiration_date字段
        if "expiration_date" not in columns:
            print("添加expiration_date字段...")
            cursor.execute("""
            ALTER TABLE coupon_history
            ADD COLUMN expiration_date TIMESTAMP
            """)
            print("成功添加expiration_date字段")
        else:
            print("expiration_date字段已存在")
        
        # 添加terms字段
        if "terms" not in columns:
            print("添加terms字段...")
            cursor.execute("""
            ALTER TABLE coupon_history
            ADD COLUMN terms TEXT
            """)
            print("成功添加terms字段")
        else:
            print("terms字段已存在")
        
        # 提交更改
        conn.commit()
        print("迁移完成")
        
    except Exception as e:
        conn.rollback()
        print(f"迁移失败: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration() 