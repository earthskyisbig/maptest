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
| 2026-07-11 | class_slide 스킬 추가 (강의 슬라이드 웹앱 생성기) | skills/class_slide | 강의 슬라이드 제작 재사용화 |
| 2026-09-02 | SHP→GeoJSON→카카오맵 실습 추가 (scripts/shp_to_geojson.py·build_shp_map.py, course/06-SHP지도화.md, 수도권정비권역 레이어) | scripts·course·_workspace | 공공 SHP 지도화 따라하기 강의 |
| 2026-09-02 | 서울플랜+ UQ120 변환기 추가 (scripts/seoulplan_to_geojson.py, layer_zone_redev_seoulplan.geojson, seoul_redev_map.html) | scripts·_workspace | 정비구역 원본 SHP 재현·코드표 매핑 실습 |
| 2026-09-02 | VWorld D029 정비구역(2,231)·D314 재정비촉진지구(243) 변환, 멀티레이어 빌드 (shp_to_geojson 프로필화, build_shp_map 다중 입력, vworld_zone_map.html) | scripts·_workspace | 최신(2026-08-06) 정비구역을 기준 데이터로 채택 |
| 2026-09-02 | 서울 아파트 경매물건 수집→DuckDB→지도 (collect_auction_seoul.py·load_auction_duckdb.py·build_auction_map.py, data/estate.duckdb, seoul_auction_map.html: 카카오/브이월드 선택·클러스터·스카이뷰·로드뷰·민트 마커) | scripts·data·course/07 | 서울플랜+ 기준 지도 위 경매물건 서비스 실습 |
| 2026-09-02 | 경매 지도 고도화 (면적·감정가·최저가·매각기일 필터, 호버 툴팁, 관심물건 저장·금색 마커, API키 접기, 팝업 항목 정리) + 프롬프트 로그 course/08 | scripts/auction_map_template.html·course | 강의용 따라하기 기록 |
| 2026-09-02 | 경매 지도 도구 확장: 파란 마커, 주소·장소 검색, 장소 저장(별표 6색), 주변 시설 검색(12카테고리), 거리·면적·반경 측정 | scripts/auction_map_template.html·course/07·08 | 카카오맵 표준 도구 이식 |
| 2026-09-02 | 경매 팝업 210px로 축소+스크롤, 거리·면적 측정을 드래그 그리기+더블클릭 마무리로 변경 (DOM mousemove→coordsFromContainerPoint) | scripts/auction_map_template.html | 사용성 개선 |
| 2026-09-02 | 구역 폴리곤 클릭 팝업 수정(지도 click 전파 차단) + 호버 툴팁 + 구역 내 경매물건 목록 | scripts/auction_map_template.html | 구역 정보 확인 요청 |
| 2026-09-04 | VWorld 3개 주제도(D014 수도권정비권역·D029 정비구역·D314 재정비촉진지구) 통합 지도 vworld_three_map.html + 2장 요약 슬라이드 course/slides_auction_map_2p.html | 루트·course | 강의용 |
| 2026-09-04 | D316(정비예정구역·정비계획수립중, 105건) 추가 → 4레이어 지도 vworld_four_map.html; D316 프로필 제목·이름필드 수정 | scripts/shp_to_geojson.py·루트 | 강의용 |
| 2026-09-04 | 공동주택 공시가격(D167 CSV 278만호) DuckDB 적재(load_apt_price.py) + 경매물건 PNU·호 매칭 → 팝업 공시가격 박스(최저가/공시가 비율) | scripts·data·course/08 | 주소 클릭 시 공시가격 표시 요청 |
| 2026-09-04 | 경매 지도에 D316 정비예정구역·정비계획수립중(105) 레이어 추가 (build_auction_map --extra-zones) | scripts/build_auction_map.py | 구역 레이어 보강 |
| 2026-09-04 | GIS건물통합정보(D010, 69.6만 동) DuckDB 적재(load_buildings.py) + 경매물건 PNU 매칭 → 팝업 건축물 박스(용도·구조·연식·층수·용적률·위반여부) + 경매 필지 건물 윤곽 레이어(709동) | scripts·data·course/08 | 건물 데이터 반영 요청 |
| 2026-09-07 | VWorld D060 산업단지·D315 공공주택지구 프로필 + shp_to_geojson --sido 필터, UPIS C_UQ152 철도망 추출기(upis_to_geojson.py) → vworld_seven_map.html(7레이어), 경매 지도 구역 레이어 확장(4,641). D350 개발제한구역은 0건(빈 파일) | scripts·_workspace·루트·course/08 | 철도·공공주택·산단·GB 레이어 요청 |
| 2026-09-07 | 범례 UI 개선: 스크롤·접기 버튼, 레이어 그룹 접기/전체 on-off(shp 템플릿), 구역·출처 details 접기(경매 템플릿) | scripts/shp_map_template.html·auction_map_template.html | 범례가 길어 지도가 가려지는 문제 |
| 2026-09-07 | 경매 지도 구역 레이어 선택: 레이어(권역·서울플랜+·예정구역·공공주택·산단·철도)별 전체 on/off + 구분별 체크, 선택 상태 localStorage 저장, 기본은 서울플랜+만 표시 (build_auction_map 기본 extra-zones 5종) | scripts/auction_map_template.html·build_auction_map.py | 경매지도에서 권역·구역·지구 선택 요청 |
| 2026-09-08 | 경매 수집 범위 확장: 아파트+다세대(연립·빌라 포함) 60일, 949건(다세대 865·아파트 84) → DuckDB·지도 갱신. 용도별 마커 색(아파트 파랑·다세대 주황)·용도 필터·범례 추가 | scripts/collect_auction_seoul.py·load_auction_duckdb.py·auction_map_template.html | 2개월 내 서울 아파트·다세대 경매 조사 요청 |
| 2026-09-08 | load_buildings.py 메모리 절약 재작성: 속성은 도형 없이 1만 행 배치·DuckDB memory_limit 400MB, 도형은 경매 필지 PNU만 OGR where로 추출(--footprints-only). 건물 윤곽 1,188동·건축물 매칭 720건 | scripts/load_buildings.py | 69.6만 동 재적재가 OOM으로 반복 실패 |
