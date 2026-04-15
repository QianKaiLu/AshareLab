from openai import OpenAI
from typing import Literal
import os
from dotenv import load_dotenv

load_dotenv()
QIANWEN_API_KEY = os.getenv("QIANWEN_API_KEY", default="")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", default="")
DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY", default="")

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

def QWEN_3_6_PLUS() -> ApiProfile:
    return ApiProfile("qwen3.6-plus", QIANWEN_API_KEY, "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3.6-plus")

def DOUBAO_Seed_2_0_mini() -> ApiProfile:
    return ApiProfile("doubao-seed-2-0-mini-260215", DOUBAO_API_KEY, "https://ark.cn-beijing.volces.com/api/v3", "doubao-seed-2-0-mini-260215")

def DEEPSEEK_REASONER() -> ApiProfile:
    return ApiProfile("deepseek-reasoner", DEEPSEEK_API_KEY, "https://api.deepseek.com", "deepseek-reasoner")