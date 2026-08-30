"""GitHub 저장소 트래픽(조회수, 클론수, 릴리스 다운로드, 스타) 통계 자동 수집 및 README 업데이트."""
from __future__ import annotations

import csv
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "rubatoyd/kakao-book-mcp")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = Path(os.environ.get("USAGE_CSV", "docs/usage.csv"))

FIELDS = [
    "date", "views", "view_uniques", "clones", "clone_uniques",
    "release_downloads", "releases", "stars", "forks", "note"
]


def api(path: str = ""):
    """GitHub API GET 요청."""
    url = f"https://api.github.com/repos/{REPO}" + (f"/{path}" if path else "")
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "usage-recorder",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  !! {path} 실패 HTTP {e.code}", file=sys.stderr)
        return None
    except Exception as e:  # noqa: BLE001
        print(f"  !! {path} 실패 {type(e).__name__}", file=sys.stderr)
        return None


def load() -> dict[str, dict]:
    if not OUT.exists():
        return {}
    with OUT.open(encoding="utf-8") as f:
        return {row["date"]: row for row in csv.DictReader(f)}


README = Path(os.environ.get("USAGE_README", "README.md"))
CHART = Path(os.environ.get("USAGE_SVG", "docs/usage.svg"))
MARK_A, MARK_B = "<!-- usage:start -->", "<!-- usage:end -->"

_CLONE, _VIEW, _AXIS = "#3b82f6", "#f59e0b", "#8b949e"


def write_chart(rows: dict[str, dict]) -> bool:
    """일별 클론·조회 추이를 순수 SVG로 렌더링."""
    dates = sorted(rows)
    if len(dates) < 2:
        return False
    clones = [int(rows[d].get("clones") or 0) for d in dates]
    views = [int(rows[d].get("views") or 0) for d in dates]
    hi = max(max(clones), max(views), 1)

    W, H, PAD_L, PAD_B, PAD_T = 720, 200, 34, 26, 16
    iw, ih = W - PAD_L - 10, H - PAD_B - PAD_T

    def pts(vals):
        n = len(vals) - 1 or 1
        return " ".join(
            f"{PAD_L + i * iw / n:.1f},{PAD_T + ih - v * ih / hi:.1f}"
            for i, v in enumerate(vals)
        )

    ticks = "".join(
        f'<line x1="{PAD_L}" y1="{PAD_T + ih - f * ih:.1f}" x2="{W - 10}" '
        f'y2="{PAD_T + ih - f * ih:.1f}" stroke="{_AXIS}" stroke-opacity=".25"/>'
        f'<text x="{PAD_L - 6}" y="{PAD_T + ih - f * ih + 4:.1f}" font-size="10" '
        f'fill="{_AXIS}" text-anchor="end">{int(hi * f)}</text>'
        for f in (0, 0.5, 1)
    )
    xl = "".join(
        f'<text x="{PAD_L + i * iw / (len(dates) - 1):.1f}" y="{H - 8}" font-size="10" '
        f'fill="{_AXIS}" text-anchor="{a}">{dates[i][5:]}</text>'
        for i, a in ((0, "start"), (len(dates) // 2, "middle"), (len(dates) - 1, "end"))
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="-apple-system,Segoe UI,sans-serif" role="img" aria-label="일별 클론·조회 추이">
<title>일별 클론·조회 추이 ({dates[0]} ~ {dates[-1]})</title>
{ticks}{xl}
<polyline fill="none" stroke="{_CLONE}" stroke-width="2" points="{pts(clones)}"/>
<polyline fill="none" stroke="{_VIEW}" stroke-width="2" points="{pts(views)}"/>
<circle cx="{W - 150}" cy="12" r="4" fill="{_CLONE}"/>
<text x="{W - 140}" y="16" font-size="11" fill="{_AXIS}">clones</text>
<circle cx="{W - 78}" cy="12" r="4" fill="{_VIEW}"/>
<text x="{W - 68}" y="16" font-size="11" fill="{_AXIS}">views</text>
</svg>
"""
    CHART.parent.mkdir(parents=True, exist_ok=True)
    CHART.write_text(svg, encoding="utf-8")
    return True


def update_readme(rows: dict[str, dict], snap: dict, today: str) -> None:
    """README에 사용량 통계 표기 업데이트."""
    if not README.exists():
        return
    text = README.read_text(encoding="utf-8")
    if MARK_A not in text or MARK_B not in text:
        print(f"  (README에 {MARK_A} 마커가 없어 건너뜁니다)")
        return

    recent = sorted(rows)[-14:]

    def s(key: str) -> int:
        return sum(int(rows[d].get(key) or 0) for d in recent)

    dl = snap.get("release_downloads") or "0"
    chart = f"\n>\n> ![일별 클론·조회 추이]({CHART.as_posix()})\n" if write_chart(rows) else ""
    body = (
        f"> 📊 **사용량 통계** — 최근 14일 조회 **{s('views'):,}**회(순 {s('view_uniques'):,}) · "
        f"클론 **{s('clones'):,}**회(순 {s('clone_uniques'):,}) · "
        f"릴리스 다운로드 **{dl}**건"
        f"{chart}"
        f">\n> <sub>{today} 자동 집계됨 · 전체 이력 [`docs/usage.csv`](docs/usage.csv). "
        f"GitHub 트래픽 API 14일 창을 영구 보존합니다.</sub>"
    )

    head, rest = text.split(MARK_A, 1)
    _old, tail = rest.split(MARK_B, 1)
    README.write_text(f"{head}{MARK_A}\n{body}\n{MARK_B}{tail}", encoding="utf-8")
    print("  README 사용량 섹션 업데이트 완료")


def main() -> int:
    if not REPO or not TOKEN:
        print("GITHUB_REPOSITORY / GITHUB_TOKEN 환경변수가 필요합니다.", file=sys.stderr)
        return 1

    rows = load()
    before = len(rows)
    notes: list[str] = []

    def touch(d: str) -> dict:
        return rows.setdefault(d, {**{k: "" for k in FIELDS}, "date": d})

    # 트래픽 14일치 일별 조회 및 병합
    for kind, keys in (("views", ("views", "view_uniques")),
                       ("clones", ("clones", "clone_uniques"))):
        data = api(f"traffic/{kind}")
        if data is None:
            notes.append(f"{kind}:권한부족")
            continue
        for item in data.get(kind, []):
            d = item["timestamp"][:10]
            r = touch(d)
            r[keys[0]] = item["count"]
            r[keys[1]] = item["uniques"]

    # 오늘자 스냅샷
    today = datetime.now(timezone.utc).date().isoformat()
    snap = touch(today)

    rel = api("releases")
    if rel is not None:
        snap["release_downloads"] = sum(
            a.get("download_count", 0) for x in rel for a in x.get("assets", [])
        )
        snap["releases"] = len(rel)
    else:
        notes.append("releases:조회실패")

    meta = api("")
    if meta is not None:
        snap["stars"] = meta.get("stargazers_count", "")
        snap["forks"] = meta.get("forks_count", "")
    else:
        notes.append("repo:조회실패")

    snap["note"] = ";".join(notes)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for d in sorted(rows):
            w.writerow({k: rows[d].get(k, "") for k in FIELDS})

    update_readme(rows, snap, today)

    print(f"{REPO}: {before} -> {len(rows)}행 기록 ({OUT})")
    print(
        f"  오늘({today}) 스냅샷: 릴리스 다운로드 {snap['release_downloads']} · "
        f"스타 {snap['stars']} · 조회 {snap['views']} · 클론 {snap['clones']}"
    )
    if notes:
        print(f"  참고: {';'.join(notes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
