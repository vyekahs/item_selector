# 수동 검증 절차

자동 테스트 없음 (Chrome 확장은 실제 브라우저 + 실제 사이트 DOM 의존).
아래 체크리스트를 처음 설치 후, 그리고 주요 변경 후 수행한다.

## 0. 사전 준비

- [ ] 백엔드가 `https://<your-host>/api/detail-pages?limit=1` 에 응답 (200 + JSON)
- [ ] basic_auth 자격증명 보유
- [ ] Chrome (또는 Edge) 최신 버전 — Manifest V3 service worker 지원 필요

## 1. Manifest 검증

```bash
cd /Users/arang/projects/itemSelector/chrome-extension
python3 -m json.tool manifest.json > /dev/null && echo "manifest OK"
```

## 2. 설치 검증

- [ ] `chrome://extensions` 에서 **압축해제된 확장 프로그램 로드** → 경로 선택
- [ ] 에러 배너 없음 (특히 manifest 에러, icon 누락)
- [ ] 도구모음에 itemSelector 아이콘 보임

## 3. Popup 설정 + 연결 테스트

- [ ] 도구모음 아이콘 클릭 → 팝업 열림 (340px 가로)
- [ ] 백엔드 URL + 사용자명 + 비밀번호 입력
- [ ] **💾 저장** → `✅ 저장되었습니다.`
- [ ] **🩺 연결 테스트** → `✅ 200 OK — 백엔드 연결 성공`
- [ ] 잘못된 비밀번호로 다시 시도 → `❌ HTTP 401 …`
- [ ] 백엔드 URL 끝에 `/` 추가해서 저장 → 자동 제거되어 다시 200

## 4. 1688 페이지 통합 테스트

테스트 URL 예시 (변경될 수 있음):
- `https://detail.1688.com/offer/<offer_id>.html`

- [ ] 페이지 로드 후 우측 상단에 **🎨 상세페이지 생성** 버튼 보임
- [ ] 버튼 호버 시 색상 변화 (slate-800 → slate-700)
- [ ] 버튼 클릭 → 상태 박스에 `⏳ 전송 중…` 표시
- [ ] 1~2초 내 `✅ 등록됨 (id #N)` 표시
- [ ] 백엔드 frontend (`/detail-pages`) 에서 새 row 확인
- [ ] DB `source_products.raw_payload` JSONB 에 다음 필드가 채워졌는지 확인:
  - `title_zh` — 빈 문자열 아니어야 함
  - `main_images` — 1개 이상 (이상적으로 5+)
  - `category_path` — 1개 이상 (lazy-load 면 빈 배열 가능)
  - `specs` — 핵심 라벨 (브랜드/재질 등) 포함
- [ ] 같은 페이지에서 버튼을 한 번 더 누름 → `source_products` 는 upsert (같은 id),
      `detail_pages` 는 새 row 생성 (백엔드 contract 의도)

## 5. 타오바오 페이지 통합 테스트

- [ ] `https://item.taobao.com/item.htm?id=<num>` 또는
      `https://detail.tmall.com/item.htm?id=<num>`
- [ ] 버튼 주입됨
- [ ] 클릭 → 성공 응답
- [ ] payload 의 `source_platform === 'taobao'` 확인 (tmall 도 'taobao' 로 매핑)

## 6. 에러 케이스

- [ ] 백엔드 끔 → 클릭 → `❌ fetch 실패: …` 또는 `❌ HTTP 5xx`
- [ ] 비밀번호 변경 후 재시도 → `❌ HTTP 401`
- [ ] 1688/타오바오가 아닌 페이지 (예: google.com) → 버튼이 주입되지 않아야 함
- [ ] 같은 페이지에서 새로고침 후 클릭 → 재주입 (`window.__itemSelectorInjected`
      가드로 중복 주입 방지)
- [ ] 메인 이미지가 lazy-load 라 못 찾는 케이스 →
      `❌ 메인 이미지를 찾지 못했습니다.`

## 7. 성능 / 침투성

- [ ] 페이지 스크롤/클릭이 버튼 때문에 막히지 않음
- [ ] 버튼이 페이지의 다른 fixed 요소 (예: 채팅 위젯) 에 가려지지 않음
      (z-index 2147483647 → 거의 항상 위)
- [ ] DevTools console 에 `[itemSelector] selector failed:` 경고가 너무 많이 뜨면
      해당 셀렉터가 깨졌다는 신호 → `content.js` 의 fallback 셀렉터 추가

## 8. 정리

- [ ] popup 비밀번호 입력 type 이 `password` (가려짐)
- [ ] storage 에 평문 저장된다는 사실이 hint 텍스트로 노출됨
- [ ] README 의 troubleshooting 섹션이 위 시나리오를 커버
