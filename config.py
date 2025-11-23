import os
from dotenv import load_dotenv

load_dotenv()

QIANWEN_API_KEY = os.getenv("QIANWEN_API_KEY")

TUSHARE_TOKENS = [
    '2cf551afc37b607a31ddb855966986de8b8ec67aa856914b4a893b51',
    'd2f856055cefeb4a3a43784054478263d38d77072561d7fdba5e8f4e',
    '308f2d3c494e5add2301624bc8703c7a3eeecae9d6307f863c905599',
    'a05d2238998be545a38a4e35c053defdb4b2cf056a2d06b504f0af46',
    '423b7e052a0912df2999fe0bd3e2b5466f84b4ca8f1346aef23e5bf5',
    'ca128aaafea1696544a545f7e41de5aa03c63c79f81131fc22582425',
    'd4d83b954b4322c8d343f74a707cb2200d162acdb97c80dd513f6bd5'
] 
# + os.getenv("TUSHARE_TOKENS", "").split(",")