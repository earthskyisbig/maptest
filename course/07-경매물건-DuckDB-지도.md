# 07. 서울 아파트 경매물건 → DuckDB → 카카오/브이월드 지도 (따라하기)

> **목표** — 법원경매 사이트에서 서울 아파트 경매물건을 전량 수집해 정규화하고, DuckDB에 저장한 뒤,
> 서울플랜+ 정비구역 지도 위에 민트색 클러스터 마커로 올린다. 카카오맵(스카이뷰·로드뷰)과 브이월드맵을 골라 볼 수 있다.
> **소요** — 30분. **결과물** — `seoul_auction_map.html`, `data/estate.duckdb`

---

## 0. 프롬프트 (한 줄로 시작)

```
지난번 만든 서울플랜지도를 기준으로 서울시 아파트 경매물건 리스트업해서 정규화하여 덕디비에 저장하고,
지도(브이월드맵, 카카오맵 선택)에 표시할수 있도록 해줘. 지도는 스카이뷰와 로드뷰, 경매물건은 클러스터링이 되면 좋겠어.
마커는 민트색상으로 해줘. 경매물건에 대한 정보(물건번호, 유찰회수, 감정가, 최저가, 면적, 특이사항등)는 되도록 많이 넣어줘.
```

에이전트는 이것을 **수집 → 정규화/적재 → 지도 빌드** 세 단계, 스크립트 세 개로 나눕니다.

| 단계 | 스크립트 | 입력 → 출력 |
|---|---|---|
| ① 수집 | `scripts/collect_auction_seoul.py` | 법원경매 API → `_workspace/auction_raw_seoul.json` |
| ② 정규화·적재 | `scripts/load_auction_duckdb.py` | 원본 JSON + 서울플랜 구역 → `data/estate.duckdb`, `_workspace/layer_auction_seoul_apt.geojson` |
| ③ 지도 | `scripts/build_auction_map.py` (+ `auction_map_template.html`) | GeoJSON 2개 → `seoul_auction_map.html` |

```
python scripts/collect_auction_seoul.py --days 60
python scripts/load_auction_duckdb.py
python scripts/build_auction_map.py
python -m http.server 8000     →  http://localhost:8000/seoul_auction_map.html
```

---

## 1. 수집 — 법원경매 검색 API를 직접 페이징한다

법원경매정보(courtauction.go.kr)의 목록 화면은 WebSquare로 만들어져 **페이지 버튼을 클릭하는 방식은 물건을 대량 누락**합니다
(실측: 328건 중 113건만 수집). 대신 화면이 내부적으로 부르는 검색 API를 `pageNo` 1..N으로 직접 호출합니다.

```
POST https://www.courtauction.go.kr/pgj/pgjsearch/searchControllerMain.on
{ "dma_pageInfo": {"pageNo": 1, "pageSize": 40, ...},
  "dma_srchGdsDtlSrchInfo": {"cortOfcCd": "B000210", "lclDspslGdsLstUsgCd": "20000", "bidBgngYmd": "20260902", "bidEndYmd": "20261101", ...} }
```

서울 5개 법원(중앙 B000210 · 동부 B000211 · 남부 B000212 · 북부 B000213 · 서부 B000215)을 "건물" 대분류로 전량 받은 뒤
용도명(`dspslUsgNm`)에 **아파트**가 있는 서울 소재 물건만 남깁니다.

### 함정 3가지 (전부 실제로 겪은 것)

| 함정 | 증상 | 해결 |
|---|---|---|
| 총건수 필드 | `totalCnt`가 항상 `""` → 0건으로 오판 | `groupTotalCount`를 읽는다 |
| 마지막 페이지 | 창을 앞으로 당겨 항상 40건을 채워 옴 → 앞부분 중복 | 남은 건수만큼 **뒤에서** 잘라 쓴다 |
| 시/도 필터 | 폼에서 서울을 골라도 전국이 옴 | `hjguSido`로 **사후 필터** |

이번 실행 결과 (2026-09-02, 매각기일 60일 범위)

```
서울중앙 410 · 서울동부 301 · 서울남부 1,494 · 서울북부 117 · 서울서부 181  = 건물 2,503건
→ 아파트 + 서울 소재 필터 → 115건
```

> 5개 법원 모두 수집 건수 = 총건수로 정합성 검증을 통과했습니다. 미달이면 스크립트가 ⚠️를 찍습니다. 조용히 넘어가지 않는 것이 핵심입니다.

---

## 2. 정규화 — 좌표·금액·면적·특수조건

### 2-1. 좌표는 지오코딩이 필요 없다 (TM128)
목록 API가 `xCordi`/`yCordi`를 함께 줍니다. 값이 `312192, 555694`처럼 미터 단위인데 EPSG:5186도 5174도 아니고
**KATECH TM128**(Bessel 타원체, 원점 128°E 38°N, 가산 400000/600000)입니다.

```python
TM128 = CRS.from_proj4("+proj=tmerc +lat_0=38 +lon_0=128 +k=0.9999 +x_0=400000 +y_0=600000 "
                       "+ellps=bessel +towgs84=-115.80,474.99,674.11,1.16,-2.31,-1.63,6.43 +units=m")
lon, lat = Transformer.from_crs(TM128, "EPSG:4326", always_xy=True).transform(x, y)
```

검증: 정릉동 508-123 → (127.00339, 37.59934). VWorld 지오코딩 결과와 **1m 이내 일치**.
좌표가 없는 물건만 VWorld 주소 지오코딩으로 보완하고, 실패는 `geocode_failed=true`로 남깁니다(이번엔 0건).

> 🔧 **어떻게 알아냈나** — 후보 좌표계 5개(5178·5179·5174·5186·2097)로 변환해 봤더니 전부 엉뚱한 곳(대만 앞바다, 강릉)이 나왔습니다.
> 가산값(400000/600000)과 원점(128°)이 맞는 TM128을 직접 정의하고 나서야 맞았습니다. **좌표계는 "맞을 것 같은 EPSG"가 아니라 실제 지점과 대조해 확정**하세요.

### 2-2. 정규화 컬럼 (DuckDB `auction_apt_seoul`)

| 그룹 | 컬럼 | 원본 필드 |
|---|---|---|
| 식별 | `id`, `court`, `case_no`, `item_no`(물건번호), `dup_case_no`(중복사건), `dept`, `dept_tel` | docid, jiwonNm, srnSaNo, maemulSer, dupSaNo, jpDeptNm, tel |
| 위치 | `address`, `sigungu`, `dong`, `lot_no`, `building_name`, `floor_unit`, `lon`, `lat`, `coord_source` | printSt, hjgu*, daepyoLotno, buldNm, buldList, xCordi/yCordi |
| 물건 | `usage`, `structure`, `area_m2`, `area_pyeong`, `area_list` | dspslUsgNm, pjbBuldList |
| 가격 | `appraisal`(감정가), `min_bid`(최저가), `min_bid_rate`(%), `discount_pct` | gamevalAmt, notifyMinmaePrice1, notifyMinmaePriceRate1 |
| 진행 | `fail_count`(유찰), `round_no`, `sale_date`, `sale_time`, `sale_place`, `decision_date` | yuchalCnt, maeGiilCnt, maeGiil, maeHh1, maePlace, maegyuljGiil |
| 특이 | `special_conditions`, `special_cond_codes`, `note`(물건비고), `view_count`, `related_items` | spJogCd, mulBigo, inqCnt, gwansMulRegCnt |
| 정비구역 | `zone_name`, `zone_category`, `zone_subtype`, `zone_stage` | 서울플랜+ 폴리곤 point-in-polygon |

면적 파싱 함정: `'84. 9460㎡'`(소수점 뒤 공백)이 섞여 있어 `re.sub(r'(\d)\.\s+(\d)', r'\1.\2')`로 먼저 붙입니다.

### 2-3. 특수조건 코드는 검증된 것만 이름을 붙인다
`spJogCd`는 `0004302,0004303` 같은 코드로만 옵니다. 물건비고 문구와 대조해 **확인된 두 개만** 이름을 붙였습니다.

| 코드 | 이름 | 근거 |
|---|---|---|
| 0004306 | 특별매각조건 | 비고 "특별매각조건 매수신청보증금 20%", "대항력 포기조건 매각" 15건 전부 일치 |
| 0004310 | 지분매각 | 비고 "지분매각. 공유자 우선매수 1회 제한" |
| 0004302 / 0004303 | **미확인** → 화면에 `조건코드 0004302`로 노출 | 추측하지 않음 |

> 처음엔 코드표를 "그럴듯하게" 만들어 0004306을 위반건축물로 붙였다가, 비고 문구와 대조해 특별매각조건임을 확인하고 걷어냈습니다.
> **코드→이름 매핑은 반드시 원자료로 검증**하세요. 틀린 이름은 없는 것보다 나쁩니다.

### 2-4. DuckDB 확인

```python
import duckdb
c = duckdb.connect("data/estate.duckdb", read_only=True)
c.sql("SELECT sigungu, count(*) n, round(avg(min_bid)/1e8,2) 평균최저가_억 FROM auction_apt_seoul GROUP BY 1 ORDER BY n DESC")
c.sql("SELECT case_no, building_name, area_m2, fail_count, min_bid, zone_name FROM auction_apt_seoul WHERE zone_name IS NOT NULL")
c.sql("SELECT * FROM collect_runs")   # 수집 이력 (실행마다 1행)
```

테이블: `auction_apt_seoul`(115행) · `seoulplan_zones`(2,585행, 속성 + WKT) · `collect_runs`(수집 이력).
정비구역 안에 있는 물건은 20건(성동·송파 3, 강남·관악·양천·중·중랑 2 …).

---

## 3. 지도 — 엔진 두 개, 데이터 하나

```
DATA = { auction: GeoJSON(115), zones: GeoJSON(2585) }   ← HTML 안에 인라인
   ├─ 카카오맵 엔진: Map + MarkerClusterer + CustomOverlay 팝업 + Roadview 패널 + SKYVIEW/HYBRID
   └─ 브이월드맵 엔진: Leaflet + VWorld WMTS(Base/Satellite/Hybrid) + markercluster
```

| 요구 | 구현 |
|---|---|
| 카카오/브이월드 선택 | 상단 세그먼트. 선택은 localStorage에 기억 |
| 스카이뷰 | 카카오 `setMapTypeId(SKYVIEW / HYBRID)`, 브이월드 `Satellite` / `Hybrid` 타일 |
| 로드뷰 | 카카오 전용. 버튼 또는 팝업의 "이 위치 로드뷰" → 우측 45% 패널, 지도 클릭으로 이동 |
| 클러스터링 | 카카오 `MarkerClusterer`(gridSize 70) / Leaflet `markerClusterGroup` — 둘 다 민트 원형 |
| 민트 마커 | `#1abc9c` SVG 원, 앵커를 정중앙(13,13)으로 지정 |
| 필터 | 구 · 유찰 범위 · 면적㎡ 범위 · 감정가억 범위 · 최저가억 범위 · 매각기일 from~to · 정비구역 내만 · 관심물건만 ("⚙ 필터"로 접기) |
| 마커 호버 | 카카오 마커 확대(26→36px)+툴팁(사건번호·면적·최저가·유찰·매각기일), Leaflet CSS scale+툴팁 |
| 관심물건 | 팝업 ☆ 저장 → localStorage, 마커 금색(#f59e0b), 상단 ★ 패널(목록·이동·삭제·TSV 복사) |
| API 키 | 저장하면 패널 자동 접힘, 🔑 버튼으로 열기. 키 없을 때만 자동 표시 |
| 배경 레이어 | 서울플랜+ 구역 토글 (6개 대분류 색) |

팝업에서 제외한 항목: 용도(전부 아파트), 경매계 전화번호, 좌표출처.

### 카카오 SDK 함정 (kakao-map-js 스킬)
- 팝업 안 버튼이 안 눌리면 → `CustomOverlay` 내용을 **DOM 요소**로 만들고 `stopPropagation()` + `kakao.maps.event.preventMap()`.
- 로드뷰 패널이 검게 나오면 → 패널을 연 **뒤** `map.relayout()`·`roadview.relayout()`을 호출(0×0으로 재진 것).
- 마커 수천 개에서 멈추면 → `CustomOverlay` 말고 `Marker` + `MarkerClusterer`. 마커는 **최초 1회 생성**, 필터는 `clear()`→`addMarkers()`.
- 원형 마커가 위로 떠 보이면 → `MarkerImage`의 `offset`을 (size/2, size/2)로.

### VWorld 타일
```
https://api.vworld.kr/req/wmts/1.0.0/{인증키}/Base/{z}/{y}/{x}.png       기본
https://api.vworld.kr/req/wmts/1.0.0/{인증키}/Satellite/{z}/{y}/{x}.jpeg 영상
https://api.vworld.kr/req/wmts/1.0.0/{인증키}/Hybrid/{z}/{y}/{x}.png     지명 오버레이
```
키는 화면 "🔑 API 키"에서 입력 → localStorage. 소스에 키가 들어가지 않습니다.

---

## 4. 확인 체크리스트
- [ ] 상단 통계에 `115 / 115건 표시 · 매각기일 2026-09-02~2026-11-01`
- [ ] 카카오맵: 민트 클러스터 → 확대하면 개별 원형 마커 → 클릭 시 사건번호·물건번호·법원·감정가·최저가·유찰·매각기일·특수조건·비고 팝업
- [ ] 팝업의 "📷 이 위치 로드뷰 보기" → 우측 패널에 거리 사진, 지도에 파란 도로망 오버레이
- [ ] 배경 "스카이뷰" → 위성사진 위 마커
- [ ] 브이월드맵 전환 → VWorld 기본/영상 타일, 같은 115건 클러스터
- [ ] "서울플랜+ 구역" 토글 → 6색 폴리곤, "정비구역 내만" 체크 → 20건

---

## 5. 갱신하기
경매물건은 유찰·취하로 매일 바뀝니다. 세 줄을 다시 실행하면 `collect_runs`에 이력이 한 줄 늘고 지도가 갱신됩니다.
```
python scripts/collect_auction_seoul.py --days 60 && python scripts/load_auction_duckdb.py && python scripts/build_auction_map.py
```
범위를 넓히려면 `--days 90`, 용도를 바꾸려면 `--usage 다세대`.

## 6. 이 장에서 배운 것
1. 화면 스크래핑보다 화면이 부르는 **API를 직접 페이징**한다. 총건수와 수집건수를 반드시 대조한다.
2. 좌표계는 EPSG 번호를 추측하지 말고 **실제 지점과 대조해 확정**한다(TM128).
3. 코드→이름 매핑은 **원자료로 검증된 것만** 붙이고, 나머지는 코드 그대로 보여준다.
4. 정규화된 테이블은 DuckDB에 넣고, 지도는 그 테이블에서 뽑은 GeoJSON을 읽는다. 데이터와 표현을 분리한다.
5. 지도 엔진이 둘이어도 데이터는 하나. 팝업 HTML 생성 함수를 공유하면 두 엔진이 같은 정보를 보여준다.
