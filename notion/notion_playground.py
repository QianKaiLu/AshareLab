import os
from notion_client import Client, AsyncClient
from dotenv import load_dotenv
import asyncio

load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN", default="")
notion = Client(auth=NOTION_TOKEN)

def verify_notion_connection():
    try:
        response = notion.users.me()
        print("Successfully connected to Notion!")
        print(f"User ID: {response['id']}")
        print(f"User Name: {response['name']}")
    except Exception as e:
        print("Failed to connect to Notion.")
        print(f"Error: {e}")

async def verify_notion_connection_async() -> bool:
    async_notion = AsyncClient(auth=NOTION_TOKEN)
    try:
        response = await async_notion.users.me()
        print(response)
        if response['id'] is not None:
            return True
        else:
            return False

    except Exception as e:
        return False
    
def fetch_notion_databases(database_id: str = None):
    query_payload = {
        "database_id": database_id,
        "filter": {
            "and":
        },
        "sorts":
    }
    
    # 调用 Database Query 接口 
    response = notion.databases.query(**query_payload)
    print(response)

if __name__ == "__main__":
    fetch_notion_databases(database_id='349b4139bc644bf2884ecc28959bdacc')