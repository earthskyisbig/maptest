# 06. 공공 SHP 파일을 카카오맵에 올리기 (따라하기)

> **목표** — 국토정보플랫폼에서 내려받은 SHP 압축파일 하나를, 더블클릭으로 열리는 카카오맵 HTML로 만든다.
> **소요** — 15분. **결과물** — `capital_zone_map.html` (수도권정비권역 541개 폴리곤, 구분별 on/off, 클릭 팝업)

---

## 0. 왜 이 실습인가

경매물건은 **점**(위경도 하나)이지만, 정비구역·권역·용도지역은 **면(폴리곤)** 입니다.
면 데이터는 API로 잘 주지 않고 대부분 **SHP(Shapefile)** 로 배포됩니다. 그래서 "SHP → 웹지도" 변환은 부동산 지도 만들기의 필수 기술입니다.

이번 예제 파일 `AL_D014_00_20260809.zip`은 **수도권정비계획법상 권역**(과밀억제·성장관리·자연보전)입니다.
어느 권역에 속하느냐에 따라 공장 신설, 대학 이전, 대규모 개발 허용 여부가 갈리므로 투자 판단에 직접 쓰입니다.

---

## 1. 준비물

| 항목 | 어디서 | 비고 |
|---|---|---|
| SHP 압축파일 | [국토정보플랫폼(VWorld) 다운로드](https://www.vworld.kr) → 공간정보 다운로드 → "수도권정비권역" 검색 | 파일명 `AL_D014_00_YYYYMMDD.zip` |
| 카카오 JavaScript 앱키 | [developers.kakao.com](https://developers.kakao.com) → 내 애플리케이션 → 앱 키 | 플랫폼 &gt; Web 사이트 도메인에 `http://localhost:8000` 등록 |
| Python 패키지 | `pip install geopandas` | pyproj·shapely가 함께 설치됨 |

> 압축을 풀면 `.shp .shx .dbf .prj .fix` 5개 파일이 나옵니다. **항상 세트로** 다뤄야 합니다.
> `.shp` 도형, `.dbf` 속성표, `.prj` 좌표계 정의. 하나라도 빠지면 읽지 못합니다.

---

## 2. SHP 안을 먼저 들여다보기 (프롬프트)

Claude Code에 이렇게 요청합니다.

```
C:\Users\<me>\Downloads\AL_D014_00_20260809.zip 압축 풀고 SHP의 좌표계, 건수, 필드, 각 필드 값 종류를 보여줘
```

확인해야 할 세 가지가 나옵니다.

```
crs   EPSG:5186            ← 중부원점 TM, 미터 단위. 웹지도(위경도 4326)와 다르다
rows  541                  ← Polygon 523 + MultiPolygon 18
A2    지역/수도권정비권역     ← 필드명이 A0~A9로 익명화되어 있다
A6    과밀억제권역 / 성장관리권역 / 자연보전권역
```

### 공공 SHP의 함정 3가지 (여기서 전부 나온다)

| 함정 | 증상 | 해결 |
|---|---|---|
| ① 좌표계 5186 | 지도에 올리면 아프리카 앞바다에 찍힘 | `to_crs(epsg=4326)` 재투영 |
| ② 인코딩 EUC-KR | 한글이 `����`로 깨짐 | `encoding="cp949"`로 읽기 |
| ③ 필드명 A0~A9 | 무슨 값인지 알 수 없음 | 매핑표로 이름 붙이기 (A4 시군구코드, A6 구분명…) |

---

## 3. 변환 실행 (프롬프트)

```
이 SHP를 표준 GeoJSON(WGS84, layer/id/name/category/color 5필드)으로 변환하는 스크립트를 scripts/에 만들고 실행해줘.
구분(과밀억제/성장관리/자연보전)별로 색을 다르게 하고, 지도 배경과 구분되는 색을 써줘
```

결과: `scripts/shp_to_geojson.py` 가 생기고 실행하면

```
python scripts/shp_to_geojson.py "C:/Users/<me>/Downloads/AL_D014_00_20260809.zip"
```

```json
{
  "layer": "zone_capital",
  "source_crs": "EPSG:5186",
  "count": 541,
  "category_counts": { "과밀억제권역": 153, "성장관리권역": 347, "자연보전권역": 41 }
}
저장: _workspace/layer_zone_capital.geojson  (2.8 MB)
```

스크립트 핵심 6줄만 이해하면 됩니다.

```python
gdf = gpd.read_file(shp, encoding="cp949")          # ② 인코딩
gdf = gdf.to_crs(epsg=4326)                          # ① 좌표계
gdf = gdf.rename(columns={"A4": "sgg_code", "A6": "type_name", ...})  # ③ 필드명
gdf["geometry"] = gdf.geometry.buffer(0).simplify(0.0001)  # 깨진 도형 보정 + 10m 단순화(용량↓)
props = {"layer": "zone_capital", "id": ..., "name": ..., "category": cat, "color": COLOR[cat]}
json.dump(FeatureCollection, ...)
```

> **단순화(simplify)를 왜 하나** — 원본 그대로면 4.6MB, 10m 단순화하면 2.8MB. 광역 권역은 10m 오차가 눈에 안 보입니다. 필지 단위 데이터라면 단순화 값을 0.00001(1m) 이하로 낮추세요.

---

## 4. 지도 HTML 만들기 (프롬프트)

```
_workspace/layer_zone_capital.geojson을 카카오맵에 폴리곤으로 올리는 단일 HTML을 만들어줘.
카카오 키는 화면에서 입력받아 localStorage에 저장하고, 구분별 체크박스 토글, 클릭하면 상세 팝업이 나오게 해줘
```

결과: `scripts/shp_map_template.html` + `scripts/build_shp_map.py` 가 생기고

```
python scripts/build_shp_map.py
→ 저장: capital_zone_map.html (2.8 MB)
```

### 왜 데이터를 HTML 안에 넣는가
브라우저는 `file://`로 연 페이지에서 다른 파일을 `fetch()`로 읽지 못합니다. 그래서 GeoJSON을 HTML 안에 `var DATA = {...}`로 심어 **더블클릭 한 번으로 열리는** 파일을 만듭니다. 이것이 `estate_map.html`이 11MB인 이유이기도 합니다.

### 카카오맵 폴리곤 핵심 코드

```js
// GeoJSON은 [경도, 위도], 카카오는 LatLng(위도, 경도) — 순서가 반대!
function ring2path(ring){ return ring.map(c => new kakao.maps.LatLng(c[1], c[0])); }

var rings = g.type === 'Polygon' ? [g.coordinates] : g.coordinates;  // MultiPolygon 대응
rings.forEach(polyCoords => {
  new kakao.maps.Polygon({
    map: map,
    path: polyCoords.map(ring2path),   // 첫 링=외곽, 나머지=구멍
    strokeColor: p.color, fillColor: p.color, fillOpacity: .28
  });
});
```

---

## 5. 열어서 확인

```
python -m http.server 8000
```
브라우저에서 `http://localhost:8000/capital_zone_map.html` 을 열고, 우측 상단에 카카오 JavaScript 키를 입력합니다.

체크리스트
- [ ] 서울·인천·경기 남부가 **빨강**(과밀억제), 경기 외곽이 **주황**(성장관리), 동부가 **초록**(자연보전)
- [ ] 좌상단 범례의 체크박스를 끄면 해당 색 폴리곤이 사라진다
- [ ] 폴리곤을 클릭하면 좌하단에 구분·시도·시군구코드·고시일이 나온다

지도가 안 나오면
| 증상 | 원인 |
|---|---|
| 회색 화면 + "SDK 로드 실패" | 앱키 오타, 또는 플랫폼 Web 도메인에 `http://localhost:8000` 미등록 |
| 지도는 나오는데 폴리곤이 없음 | 좌표계 변환 누락(5186 그대로). 콘솔에서 `DATA.features[0].geometry.coordinates[0][0]` 이 `[127.x, 37.x]` 인지 확인 |
| 한글이 `????` | `encoding="cp949"` 누락 |

---

## 6. 다른 SHP에도 그대로 쓰기

VWorld 도시계획 주제도는 파일명 코드만 다르고 구조(A0~A9)가 같습니다.

| 코드 | 내용 |
|---|---|
| D014 | 수도권정비권역 (이번 실습) |
| D027 / D029 | 정비구역·정비예정구역 |
| D314 / D316 | 개발행위허가제한·행위제한 |

`scripts/shp_to_geojson.py`의 `LAYER_ID`·`CATEGORY_COLOR` 두 곳만 바꾸면 됩니다.

```
D029 정비구역 SHP도 같은 방식으로 변환해서 layer_zone_redev.geojson을 갱신하고 estate_map.html에 반영해줘
```

---

## 6-2. 실습 2 — 서울플랜+ 도시계획사업(UQ120) SHP

서울시 도시계획포털 **서울플랜+** 에서 받은 `UQ120_도시계획사업(서울플랜+)_202602.zip`.
서울 전역 정비사업·모아타운·역세권사업·재정비촉진·공공주택지구 **2,585개 구역**입니다. 기존 `estate_map.html`의 정비구역 레이어 원본이 바로 이 데이터입니다.

### VWorld 주제도와 다른 점 3가지

| 항목 | VWorld (D014) | 서울플랜+ (UQ120) |
|---|---|---|
| 좌표계 | EPSG:5186 (GRS80) | **EPSG:5174** (Bessel 구 중부원점). `.prj`를 꼭 확인 |
| 필드명 | A0~A9 익명 | `LCLAS_CL`, `SCLAS_CL`, `PROPEL_CD`, `SIGNGU_SE` 등 UPIS 표준명 |
| 값 | 한글 그대로 | **전부 코드**(BZ101, PP0204…). 압축파일에 동봉된 `코드정의표.xlsx`로 한글명을 붙여야 함 |

> `.sbn .sbx .shp.xml`이 더 들어 있어도 무시해도 됩니다. ArcGIS 인덱스·메타데이터 파일입니다.

### 프롬프트

```
C:\Users\<me>\Downloads\UQ120_도시계획사업(서울플랜+)_202602.zip를 해줘.
아까것(수도권정비권역)은 따로 저장해둬
```

결과: `scripts/seoulplan_to_geojson.py` → `_workspace/layer_zone_redev_seoulplan.geojson` → `seoul_redev_map.html`

```
python scripts/seoulplan_to_geojson.py "C:/Users/<me>/Downloads/UQ120_도시계획사업(서울플랜+)_202602.zip"
python scripts/build_shp_map.py _workspace/layer_zone_redev_seoulplan.geojson seoul_redev_map.html "서울 도시계획사업(서울플랜+) 지도"
```

### 코드표 붙이기 (핵심)

```python
x = pd.ExcelFile("서울플랜+코드정의표(대민용).xlsx")
s1 = x.parse("01. 사업유형_코드")      # LCLAS_CL/SCLAS_CL → 사업유형 한글명
s2 = x.parse("02. 추진단계_코드")      # PROPEL_CD → 추진단계 한글명
lclas  = dict(zip(s1["LCLAS_CL"], s1.iloc[:, 0].ffill().str.strip()))   # BZ100 → 정비사업
sclas  = dict(zip(s1["SCLAS_CL"], s1.iloc[:, 3]))                       # BZ202 → 가로주택정비사업
propel = dict(zip(s2["PROPEL_CD"], s2.iloc[:, 3]))                      # PP0206 → 조합설립인가
```

대분류 6개 분포: 소규모 정비사업 1,014 · 정비사업 740 · 역세권사업 311 · 재정비촉진사업 293 · 기타사업 173 · 국토부사업 54

### 실패담 — 자치구 이름을 행 순서로 붙이면 80%가 틀린다

이전 버전 `정비구역.geojson`은 자치구명을 **행 순서대로** 대입해 80.7%가 틀렸고, `BZ200`(소규모 정비사업) 1,014건을 "재건축"으로 잘못 붙였습니다.
반드시 `SIGNGU_SE` **코드를 키로** 매핑하고(11680 → 강남구), 사업유형은 동봉된 **공식 코드표**로 붙이세요. 눈대중 추측 금지.

### 확인 체크리스트
- [ ] 서울 안에만 폴리곤이 찍힌다 (5174 재투영이 빠지면 지도 밖으로 나감)
- [ ] 범례에 6개 대분류가 보이고 체크박스로 켜고 끌 수 있다
- [ ] 폴리곤 클릭 시 사업유형(소분류)·추진단계·자치구·면적이 팝업에 나온다 — 예) 남산 일대 / 도시재생활성화지역 / 활성화계획수립 / 중구 / 3,295,806㎡

---

## 6-3. 실습 3 — VWorld 최신 정비구역(D029) + 재정비촉진지구(D314) 합치기 ★ 기준 데이터

서울플랜+ 자료는 2026년 2월 기준이라 최신이 아닙니다. VWorld 국토정보플랫폼에서 **2026-08-06 기준**으로 새로 받은 두 파일을 기준 데이터로 씁니다.

| 파일 | 주제도 | 건수 | 범위 |
|---|---|---|---|
| `AL_D029_00_20260809.zip` | 도시및주거환경정비 / **정비구역** | 2,231 | 전국 (서울 776 · 경기 355 · 부산 348 · 인천 118 …) |
| `AL_D314_00_20260809.zip` | 도시재정비 / **재정비촉진지구** | 243 | 전국 (대전 89 · 서울 70 · 부산 46 …) |

둘 다 D014와 같은 VWorld 표준 형식(A0~A9, EPSG:5186)이라 **변환기를 고치지 않고 파일만 바꿔 넣으면 됩니다.**
변환기는 파일명의 주제도 코드(`_D029_`, `_D314_`)를 읽어 레이어 이름과 색을 자동으로 고릅니다.

### 프롬프트

```
서울것은 26년2월 업데이트된 것이라 최근 것이 없다.
C:\Users\<me>\Downloads\AL_D029_00_20260809.zip, C:\Users\<me>\Downloads\AL_D314_00_20260809.zip가 브이월드에서 다운받은 자료이다. 이걸 기준으로 작업해보자
```

### 실행

```
python scripts/shp_to_geojson.py "C:/Users/<me>/Downloads/AL_D029_00_20260809.zip" _workspace/layer_zone_redev_vworld.geojson
python scripts/shp_to_geojson.py "C:/Users/<me>/Downloads/AL_D314_00_20260809.zip" _workspace/layer_zone_promo.geojson
python scripts/build_shp_map.py -o vworld_zone_map.html -t "정비구역·재정비촉진지구 지도 (VWorld 2026-08)" _workspace/layer_zone_redev_vworld.geojson _workspace/layer_zone_promo.geojson
```

빌드 스크립트에 GeoJSON을 **여러 개** 주면 한 지도에 합쳐지고, 범례가 레이어별로 묶입니다.

```
정비구역              재정비촉진지구
 ☑ 정비구역     2031   ☑ 재정비촉진지구     149
 ☑ 정비구역기타  191   ☑ 재정비촉진지구기타  94
 ☑ 정비구역미분류  9
```

### 여기서 새로 배우는 것 — 같은 형식이라도 "이름 필드"가 다르다

| 주제도 | A8 (사업명) | A9 (구역명) | 팝업 제목으로 쓸 것 |
|---|---|---|---|
| D029 정비구역 | `도렴도시환경정비사업` | `효제1구역` | **A9** 구역명 |
| D314 재정비촉진지구 | `천호4구역` | `자세한사항은 서울시고시 제2026-272호 참조` | **A8** (A9는 비고성 문구) |

같은 A0~A9 배치인데 기관마다 A8/A9에 넣는 내용이 다릅니다. **변환 전에 반드시 샘플 5행을 눈으로 보고** 어느 필드를 이름으로 쓸지 정하세요. 변환기에는 주제도별 `name_fields` 우선순위로 반영돼 있습니다.

### 확인 체크리스트
- [ ] 범례가 정비구역 / 재정비촉진지구 두 그룹으로 나뉘고 총 5개 체크박스가 보인다
- [ ] "정비구역" 체크를 끄면 보라색 폴리곤 2,031개가 모두 사라진다
- [ ] 지도를 부산·대전으로 옮겨도 폴리곤이 있다 (전국 데이터)
- [ ] 폴리곤 클릭 시 레이어명·구역명·사업명·시도·고시일이 나온다

### 다음 단계
이 두 레이어(`layer_zone_redev_vworld.geojson`, `layer_zone_promo.geojson`)를 `estate_map.html`의 정비구역 레이어와 교체하면 경매물건과 최신 정비구역을 한 지도에서 볼 수 있습니다.

```
estate_map.html의 정비구역 레이어를 _workspace/layer_zone_redev_vworld.geojson으로 교체하고 재정비촉진지구 레이어를 추가해줘
```

---

## 7. 이 장에서 배운 것

1. 면 데이터는 SHP로 온다. `.shp .shx .dbf .prj`는 세트다.
2. 공공 SHP 함정 3가지: **좌표계 5186 → 4326**, **cp949**, **A0~A9 필드명**.
3. GeoJSON은 `[경도, 위도]`, 카카오는 `LatLng(위도, 경도)`. 순서가 반대다.
4. 단일 HTML로 배포하려면 데이터를 파일 안에 심는다.
5. 변환 스크립트 하나면 VWorld 주제도 전체를 같은 방식으로 지도화할 수 있다.
6. 코드로 오는 데이터(서울플랜+)는 동봉된 코드표로 한글명을 붙이고, 자치구는 코드를 키로 매핑한다.
7. 같은 A0~A9 형식이라도 A8/A9 내용은 주제도마다 다르다. 샘플 5행을 보고 이름 필드를 정한다.
8. 기준일이 최신인 소스를 기준 데이터로 삼는다 (서울플랜+ 2026-02 < VWorld 2026-08).
