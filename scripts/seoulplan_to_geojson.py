"""
서울플랜+ 도시계획사업(UQ120) SHP → 웹지도용 GeoJSON 변환기

서울시 도시계획포털 "서울플랜+"에서 내려받은 UQ120(도시계획사업) 압축파일을 넣으면
정비사업·모아타운·역세권사업·재정비촉진·공공주택·기타 6개 대분류로 색을 나눈
표준 GeoJSON(layer: zone_redev)을 만든다.

VWorld 주제도(A0~A9)와 다른 점
  1. 좌표계: EPSG:5174 (Bessel 타원체, 구 중부원점) — 5186과 다르니 .prj를 꼭 확인
  2. 필드명이 UPIS 표준(LCLAS_CL, SCLAS_CL, PROPEL_CD, SIGNGU_SE …)이라 익명은 아니지만
     값이 전부 코드(BZ101, PP0204 …) → 동봉된 코드정의표(xlsx)로 한글명을 붙여야 한다
  3. 자치구는 SIGNGU_SE(법정동코드 5자리)로만 온다 → 코드→이름 표로 붙인다 (행 순서 대입 금지)

사용법
  python scripts/seoulplan_to_geojson.py <zip 경로> [출력 geojson 경로]
"""

import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

LAYER_ID = "zone_redev"
SIMPLIFY_DEG = 0.00002  # 약 2m. 구역 단위 폴리곤이라 권역보다 촘촘하게

# 대분류(LCLAS_CL) → 색. 경매 마커(민트)·배경과 구분
LCLAS_COLOR = {
    "BZ100": "#8e44ad",  # 정비사업(재개발·재건축·신통기획) 바이올렛
    "BZ200": "#e67e22",  # 소규모 정비사업(모아타운·가로주택) 주황
    "BZ300": "#2980b9",  # 역세권사업 파랑
    "BZ400": "#c0392b",  # 재정비촉진사업 빨강
    "BZ500": "#16a085",  # 국토부사업(공공주택지구) 청록
    "BZ600": "#7f8c8d",  # 기타사업 회색
}

SEOUL_GU = {
    "11110": "종로구", "11140": "중구", "11170": "용산구", "11200": "성동구", "11215": "광진구",
    "11230": "동대문구", "11260": "중랑구", "11290": "성북구", "11305": "강북구", "11320": "도봉구",
    "11350": "노원구", "11380": "은평구", "11410": "서대문구", "11440": "마포구", "11470": "양천구",
    "11500": "강서구", "11530": "구로구", "11545": "금천구", "11560": "영등포구", "11590": "동작구",
    "11620": "관악구", "11650": "서초구", "11680": "강남구", "11710": "송파구", "11740": "강동구",
}


def extract(src: Path, workdir: Path) -> Path:
    out = workdir / "UQ120_seoulplan"
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as z:
        z.extractall(out)
    return out


def load_codes(folder: Path):
    """동봉된 코드정의표 xlsx → {코드: 한글명} 3개 사전."""
    xlsx = next(folder.rglob("*.xlsx"))
    x = pd.ExcelFile(xlsx)
    s1 = x.parse(x.sheet_names[0], header=0)
    s2 = x.parse(x.sheet_names[1], header=0)
    lclas = dict(zip(s1["LCLAS_CL"], s1.iloc[:, 0].ffill().str.strip()))         # BZ100 → 정비사업
    sclas = dict(zip(s1["SCLAS_CL"], s1.iloc[:, 3].astype(str).str.strip()))                  # BZ102 → 재개발(도시정비형)
    propel = dict(zip(s2["PROPEL_CD"], s2.iloc[:, 3].astype(str).str.strip()))                # PP0204 → 구역지정
    return lclas, sclas, propel


def convert(folder: Path, out: Path) -> dict:
    shp = next(folder.rglob("*.shp"))
    lclas, sclas, propel = load_codes(folder)

    gdf = gpd.read_file(shp, encoding="cp949")
    src_crs = str(gdf.crs)
    n_src = len(gdf)
    gdf = gdf.to_crs(epsg=4326)
    gdf["geometry"] = gdf.geometry.buffer(0).simplify(SIMPLIFY_DEG, preserve_topology=True)
    gdf = gdf[~gdf.geometry.is_empty]

    features, cat_counts, gu_counts = [], {}, {}
    for i, r in enumerate(gdf.itertuples(index=False), start=1):
        lc = r.LCLAS_CL or ""
        cat = lclas.get(lc, "기타사업")
        gu = SEOUL_GU.get(str(r.SIGNGU_SE), str(r.SIGNGU_SE))
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        gu_counts[gu] = gu_counts.get(gu, 0) + 1
        props = {
            "layer": LAYER_ID,
            "id": f"redev_{i:04d}",
            "name": r.DGM_NM or f"{cat} {i}",
            "category": cat,
            "color": LCLAS_COLOR.get(lc, "#7f8c8d"),
            "subtype": sclas.get(r.SCLAS_CL, r.SCLAS_CL),
            "stage": propel.get(r.PROPEL_CD, r.PROPEL_CD),
            "sido": "서울특별시",
            "sigungu": gu,
            "sgg_code": str(r.SIGNGU_SE),
            "area_m2": round(float(r.DGM_AR)) if r.DGM_AR else None,
            "base_date": str(r.CREATE_DAT)[:10] if r.CREATE_DAT else None,
            "present_sn": r.PRESENT_SN,
        }
        features.append({
            "type": "Feature",
            "properties": {k: v for k, v in props.items() if v not in (None, "")},
            "geometry": r.geometry.__geo_interface__,
        })

    fc = {
        "type": "FeatureCollection",
        "meta": {
            "layer": LAYER_ID, "title": "서울 도시계획사업(서울플랜+)",
            "source": f"서울플랜+ 도시계획사업 UQ120 ({shp.name}, 서울 25개 자치구)",
            "source_crs": src_crs,
            "collected_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "base_date": str(gdf["CREATE_DAT"].max())[:10],
            "count": len(features),
            "count_source": n_src,
            "category_counts": dict(sorted(cat_counts.items(), key=lambda kv: -kv[1])),
            "region_counts": dict(sorted(gu_counts.items(), key=lambda kv: -kv[1])),
        },
        "features": features,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return fc["meta"]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    root = Path(__file__).resolve().parent.parent
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "_workspace" / "layer_zone_redev_seoulplan.geojson"
    folder = extract(src, root / "raw") if src.suffix.lower() == ".zip" else src
    meta = convert(folder, out)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"\n저장: {out}  ({out.stat().st_size/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()
