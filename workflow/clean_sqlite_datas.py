from datas.create_database import delete_table_if_exists, create_daily_bar_table, DAILY_BAR_TABLE, get_db_connection
from tools.log import get_fetch_logger

logger = get_fetch_logger()

# delete_table_if_exists(f"{DAILY_BAR_TABLE}")
# create_daily_bar_table()

with get_db_connection() as conn:
    logger.info(f"Clearing all data from table '{DAILY_BAR_TABLE}'.")
    delete_query = f"DELETE FROM {DAILY_BAR_TABLE};"
    conn.execute(delete_query)
    conn.commit()
    logger.info(f"✅ Cleared all data from table '{DAILY_BAR_TABLE}'.")