"""Client HTTP and filtering tests with mock responses."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from kakao_book_mcp.client import KakaoBookClient, KakaoBookError
from kakao_book_mcp.models import BookRecord


@pytest.fixture
def mock_client():
    return KakaoBookClient(api_key="mock_kakao_key_12345", throttle=0.0)


def test_search_page_success(mock_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "meta": {"total_count": 150, "pageable_count": 120, "is_end": False},
        "documents": [
            {
                "title": "파이썬 프로그래밍",
                "contents": "파이썬 기초 가이드",
                "url": "https://example.com/book/1",
                "isbn": "9781111111111",
                "datetime": "2023-03-15T00:00:00.000+09:00",
                "authors": ["김철수"],
                "publisher": "IT출판사",
                "translators": [],
                "price": 25000,
                "sale_price": 22500,
                "thumbnail": "https://example.com/thumb.jpg",
                "status": "정상판매",
            }
        ],
    }

    with patch.object(mock_client.session, "get", return_value=mock_resp):
        total, pageable, is_end, recs, meta = mock_client.search_page(
            "파이썬", target="title", sort="accuracy", page=1, size=10
        )
        assert total == 150
        assert pageable == 120
        assert is_end is False
        assert len(recs) == 1
        assert recs[0].title == "파이썬 프로그래밍"
        assert recs[0].pub_year == "2023"


def test_search_isbn(mock_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "meta": {"total_count": 1, "pageable_count": 1, "is_end": True},
        "documents": [
            {
                "title": "클린 코드",
                "isbn": "9788966260959",
                "authors": ["로버트 C. 마틴"],
                "publisher": "인사이트",
            }
        ],
    }

    with patch.object(mock_client.session, "get", return_value=mock_resp):
        recs = mock_client.search_isbn("978-89-6626-095-9")
        assert len(recs) == 1
        assert recs[0].title == "클린 코드"


def test_search_meta_filtering_and_truncation(mock_client):
    # 1페이지 모의 응답
    mock_resp1 = MagicMock()
    mock_resp1.status_code = 200
    mock_resp1.json.return_value = {
        "meta": {"total_count": 3000, "pageable_count": 2500, "is_end": False},
        "documents": [
            {
                "title": "딥러닝 입문",
                "contents": "딥러닝 알고리즘 및 텐서플로",
                "isbn": "9781111111111",
                "datetime": "2021-01-01T00:00:00.000+09:00",
                "authors": ["이영희"],
                "publisher": "인공지능사",
                "price": 30000,
                "sale_price": 27000,
                "status": "정상판매",
            },
            {
                "title": "머신러닝 실전",
                "contents": "사이킷런 머신러닝",
                "isbn": "9782222222222",
                "datetime": "2019-05-01T00:00:00.000+09:00",
                "authors": ["박지성"],
                "publisher": "데이터북스",
                "price": 20000,
                "sale_price": 18000,
                "status": "정상판매",
            },
        ],
    }

    with patch.object(mock_client.session, "get", return_value=mock_resp1):
        # 2020년 이후 + '딥러닝' 포함 필터
        recs, meta = mock_client.search_meta(
            "인공지능",
            max_records=10,
            year_from="2020",
            contains="딥러닝",
        )
        assert len(recs) == 1
        assert recs[0].title == "딥러닝 입문"
        assert meta["cap_hit"] is True  # total_count(3000) > API_RECORD_CAP(2500)
        assert "warning" in meta


def test_auth_error(mock_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    with patch.object(mock_client.session, "get", return_value=mock_resp):
        with pytest.raises(KakaoBookError, match="인증 실패"):
            mock_client.search_page("테스트")
