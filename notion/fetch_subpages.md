# Notion API：获取指定页面所有子页面
本文基于 Notion 官方 API 文档，说明如何通过 Notion Data API 获取一个页面下的**所有子页面（child_page）**，包含基础调用、递归获取嵌套子页面、完整代码示例。

---

## 一、核心概念
1. **页面本质**：Notion 页面本身是一种特殊 block，子页面在父页面中以 `child_page` 类型 block 存在。
2. **获取入口**：使用「获取 block 子节点」接口 `GET /v1/blocks/{block_id}/children`。
3. **子页面标识**：返回结果中 `type: "child_page"` 的 block 即为子页面。

---

## 二、前置条件
1. 创建 Notion 集成，获取 **API Key（Internal Integration Token）**。
2. 将集成**关联到目标页面**（页面右上角 ••• → Add connections）。
3. 获取目标页面 ID（从页面链接提取，按 8-4-4-4-12 格式格式化）。

---

## 三、基础步骤：获取一级子页面
### 1. 请求接口
```http
GET https://api.notion.com/v1/blocks/{page_id}/children?page_size=100
```

### 2. 请求头
```http
Authorization: Bearer {NOTION_API_KEY}
Notion-Version: 2026-03-11
Content-Type: application/json
```

### 3. 请求说明
- `page_id`：目标父页面 ID
- `page_size`：单页最大返回数量（最大 100）
- 支持分页：使用 `start_cursor` 遍历更多结果

### 4. 筛选子页面
接口返回所有子 block，**只保留 `type: "child_page"`** 的项。

### 5. 响应示例（关键部分）
```json
{
  "object": "list",
  "results": [
    {
      "object": "block",
      "id": "xxxx-xxxx-xxxx-xxxx",
      "parent": { "type": "page_id", "page_id": "父页面ID" },
      "type": "child_page",
      "child_page": {
        "title": "子页面标题"
      },
      "has_children": true
    }
  ],
  "has_more": false,
  "next_cursor": null
}
```

---

## 四、进阶：递归获取所有嵌套子页面
子页面可能还有下一级子页面，需**递归调用**获取完整层级。

### 递归逻辑
1. 调用 `GET /blocks/{id}/children` 获取当前 block 的子节点
2. 遍历结果，筛选 `type: "child_page"`
3. 对每个子页面，重复步骤 1–2，直到无更多子页面

---

## 五、完整代码示例（JavaScript）
```javascript
const NOTION_API_KEY = "你的集成Token";
const NOTION_VERSION = "2026-03-11";
const rootPageId = "根页面ID";

// 获取单个 block 的子节点（带分页）
async function getBlockChildren(blockId) {
  let allResults = [];
  let cursor = null;
  do {
    const url = new URL(`https://api.notion.com/v1/blocks/${blockId}/children`);
    if (cursor) url.searchParams.set("start_cursor", cursor);
    url.searchParams.set("page_size", "100");

    const res = await fetch(url.toString(), {
      headers: {
        Authorization: `Bearer ${NOTION_API_KEY}`,
        "Notion-Version": NOTION_VERSION,
      },
    });

    const data = await res.json();
    allResults = allResults.concat(data.results);
    cursor = data.next_cursor;
  } while (cursor);

  return allResults;
}

// 递归获取所有子页面
async function getAllChildPages(blockId) {
  const children = await getBlockChildren(blockId);
  const childPages = children.filter((b) => b.type === "child_page");

  const result = childPages.map((p) => ({
    id: p.id,
    title: p.child_page.title,
    hasChildren: p.has_children,
  }));

  // 递归获取子页面的子页面
  for (const page of childPages) {
    if (page.has_children) {
      const nested = await getAllChildPages(page.id);
      result.push(...nested);
    }
  }

  return result;
}

// 执行
getAllChildPages(rootPageId).then((pages) => {
  console.log("所有子页面：", pages);
});
```

---

## 六、常见问题
1. **返回空列表**
   - 集成未关联页面
   - Page ID 格式错误
   - 无权限读取该页面

2. **只拿到一级子页面**
   - 未做递归处理
   - 未判断 `has_children: true`

3. **速率限制**
   - 大量递归调用需注意 Notion API 速率限制，建议加延迟或队列。

---

## 七、参考接口
- [获取 block 子节点](https://developers.notion.com/reference/get-block-children)
- [Notion block 类型：child_page](https://developers.notion.com/reference/block#child-page)

---

要不要我帮你整理一份**可直接复制的 Python 版本代码**，方便快速运行？