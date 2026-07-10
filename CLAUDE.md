# maptest — 부동산 전용 멀티레이어 맵서비스

경매물건·정비구역·공공주택·산업단지·생활인프라를 한 지도 위에 레이어로 보여주는 부동산 맵서비스.

## 하네스: 부동산 맵서비스

**목표:** 5개 레이어(경매·정비구역·공공주택·산업단지·생활인프라)를 수집·통합해 하나의 카카오/VWorld 인터랙티브 지도로 산출한다.

**트리거:** 지도 구축·레이어 수집/추가/갱신·지도 렌더 관련 요청 시 `realestate-map-build` 스킬(오케스트레이터)을 사용하라. 개별 레이어만 손볼 때는 해당 레이어 스킬(`layer-auction-collect`·`layer-zone-boundary`·`layer-infra-poi`·`map-render`)이 직접 트리거된다. 단순 질문은 직접 응답 가능.

**공유 데이터 계약:** 모든 레이어는 `.claude/skills/realestate-map-build/references/geojson-schema.md`의 표준 GeoJSON 규격(WGS84, 필수 5필드)을 따른다.

**재사용 자산:** `../auction_crawling/map_with_infra.py`(베이스맵·클러스터·WMS 뼈대), `geocode_all.py`(지오코딩), 글로벌 `vworld-map` 스킬(프록시), auction-council `court-auction-scraper`·`naver-land` 스킬.

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-07-10 | 초기 구성 (에이전트 5·스킬 5·GeoJSON 규격) | 전체 | 하네스 신규 구축 |
