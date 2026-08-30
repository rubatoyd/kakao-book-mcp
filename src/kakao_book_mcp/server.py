"""카카오 Daum 책 검색 MCP 서버 (FastMCP).

⚠️ FastMCP 호환을 위해 mcp>=1.2.0,<2 버전을 전제로 하며,
   모든 도구는 @_safe 데코레이터를 통해 어떤 예외도 JSON 직렬화 가능한 dict로 안전하게 반환합니다.
"""
from __future__ import annotations

import argparse
import functools
import os
import sys
from pathlib import Path
from typing import Sequence

from mcp.server.fastmcp import FastMCP

from .client import KakaoBookClient, KakaoBookError
from .config import API_RECORD_CAP, get_api_key, redact
from .exporters import export

mcp = FastMCP("kakao_book")


def _safe(fn):
    """도구는 **항상 JSON 직렬화 가능한 dict** 를 반환 — 어떤 예외도 도구 밖으로 누수 금지."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            return {"error": f"{type(e).__name__}: {e}"}
    return wrapper


# MCP 안전성 어노테이션
_READ = {"readOnlyHint": True, "openWorldHint": True}
_WRITE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True}

_NO_KEY = {
    "error": "KAKAO_API_KEY 미설정 — 카카오 책 검색에는 REST API 키가 필요합니다.",
    "hint": "https://developers.kakao.com 에서 REST API 키를 발급받아 .env 또는 환경변수 KAKAO_API_KEY 로 설정하세요.",
}


@mcp.tool(annotations=_READ)
@_safe
def kakao_book_status() -> dict:
    """[연결 점검] 인증키 설정 여부 및 카카오 책 검색 API 실제 왕복 1회 테스트."""
    key = get_api_key()
    info: dict = {
        "has_api_key": key is not None,
        "api": "카카오 Daum 책 검색 (v3/search/book)",
        "api_record_cap": API_RECORD_CAP,
    }
    if not info["has_api_key"]:
        info["ok"] = False
        info["note"] = _NO_KEY["error"]
        info["hint"] = _NO_KEY["hint"]
        return info

    try:
        total, pageable, is_end, recs, _ = KakaoBookClient(api_key=key).search_page("도서", page=1, size=1)
        info["ok"] = True
        info["key_masked"] = redact(key)
        info["probe"] = {
            "query": "도서",
            "total_count": total,
            "pageable_count": pageable,
            "returned": len(recs),
        }
        info["note"] = "인증키 유효 — 카카오 책 검색 API 정상 작동 중."
    except KakaoBookError as e:
        info["ok"] = False
        info["note"] = str(e)
    return info


@mcp.tool(annotations=_READ)
@_safe
def kakao_book_search(
    query: str,
    target: str | None = None,
    sort: str = "accuracy",
    page: int = 1,
    size: int = 10,
) -> dict:
    """[도서 검색] 카카오 Daum 책 검색 API로 도서를 검색합니다.

    query: 검색을 원하는 질의어 (필수).
    target: 검색 필드 제한 (`title`: 제목, `isbn`: ISBN, `publisher`: 출판사, `person`: 인명/저자/역자). 기본값은 전체.
    sort: 정렬 방식 (`accuracy`: 정확도순, `latest`: 발간일순). 기본값: accuracy.
    page: 결과 페이지 번호 (1 ~ 50).
    size: 한 페이지에 보여질 문서 수 (1 ~ 50, 기본값 10).

    ⚠️ 카카오 API는 최대 50페이지 * 50건 = 2,500건까지만 페이징을 지원합니다.
       total_count가 2,500을 넘으면 `cap_hit=true`로 보고되며, 검색식을 세분화해야 합니다.
    """
    key = get_api_key()
    if key is None:
        return dict(_NO_KEY)

    try:
        total, pageable, is_end, recs, _ = KakaoBookClient(api_key=key).search_page(
            query=query,
            target=target,
            sort=sort,
            page=page,
            size=size,
        )
    except KakaoBookError as e:
        return {"error": str(e)}

    out = {
        "count": len(recs),
        "total_count": total,
        "pageable_count": pageable,
        "page": page,
        "size": size,
        "is_end": is_end,
        "truncated": bool(pageable) and (page * size) < pageable,
        "cap_hit": total > API_RECORD_CAP,
        "api_record_cap": API_RECORD_CAP,
        "records": [r.to_row() for r in recs],
    }

    if out["cap_hit"]:
        out["warning"] = (
            f"⚠️ 전체 검색 결과({total:,}건)가 카카오 API 페이징 한계({API_RECORD_CAP:,}건)를 초과합니다. "
            "검색어를 세분화하거나 target 필드를 지정하세요."
        )
    elif out["truncated"]:
        out["warning"] = (
            f"전체 {total:,}건(제공 가능 {pageable:,}건) 중 {page}페이지({len(recs)}건)만 반환되었습니다."
        )

    return out


@mcp.tool(annotations=_READ)
@_safe
def kakao_book_isbn(isbn: str) -> dict:
    """[ISBN 도서 조회] ISBN(10자리 또는 13자리, 하이픈 포함 가능)으로 도서를 조회합니다.

    isbn: 조회할 ISBN 문자열 (예: '9788996991342', '8996991341', 쉼표로 복수 지정 가능).
    """
    key = get_api_key()
    if key is None:
        return dict(_NO_KEY)

    client = KakaoBookClient(api_key=key)
    isbn_list = [t.strip() for t in isbn.split(",") if t.strip()]
    if not isbn_list:
        return {"error": "ISBN이 입력되지 않았습니다."}

    all_records = []
    for code in isbn_list:
        try:
            recs = client.search_isbn(code)
            all_records.extend(recs)
        except KakaoBookError as e:
            return {"error": f"ISBN {code} 조회 실패: {e}"}

    return {
        "query_isbns": isbn_list,
        "found_count": len(all_records),
        "records": [r.to_row() for r in all_records],
    }


@mcp.tool(annotations=_WRITE)
@_safe
def kakao_book_collect(
    terms: list[str] | str,
    target: str | None = None,
    sort: str = "accuracy",
    max_records: int = 50,
    year_from: str | None = None,
    year_to: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    status: str | None = None,
    contains: list[str] | str | None = None,
    formats: list[str] | None = None,
    out_dir: str | None = None,
    name: str | None = None,
) -> dict:
    """[도서 대량 수집 및 내보내기] 여러 검색어/필터 조건으로 도서를 자동 페이징 수집하고 중복 제거 후 로컬 파일로 저장합니다.

    terms: 검색어 단일 문자열 또는 문자열 리스트 (예: ['인공지능', '머신러닝']).
    target: 검색 대상 필드 (`title`, `isbn`, `publisher`, `person`, 기본값: 전체).
    sort: 정렬 방식 (`accuracy`, `latest`).
    max_records: 검색어당 최대 수집 건수 (기본 50, 최대 2500).
    year_from / year_to: 출판연도 필터 (YYYY 형식, 클라이언트 후처리).
    min_price / max_price: 가격 범위 필터 (원 단위, 클라이언트 후처리).
    status: 도서 상태 필터 (예: '정상판매', '품절', '절판').
    contains: 본문/제목/저자/출판사에 반드시 포함되어야 할 추가 키워드.
    formats: 저장할 파일 포맷 리스트 (['xlsx', 'csv', 'json', 'sqlite'], 기본값: ['xlsx', 'csv', 'json']).
    out_dir: 저장할 폴더 경로 (기본값: ./output).
    name: 파일 기본 이름 (기본값: 첫 검색어 기준 자동 생성).
    """
    key = get_api_key()
    if key is None:
        return dict(_NO_KEY)

    term_list = [terms] if isinstance(terms, str) else list(terms)
    if not term_list:
        return {"error": "검색어(terms)가 지정되지 않았습니다."}

    client = KakaoBookClient(api_key=key)
    try:
        recs, meta = client.search_terms_meta(
            term_list,
            target=target,
            sort=sort,
            max_records=max_records,
            year_from=year_from,
            year_to=year_to,
            min_price=min_price,
            max_price=max_price,
            status=status,
            contains=contains,
        )
    except KakaoBookError as e:
        return {"error": str(e)}

    base_out = out_dir or str(Path.cwd() / "output")
    base_name = name or f"kakao_book_{term_list[0]}"
    fmts = formats or ["xlsx", "csv", "json"]

    created_files = []
    if recs:
        created_files = export(recs, fmts, base_out, base_name)

    return {
        "total_collected": len(recs),
        "terms": term_list,
        "meta": meta,
        "saved_files": created_files,
        "sample_preview": [r.to_row() for r in recs[:5]],
    }


def main():
    """MCP 서버 실행 진입점."""
    parser = argparse.ArgumentParser(description="Kakao Daum Book Search MCP Server")
    parser.parse_args()
    mcp.run()


if __name__ == "__main__":
    main()
