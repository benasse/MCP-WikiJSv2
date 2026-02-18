"""Tests for Pydantic input/output models."""

import pytest
from pydantic import ValidationError

from wikijs_mcp.models import (
    CreatePageInput,
    DeletePageInput,
    GetPageByPathInput,
    GetPageInput,
    ListPagesInput,
    ResponseFormat,
    SearchPagesInput,
    UpdatePageInput,
)


# ---------------------------------------------------------------------------
# ResponseFormat
# ---------------------------------------------------------------------------

class TestResponseFormat:
    def test_values(self):
        assert ResponseFormat.JSON == "json"
        assert ResponseFormat.MARKDOWN == "markdown"

    def test_from_string(self):
        assert ResponseFormat("json") == ResponseFormat.JSON
        assert ResponseFormat("markdown") == ResponseFormat.MARKDOWN


# ---------------------------------------------------------------------------
# SearchPagesInput
# ---------------------------------------------------------------------------

class TestSearchPagesInput:
    def test_valid(self):
        m = SearchPagesInput(query="docker install")
        assert m.query == "docker install"
        assert m.response_format == ResponseFormat.JSON

    def test_whitespace_stripped(self):
        m = SearchPagesInput(query="  hello  ")
        assert m.query == "hello"

    def test_query_too_short(self):
        with pytest.raises(ValidationError):
            SearchPagesInput(query="")

    def test_query_too_long(self):
        with pytest.raises(ValidationError):
            SearchPagesInput(query="x" * 501)

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            SearchPagesInput(query="test", unknown="bad")

    def test_markdown_format(self):
        m = SearchPagesInput(query="test", response_format="markdown")
        assert m.response_format == ResponseFormat.MARKDOWN


# ---------------------------------------------------------------------------
# ListPagesInput
# ---------------------------------------------------------------------------

class TestListPagesInput:
    def test_defaults(self):
        m = ListPagesInput()
        assert m.limit == 20
        assert m.offset == 0
        assert m.order_by == "TITLE"
        assert m.response_format == ResponseFormat.JSON

    def test_limit_boundaries(self):
        assert ListPagesInput(limit=1).limit == 1
        assert ListPagesInput(limit=100).limit == 100
        with pytest.raises(ValidationError):
            ListPagesInput(limit=0)
        with pytest.raises(ValidationError):
            ListPagesInput(limit=101)

    def test_offset_non_negative(self):
        assert ListPagesInput(offset=0).offset == 0
        with pytest.raises(ValidationError):
            ListPagesInput(offset=-1)

    def test_order_by_uppercased(self):
        assert ListPagesInput(order_by="updated").order_by == "UPDATED"
        assert ListPagesInput(order_by="PATH").order_by == "PATH"

    def test_invalid_order_by(self):
        with pytest.raises(ValidationError):
            ListPagesInput(order_by="RANDOM")

    def test_all_valid_order_by_values(self):
        for val in ("TITLE", "PATH", "CREATED", "UPDATED"):
            m = ListPagesInput(order_by=val)
            assert m.order_by == val


# ---------------------------------------------------------------------------
# GetPageInput
# ---------------------------------------------------------------------------

class TestGetPageInput:
    def test_valid(self):
        m = GetPageInput(page_id=15)
        assert m.page_id == 15
        assert m.response_format == ResponseFormat.JSON

    def test_page_id_minimum(self):
        with pytest.raises(ValidationError):
            GetPageInput(page_id=0)

    def test_page_id_must_be_int(self):
        with pytest.raises(ValidationError):
            GetPageInput(page_id="abc")

    def test_extra_forbidden(self):
        with pytest.raises(ValidationError):
            GetPageInput(page_id=1, extra_field="x")


# ---------------------------------------------------------------------------
# GetPageByPathInput
# ---------------------------------------------------------------------------

class TestGetPageByPathInput:
    def test_valid(self):
        m = GetPageByPathInput(path="guides/installation")
        assert m.path == "guides/installation"
        assert m.locale == "en"

    def test_locale_too_short(self):
        with pytest.raises(ValidationError):
            GetPageByPathInput(path="home", locale="x")

    def test_locale_too_long(self):
        with pytest.raises(ValidationError):
            GetPageByPathInput(path="home", locale="x" * 11)

    def test_path_stripped(self):
        m = GetPageByPathInput(path="  home  ")
        assert m.path == "home"


# ---------------------------------------------------------------------------
# CreatePageInput
# ---------------------------------------------------------------------------

class TestCreatePageInput:
    def test_valid_minimal(self):
        m = CreatePageInput(title="Test", path="test", content="# Test")
        assert m.path == "test"
        assert m.editor == "markdown"
        assert m.is_published is True
        assert m.is_private is False
        assert m.tags == []

    def test_leading_slash_stripped_from_path(self):
        m = CreatePageInput(title="T", path="/guides/install", content="x")
        assert m.path == "guides/install"

    def test_multiple_leading_slashes_stripped(self):
        m = CreatePageInput(title="T", path="//deep/path", content="x")
        assert m.path == "deep/path"

    def test_title_required(self):
        with pytest.raises(ValidationError):
            CreatePageInput(title="", path="p", content="c")

    def test_title_max_length(self):
        with pytest.raises(ValidationError):
            CreatePageInput(title="x" * 256, path="p", content="c")

    def test_invalid_editor(self):
        with pytest.raises(ValidationError):
            CreatePageInput(title="T", path="p", content="c", editor="word")

    def test_all_valid_editors(self):
        for editor in ("markdown", "ckeditor", "code", "asciidoc"):
            m = CreatePageInput(title="T", path="p", content="c", editor=editor)
            assert m.editor == editor

    def test_tags_default_empty_list(self):
        m = CreatePageInput(title="T", path="p", content="c")
        assert m.tags == []

    def test_tags_provided(self):
        m = CreatePageInput(title="T", path="p", content="c", tags=["devops", "linux"])
        assert m.tags == ["devops", "linux"]


# ---------------------------------------------------------------------------
# UpdatePageInput
# ---------------------------------------------------------------------------

class TestUpdatePageInput:
    def test_all_fields_optional_except_page_id(self):
        m = UpdatePageInput(page_id=1)
        assert m.title is None
        assert m.content is None
        assert m.description is None
        assert m.tags is None
        assert m.is_published is None
        assert m.is_private is None

    def test_page_id_minimum(self):
        with pytest.raises(ValidationError):
            UpdatePageInput(page_id=0)

    def test_partial_update(self):
        m = UpdatePageInput(page_id=15, title="New Title", is_published=False)
        assert m.title == "New Title"
        assert m.is_published is False
        assert m.content is None


# ---------------------------------------------------------------------------
# DeletePageInput
# ---------------------------------------------------------------------------

class TestDeletePageInput:
    def test_valid(self):
        m = DeletePageInput(page_id=99)
        assert m.page_id == 99

    def test_page_id_minimum(self):
        with pytest.raises(ValidationError):
            DeletePageInput(page_id=0)

    def test_extra_forbidden(self):
        with pytest.raises(ValidationError):
            DeletePageInput(page_id=1, confirm=True)
