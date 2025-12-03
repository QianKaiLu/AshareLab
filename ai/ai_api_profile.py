from openai import OpenAI
from typing import Literal
import os
from dotenv import load_dotenv

load_dotenv()
QIANWEN_API_KEY = os.getenv("QIANWEN_API_KEY", default="")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", default="")

class ApiProfile:
    name: str
    api_key: str
    base_url: str
    model: str
    
    def __init__(self, name: str, api_key: str, base_url: str, model: str):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

def QWEN_MAX() -> ApiProfile:
    return ApiProfile("qwen-max", QIANWEN_API_KEY, "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3-max")

def DEEPSEEK_REASONER() -> ApiProfile:
    return ApiProfile("deepseek-reasoner", DEEPSEEK_API_KEY, "https://api.deepseek.com", "deepseek-reasoner")