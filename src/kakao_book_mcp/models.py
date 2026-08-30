"""카카오 Daum 책 검색 데이터 모델 및 정규화 스키마."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

COLUMNS = [
    "source", "title", "authors", "publisher", "translators",
    "pub_year", "pub_date", "price", "sale_price", "discount_rate",
    "status", "isbn", "isbn10", "isbn13", "url", "thumbnail", "contents"
]

_DIGITS = re.compile(r"\D")


def normalize_pub_year(datetime_str: str | None) -> str:
    """ISO 8601 출판일 문자열에서 4자리 연도를 추출한다."""
    if not datetime_str:
        return ""
    s = str(datetime_str).strip()
    match = re.search(r"\b(19\d\d|20\d\d)\b", s)
    if match:
        return match.group(1)
    digits = _DIGITS.sub("", s)[:4]
    if len(digits) == 4 and 1000 <= int(digits) <= 2100:
        return digits
    return ""


def parse_isbn(isbn_str: str | None) -> tuple[str, str]:
    """공백 또는 기타 구분자로 결합된 ISBN 문자열에서 (isbn10, isbn13)을 분리 추출한다."""
    if not isbn_str:
        return "", ""
    tokens = [t.strip().replace("-", "") for t in re.split(r"[\s,]+", str(isbn_str)) if t.strip()]
    isbn10 = ""
    isbn13 = ""
    for token in tokens:
        if len(token) == 10 and not isbn10:
            isbn10 = token
        elif len(token) == 13 and not isbn13:
            isbn13 = token
    # 토큰 중 정확한 길이가 안 맞더라도 남는 것 할당
    if not isbn10 and not isbn13 and tokens:
        if len(tokens[0]) >= 13:
            isbn13 = tokens[0]
        else:
            isbn10 = tokens[0]
    return isbn10, isbn13


@dataclass
class BookRecord:
    """카카오 Daum 책 검색 결과 도서 1건 (정규화)."""

    source: str = "kakao_book"
    title: str = ""
    contents: str = ""
    url: str = ""
    isbn: str = ""
    isbn10: str = ""
    isbn13: str = ""
    pub_date: str = ""
    pub_year: str = ""
    authors: str = ""
    authors_list: list[str] = field(default_factory=list)
    publisher: str = ""
    translators: str = ""
    translators_list: list[str] = field(default_factory=list)
    price: int = 0
    sale_price: int = -1
    discount_rate: float | None = None
    thumbnail: str = ""
    status: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api_dict(cls, data: dict[str, Any]) -> BookRecord:
        raw_authors = data.get("authors") or []
        authors_list = [str(a).strip() for a in raw_authors if str(a).strip()]
        authors_str = ", ".join(authors_list)

        raw_translators = data.get("translators") or []
        translators_list = [str(t).strip() for t in raw_translators if str(t).strip()]
        translators_str = ", ".join(translators_list)

        raw_isbn = str(data.get("isbn") or "").strip()
        isbn10, isbn13 = parse_isbn(raw_isbn)

        raw_dt = str(data.get("datetime") or "").strip()
        pub_year = normalize_pub_year(raw_dt)
        pub_date = raw_dt[:10] if len(raw_dt) >= 10 else raw_dt

        price = int(data.get("price") or 0)
        sale_price = int(data.get("sale_price") or -1)
        discount_rate = None
        if price > 0 and 0 <= sale_price < price:
            discount_rate = round((price - sale_price) / price * 100, 1)

        return cls(
            source="kakao_book",
            title=str(data.get("title") or "").strip(),
            contents=str(data.get("contents") or "").strip(),
            url=str(data.get("url") or "").strip(),
            isbn=raw_isbn,
            isbn10=isbn10,
            isbn13=isbn13,
            pub_date=pub_date,
            pub_year=pub_year,
            authors=authors_str,
            authors_list=authors_list,
            publisher=str(data.get("publisher") or "").strip(),
            translators=translators_str,
            translators_list=translators_list,
            price=price,
            sale_price=sale_price,
            discount_rate=discount_rate,
            thumbnail=str(data.get("thumbnail") or "").strip(),
            status=str(data.get("status") or "").strip(),
            raw=data,
        )

    def to_row(self) -> dict[str, Any]:
        """평탄화된 표 한 행(dict) 반환."""
        return {
            "source": self.source,
            "title": self.title,
            "authors": self.authors,
            "publisher": self.publisher,
            "translators": self.translators,
            "pub_year": self.pub_year,
            "pub_date": self.pub_date,
            "price": self.price,
            "sale_price": self.sale_price,
            "discount_rate": self.discount_rate if self.discount_rate is not None else "",
            "status": self.status,
            "isbn": self.isbn,
            "isbn10": self.isbn10,
            "isbn13": self.isbn13,
            "url": self.url,
            "thumbnail": self.thumbnail,
            "contents": self.contents,
        }
