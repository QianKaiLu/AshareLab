# Notion Integration Component

Notion API 集成组件，用于将 Markdown 文档写入 Notion 页面或数据库。

## 功能特性

- ✅ 同步和异步两种接口
- ✅ 支持 Markdown 字符串或文件路径输入
- ✅ 自动从 H1 标题提取页面标题
- ✅ 支持创建普通子页面和数据库条目
- ✅ 异步批量创建（并发控制）
- ✅ 完善的错误处理和日志记录
- ✅ 类型提示和数据类支持

## 快速开始

### 1. 配置 Token

在项目根目录的 `.env` 文件中添加：

```bash
NOTION_TOKEN=ntn_your_integration_token_here
```

### 2. 基础使用

```python
from notion import NotionClient

# 初始化客户端
client = NotionClient(token)

# 创建页面
result = client.create_page_from_markdown(
    markdown="# 我的页面\n\n这是内容。",
    parent_page_id="your-parent-page-id"
)

if result.success:
    print(f"✅ 页面已创建: {result.url}")
else:
    print(f"❌ 错误: {result.error}")
```

## API 文档

### NotionClient (同步)

```python
class NotionClient:
    def __init__(self, token: str)
    
    def create_page_from_markdown(
        self,
        markdown: Union[str, Path],
        parent_page_id: Optional[str] = None,
        parent_data_source_id: Optional[str] = None,
        title: Optional[str] = None,
        properties: Optional[dict] = None
    ) -> NotionPageResult
```

**参数说明：**
- `markdown`: Markdown 内容（字符串）或文件路径
- `parent_page_id`: 父页面 ID（创建子页面时使用）
- `parent_data_source_id`: 数据库数据源 ID（创建数据库条目时使用）
- `title`: 页面标题（可选，未提供时从 H1 提取）
- `properties`: 数据库属性字典（数据库条目必需）

**返回值：** `NotionPageResult`
- `success`: bool - 是否成功
- `page_id`: str - 页面 ID
- `url`: str - 页面 URL
- `title`: str - 页面标题
- `error`: str - 错误信息（失败时）

### AsyncNotionClient (异步)

```python
class AsyncNotionClient:
    def __init__(self, token: str)
    
    async def create_page_from_markdown(
        self,
        markdown: Union[str, Path],
        parent_page_id: Optional[str] = None,
        parent_data_source_id: Optional[str] = None,
        title: Optional[str] = None,
        properties: Optional[dict] = None
    ) -> NotionPageResult
    
    async def batch_create_pages(
        self,
        requests: list[NotionPageRequest],
        max_concurrent: int = 5
    ) -> list[NotionPageResult]
```

## 使用示例

### 示例 1: 从字符串创建页面

```python
from notion import NotionClient

client = NotionClient(token)

markdown = """# 股票分析报告

## 技术指标
- MACD: 金叉
- KDJ: 超买区

## 结论
建议关注。
"""

result = client.create_page_from_markdown(
    markdown=markdown,
    parent_page_id="494c87d072c44cf6960f55f8427f7692"
)
```

### 示例 2: 从文件创建页面

```python
result = client.create_page_from_markdown(
    markdown="output/stock_report.md",
    parent_page_id="494c87d072c44cf6960f55f8427f7692",
    title="每日股票分析"  # 可选：覆盖文件中的标题
)
```

### 示例 3: 创建数据库条目

```python
result = client.create_page_from_markdown(
    markdown="## 任务详情\n\n实现新功能。",
    parent_data_source_id="248104cd-477e-80af-bc30-000bd28de8f9",
    properties={
        "任务名称": {
            "title": [{"text": {"content": "实现股票分析功能"}}]
        },
        "优先级": {
            "select": {"name": "高"}
        }
    }
)
```

### 示例 4: 异步批量创建

```python
import asyncio
from notion import AsyncNotionClient, NotionPageRequest, NotionParent

async def batch_create():
    client = AsyncNotionClient(token)
    
    requests = [
        NotionPageRequest(
            markdown=f"# 报告 {i}\n\n内容...",
            parent=NotionParent(type="page_id", id="your-page-id"),
            title=f"报告 {i}"
        )
        for i in range(5)
    ]
    
    results = await client.batch_create_pages(requests, max_concurrent=3)
    
    for r in results:
        if r.success:
            print(f"✅ {r.title}: {r.url}")

asyncio.run(batch_create())
```

## 获取 Parent ID

### 页面 ID (page_id)

从页面 URL 中提取 32 位字符串：
```
https://www.notion.so/My-Page-494c87d072c44cf6960f55f8427f7692
                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                              这就是 page_id
```

### 数据库数据源 ID (data_source_id)

需要先调用 API 获取：

```python
from notion_client import Client

client = Client(auth=token)
database = client.databases.retrieve(database_id="your-database-id")
data_source_id = database["data_sources"][0]["id"]
```

## 错误处理

组件会捕获所有异常并返回 `NotionPageResult` 对象：

```python
result = client.create_page_from_markdown(...)

if not result.success:
    print(f"创建失败: {result.error}")
    # 处理错误...
```

常见错误：
- `validation_error`: 参数验证失败（如数据库条目缺少 properties）
- `object_not_found`: 页面/数据库未找到或未共享给集成
- `unauthorized`: Token 无效或权限不足

## 测试

运行测试脚本：

```bash
# 1. 在 test_notion_client.py 中设置 TEST_PAGE_ID
# 2. 运行测试
python notion/test_notion_client.py
```

## 依赖

- `notion-client`: Notion 官方 Python SDK
- `python-dotenv`: 环境变量管理
- 项目已有依赖（无需额外安装）

## 架构设计

```
notion/
├── __init__.py              # 包导出
├── notion_types.py          # 数据类定义
├── notion_markdown.py       # Markdown 处理工具
├── notion_client_wrapper.py # 核心客户端实现
├── example_usage.py         # 使用示例
├── test_notion_client.py    # 测试脚本
└── README.md               # 本文档
```

## 注意事项

1. **API 版本**: 使用 `2026-03-11` 版本
2. **权限**: 需要在 Notion 中将目标页面/数据库共享给集成（Add connections）
3. **速率限制**: Notion API 限制为 3 请求/秒，异步批量创建会自动控制并发
4. **数据库条目**: 创建数据库条目时必须提供 `properties`，且包含 title 属性

## 扩展功能

当前实现专注于核心功能（创建页面），未来可扩展：

- 更新页面内容
- 查询和检索页面
- 数据库查询和过滤
- 块级操作（追加/更新块）
- 文件上传支持
- 模板系统集成

## 参考文档

- [Notion API 官方文档](https://developers.notion.com/reference/post-page)
- [Markdown 内容支持](https://developers.notion.com/guides/data-apis/working-with-markdown-content)
- [数据库操作指南](https://developers.notion.com/guides/data-apis/working-with-databases)
