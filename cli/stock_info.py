"""
股票信息查询命令行工具
用法: stock-info <部分代码或全称>

示例:
    stock-info 632           → 查000632
    stock-info 600000        → 查600000
    stock-info 贵州茅台       → 模糊匹配名称
"""
import sqlite3
from pathlib import Path
import sys

# 数据库路径（根据你的实际结构调整）
DB_PATH = Path(__file__).parent.parent / "database" / "ashare_data.db"

def query_stock_info(keyword: str):
    """
    根据关键词（代码/名称）查询股票信息
    支持：
        - 数字代码自动补零到6位，查 code 或 symbol
        - 文字 → 模糊匹配 name/full_name
    """
    # 连接数据库（使用 row_factory 方便读取）
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 可以用 row['column'] 访问
    cursor = conn.cursor()

    keyword = keyword.strip()

    # 逻辑1：如果是纯数字，尝试补齐6位查询 code 或 symbol
    if keyword.isdigit():
        padded_code = keyword.zfill(6)  # 补零到6位
        
        # 先按 code 精确查
        cursor.execute("""
            SELECT * FROM stock_base_info 
            WHERE code = ? OR symbol LIKE ?
            ORDER BY length(code) ASC
            LIMIT 1
        """, (padded_code, f"%{padded_code}"))

    else:
        # 逻辑2：按名称模糊匹配
        cursor.execute("""
            SELECT * FROM stock_base_info 
            WHERE name LIKE ? OR full_name LIKE ?
            ORDER BY length(name) ASC
            LIMIT 5
        """, (f"%{keyword}%", f"%{keyword}%"))

    rows = cursor.fetchall()
    conn.close()
    return rows

def format_stock_info(row):
    """美化打印单条股票信息"""
    if not row:
        return "❌ 未找到相关股票信息。"

    lines = [
        "📊 股票基本信息".center(50, "="),
        f"🔢 代码      : {row['exchange_code']}{row['code']}",
        f"🏢 名称      : {row['name']}",
        f"📝 全称      : {row['full_name'] or '—'}",
        f"🏭 所属行业   : {row['idn_name'] or '—'} ({row['idn_code'] or '—'})",
        f"📅 上市日期   : {row['list_date'] or '—'}",
        f"📋 经营范围   : {row['operating_scope'][:100] + '...' if row['operating_scope'] and len(row['operating_scope']) > 100 else row['operating_scope'] or '—'}",
        f"🔄 更新时间   : {row['update_time'] or '—'}",
        f"⚙️  状态     : {row['status']}",
        "=" * 50
    ]
    return "\n".join(lines)

def main():
    if len(sys.argv) != 2:
        print("用法: stock-info <股票代码/名称>")
        print("示例: stock-info 632")
        print("示例: stock-info 贵州茅台")
        sys.exit(1)

    keyword = sys.argv[1]
    stocks = query_stock_info(keyword)

    if not stocks:
        print("❌ 未找到匹配的股票，请检查输入或更新数据库。")
        sys.exit(1)

    for i, stock in enumerate(stocks):
        if i > 0:
            print("\n" + "-"*50 + "\n")
        print(format_stock_info(stock))

if __name__ == "__main__":
    main()
