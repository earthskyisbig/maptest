---
name: layer-auction-collect
description: 경매물건 레이어 수집. 법원경매 물건을 API 직접 페이징으로 수집하고 주소를 지오코딩하여 표준 GeoJSON Point 레이어(layer_auction.geojson)로 만든다. "경매 레이어 만들어줘", "경매물건 수집", "경매 지도 데이터 갱신", 경매 레이어 재수집/업데이트 요청 시 사용.
---

# layer-auction-collect — 경매물건 레이어 수집

법원경매 물건을 수집·지오코딩해 표준 GeoJSON Point 레이어를 만든다. 산출물은 map-render가 병합한다.

## 워크플로우

### 1. 목록 수집 — API 직접 페이징 (UI 클릭 금지)
법원경매정보 UI의 페이지 버튼 클릭은 물건을 대량 누락시킨다(328건 중 113건만 잡힌 사례). `searchControllerMain.on` 엔드포인트를 `pageNo`로 직접 증가시켜 전 페이지를 순회한다. 총 건수(`totalCnt`)를 먼저 읽고 페이지 수를 계산해 끝까지 돈다.

> 상세 수집 절차는 auction-council의 `court-auction-scraper` 스킬을 참조한다. 브라우저 자동화 MCP(Chrome DevTools/Playwright) 또는 requests 세션으로 API를 직접 호출한다.

### 2. 지오코딩
지번/도로명 주소 → `[경도, 위도]`. `auction_crawling/geocode_all.py`·`geocoding.py`의 카카오 지오코딩 파이프라인을 재사용한다.
- 캐시 우선 조회로 API 호출을 아낀다.
- **실패 주소는 버리지 않는다** — `geometry: null` + `properties.geocode_failed: true`로 남기고 `meta.geocode_failed` 카운트에 반영한다.

### 3. GeoJSON 변환
`references/geojson-schema.md` 규격의 `layer: "auction"` FeatureCollection으로 쓴다.
- `category`·`color`는 용도 매핑(`map_with_infra.py`의 `USAGE_MAP` 계승): 아파트 `#e74c3c`, 연립/다세대 `#e91e63`, 단독/다가구 `#9c27b0`, 상업/업무 `#2196f3`, 토지 `#4caf50`, 기타 `#9e9e9e`.
- 확장 필드: `case_no`, `usage`, `appraisal`, `min_bid`, `fail_count`.
- `meta`에 `collected_at`(수집 시각), `count`, `geocode_failed` 기록.

산출: `_workspace/layer_auction.geojson`

## 왜 이렇게 하는가
- **API 직접 페이징**: UI 페이징은 세션·렌더 타이밍에 따라 누락이 발생하지만 API는 결정적이다.
- **실패 주소 보존**: 지오코딩 실패율은 데이터 품질 지표다. 조용히 버리면 지도가 완전해 보이지만 실제로는 물건이 빠진다.

## 산출 검증
- 총 물건수 = 지도 표시 + geocode_failed 합과 일치하는가.
- 좌표가 대한민국 범위(경도 124–132, 위도 33–43) 내인가.
