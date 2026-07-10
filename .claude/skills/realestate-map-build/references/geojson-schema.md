# 표준 레이어 GeoJSON 규격 (공유 데이터 계약)

모든 수집 에이전트는 이 규격으로 산출하고, map-integrator는 이 규격만 신뢰한다. QA는 이 규격으로 검증한다. 규격을 지키면 새 레이어를 추가해도 렌더러를 고치지 않아도 된다.

## 공통 구조

각 레이어는 하나의 `FeatureCollection` 파일이다. 좌표계는 **WGS84(EPSG:4326)** 고정, 좌표 순서는 `[경도, 위도]`(GeoJSON 표준).

```json
{
  "type": "FeatureCollection",
  "meta": {
    "layer": "auction",
    "source": "법원경매정보",
    "collected_at": "2026-07-10T10:00:00+09:00",
    "base_date": "2026-07-01",
    "count": 328,
    "geocode_failed": 5
  },
  "features": [ ... ]
}
```

## Feature 필수 필드 (`properties`)

| 필드 | 타입 | 설명 | 모든 레이어 필수 |
|------|------|------|:---:|
| `layer` | string | `auction` \| `zone_redev` \| `zone_pubhousing` \| `zone_industrial` \| `infra` | ✅ |
| `id` | string | 레이어 내 고유 식별자 | ✅ |
| `name` | string | 마커/팝업 제목 (사건번호·구역명·POI명) | ✅ |
| `category` | string | 레이어 내 소분류 — 토글·색상 단위 | ✅ |
| `color` | string | HEX 색 (`#e74c3c`) | ✅ |

`geometry`는 점 레이어(auction·infra)는 `Point`, 구역 레이어(zone_*)는 `Polygon`/`MultiPolygon`.

## 레이어별 권장 `properties` 확장

- **auction**: `case_no`(사건번호), `usage`(용도), `appraisal`(감정가), `min_bid`(최저가), `fail_count`(유찰), `geocode_failed`(bool)
- **zone_redev / zone_pubhousing / zone_industrial**: `stage`(단계/지정일), `area_m2`, `authority`(사업시행자/지정권자)
- **infra**: `category`(school/hospital/mart/subway/franchise), `brand`(선택)

## 카테고리·색상 컨벤션

기존 `map_with_infra.py`의 용도별 색상을 계승한다:
- 아파트 `#e74c3c` · 연립/다세대 `#e91e63` · 단독/다가구 `#9c27b0` · 상업/업무 `#2196f3` · 토지 `#4caf50` · 기타 `#9e9e9e`
- 구역은 낮은 투명도 채움: 정비구역 주황계열, 공공주택 청록계열, 산업단지 보라계열 — 서로·마커와 구분되게.

## 검증 규칙 (qa-validator 사용)

1. 모든 Feature에 필수 5필드 존재.
2. 좌표가 대한민국 범위: 경도 124–132, 위도 33–43. (`[0,0]`·위경도 뒤바뀜 탐지)
3. 파일당 `layer` 값이 `meta.layer`와 일치, 단일 레이어만 포함.
4. `category` 값이 map-render 토글 정의에 존재.
5. 빈 `FeatureCollection`은 허용(레이어 미수집) — 단 `meta.count: 0` 명시.
