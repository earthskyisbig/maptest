---
name: layer-infra-poi
description: 생활인프라 POI 레이어 수집. 학교·병원·마트·지하철역·프랜차이즈 등 생활편의 지점을 Overpass/카카오에서 bbox로 수집해 카테고리별 토글이 가능한 표준 GeoJSON Point 레이어(layer_infra.geojson)로 만든다. "생활인프라 레이어", "POI 수집", "학교/병원/지하철 표시", "인프라 레이어 추가" 요청 시 사용.
---

# layer-infra-poi — 생활인프라 POI 레이어 수집

부동산 입지 판단의 편의성 근거가 되는 생활인프라 지점을 카테고리별로 수집한다.

## 워크플로우

### 1. bbox로 범위 좁히기
대상 지역의 경계 상자(bbox)를 먼저 구하고 Overpass 쿼리를 그 안으로 제한한다. 전국 쿼리는 타임아웃·과다 응답을 부른다.

### 2. 카테고리별 수집
`category`는 토글·색상의 단위다. 반드시 채운다.

| category | Overpass/카카오 태그 예 | 색 |
|----------|----------------------|----|
| `school` | `amenity=school` | `#f39c12` |
| `hospital` | `amenity=hospital\|clinic` | `#e74c3c` |
| `mart` | `shop=supermarket\|mall` | `#16a085` |
| `subway` | `railway=station` (지하철) | `#2980b9` |
| `franchise` | 브랜드(스타벅스 등) | `#795548` |

`map_with_infra.py`가 이미 학교·병원·쇼핑몰·지하철역·스타벅스를 Overpass로 수집한다 — 그 쿼리 구조를 재사용한다.

### 3. GeoJSON 변환
`references/geojson-schema.md`의 `layer: "infra"` 규격. 필수 `category`·`color`, 선택 `brand`. `meta`에 카테고리별 개수를 기록한다.

산출: `_workspace/layer_infra.geojson`

## 왜 이렇게 하는가
- **카테고리 필수**: map-render는 카테고리 단위로 토글을 만든다. 비어 있으면 "지하철만 보기"가 불가능해진다.
- **원본 밀도 보존**: POI는 수천 개일 수 있다. 클러스터링은 렌더러(map-render)가 하니 수집 단계에서 임의로 솎지 않는다. 대신 카테고리별 개수를 리포트한다.

## 산출 검증
- 모든 Feature에 유효 `category`가 있는가.
- 좌표가 대한민국 범위 내이고 bbox 안인가.
