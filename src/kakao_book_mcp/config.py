"""환경설정 및 자격증명 로딩 — 카카오 Daum 책 검색 OpenAPI.

인증키는 코드/로그에 하드코딩하지 않고 `.env`(gitignore), OS 프로세스 환경변수,
또는 Windows 사용자/시스템 환경변수 레지스트리에서 읽는다.
`KAKAO_API_KEY`, `KAKAO_REST_API_KEY` 등의 환경변수를 지원한다.
"""
from __future__ import annotations

import os
import sys
from dotenv import load_dotenv

# .env 를 한 번 로드 (이미 설정된 환경변수는 덮어쓰지 않음)
load_dotenv(override=False)

BOOK_SEARCH_API_URL = os.environ.get(
    "KAKAO_BOOK_SEARCH_API_URL", "https://dapi.kakao.com/v3/search/book"
)
KAKAO_BASE_URL = os.environ.get("KAKAO_BASE_URL", "https://dapi.kakao.com")

# 카카오 책 검색 API 제약 조건
# page: 1 ~ 50, size: 1 ~ 50
# 따라서 한 검색식으로 수집 가능한 최대 누적 건수는 50 * 50 = 2,500건이다.
MAX_PAGE = 50
MAX_PAGE_SIZE = 50
API_RECORD_CAP = 2500

# 지원하는 검색 대상 (target)
TARGET_FIELDS = {"title", "isbn", "publisher", "person"}

# 지원하는 정렬 옵션 (sort)
SORT_OPTIONS = {"accuracy", "latest"}

_CANDIDATE_KEYS = [
    "KAKAO_API_KEY",
    "KAKAO_REST_API_KEY",
    "KAKAO_REST_KEY",
    "KAKAO_KEY",
    "KAKAO_APP_KEY",
]


def _get_from_windows_registry(var_name: str) -> str | None:
    """Windows 환경변수(HKCU / HKLM)에서 직접 키를 조회 (터미널 미재시작 대비)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        for root, subkey in [
            (winreg.HKEY_CURRENT_USER, r"Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        ]:
            try:
                with winreg.OpenKey(root, subkey) as k:
                    val, _ = winreg.QueryValueEx(k, var_name)
                    if val and str(val).strip():
                        return str(val).strip()
            except Exception:
                continue
    except Exception:
        pass
    return None


def get_api_key() -> str | None:
    """환경변수, .env 또는 Windows 사용자 환경변수에서 Kakao REST API Key 를 가져온다."""
    for c in _CANDIDATE_KEYS:
        val = os.environ.get(c)
        if val and val.strip():
            return val.strip()

    for c in _CANDIDATE_KEYS:
        val = _get_from_windows_registry(c)
        if val and val.strip():
            # 프로세스 캐싱을 위해 os.environ 에도 보관
            os.environ["KAKAO_API_KEY"] = val.strip()
            return val.strip()

    return None


def require_api_key() -> str:
    """인증키가 반드시 필요할 때 호출. 없으면 사용자 친화적 에러 발생."""
    key = get_api_key()
    if not key:
        raise RuntimeError(
            "KAKAO_API_KEY 미설정 — 카카오 책 검색에는 REST API 키가 필요합니다.\n"
            "https://developers.kakao.com 에서 앱 생성 후 REST API 키를 발급받아 "
            ".env 또는 환경변수 KAKAO_API_KEY 로 설정하세요."
        )
    return key


def redact(key: str | None, keep: int = 4) -> str:
    """인증키를 로그나 화면에 안전하게 마스킹하여 표시한다."""
    if not key:
        return "None"
    k = key.strip()
    if len(k) <= keep * 2:
        return "***"
    return f"{k[:keep]}...{k[-keep:]}"


def use_os_trust() -> None:
    """사내망/교육망 SSL 인터셉션 대응을 위해 OS 신뢰 저장소를 활성화한다."""
    flag = os.environ.get("KAKAO_OS_TRUST", "1").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        try:
            import truststore
            truststore.inject_into_ssl()
        except Exception:
            pass
