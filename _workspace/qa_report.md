# QA 검증 리포트 — 분당구 부동산 멀티레이어 지도

- 검증일: 2026-07-10
- 검증자: qa-validator
- 대상 리전: 경기도 성남시 분당구
- 검증 방식: Python 파싱 스크립트 실전 검사(파일 존재 확인 아님) + HTML 경계면 교차 비교
- 검증 스크립트: `scratchpad/qa_validate.py`

## 종합 판정: ❌ FAIL (배포 불가) — 치명적 렌더 크래시 1건

지도 HTML이 **로드 시 JS 런타임 예외로 전체 스크립트가 중단**된다. 경매 레이어에 `geometry:null`인 피처 2건이 임베드되어 있고, 렌더 루프에 null 가드가 없어 첫 null 피처에서 크래시 → 공공주택 폴리곤·인프라 클러스터·모든 토글 이벤트 바인딩이 실행되지 않는다. 데이터 레이어 4종 자체는 좌표·스키마 대부분 양호하나, 이 크래시로 최종 산출물은 동작하지 않는다.

---

## 1. 레이어별 요약

| 레이어 | meta.count | 실제 feat | geometry | 스키마 위반 | 좌표 실패 | layer≡meta | 판정 |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| auction | 64 | 64 | Point | **2 (geometry=null)** | 0 | ✅ | ⚠️ FAIL |
| infra | 379 | 379 | Point | 0 | 0 | ✅ | ✅ PASS |
| zone_pubhousing | 13 | 13 | Polygon/MultiPolygon | 0 | 0 | ✅ | ✅ PASS |
| zone_redev | 0 | 0 | — | 0 | 0 | ✅ | ✅ PASS(빈 레이어) |
| zone_industrial | 0 | 0 | — | 0 | 0 | ✅ | ✅ PASS(빈 레이어) |

---

## 2. 스키마 준수 (필수 5필드 + geometry + layer≡meta.layer)

- 필수 5필드(`layer/id/name/category/color`): 전 레이어 **위반 0**.
- `layer` 값 == `meta.layer`: 전 레이어 **일치**(mismatch 0), 단일 레이어만 포함.
- **geometry 위반 2건 (auction)** — 아래 상세.

### ❌ 위반: auction geometry=null 2건 (담당: auction-collector)

| feature idx | id | name | usage | geometry |
|:---:|---|---|---|---|
| 30 | B0002512025013005235311 | 2025타경52353 | 자동차 | **null** |
| 61 | B0002512025013005340411 | 2025타경53404 | 자동차 | **null** |

- 원인: 지오코딩 실패한 "자동차" 물건(주소 없음). `meta.geocode_failed:2`와 일치 — 수집가가 실패를 투명하게 표기한 점은 양호.
- 규격 위반: geojson-schema.md는 모든 Feature에 geometry 존재를 요구(검증규칙 #1). geocode 실패 피처는 **features 배열에서 제외**하고 `meta.geocode_failed`로만 카운트해야 한다. 현재는 null geometry로 배열에 포함되어 스키마를 깨고, 다운스트림 렌더러를 크래시시킴.

---

## 3. 좌표 유효성

- 검사 범위: 경도 124–132 / 위도 33–43. Polygon·MultiPolygon은 전 ring 좌표 전수 검사.
- 결과: **전 레이어 좌표 실패 0건**. `[0,0]` 0건 / 위경도 뒤바뀜 0건 / EPSG 미변환(1000+ 좌표) 0건.
- 좌표 순서: `[경도, 위도]` GeoJSON 표준 준수. 모든 레이어 WGS84 동일 좌표계 확인.

---

## 4. 레이어 간 정합 + 경매 마커 스팟체크

- 좌표계: 5개 레이어 전부 WGS84 단일 좌표계. 혼용 없음.
- **경매 마커 스팟체크 (실제 분당구 위치 여부, 샘플 8건 전부 OK):**

| name | category | 좌표(lon,lat) | 주소 | 분당범위 |
|---|---|---|---|:---:|
| 2024타경4294 | 기타 | 127.12728, 37.41309 | 분당구 야탑동 341 (터미널복합건물) | OK |
| 2024타경4300 | 상업/업무 | 127.12728, 37.41309 | 분당구 야탑동 341 | OK |
| 2024타경4447 | 상업/업무 | 127.12728, 37.41309 | 분당구 야탑동 341 | OK |
| 2024타경55322 | 상업/업무 | 127.10994, 37.34038 | 분당구 구미동 182 | OK |
| 2025타경688 | 토지 | 127.06447, 37.38857 | 분당구 운중동 산100-3 | OK |

- 전체 64건 중 분당 bbox(127.06–127.17 / 37.30–37.43) 내 **62건**, null geometry 2건. 위치 매핑 정확도 양호(야탑동 집합건물 다수가 동일 좌표에 적층 — 집합건물 특성상 정상).

---

## 5. 렌더 계약 일치 (estate_map.html ↔ 데이터) — 경계면 교차 비교

### 5-1. 토글 레이어 이름 (PASS)
HTML 토글 id와 데이터 레이어가 일대일 대응:
- `t_auction`(경매물건 64) · `t_pub`(공공주택지구 13) · `t_infra`(생활인프라 379) — 카운트 라벨이 실제 feat 수와 일치.
- 인프라 하위 토글 `ti_school`(154)/`ti_hospital`(108)/`ti_mart`(97)/`ti_subway`(20) — **데이터 category_counts와 정확히 일치**.

### 5-2. category 키 (PASS)
데이터가 제공하는 모든 category 토큰이 HTML에 인용부호로 존재:
- auction: `기타`·`상업/업무`·`토지`·`아파트` 전부 존재.
- infra: `school`·`hospital`·`mart`·`subway` 전부 존재.
- pubhousing: `pubhousing` 존재.
- 데이터에 있으나 HTML이 모르는 category = **0건**.

### 5-3. color 키 (PASS)
데이터의 모든 HEX color가 HTML에 존재:
- auction #e74c3c/#2196f3/#4caf50/#9e9e9e, infra #f39c12/#e74c3c/#16a085/#2980b9, pub #009688 — 전부 매칭. 인프라 범례 색상(학교 #f39c12·병원 #e74c3c·마트 #16a085·지하철 #2980b9)이 데이터 color와 일치.

### 5-4. ❌ 치명적 렌더 크래시 (담당: map-integrator, 근인: auction-collector)
`estate_map.html` L97–108 경매 렌더 루프:
```js
(AUCTION.features||[]).forEach(function(f){
  var c=f.geometry.coordinates, p=f.properties;   // ← null 가드 없음
```
- 임베드된 AUCTION.features 64건 중 2건이 `geometry:null`(idx 30, 61) → `f.geometry.coordinates`에서 **Uncaught TypeError: Cannot read properties of null**.
- try/catch 없음(검색된 "try"는 "geome**try**" 오탐, 실제 예외 처리 부재 확인).
- 최상위 인라인 스크립트에서 예외 발생 → **이후 코드 전부 미실행**: 공공주택 폴리곤(L125~)·인프라 클러스터(L110~)·토글 onchange 바인딩(L145~) 모두 로드 안 됨. 지도는 베이스 타일 + 죽은 UI만 표시.
- 부수 문제: 토글 카운트 라벨 "경매물건 64"는 실제 매핑 가능 마커(62)와 불일치.

---

## 6. 빈 레이어 처리 (PASS)

- `zone_redev`·`zone_industrial`: `meta.count:0`, 빈 features 배열, `meta.note`에 미확보 사유 명시.
- HTML 처리 양호: 상단 요약 "정비구역 **0** / 산업단지 **0**", 토글은 `class="row disabled"` + `disabled` 속성 + "데이터 없음" 라벨(L52–53). 비활성 표기 정상.

---

## 7. 반려 및 조치 요청

### 🚨 map-integrator (필수 — 크래시)
경매 렌더 루프에 null 가드 추가:
```js
(AUCTION.features||[]).forEach(function(f){
  if(!f.geometry || !f.geometry.coordinates) return;   // 추가
  var c=f.geometry.coordinates, p=f.properties;
```
- 인프라 루프(L116)도 동일 방어 코드 권장(현재 infra는 null 0건이나 회귀 방지).
- 토글 카운트를 매핑 가능 건수 기준으로 표기하거나 "64건(2건 위치정보 없음)"으로 명시.

### auction-collector (권장 — 근본 원인)
- geocode 실패 물건 2건(2025타경52353·2025타경53404, 용도 "자동차")을 `features` 배열에서 제외. `meta.geocode_failed:2`로만 집계 유지(schema 검증규칙 #1 준수).
- 이렇게 하면 렌더러 방어 코드가 없어도 크래시가 발생하지 않음. 방어 코드(map-integrator)와 소스 정제(auction-collector) **양쪽 모두 적용 권장**.

---

## 회귀 비교
- 기존 `qa_report.md` 없음 — 본 리포트가 최초 기준선(baseline).
