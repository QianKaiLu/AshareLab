"""
notion_types.py
Type definitions and dataclasses for Notion API integration.
"""

from dataclasses import dataclass
from typing import Optional, Literal


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
        """Convert to Notion API format."""
        return {"type": self.type, self.type: self.id}


@dataclass
class NotionPageRequest:
    """Request parameters for creating a Notion page."""

    markdown: str
    parent: NotionParent
    title: Optional[str] = None
    properties: Optional[dict] = None
