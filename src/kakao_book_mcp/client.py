"""카카오 Daum 책 검색 API 클라이언트."""
from __future__ import annotations

import re
import time
from typing import Any, Sequence

import requests

from .config import (
    API_RECORD_CAP,
    BOOK_SEARCH_API_URL,
    MAX_PAGE,
    MAX_PAGE_SIZE,
    SORT_OPTIONS,
    TARGET_FIELDS,
    require_api_key,
    use_os_trust,
)
from .models import BookRecord


class KakaoBookError(RuntimeError):
    """카카오 책 검색 API 호출/응답 오류. 메시지에 인증키가 노출되지 않는다."""


class KakaoBookClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        throttle: float = 0.2,
        timeout: int = 30,
    ):
        use_os_trust()
        self.api_key = api_key or require_api_key()
        self.throttle = throttle
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"KakaoAK {self.api_key}",
            "User-Agent": "Mozilla/5.0 (compatible; kakao-book-mcp)",
            "Accept": "application/json",
        })

    # ── 저수준 호출 ───────────────────────────────────────────────────────────
    def _call(self, params: dict[str, Any]) -> dict[str, Any]:
        """GET 1회 요청(재시도 및 지수 백오프 포함). 인증키 누출 방지."""
        query = {k: v for k, v in params.items() if v not in (None, "")}
        last_exc: Exception | None = None
        r = None

        for attempt in range(3):
            if attempt > 0:
                time.sleep(1.0 * (2 ** (attempt - 1)))
            try:
                r = self.session.get(
                    BOOK_SEARCH_API_URL,
                    params=query,
                    timeout=self.timeout,
                )
            except requests.exceptions.RequestException as e:
                last_exc = e
                continue

            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                continue
            break

        if r is None:
            raise KakaoBookError(
                f"네트워크 오류({type(last_exc).__name__}) — dapi.kakao.com 연결을 확인하세요."
            )

        if r.status_code == 401 or r.status_code == 403:
            raise KakaoBookError(
                f"인증 실패(HTTP {r.status_code}) — 카카오 REST API 키가 유효하지 않거나 권한이 없습니다."
            )
        if r.status_code == 429:
            raise KakaoBookError("요청 한도 초과(HTTP 429) — 일일/분당 쿼터를 확인하거나 잠시 후 재시도하세요.")
        if r.status_code >= 400:
            msg = r.text
            try:
                err_json = r.json()
                msg = err_json.get("message") or err_json.get("errorType") or msg
            except Exception:
                pass
            raise KakaoBookError(f"HTTP {r.status_code} 카카오 API 오류: {msg}")

        try:
            data = r.json()
        except Exception as e:
            raise KakaoBookError(f"JSON 파싱 실패: {e}") from e

        if not isinstance(data, dict):
            raise KakaoBookError(f"예상치 못한 응답 형식: {type(data)}")

        return data

    # ── 단일 페이지 검색 ──────────────────────────────────────────────────────
    def search_page(
        self,
        query: str,
        *,
        target: str | None = None,
        sort: str | None = None,
        page: int = 1,
        size: int = 10,
    ) -> tuple[int, int, bool, list[BookRecord], dict[str, Any]]:
        """1개 페이지 검색.

        반환: (total_count, pageable_count, is_end, records, meta)
        """
        q = (query or "").strip()
        if not q:
            raise KakaoBookError("검색어(query)가 비어 있습니다.")

        params: dict[str, Any] = {
            "query": q,
            "page": max(1, min(int(page), MAX_PAGE)),
            "size": max(1, min(int(size), MAX_PAGE_SIZE)),
        }
        if target and target.strip().lower() in TARGET_FIELDS:
            params["target"] = target.strip().lower()
        if sort and sort.strip().lower() in SORT_OPTIONS:
            params["sort"] = sort.strip().lower()

        data = self._call(params)
        meta = data.get("meta") or {}
        docs = data.get("documents") or []

        total_count = int(meta.get("total_count") or 0)
        pageable_count = int(meta.get("pageable_count") or 0)
        is_end = bool(meta.get("is_end", False))

        records = [BookRecord.from_api_dict(doc) for doc in docs if isinstance(doc, dict)]
        return total_count, pageable_count, is_end, records, meta

    # ── ISBN 전용 조회 ────────────────────────────────────────────────────────
    def search_isbn(self, isbn: str) -> list[BookRecord]:
        """ISBN으로 책을 검색한다."""
        clean_isbn = re.sub(r"[^\dX]", "", str(isbn or "").upper())
        if not clean_isbn:
            return []
        _, _, _, records, _ = self.search_page(clean_isbn, target="isbn", size=10)
        return records

    # ── 메타데이터 및 다중 페이지 수집 ────────────────────────────────────────
    def search_meta(
        self,
        query: str,
        *,
        target: str | None = None,
        sort: str | None = None,
        max_records: int = 50,
        year_from: str | None = None,
        year_to: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        status: str | None = None,
        contains: str | Sequence[str] | None = None,
    ) -> tuple[list[BookRecord], dict[str, Any]]:
        """페이징을 순회하며 조건에 맞는 도서 수집 및 절단/상한 메타데이터 산출."""
        q = (query or "").strip()
        if not q:
            return [], {"total_count": 0, "pageable_count": 0, "fetched_count": 0, "returned_count": 0}

        target_count = max(1, min(int(max_records), API_RECORD_CAP))
        page_size = MAX_PAGE_SIZE

        collected_map: dict[str, BookRecord] = {}
        total_count = 0
        pageable_count = 0
        stopped_reason = "exhausted"
        requests_count = 0

        for p in range(1, MAX_PAGE + 1):
            if len(collected_map) >= target_count:
                stopped_reason = "max_records"
                break

            if requests_count > 0 and self.throttle > 0:
                time.sleep(self.throttle)

            requests_count += 1
            tot, pageable, is_end, recs, _ = self.search_page(
                q, target=target, sort=sort, page=p, size=page_size
            )
            if p == 1:
                total_count = tot
                pageable_count = pageable

            if not recs:
                stopped_reason = "empty_page"
                break

            for r in recs:
                # 중복 제거 키: isbn13 > isbn10 > isbn > (title, publisher)
                dedup_key = r.isbn13 or r.isbn10 or r.isbn or f"{r.title}_{r.publisher}"
                if dedup_key not in collected_map:
                    collected_map[dedup_key] = r
                    if len(collected_map) >= target_count:
                        break

            if is_end:
                stopped_reason = "is_end"
                break

            if p == MAX_PAGE and not is_end:
                stopped_reason = "cap_hit"

        fetched_records = list(collected_map.values())
        filtered_records = self._apply_filters(
            fetched_records,
            year_from=year_from,
            year_to=year_to,
            min_price=min_price,
            max_price=max_price,
            status=status,
            contains=contains,
        )

        cap_hit = total_count > API_RECORD_CAP
        truncated = total_count > len(fetched_records)

        meta: dict[str, Any] = {
            "query": q,
            "target": target or "all",
            "sort": sort or "accuracy",
            "total_count": total_count,
            "pageable_count": pageable_count,
            "fetched_count": len(fetched_records),
            "returned_count": len(filtered_records),
            "truncated": truncated,
            "cap_hit": cap_hit,
            "api_record_cap": API_RECORD_CAP,
            "stopped_reason": stopped_reason,
            "requests_count": requests_count,
        }

        if cap_hit:
            meta["warning"] = (
                f"⚠️ 전체 검색 결과({total_count:,}건)가 카카오 API 최대 페이징 상한({API_RECORD_CAP:,}건)을 초과합니다. "
                "더 많은 자료를 수집하려면 검색어를 세분화하거나 target(title/person/publisher)을 지정하세요."
            )
        elif truncated and len(fetched_records) < pageable_count:
            meta["warning"] = (
                f"제공 가능한 {pageable_count:,}건 중 max_records({target_count}) 설정에 따라 "
                f"{len(fetched_records):,}건만 수집되었습니다."
            )

        return filtered_records, meta

    # ── 다중 검색어 일괄 수집 ────────────────────────────────────────────────
    def search_terms_meta(
        self,
        terms: Sequence[str],
        *,
        target: str | None = None,
        sort: str | None = None,
        max_records: int = 100,
        year_from: str | None = None,
        year_to: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        status: str | None = None,
        contains: str | Sequence[str] | None = None,
    ) -> tuple[list[BookRecord], dict[str, Any]]:
        """여러 검색어에 대한 합집합 수집."""
        union_map: dict[str, BookRecord] = {}
        axes_stats: list[dict[str, Any]] = []
        total_requests = 0

        clean_terms = [t.strip() for t in terms if t and t.strip()]
        for term in clean_terms:
            recs, meta = self.search_meta(
                term,
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
            total_requests += meta.get("requests_count", 0)
            new_added = 0
            for r in recs:
                dedup_key = r.isbn13 or r.isbn10 or r.isbn or f"{r.title}_{r.publisher}"
                if dedup_key not in union_map:
                    union_map[dedup_key] = r
                    new_added += 1

            axes_stats.append({
                "term": term,
                "total_count": meta["total_count"],
                "pageable_count": meta["pageable_count"],
                "fetched_count": meta["fetched_count"],
                "returned_count": meta["returned_count"],
                "new_added": new_added,
                "cap_hit": meta["cap_hit"],
            })

        all_records = list(union_map.values())
        overall_meta = {
            "terms": clean_terms,
            "axes": axes_stats,
            "total_unique_collected": len(all_records),
            "total_requests": total_requests,
        }
        return all_records, overall_meta

    # ── 클라이언트 측 후처리 필터 ───────────────────────────────────────────
    @staticmethod
    def _apply_filters(
        records: list[BookRecord],
        *,
        year_from: str | None = None,
        year_to: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        status: str | None = None,
        contains: str | Sequence[str] | None = None,
    ) -> list[BookRecord]:
        result = records

        if year_from:
            yf = str(year_from).strip()
            result = [r for r in result if r.pub_year and r.pub_year >= yf]

        if year_to:
            yt = str(year_to).strip()
            result = [r for r in result if r.pub_year and r.pub_year <= yt]

        if min_price is not None:
            result = [r for r in result if r.sale_price >= min_price or (r.sale_price < 0 and r.price >= min_price)]

        if max_price is not None:
            result = [r for r in result if (0 <= r.sale_price <= max_price) or (r.sale_price < 0 and r.price <= max_price)]

        if status:
            st = str(status).strip()
            result = [r for r in result if st in r.status]

        if contains:
            kw_list = [contains] if isinstance(contains, str) else list(contains)
            clean_kws = [k.strip().lower() for k in kw_list if k and k.strip()]
            if clean_kws:
                filtered = []
                for r in result:
                    search_text = f"{r.title} {r.contents} {r.authors} {r.publisher}".lower()
                    if all(k in search_text for k in clean_kws):
                        filtered.append(r)
                result = filtered

        return result
