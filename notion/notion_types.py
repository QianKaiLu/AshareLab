"""
notion_types.py
Type definitions and dataclasses for Notion API integration.
"""

from dataclasses import dataclass, field
from typing import Optional, Literal, Any


@dataclass
class NotionPageResult:
    """Result of a Notion page creation operation."""

    page_id: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    error: Optional[str] = None
    success: bool = False


@dataclass
class NotionParent:
    """Parent container specification for Notion pages."""

    type: Literal["page_id", "data_source_id"]
    id: str

    def to_dict(self) -> dict:
        return {self.type: self.id}


@dataclass
class NotionPageRequest:
    """Batch request item for creating a Notion page."""

    markdown: str
    parent: NotionParent
    title: Optional[str] = None
    properties: Optional[dict] = None


@dataclass
class NotionAPIError:
    """Parsed Notion API error response."""

    status: int
    code: str = ""
    message: str = ""

    def __str__(self) -> str:
        return f"[{self.status}] {self.code}: {self.message}"


@dataclass
class NotionChildPage:
    """Represents a child page in Notion."""

    id: str
    title: str
    has_children: bool
    parent_id: str
    children: list["NotionChildPage"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "has_children": self.has_children,
            "parent_id": self.parent_id,
            "children": [c.to_dict() for c in self.children],
        }