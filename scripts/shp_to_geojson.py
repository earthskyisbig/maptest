"""
공공 SHP(Shapefile) → 웹지도용 GeoJSON 변환기  (VWorld 국토정보플랫폼 주제도 공통)

수강생 따라하기용. VWorld에서 내려받은 SHP 압축파일(AL_Dxxx_00_YYYYMMDD.zip)을 넣으면
카카오맵에 바로 올릴 수 있는 표준 GeoJSON을 만든다. 파일명의 주제도 코드(D014/D029/D314…)를
보고 레이어 이름·색상을 자동으로 고른다.

처리하는 함정 3가지
  1. 좌표계: 공공 SHP는 EPSG:5186(중부원점 TM, 미터 단위) → 웹지도는 EPSG:4326(위경도)로 재투영
  2. 인코딩: 속성이 EUC-KR/CP949 → 그대로 읽으면 한글이 깨짐
  3. 필드명: A0~A9로 익명화 → 의미 있는 이름으로 바꿔 준다

사용법
  python scripts/shp_to_geojson.py <zip 또는 shp 경로> [출력 geojson 경로]

예)
  python scripts/shp_to_geojson.py "C:/Users/me/Downloads/AL_D029_00_20260809.zip"
  → _workspace/layer_zone_redev.geojson
"""

import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import geopandas as gpd

# ── 1. VWorld 도시계획 주제도 공통 속성 배치 (D014/D027/D029/D314/D316 동일) ──
FIELDS = {
    "A0": "seq",          # 일련번호
    "A1": "mgmt_no",      # 관리번호
    "A2": "theme",        # 주제도명 (예: 도시및주거환경정비/정비구역)
    "A3": "base_date",    # 데이터 기준일
    "A4": "sgg_code",     # 시군구 법정동코드(5자리)
    "A5": "type_code",    # 구분코드 (UDT100 등)
    "A6": "type_name",    # 구분명 (정비구역 등) → category
    "A7": "notice_date",  # 고시일
    "A8": "name_raw",     # 사업명
    "A9": "zone_name",    # 구역명
}

# ── 2. 주제도 코드별 프로필: 레이어 id, 표시명, 구분별 색 ──
PROFILES = {
    "D014": {
        "layer": "zone_capital", "title": "수도권정비권역",
        "colors": {"과밀억제권역": "#e74c3c", "성장관리권역": "#f39c12", "자연보전권역": "#27ae60"},
    },
    "D029": {
        "layer": "zone_redev", "title": "정비구역", "name_fields": ("zone_name", "name_raw"),
        "colors": {"정비구역": "#8e44ad", "정비구역기타": "#b58ccf", "정비구역미분류": "#95a5a6"},
    },
    "D027": {
        "layer": "zone_redev_planned", "title": "정비예정구역",
        "colors": {},
    },
    "D314": {
        "layer": "zone_promo", "title": "재정비촉진지구", "name_fields": ("name_raw", "zone_name"),  # A9는 비고성 문구
        "colors": {"재정비촉진지구": "#c0392b", "재정비촉진지구기타": "#e59866"},
    },
    "D316": {
        "layer": "zone_restrict", "title": "행위제한구역",
        "colors": {},
    },
}
FALLBACK_PALETTE = ["#8e44ad", "#e67e22", "#2980b9", "#c0392b", "#16a085", "#7f8c8d", "#d35400", "#2c3e50"]

# ── 3. 시도 코드 → 이름 (법정동코드 앞 2자리) ──
SIDO = {
    "11": "서울특별시", "12": "부산광역시", "26": "부산광역시", "27": "대구광역시", "28": "인천광역시",
    "29": "광주광역시", "30": "대전광역시", "31": "울산광역시", "36": "세종특별자치시",
    "41": "경기도", "42": "강원도", "43": "충청북도", "44": "충청남도", "45": "전라북도",
    "46": "전라남도", "47": "경상북도", "48": "경상남도", "50": "제주특별자치도",
    "51": "강원특별자치도", "52": "전북특별자치도",
}
SEOUL_GU = {
    "11110": "종로구", "11140": "중구", "11170": "용산구", "11200": "성동구", "11215": "광진구",
    "11230": "동대문구", "11260": "중랑구", "11290": "성북구", "11305": "강북구", "11320": "도봉구",
    "11350": "노원구", "11380": "은평구", "11410": "서대문구", "11440": "마포구", "11470": "양천구",
    "11500": "강서구", "11530": "구로구", "11545": "금천구", "11560": "영등포구", "11590": "동작구",
    "11620": "관악구", "11650": "서초구", "11680": "강남구", "11710": "송파구", "11740": "강동구",
}

SIMPLIFY_DEG = {"zone_capital": 0.0001}   # 광역 권역만 10m, 나머지 구역 단위는 2m
DEFAULT_SIMPLIFY = 0.00002


def find_shp(src: Path, workdir: Path) -> Path:
    """zip이면 raw/ 아래에 풀고 .shp 경로를 돌려준다."""
    if src.suffix.lower() == ".zip":
        out = workdir / src.stem
        out.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src) as z:
            z.extractall(out)
        return next(out.rglob("*.shp"))
    return src


def detect_profile(shp: Path) -> tuple[str, dict]:
    m = re.search(r"_(D\d{3})_", shp.name)
    code = m.group(1) if m else "UNKNOWN"
    prof = PROFILES.get(code, {"layer": f"zone_{code.lower()}", "title": code, "colors": {}})
    return code, prof


def convert(shp: Path, out: Path | None) -> tuple[dict, Path]:
    code, prof = detect_profile(shp)
    layer = prof["layer"]
    root = Path(__file__).resolve().parent.parent
    out = out or root / "_workspace" / f"layer_{layer}.geojson"

    gdf = gpd.read_file(shp, encoding="cp949")              # 함정 2: cp949
    src_crs, n_src = str(gdf.crs), len(gdf)
    gdf = gdf.to_crs(epsg=4326)                              # 함정 1: 재투영
    gdf = gdf.rename(columns={k: v for k, v in FIELDS.items() if k in gdf.columns})  # 함정 3: 필드명
    tol = SIMPLIFY_DEG.get(layer, DEFAULT_SIMPLIFY)
    gdf["geometry"] = gdf.geometry.buffer(0).simplify(tol, preserve_topology=True)
    gdf = gdf[~gdf.geometry.is_empty]

    colors = dict(prof["colors"])
    features, cat_counts, sido_counts = [], {}, {}
    for i, r in enumerate(gdf.itertuples(index=False), start=1):
        cat = str(getattr(r, "type_name", "") or "기타")
        if cat not in colors:
            colors[cat] = FALLBACK_PALETTE[len(colors) % len(FALLBACK_PALETTE)]
        sgg = str(getattr(r, "sgg_code", "") or "")
        sido = SIDO.get(sgg[:2], "")
        gu = SEOUL_GU.get(sgg, "")
        nf = prof.get("name_fields", ("zone_name", "name_raw"))
        first = getattr(r, nf[0], None) or ""
        second = getattr(r, nf[1], None) or ""
        name = first or second or f"{cat} ({sido} {sgg})".strip()
        biz = second if second != name else ""
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        sido_counts[sido] = sido_counts.get(sido, 0) + 1
        props = {
            # 표준 5필드 (geojson-schema.md)
            "layer": layer, "id": f"{layer}_{i:04d}", "name": name,
            "category": cat, "color": colors[cat],
            # 확장 필드
            "subtype": biz if biz and biz != name else None,
            "sido": sido, "sigungu": gu or None, "sgg_code": sgg,
            "type_code": getattr(r, "type_code", None),
            "notice_date": getattr(r, "notice_date", None),
            "note": None,
            "mgmt_no": getattr(r, "mgmt_no", None),
        }
        features.append({
            "type": "Feature",
            "properties": {k: v for k, v in props.items() if v not in (None, "")},
            "geometry": r.geometry.__geo_interface__,
        })

    theme = str(gdf["theme"].iloc[0]) if "theme" in gdf.columns else ""
    base_date = str(gdf["base_date"].iloc[0])[:10] if "base_date" in gdf.columns else ""
    fc = {
        "type": "FeatureCollection",
        "meta": {
            "layer": layer, "title": prof["title"], "theme_code": code,
            "source": f"VWorld 국토정보플랫폼 SHP {shp.name} ({theme})",
            "source_crs": src_crs,
            "collected_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "base_date": base_date,
            "count": len(features), "count_source": n_src,
            "category_counts": dict(sorted(cat_counts.items(), key=lambda kv: -kv[1])),
            "sido_counts": dict(sorted(sido_counts.items(), key=lambda kv: -kv[1])),
        },
        "features": features,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return fc["meta"], out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    root = Path(__file__).resolve().parent.parent
    shp = find_shp(Path(sys.argv[1]), root / "raw")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    meta, out = convert(shp, out)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"\n저장: {out}  ({out.stat().st_size/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()
