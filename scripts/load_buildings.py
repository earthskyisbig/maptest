"""
GIS건물통합정보(VWorld D010) SHP → DuckDB 적재 + 경매물건 필지의 건물 윤곽 GeoJSON

입력: AL_D010_11_20260809.zip (11=서울, 건물 폴리곤 69.6만 동, EPSG:5186, dbf 1.3GB)
출력: data/estate.duckdb 테이블 buildings (속성만, 폴리곤 제외)
      _workspace/layer_buildings_auction.geojson (경매물건 필지(PNU)에 있는 건물 윤곽만, WGS84)

메모리를 아끼는 방식 (69.6만 동 폴리곤을 한 번에 올리면 16GB PC에서도 실패했다)
  1. 속성은 도형을 읽지 않고(read_geometry=False) 2.5만 행씩 DuckDB에 넣는다
  2. 도형은 경매물건 필지 PNU만 OGR where 절(A2 IN (...))로 골라 읽는다 → 수백 동만 메모리에 올라온다

필드 배치 (VWorld GIS건물통합정보 표준)
  A1 건물ID · A2 PNU · A3 법정동코드 · A4 법정동명 · A5 지번 · A7 특수지(일반/산)
  A8/A9 건축물용도코드/명 · A10/A11 구조코드/명 · A12 건축면적 · A13 사용승인일 · A14 연면적 · A15 대지면적
  A16 높이 · A17 건폐율 · A18 용적률 · A19 건축물ID · A20 위반건축물여부 · A22 데이터기준일 · A24 건물명 · A25 동명
  A26 지상층수 · A27 지하층수 · A28 생성변경일

사용법
  python scripts/load_buildings.py "C:/Users/me/Downloads/AL_D010_11_20260809.zip"
  python scripts/load_buildings.py "...zip" --footprints-only   # 경매물건 갱신 후 건물 윤곽만 다시 뽑기
"""

import json
import sys
import zipfile
from pathlib import Path

import duckdb
import pandas as pd
import pyogrio

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "estate.duckdb"
OUT = ROOT / "_workspace" / "layer_buildings_auction.geojson"
FIELDS = {"A1": "bld_id", "A2": "pnu", "A3": "bjd_code", "A4": "bjd_name", "A5": "jibun", "A7": "land_type",
          "A8": "use_code", "A9": "use_name", "A10": "struct_code", "A11": "struct_name", "A12": "bld_area_m2",
          "A13": "approval_date", "A14": "total_floor_area_m2", "A15": "land_area_m2", "A16": "height_m",
          "A17": "bcr_pct", "A18": "far_pct", "A19": "arch_id", "A20": "violation", "A22": "base_date",
          "A24": "bld_name", "A25": "dong_name", "A26": "floors_above", "A27": "floors_below", "A28": "updated"}
NUM = ["bld_area_m2", "total_floor_area_m2", "land_area_m2", "height_m", "bcr_pct", "far_pct", "floors_above", "floors_below"]
STEP = 10_000


def load_attributes(shp: Path, con, n_total: int):
    """도형 없이 속성만 배치로 읽어 buildings 테이블을 만든다."""
    con.execute("DROP TABLE IF EXISTS buildings")
    first = True
    for start in range(0, n_total, STEP):
        df = pyogrio.read_dataframe(shp, encoding="cp949", read_geometry=False, skip_features=start, max_features=STEP,
                                    columns=list(FIELDS.keys()))
        df = df.rename(columns=FIELDS)
        for c in NUM:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        con.register("_chunk", df)
        con.execute("CREATE TABLE buildings AS SELECT * FROM _chunk" if first else "INSERT INTO buildings SELECT * FROM _chunk")
        con.unregister("_chunk"); first = False
        del df
        print(f"  속성 {min(start + STEP, n_total):,}/{n_total:,}")
    con.execute("CREATE INDEX IF NOT EXISTS idx_bld_pnu ON buildings(pnu)")


def export_footprints(shp: Path, pnus: set) -> list:
    """경매물건 필지 PNU에 해당하는 건물 도형만 where 절로 골라 WGS84 GeoJSON feature 로."""
    feats = []
    pnus = sorted(p for p in pnus if p)
    for i in range(0, len(pnus), 150):
        chunk = pnus[i:i + 150]
        where = "A2 IN (" + ",".join(f"'{p}'" for p in chunk) + ")"
        gdf = pyogrio.read_dataframe(shp, encoding="cp949", where=where, columns=list(FIELDS.keys()))
        if not len(gdf):
            continue
        gdf = gdf.rename(columns=FIELDS).to_crs(epsg=4326)
        for r in gdf.itertuples(index=False):
            props = {k: (None if pd.isna(getattr(r, k)) else getattr(r, k)) for k in FIELDS.values() if hasattr(r, k)}
            feats.append({"type": "Feature",
                          "properties": {"layer": "building", "id": props.get("bld_id"),
                                         "name": props.get("bld_name") or props.get("use_name") or "건물",
                                         "category": props.get("use_name") or "기타", "color": "#0f766e", **props},
                          "geometry": r.geometry.__geo_interface__})
        del gdf
    return feats


def main():
    footprints_only = "--footprints-only" in sys.argv
    src = Path([x for x in sys.argv[1:] if not x.startswith("--")][0])
    work = ROOT / "raw" / src.stem
    work.mkdir(parents=True, exist_ok=True)
    if not list(work.glob("*.shp")):
        with zipfile.ZipFile(src) as z:
            z.extractall(work)
    shp = next(work.glob("*.shp"))
    n_total = pyogrio.read_info(shp)["features"]
    con = duckdb.connect(str(DB))
    con.execute("SET memory_limit='400MB'"); con.execute("SET threads=2")   # 메모리가 빡빡한 PC에서도 돌아가게

    if not footprints_only:
        print(f"건물 {n_total:,}동 속성 적재 시작 (배치 {STEP:,}, 도형 제외)")
        load_attributes(shp, con, n_total)
        n = con.execute("SELECT count(*), count(DISTINCT pnu) FROM buildings").fetchone()
        print(f"buildings: {n[0]:,}동 · 필지 {n[1]:,}")
        print(con.execute("SELECT use_name, count(*) FROM buildings GROUP BY 1 ORDER BY 2 DESC LIMIT 6").fetchall())

    try:
        pnus = {r[0] for r in con.execute("SELECT DISTINCT pnu FROM auction_apt_seoul WHERE pnu IS NOT NULL").fetchall()}
    except duckdb.CatalogException:
        pnus = set()
    con.close()
    feats = export_footprints(shp, pnus) if pnus else []
    OUT.write_text(json.dumps({"type": "FeatureCollection", "meta": {"layer": "building", "title": "경매물건 필지 건물 윤곽",
                   "source": f"VWorld GIS건물통합정보 {shp.name}", "count": len(feats), "pnus": len(pnus)}, "features": feats},
                   ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")
    print(f"윤곽 GeoJSON: {OUT} ({len(feats)}동, 경매 필지 {len(pnus)}개)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
