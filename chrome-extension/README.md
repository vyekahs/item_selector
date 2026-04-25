# itemSelector — 상세페이지 생성기 (Chrome Extension)

1688 / 타오바오 / 티몰 상품 페이지에 floating 버튼을 주입해서, 상품 데이터를
itemSelector 백엔드 (`POST /detail-pages/ingest`) 로 한 번의 클릭으로 전송한다.

> Phase 3 Module E. Manifest V3 기반 vanilla JS — 빌드 도구 없음.

## 디렉터리 구조

```
chrome-extension/
├── manifest.json       — Manifest V3 정의
├── content.js          — 1688/타오바오 페이지에서 DOM 파싱 + 버튼 주입
├── background.js       — service worker, 백엔드 fetch (basic auth 부착)
├── popup.html / .css / .js  — 백엔드 URL + 자격증명 설정 UI
├── icons/              — placeholder 아이콘 16/48/128px
├── README.md           — 이 파일
└── tests.md            — 수동 검증 절차
```

## 설치 (개발자 모드)

1. 크롬에서 `chrome://extensions` 열기
2. 우측 상단 **개발자 모드** 토글 ON
3. **압축해제된 확장 프로그램을 로드합니다** 클릭
4. 이 디렉터리 (`chrome-extension/`) 선택
5. 좌측 상단 도구모음에 itemSelector 아이콘이 나타나면 성공

## 첫 실행 설정

1. 도구모음의 itemSelector 아이콘 클릭 → 팝업 열기
2. 입력
   - **백엔드 base URL**: 예) `https://itemselector.mooo.com/api`
     - 끝의 `/` 는 자동 제거
     - 로컬 개발은 `http://localhost:8000` (Caddy 우회 시 basic auth 불필요)
   - **사용자명 / 비밀번호**: Caddy basic_auth 자격증명 (현재 배포 기준 `arang` / 설정값)
3. **💾 저장** → 자격증명이 `chrome.storage.sync` 에 저장됨
4. **🩺 연결 테스트** → `GET /detail-pages?limit=1` 호출. `✅ 200 OK` 가 뜨면 OK
   - `❌ 401` → 자격증명 오류
   - `❌ HTTP 404` → backendUrl 의 prefix (`/api` 등) 누락 가능성
   - `❌ fetch 실패` → URL 오타 또는 백엔드 다운

## 사용법

1. 1688 (`https://detail.1688.com/...`) / 타오바오 (`https://item.taobao.com/...`)
   / 티몰 (`https://detail.tmall.com/...`) 상품 페이지 이동
2. 우측 상단의 **🎨 상세페이지 생성** 버튼 클릭
3. 버튼 아래 상태 표시 확인:
   - `⏳ 전송 중…` → 파싱 + POST 진행
   - `✅ 등록됨 (id #N)` → 성공. 백엔드가 백그라운드에서 LLM + 렌더 진행
   - `❌ 실패: <reason>` → 사유 확인 후 재시도
4. 결과는 frontend (`/detail-pages`) 에서 확인

## 알려진 한계

- **DOM 셀렉터 취약성**: 1688/타오바오 사이트 업데이트 시 셀렉터가 깨질 수 있음.
  사용자가 직접 `content.js` 의 `parse1688()` / `parseTaobao()` 함수 안의 셀렉터
  배열을 수정할 수 있도록 모든 추출 로직은 try/catch + fallback 패턴으로 작성됨.
  주요 필드 (title, mainImages, specs 등) 는 여러 셀렉터를 순차 시도.
- **`host_permissions: ["<all_urls>"]`**: MVP 편의를 위해 모든 호스트 권한을 요청.
  Production 배포 시에는 `["https://*.1688.com/*", "https://*.taobao.com/*",
  "https://*.tmall.com/*", "<자기 백엔드 URL>"]` 로 좁히는 것이 좋음.
- **이미지 URL 정규화**: `//img...` 같은 schemeless URL 은 `https:` 로 자동 보정.
  1688 의 `_60x60.jpg` 썸네일은 원본으로 업그레이드 시도.
- **placeholder 아이콘**: `icons/icon{16,48,128}.png` 는 단색+점 placeholder.
  실제 아이덴티티 아이콘이 준비되면 같은 경로로 덮어쓰기.
- **Tmall 페이지의 `source_platform`**: 백엔드 schema 가 `Literal['1688','taobao']`
  만 허용해서 tmall 도 `'taobao'` 로 보냄. 분리 필요 시 백엔드 schema 와 같이 확장.

## Troubleshooting

### CORS 오류
- **content script → background**: Chrome 메시지 채널이라 CORS 무관.
- **background → 백엔드**: `host_permissions` 가 적용되어 CORS 우회됨.
- **popup 의 fetch (현재 코드는 background 경유)**: popup → SW → fetch 흐름이라 OK.
- 그래도 CORS 오류가 보이면 백엔드 `API_CORS_ORIGINS` 에
  `chrome-extension://<extension-id>` 추가 또는 `*` 임시 허용 후 디버그.

### 401 Unauthorized
- 팝업의 사용자명/비밀번호가 Caddy basic_auth 와 정확히 일치하는지 확인.
- 비밀번호에 특수문자가 있다면 그대로 입력 (자동 인코딩됨).

### 버튼이 보이지 않음
- 페이지 URL 이 manifest 의 `content_scripts.matches` 와 일치하는지 확인.
- DevTools console 에 `[itemSelector]` 로그가 있는지 확인.
- 다른 확장이 `z-index` 충돌을 일으킬 수 있음 — 이 확장은 `2147483647` (max int32) 사용.

### "메인 이미지를 찾지 못했습니다"
- 페이지가 lazy-load 중일 수 있음. 잠시 기다린 후 재시도하거나 스크롤 다운.
- 셀렉터가 깨졌다면 DevTools 로 main-image element 구조를 확인 후 `content.js`
  `parse1688().mainImages` 또는 `parseTaobao().mainImages` 의 셀렉터 배열에 추가.

### "전송 중" 에서 멈춤
- background service worker 가 idle 후 종료된 후 재시작될 수 있음.
- `chrome://extensions` → 이 확장의 **service worker** 링크 클릭 → console 확인.

## 개발자 노트

- 빌드 단계 없음. 파일 수정 후 `chrome://extensions` 의 새로고침 (⟳) 클릭만으로 반영.
- `manifest.json` 변경 시에는 반드시 새로고침 필요. content.js 만 수정하고 페이지를
  새로고침해도 적용됨.
- 백엔드 contract 가 바뀌면 `content.js` 의 `buildPayload()` 를 우선 수정. 필드명은
  `backend/app/schemas/requests/detail_page.py:IngestRequest` 와 1:1 매칭.
