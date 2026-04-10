### ✅ 目标
在 Notion 中：
- 若目标是 **页面（Page）** → 在其下创建子页面
- 若目标是 **数据库（Database）** → 在其数据源中创建新条目（Page）
- 新页面的内容 = 指定的 Markdown 字符串

---

### 🔑 核心 API 端点
`POST https://api.notion.com/v1/pages`

> ✨ 此端点同时支持创建普通子页面和数据库条目，并可通过 `markdown` 参数直接传入 Markdown 内容。

---

### 📥 请求体参数（JSON）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `parent` | object | ✅ | 指定父容器：<br>- 页面：`{ "type": "page_id", "page_id": "..." }`<br>- 数据库数据源：`{ "type": "data_source_id", "data_source_id": "..." }` |
| `markdown` | string | ✅ | **Markdown 格式的页面内容**（含 `\n` 换行） |
| `properties` | object | ⚠️ 条件必填 | - 创建**普通子页面**：可省略（若提供，必须含 `title`）<br>- 创建**数据库条目**：**必须提供**，且符合数据库 schema（至少包含 `title` 属性） |

> ⚠️ `markdown` 与 `children`/`content` 互斥 —— **不要同时使用**。

---

### 🧩 关键细节说明

#### 1. 如何获取 `parent` ID？
- **页面 ID**：
  - 从页面 URL 获取（32位无连字符字符串），API 接受带或不带 `-` 的格式。
- **数据库数据源 ID**：
  - 先调用 `GET /v1/databases/{database_id}` 获取 `data_sources` 数组
  - 取其中 `id` 字段（如 `"248104cd-477e-80af-bc30-000bd28de8f9"`）

#### 2. 数据库场景下的 `properties`
- 必须包含数据库定义的 **title 属性**（名称可能不是 "Title"，需查 schema）
- 示例（假设 title 属性名为 “Task”）：
  ```json
  "properties": {
    "Task": {
      "title": [{ "text": { "content": "自动生成的任务" } }]
    }
  }
  ```
- 若省略 `properties.title`，API 会尝试从 `markdown` 中提取第一个 `# H1` 作为标题（仅适用于普通页面，**数据库中无效**）。

#### 3. Markdown 格式要求
- 使用标准换行符 `\n`（在 JSON 字符串中需转义为 `"\\n"`）
- 支持增强语法：标题、列表、待办 `- [ ]`、代码块、图片 `![alt](url)`、子页面 `<page url="...">` 等
- 文件类 URL（图片/PDF等）会被自动转换为预签名链接

---

### 🔐 所需权限（Integration Capabilities）
- `insert_content`
- `insert_property`（仅数据库场景需要）

> 💡 在 Notion 中将目标页面/数据库通过 **⋯ → Add connections** 共享给你的集成。

---

### 🧪 示例请求（cURL）

#### 场景 A：在现有页面下创建子页面
```bash
curl -X POST 'https://api.notion.com/v1/pages' \
  -H 'Authorization: Bearer YOUR_API_KEY' \
  -H 'Notion-Version: 2026-03-11' \
  -H 'Content-Type: application/json' \
  --data '{
    "parent": { "page_id": "494c87d072c44cf6960f55f8427f7692" },
    "markdown": "# 会议纪要\n\n讨论了项目计划。\n\n## 待办事项\n\n- [ ] 编写文档\n- [ ] 安排评审"
  }'
```

#### 场景 B：在数据库中创建新条目
```bash
curl -X POST 'https://api.notion.com/v1/pages' \
  -H 'Authorization: Bearer YOUR_API_KEY' \
  -H 'Notion-Version: 2026-03-11' \
  -H 'Content-Type: application/json' \
  --data '{
    "parent": { "data_source_id": "248104cd-477e-80af-bc30-000bd28de8f9" },
    "properties": {
      "任务名称": {
        "title": [{ "text": { "content": "AI生成任务" } }]
      }
    },
    "markdown": "## 背景\n由AI自动创建。\n\n- 优先级：高\n- 截止日期：尽快"
  }'
```

---

### 📚 相关官方文档链接
- [Create a page (with markdown)](https://developers.notion.com/reference/post-page)
- [Working with markdown content](https://developers.notion.com/guides/data-apis/working-with-markdown-content)
- [Database & data source structure](https://developers.notion.com/guides/data-apis/working-with-databases)

---

### 🚫 常见错误规避
- ❌ 向数据库创建页面时未提供 `properties` → `validation_error`
- ❌ `markdown` 中使用 `\n` 但未在 JSON 中正确转义 → 内容显示为字面 `\n`
- ❌ 使用数据库的 **database_id** 而非 **data_source_id** 作为 parent → 失败
- ❌ 未将目标页面/数据库共享给集成 → `object_not_found`
