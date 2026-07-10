---
name: layer-zone-boundary
description: 구역 경계 레이어 수집. 정비구역·공공주택지구(LH)·산업단지 경계를 VWorld/LURIS WMS 및 공공데이터에서 가져와 표준 GeoJSON Polygon 레이어 또는 WMS 오버레이 설정으로 만든다. "정비구역 레이어", "공공주택 경계", "산업단지 레이어", "구역 경계 추가", "LH 사업지구 경계" 요청 시 사용.
---

# layer-zone-boundary — 구역 경계 레이어 수집

정비구역·공공주택지구·산업단지 세 종류의 면(Polygon) 경계를 동일 기법으로 처리한다. 실시간 오버레이면 WMS 설정, 분석·필터가 필요하면 GeoJSON 다운로드를 선택한다.

## 소스 매핑

| 구역 | 주 소스 | layer 값 | 색 계열 |
|------|--------|---------|--------|
| 정비구역(재개발·재건축) | LURIS(토지이용규제) WMS / 지자체 | `zone_redev` | 주황 |
| 공공주택지구 | LH 사업지구경계선(VWorld) / 공공데이터포털 | `zone_pubhousing` | 청록 |
| 산업단지 | 한국산업단지공단 / 공공데이터포털 GeoJSON | `zone_industrial` | 보라 |

## 워크플로우

### 1. WMS vs GeoJSON 판단
- **WMS(타일 오버레이)**: 경계를 배경으로 얹기만 하면 됨 → URL·레이어명·투명도만 설정(`_workspace/zone_wms_config.json`). `vworld-map` 스킬로 프록시 서버를 띄워 CORS를 우회한다.
- **GeoJSON(벡터)**: 경매 마커가 구역 안/밖인지 판정하거나 면적 필터가 필요 → 경계를 GeoJSON으로 내려받아 `_workspace/layer_zone_*.geojson`으로 저장.

### 2. 좌표계 정규화
공공 GIS는 EPSG:5179/5186을 자주 쓴다. **반드시 WGS84(EPSG:4326)로 변환**한 뒤 병합한다. 변환 누락은 구역이 엉뚱한 위치(바다·다른 시)에 찍히는 대표 버그다.

### 3. 스키마·메타
`references/geojson-schema.md`의 `zone_*` 규격. 확장 필드 `stage`(지정일/단계), `area_m2`, `authority`(지정권자/시행자). `meta.source`·`meta.base_date`를 반드시 남긴다 — 구역은 지정·해제가 잦아 기준일이 신뢰의 핵심이다.

## 왜 이렇게 하는가
- **면과 점의 위계**: 구역은 낮은 투명도 채움으로 배경 처리. 진하면 경매 마커를 덮는다.
- **키 분리**: VWorld/공공데이터 키는 `.env`로. 산출 HTML에 하드코딩하면 노출된다.

## 산출 검증
- 좌표계가 WGS84인가(범위 검사로 확인).
- 세 레이어가 서로·마커와 색으로 구분되는가.
