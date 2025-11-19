import os
from dotenv import load_dotenv

load_dotenv()

QIANWEN_API_KEY = os.getenv("QIANWEN_API_KEY")

TUSHARE_TOKENS = [
    '2cf551afc37b607a31ddb855966986de8b8ec67aa856914b4a893b51',
    'd2f856055cefeb4a3a43784054478263d38d77072561d7fdba5e8f4e'
] + os.getenv("TUSHARE_TOKENS", "").split(",")