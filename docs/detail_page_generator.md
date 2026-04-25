# 상세페이지 자동 생성기 — 기획서

## 목표
1688/타오바오 상품 페이지에서 데이터를 추출 → LLM으로 한국어 카피 생성 →
한국 e-commerce 권장 규격(가로 860px) 상세페이지 이미지로 렌더링.

## 아키텍처 (3 layer)

```
┌────────────────────┐    ┌──────────────────────┐    ┌────────────────────┐
│ Chrome Extension   │───▶│ Backend (FastAPI)     │───▶│ Renderer            │
│  (1688/타오바오)    │POST│  - 데이터 정제         │    │  (Playwright)       │
│  - DOM 파싱         │    │  - Gemini 카피라이팅   │    │  - Jinja2 템플릿    │
│  - 이미지 URL 수집  │    │  - 이미지 다운로드     │    │  - 스크린샷 → JPG   │
└────────────────────┘    │  - DB 저장            │    │  - Sharp 최적화     │
                          └──────────────────────┘    └────────────────────┘
                                    │                            │
                                    ▼                            ▼
                          ┌──────────────────────┐    ┌────────────────────┐
                          │ Postgres              │    │ Docker volume       │
                          │  - detail_pages       │    │  /app/generated/    │
                          │  - source_products    │    │   {id}/page.jpg     │
                          └──────────────────────┘    └────────────────────┘
                                                                  │
                                                                  ▼
                                                       ┌────────────────────┐
                                                       │ Frontend (Next.js)  │
                                                       │  - 생성 폼           │
                                                       │  - 결과물 미리보기   │
                                                       │  - 다운로드 버튼     │
                                                       └────────────────────┘
```

## 데이터 흐름

### 1. Chrome Extension → Backend
```http
POST /detail-pages/ingest
{
  "source_url": "https://detail.1688.com/offer/...html",
  "source_platform": "1688",
  "title_zh": "...",
  "price_cny": 28.0,
  "category_path": ["...", "..."],
  "specs": {"무게": "0.5kg", "사이즈": "M/L"},
  "main_images": ["https://...jpg", ...],
  "detail_images": ["https://...jpg", ...],   # 상세설명용 (중국어 포함)
  "option_images": [{"name": "Red", "url": "..."}, ...]
}
→ {"id": 42, "status": "pending"}
```

### 2. Backend 가공 파이프라인 (백그라운드 태스크)
```
download_images   - source URLs를 로컬 캐시로 다운로드 (Pillow로 차원 검증)
detect_chinese    - OCR(Tesseract zh)로 중국어 비율 ≥30% 이미지는 detail에서 제외
copywrite_via_llm - Gemini에 (title_zh, category, specs) 입력 → 4개 산출:
                    {
                      "title_ko": "한국어 SEO 제목 (50자 이내)",
                      "highlight": "한 줄 후킹 카피",
                      "aida": {
                        "attention": "...",
                        "interest": "...",
                        "desire": "...",
                        "action": "..."
                      },
                      "spec_table": [{"label": "...", "value": "..."}, ...]
                    }
build_props       - 위 결과를 템플릿에 넣을 dict로 변환
```

### 3. Renderer
- Jinja2가 `templates/detail_page_v1.html`에 props 바인딩 → 메모리 HTML
- Playwright headless Chromium이 HTML 로드 → 가로 860px 고정 → 전체 높이 스크린샷
- Sharp(Pillow) → JPG 80% quality, max 2MB
- `/app/generated/{detail_page_id}/page.jpg` 저장

## DB 스키마

### `source_products`
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | bigserial PK | |
| source_url | text unique | 1688/타오바오 URL |
| source_platform | varchar(16) | '1688', 'taobao' |
| raw_payload | jsonb | extension이 보낸 원본 JSON |
| created_at | timestamptz | |

### `detail_pages`
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | bigserial PK | |
| source_product_id | bigint FK | source_products.id |
| status | varchar(16) | pending/processing/done/failed |
| title_ko | varchar(200) | LLM 생성 제목 |
| props | jsonb | 템플릿 바인딩 데이터 (AIDA, spec, image paths) |
| image_path | varchar(255) | 최종 JPG 상대경로 |
| failure_reason | text | |
| created_at, updated_at | | |

## API 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| POST | `/detail-pages/ingest` | Extension에서 호출. raw 데이터 저장 + 백그라운드 가공 트리거 |
| GET | `/detail-pages` | 페이지네이션 목록 |
| GET | `/detail-pages/{id}` | 상세 (status, image_path 등) |
| POST | `/detail-pages/{id}/regenerate` | 가공 재실행 |
| GET | `/generated/{id}/page.jpg` | 정적 이미지 서빙 (또는 nginx 직접) |

## 파일 구조 (병렬 작업 분배 단위)

```
backend/
  app/
    models/
      source_product.py       ─┐ Module A (DB)
      detail_page.py          ─┘
    routers/
      detail_pages.py         ─── Module B (API)
    services/
      detail_pages/
        ingest.py             ─┐ Module C (가공 파이프라인)
        copywriter.py         ─┤    - Gemini 통합
        renderer.py           ─┤    - Playwright 호출
        image_processor.py    ─┘    - OCR + Sharp
    clients/
      gemini.py               ─── Module C (LLM client)
  templates/
    detail_page_v1.html       ─── Module D (HTML 템플릿)
    detail_page_v1.css        ─┘
  alembic/versions/
    0015_detail_pages.py      ─── Module A

chrome-extension/             ─── Module E (확장)
  manifest.json
  content.js                  - 1688/타오바오 DOM 파싱
  background.js               - 백엔드 POST
  popup.html                  - 설정 (백엔드 URL 등)

frontend/
  app/
    detail-pages/page.tsx     ─── Module F (UI)
    detail-pages/[id]/page.tsx
  components/
    DetailPageList.tsx
    DetailPagePreview.tsx
  lib/api/
    detail_pages.ts
```

## 병렬 작업 모듈 (서브 에이전트 1개씩 할당)

| 모듈 | 범위 | 의존성 | 산출물 |
|---|---|---|---|
| **A: DB schema** | source_products + detail_pages 모델/마이그레이션 | 없음 | model 파일 + 0015 마이그레이션 |
| **B: API endpoints** | `/detail-pages/*` 라우터 + 스키마 | A | router + Pydantic 스키마 |
| **C: 가공 파이프라인** | Gemini + OCR + 이미지 다운로드 + Playwright 호출 | A | services/ 하위 + clients/gemini.py |
| **D: HTML 템플릿** | Jinja2 + CSS, props 계약 정의 | (없음, mock data로 작업) | templates/ + 샘플 JPG |
| **E: Chrome Extension** | manifest v3 + 1688/타오바오 파서 | API 계약(B) 확정 후 | chrome-extension/ 하위 |
| **F: Frontend UI** | 목록/미리보기/재생성 페이지 | API 계약(B) 확정 후 | app/detail-pages/* + components |

## 스코프 결정 사항 요약
- LLM: Gemini (`GOOGLE_TRANSLATE_API_KEY` 재사용 가능, 단 Generative Language API 별도 enable 필요)
- 렌더러: Python Playwright (Pip install로 백엔드 컨테이너에 추가, +250MB)
- OCR: Tesseract zh (apt install로 백엔드 이미지에 포함)
- 저장: Docker volume `generated_pages:/app/generated`
- 인증: Caddy basic_auth로 보호 (현재와 동일)

## Phase별 우선순위
- **Phase 1 (이번 작업)**: A + B + C + D (백엔드 풀스택, 사용자가 JSON 직접 POST하면 동작)
- **Phase 2**: F (프론트 UI — 수동 입력 폼 + 결과 보기)
- **Phase 3**: E (Chrome Extension)
- **Phase 4**: 템플릿 다양화, 이미지 마스킹/리사이징 고도화

## 보류된 결정
- 템플릿 다국어 (지금은 한국어만)
- 다중 템플릿 (Phase 4)
- 가격/마진 자동 적용 (이미 있는 calculator와 통합 여부)
