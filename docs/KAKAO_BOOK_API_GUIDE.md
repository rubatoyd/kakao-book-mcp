# Kakao Daum 책 검색 REST Open API 개발자 가이드

이 문서는 카카오 디벨로퍼스에서 제공하는 **Daum 검색 > 책 검색 API**의 스펙, 파라미터 제약, 응답 구조 및 주의사항을 정리한 가이드입니다.

---

## 1. 개요 및 기본 정보

* **문서 공식 URL**: `https://developers.kakao.com/docs/ko/daum-search/dev-guide#search-book`
* **엔드포인트**: `GET https://dapi.kakao.com/v3/search/book`
* **인증 방식**: HTTP Header `Authorization: KakaoAK ${REST_API_KEY}`
  * 카카오 디벨로퍼스 [내 애플리케이션](https://developers.kakao.com)에서 앱 생성 후 **REST API 키**를 발급받아 사용합니다.
* **통신 포맷**: UTF-8 기반 JSON

---

## 2. 요청 파라미터 (Request Parameters)

| 파라미터 | 타입 | 필수 여부 | 기본값 | 설명 |
| :--- | :--- | :---: | :---: | :--- |
| **`query`** | `String` | **필수** | - | 검색 질의어 |
| **`sort`** | `String` | 선택 | `accuracy` | 결과 정렬 방식<br>• `accuracy` (정확도순)<br>• `latest` (발간일순) |
| **`page`** | `Integer` | 선택 | `1` | 결과 페이지 번호 (1 ~ 50) |
| **`size`** | `Integer` | 선택 | `10` | 한 페이지에 보여질 문서 수 (1 ~ 50) |
| **`target`** | `String` | 선택 | 전체 | 검색 필드 제한<br>• `title` (도서 제목)<br>• `isbn` (ISBN)<br>• `publisher` (출판사)<br>• `person` (인명 - 저자, 역자 등) |

---

## 3. 핵심 제약 및 상한 (API Cap)

> ⚠️ **조용한 절단(Quiet Truncation) 주의**:
> * 카카오 책 검색 API는 `page` 1~50, `size` 1~50을 지원합니다.
> * 즉, 단일 검색식으로 페이징을 통해 수집할 수 있는 이론적 최대 건수는 **2,500건(50 * 50)**입니다.
> * `total_count`가 2,500건을 넘어가거나 `pageable_count`가 `total_count`보다 작을 경우, 51페이지 이후 데이터는 API 상에서 조회할 수 없습니다.
> * 따라서 전수 조사가 필요하거나 대량의 데이터를 수집할 경우, `target` 필드를 좁히거나(예: 출판사별/저자별/연도별 세부 키워드 분할) 검색어를 구체화해야 합니다.

---

## 4. 응답 구조 (Response Structure)

### `meta` 객체
* `total_count` (Integer): 검색된 전체 문서 수
* `pageable_count` (Integer): 중복된 문서를 제외하고 실제로 노출 가능한 총 문서 수
* `is_end` (Boolean): 현재 페이지가 마지막 페이지인지 여부 (`true`이면 다음 페이지 없음)

### `documents` 배열 항목
| 필드 | 타입 | 설명 |
| :--- | :--- | :--- |
| `title` | `String` | 도서 제목 |
| `contents` | `String` | 도서 소개 요약 |
| `url` | `String` | Daum 책 상세 페이지 URL |
| `isbn` | `String` | ISBN10 / ISBN13 (공백으로 구분되어 제공) |
| `datetime` | `String` | 도서 출판일 (ISO 8601 형식: `YYYY-MM-DDThh:mm:ss.000+09:00`) |
| `authors` | `List<String>` | 저자 목록 |
| `publisher` | `String` | 출판사 |
| `translators` | `List<String>` | 번역자 목록 |
| `price` | `Integer` | 도서 정가 |
| `sale_price` | `Integer` | 도서 판매가 (-1인 경우 가격 정보 없음) |
| `thumbnail` | `String` | 도서 표지 미리보기 썸네일 이미지 URL |
| `status` | `String` | 도서 판매 상태 (예: 정상판매, 품절, 절판 등) |

---

## 5. 에러 코드 및 문제 해결

* **`400 Bad Request`**: 필수 파라미터(`query`) 누락 또는 허용 범위를 벗어난 `page` (> 50), `size` (> 50) 요청
* **`401 Unauthorized` / `403 Forbidden`**: 유효하지 않은 `Authorization: KakaoAK ...` 키 전달
* **`429 Too Many Requests`**: 쿼터 초과 (일일/초당 호출 제한 초과)
* **`500 / 502 / 503 Internal Server Error`**: 카카오 서버 일시 장애 (지수 백오프 재시도 필요)
