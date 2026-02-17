"""Shared Pydantic models and enums for wikijs_mcp tools."""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, ConfigDict


class ResponseFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class SearchPagesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    query: str = Field(..., description="Full-text search query (e.g. 'installation guide')", min_length=1, max_length=500)
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format: 'json' or 'markdown'")


class ListPagesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    limit: Optional[int] = Field(default=20, description="Maximum number of pages to return (1–100)", ge=1, le=100)
    offset: Optional[int] = Field(default=0, description="Number of pages to skip for pagination", ge=0)
    order_by: Optional[str] = Field(default="TITLE", description="Sort order: 'TITLE', 'PATH', 'CREATED', 'UPDATED'")
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format: 'json' or 'markdown'")

    @field_validator("order_by")
    @classmethod
    def validate_order_by(cls, v: str) -> str:
        allowed = {"TITLE", "PATH", "CREATED", "UPDATED"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"order_by must be one of {sorted(allowed)}")
        return upper


class GetPageInput(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    page_id: int = Field(..., description="Numeric ID of the Wiki.js page (e.g. 15)", ge=1)
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format: 'json' or 'markdown'")


class GetPageByPathInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    path: str = Field(..., description="Page path (e.g. 'home', 'guides/installation')", min_length=1, max_length=1000)
    locale: str = Field(default="en", description="Locale code (e.g. 'en', 'fr')", min_length=2, max_length=10)
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="Output format: 'json' or 'markdown'")


class CreatePageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    title: str = Field(..., description="Page title (e.g. 'Installation Guide')", min_length=1, max_length=255)
    path: str = Field(..., description="URL path for the page (e.g. 'guides/installation', no leading slash)", min_length=1, max_length=1000)
    content: str = Field(..., description="Page content in Markdown format", min_length=1)
    description: Optional[str] = Field(default="", description="Short description/summary of the page")
    locale: str = Field(default="en", description="Locale code (e.g. 'en', 'fr')", min_length=2, max_length=10)
    editor: str = Field(default="markdown", description="Editor type: 'markdown', 'ckeditor', or 'code'")
    is_published: bool = Field(default=True, description="Whether to publish the page immediately")
    is_private: bool = Field(default=False, description="Whether the page is private")
    tags: Optional[List[str]] = Field(default_factory=list, description="List of tags to apply to the page")

    @field_validator("path")
    @classmethod
    def strip_leading_slash(cls, v: str) -> str:
        return v.lstrip("/")

    @field_validator("editor")
    @classmethod
    def validate_editor(cls, v: str) -> str:
        allowed = {"markdown", "ckeditor", "code", "asciidoc"}
        if v.lower() not in allowed:
            raise ValueError(f"editor must be one of {sorted(allowed)}")
        return v.lower()


class UpdatePageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    page_id: int = Field(..., description="Numeric ID of the page to update", ge=1)
    title: Optional[str] = Field(default=None, description="New page title", min_length=1, max_length=255)
    content: Optional[str] = Field(default=None, description="New page content in Markdown format")
    description: Optional[str] = Field(default=None, description="New short description")
    tags: Optional[List[str]] = Field(default=None, description="New list of tags (replaces existing tags)")
    is_published: Optional[bool] = Field(default=None, description="Change published status")
    is_private: Optional[bool] = Field(default=None, description="Change private status")


class DeletePageInput(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    page_id: int = Field(..., description="Numeric ID of the page to delete", ge=1)
