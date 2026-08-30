"""FastMCP server tool execution and safety wrapper tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from kakao_book_mcp.server import (
    kakao_book_collect,
    kakao_book_isbn,
    kakao_book_search,
    kakao_book_status,
)


def test_status_without_key():
    with patch("kakao_book_mcp.server.get_api_key", return_value=None):
        res = kakao_book_status()
        assert res["has_api_key"] is False
        assert res["ok"] is False
        assert "KAKAO_API_KEY 미설정" in res["note"]


def test_status_with_valid_key():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "meta": {"total_count": 100, "pageable_count": 100, "is_end": True},
        "documents": [{"title": "도서", "isbn": "9781234567890"}],
    }

    with patch("kakao_book_mcp.server.get_api_key", return_value="dummy_kakao_key_12345"), \
         patch("kakao_book_mcp.client.requests.Session.get", return_value=mock_resp):
        res = kakao_book_status()
        assert res["has_api_key"] is True
        assert res["ok"] is True
        assert res["probe"]["query"] == "도서"


def test_search_tool_with_mock():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "meta": {"total_count": 50, "pageable_count": 50, "is_end": True},
        "documents": [
            {
                "title": "클린 아키텍처",
                "authors": ["로버트 C. 마틴"],
                "publisher": "인사이트",
                "price": 28000,
                "sale_price": 25200,
                "isbn": "9788966262472",
            }
        ],
    }

    with patch("kakao_book_mcp.server.get_api_key", return_value="dummy_key"), \
         patch("kakao_book_mcp.client.requests.Session.get", return_value=mock_resp):
        res = kakao_book_search(query="클린 아키텍처", target="title")
        assert res["count"] == 1
        assert res["total_count"] == 50
        assert res["records"][0]["title"] == "클린 아키텍처"


def test_isbn_tool_with_mock():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "meta": {"total_count": 1, "pageable_count": 1, "is_end": True},
        "documents": [{"title": "리팩터링 2판", "isbn": "9788966262533"}],
    }

    with patch("kakao_book_mcp.server.get_api_key", return_value="dummy_key"), \
         patch("kakao_book_mcp.client.requests.Session.get", return_value=mock_resp):
        res = kakao_book_isbn("978-89-6626-253-3")
        assert res["found_count"] == 1
        assert res["records"][0]["title"] == "리팩터링 2판"


def test_collect_tool_with_mock(tmp_path):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "meta": {"total_count": 1, "pageable_count": 1, "is_end": True},
        "documents": [
            {
                "title": "파이썬 클린코드",
                "isbn": "9788966262500",
                "price": 30000,
                "sale_price": 27000,
            }
        ],
    }

    with patch("kakao_book_mcp.server.get_api_key", return_value="dummy_key"), \
         patch("kakao_book_mcp.client.requests.Session.get", return_value=mock_resp):
        res = kakao_book_collect(
            terms=["파이썬"],
            formats=["json"],
            out_dir=str(tmp_path),
            name="test_out",
        )
        assert res["total_collected"] == 1
        assert len(res["saved_files"]) == 1


def test_safe_wrapper_catches_exception():
    with patch("kakao_book_mcp.server.get_api_key", return_value="dummy_key"), \
         patch("kakao_book_mcp.client.KakaoBookClient.search_page", side_effect=Exception("Critical Internal Failure")):
        res = kakao_book_search(query="테스트")
        assert "error" in res
        assert "Critical Internal Failure" in res["error"]
