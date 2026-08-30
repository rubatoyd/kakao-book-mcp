"""카카오 Daum 책 검색 CLI — status / search / isbn / collect."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .client import KakaoBookClient, KakaoBookError
from .config import API_RECORD_CAP, get_api_key, redact
from .exporters import export


def _err(msg: str) -> int:
    print(f"오류: {msg}", file=sys.stderr)
    return 1


def cmd_status(args: argparse.Namespace) -> int:
    key = get_api_key()
    print(f"KAKAO_API_KEY: {'설정됨 ' + redact(key) if key else '미설정'}")
    if not key:
        return _err("인증키가 없습니다 — .env 또는 환경변수 KAKAO_API_KEY 를 설정하세요.")

    try:
        total, pageable, is_end, recs, _ = KakaoBookClient().search_page("도서", page=1, size=1)
    except KakaoBookError as e:
        return _err(f"연결 실패: {e}")

    print("카카오 Daum 책 검색 API: 정상")
    print(f"  시범 검색('도서') total_count = {total:,}건 / pageable_count = {pageable:,}건 / 반환 {len(recs)}건")
    print(f"  ※ 카카오 API는 페이징으로 최대 {API_RECORD_CAP:,}건(50페이지 * 50건)까지 수집할 수 있습니다.")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    if not get_api_key():
        return _err("KAKAO_API_KEY 미설정.")

    try:
        total, pageable, is_end, recs, _ = KakaoBookClient().search_page(
            query=args.query,
            target=args.target,
            sort=args.sort,
            page=args.page,
            size=args.size,
        )
    except KakaoBookError as e:
        return _err(f"검색 오류: {e}")

    if args.json:
        print(json.dumps({
            "total_count": total,
            "pageable_count": pageable,
            "page": args.page,
            "size": args.size,
            "is_end": is_end,
            "count": len(recs),
            "records": [r.to_row() for r in recs],
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"총 {total:,}건 (제공 가능 {pageable:,}건) 중 {len(recs)}건 (page {args.page})")
    if total > API_RECORD_CAP:
        print(f"⚠️ total_count가 API 상한({API_RECORD_CAP:,}건)을 초과합니다. 세부 검색어를 사용하세요.\n")

    for i, r in enumerate(recs, 1):
        price_str = f"{r.price:,}원" if r.price > 0 else "가격정보 없음"
        if r.sale_price > 0:
            disc = f" ({r.discount_rate}% 할인)" if r.discount_rate is not None else ""
            price_str += f" → {r.sale_price:,}원{disc}"

        print(f"[{i}] {r.title}")
        if r.authors:
            print(f"    저자: {r.authors}" + (f" | 역자: {r.translators}" if r.translators else ""))
        print(f"    출판: {r.publisher or '미상'} | {r.pub_date or r.pub_year or '연도미상'} | {r.status or '상태정보없음'}")
        print(f"    가격: {price_str}")
        meta_info = [x for x in (r.isbn13 and f"ISBN13 {r.isbn13}", r.isbn10 and f"ISBN10 {r.isbn10}") if x]
        if meta_info:
            print(f"    {' | '.join(meta_info)}")
        if r.contents:
            short_contents = r.contents[:100] + ("..." if len(r.contents) > 100 else "")
            print(f"    요약: {short_contents}")
        print()
    return 0


def cmd_isbn(args: argparse.Namespace) -> int:
    if not get_api_key():
        return _err("KAKAO_API_KEY 미설정.")

    client = KakaoBookClient()
    try:
        recs = client.search_isbn(args.isbn)
    except KakaoBookError as e:
        return _err(f"ISBN 조회 오류: {e}")

    if not recs:
        print(f"ISBN '{args.isbn}' 에 해당하는 도서를 찾을 수 없습니다.")
        return 0

    if args.json:
        print(json.dumps([r.to_row() for r in recs], ensure_ascii=False, indent=2))
        return 0

    for i, r in enumerate(recs, 1):
        print(f"[{i}] {r.title}")
        print(f"    저자: {r.authors} | 출판: {r.publisher} ({r.pub_year})")
        print(f"    ISBN13: {r.isbn13} | ISBN10: {r.isbn10}")
        print(f"    정가: {r.price:,}원 | 판매가: {r.sale_price:,}원 | 상태: {r.status}")
        if r.url:
            print(f"    링크: {r.url}")
        print()
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    if not get_api_key():
        return _err("KAKAO_API_KEY 미설정.")

    terms = args.terms or ([args.query] if args.query else [])
    if not terms:
        return _err("검색어가 없습니다 — --terms 또는 <query> 를 지정하세요.")

    client = KakaoBookClient()
    try:
        recs, meta = client.search_terms_meta(
            terms,
            target=args.target,
            sort=args.sort,
            max_records=args.max,
            year_from=args.year_from,
            year_to=args.year_to,
            min_price=args.min_price,
            max_price=args.max_price,
            status=args.status,
            contains=args.contains,
        )
    except KakaoBookError as e:
        return _err(f"수집 오류: {e}")

    print(f"수집 완료: 총 {len(recs)}건 (검색어 {len(terms)}개)")
    for a in meta.get("axes", []):
        flag = " ⚠️상한초과" if a.get("cap_hit") else ""
        print(f"  - [{a['term']}] total: {a['total_count']:,} / 회수: {a['fetched_count']:,} / 신규추가: {a['new_added']:,}{flag}")

    if meta.get("warning"):
        print(f"\n{meta['warning']}\n")

    fmts = args.format or ["xlsx", "csv", "json"]
    base_out = args.out or str(Path.cwd() / "output")
    base_name = args.name or f"kakao_book_{terms[0]}"

    if recs:
        saved = export(recs, fmts, base_out, base_name)
        print("\n저장된 파일:")
        for s in saved:
            print(f"  - {s}")
    else:
        print("\n조건에 일치하는 도서가 없어 파일을 생성하지 않았습니다.")

    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kbook",
        description="카카오 Daum 책 검색 Open API CLI 도구",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # status
    sub.add_parser("status", help="인증키 및 API 연결 상태 점검").set_defaults(func=cmd_status)

    # search
    s = sub.add_parser("search", help="도서 검색")
    s.add_argument("query", help="검색어")
    s.add_argument("--target", choices=["title", "isbn", "publisher", "person"], help="검색 대상 필드")
    s.add_argument("--sort", choices=["accuracy", "latest"], default="accuracy", help="정렬 방식")
    s.add_argument("--page", type=int, default=1, help="페이지 번호 (1~50)")
    s.add_argument("--size", type=int, default=10, help="페이지당 건수 (1~50)")
    s.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    s.set_defaults(func=cmd_search)

    # isbn
    ib = sub.add_parser("isbn", help="ISBN 전용 조회")
    ib.add_argument("isbn", help="ISBN (10자리 또는 13자리)")
    ib.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    ib.set_defaults(func=cmd_isbn)

    # collect
    c = sub.add_parser("collect", help="도서 대량 수집 및 파일 저장")
    c.add_argument("query", nargs="?", help="기본 검색어")
    c.add_argument("--terms", nargs="+", help="복수 검색어 리스트")
    c.add_argument("--target", choices=["title", "isbn", "publisher", "person"], help="검색 대상 필드")
    c.add_argument("--sort", choices=["accuracy", "latest"], default="accuracy", help="정렬 방식")
    c.add_argument("--max", type=int, default=50, help="검색어당 최대 수집 건수 (기본 50)")
    c.add_argument("--year-from", help="출판연도 시작 (YYYY)")
    c.add_argument("--year-to", help="출판연도 종료 (YYYY)")
    c.add_argument("--min-price", type=int, help="최소 가격 (원)")
    c.add_argument("--max-price", type=int, help="최대 가격 (원)")
    c.add_argument("--status", help="도서 상태 (예: 정상판매, 품절)")
    c.add_argument("--contains", nargs="+", help="포함 필수 키워드")
    c.add_argument("--format", nargs="+", default=["xlsx", "csv", "json"], help="저장 포맷 (xlsx csv json sqlite)")
    c.add_argument("--out", help="출력 디렉터리 (기본: ./output)")
    c.add_argument("--name", help="출력 파일 기본 이름")
    c.set_defaults(func=cmd_collect)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
