"""
Tests for pagination utilities.
"""

from app.core.pagination import PaginationParams, paginate, make_paginated_result


class TestPaginationParams:
    def test_defaults(self):
        p = PaginationParams()
        assert p.page == 1
        assert p.page_size == 20
        assert p.offset == 0
        assert p.limit == 20

    def test_page_2(self):
        p = PaginationParams(page=2, page_size=10)
        assert p.offset == 10
        assert p.range_start == 10
        assert p.range_end == 19

    def test_clamp_page_size_max(self):
        p = PaginationParams(page_size=999)
        assert p.page_size == 100

    def test_clamp_page_min(self):
        p = PaginationParams(page=0)
        assert p.page == 1

    def test_clamp_page_size_min(self):
        p = PaginationParams(page_size=0)
        assert p.page_size == 1


class TestPaginate:
    def test_basic_pagination(self):
        items = list(range(50))
        result = paginate(items, page=1, page_size=10)
        assert result["total"] == 50
        assert len(result["items"]) == 10
        assert result["items"] == list(range(10))
        assert result["total_pages"] == 5

    def test_last_page(self):
        items = list(range(25))
        result = paginate(items, page=3, page_size=10)
        assert result["items"] == [20, 21, 22, 23, 24]
        assert result["total_pages"] == 3

    def test_empty_list(self):
        result = paginate([], page=1, page_size=10)
        assert result["items"] == []
        assert result["total"] == 0
        assert result["total_pages"] == 1

    def test_beyond_last_page(self):
        result = paginate([1, 2, 3], page=10, page_size=10)
        assert result["items"] == []


class TestMakePaginatedResult:
    def test_builds_result(self):
        result = make_paginated_result(["a", "b"], total=50, page=3, page_size=10)
        assert result["items"] == ["a", "b"]
        assert result["total"] == 50
        assert result["total_pages"] == 5
        assert result["page"] == 3
