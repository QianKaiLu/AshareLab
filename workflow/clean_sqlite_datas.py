from datas.create_database import delete_table_if_exists, create_daily_bar_table, DAILY_BAR_TABLE, get_db_connection

# delete_table_if_exists(f"{DAILY_BAR_TABLE}")
# create_daily_bar_table()

with get_db_connection() as conn:
    delete_query = f"DELETE FROM {DAILY_BAR_TABLE};"
    conn.execute(delete_query)
    conn.commit()