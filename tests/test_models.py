"""Models and normalization tests."""
from __future__ import annotations

from kakao_book_mcp.models import (
    BookRecord,
    normalize_pub_year,
    parse_isbn,
)


def test_normalize_pub_year():
    assert normalize_pub_year("2014-11-17T00:00:00.000+09:00") == "2014"
    assert normalize_pub_year("2023-05-01") == "2023"
    assert normalize_pub_year("1998") == "1998"
    assert normalize_pub_year("invalid") == ""
    assert normalize_pub_year(None) == ""


def test_parse_isbn():
    # 10자리 + 13자리 결합
    isbn10, isbn13 = parse_isbn("8996991341 9788996991342")
    assert isbn10 == "8996991341"
    assert isbn13 == "9788996991342"

    # 하이픈 포함 13자리 단독
    isbn10, isbn13 = parse_isbn("978-89-969913-4-2")
    assert isbn10 == ""
    assert isbn13 == "9788996991342"

    # 10자리 단독
    isbn10, isbn13 = parse_isbn("8996991341")
    assert isbn10 == "8996991341"
    assert isbn13 == ""

    # 빈 값
    assert parse_isbn("") == ("", "")
    assert parse_isbn(None) == ("", "")


def test_book_record_from_api_dict():
    sample_doc = {
        "title": "미움받을 용기",
        "contents": "인간은 변할 수 있고 누구나 행복해질 수 있다.",
        "url": "https://search.daum.net/search?w=book&q=...",
        "isbn": "8996991341 9788996991342",
        "datetime": "2014-11-17T00:00:00.000+09:00",
        "authors": ["기시미 이치로", "고가 후미타케"],
        "publisher": "인플루엔셜",
        "translators": ["전경아"],
        "price": 14900,
        "sale_price": 13410,
        "thumbnail": "https://search1.kakaocdn.net/thumb/R120x174.q85/?fname=...",
        "status": "정상판매",
    }

    record = BookRecord.from_api_dict(sample_doc)
    assert record.title == "미움받을 용기"
    assert record.authors == "기시미 이치로, 고가 후미타케"
    assert record.translators == "전경아"
    assert record.publisher == "인플루엔셜"
    assert record.pub_year == "2014"
    assert record.pub_date == "2014-11-17"
    assert record.isbn10 == "8996991341"
    assert record.isbn13 == "9788996991342"
    assert record.price == 14900
    assert record.sale_price == 13410
    assert record.discount_rate == 10.0
    assert record.status == "정상판매"

    row = record.to_row()
    assert row["title"] == "미움받을 용기"
    assert row["authors"] == "기시미 이치로, 고가 후미타케"
    assert row["discount_rate"] == 10.0
