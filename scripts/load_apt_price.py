"""
공동주택가격(공시가격) CSV → DuckDB 적재

입력: VWorld 국토정보플랫폼 D167 공동주택가격정보 zip (예: AL_D167_11_20260519.zip, 11=서울)
      안에 CSV 하나 (cp949 인코딩, 호 단위 278만 행)
출력: data/estate.duckdb 테이블 apt_price  (호 단위) + apt_price_complex (단지·면적별 요약 뷰)

컬럼: 고유번호(PNU 19자리) · 법정동코드 · 법정동명 · 지번 · 기준연도 · 기준월 · 공동주택코드 · 공동주택구분명(아파트/연립/빌라…)
      · 공동주택명 · 동명 · 층명 · 호명 · 전용면적 · 공시가격 · 데이터기준일자

사용법
  python scripts/load_apt_price.py "C:/Users/me/Downloads/AL_D167_11_20260519.zip"
"""

import io
import sys
import zipfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "estate.duckdb"


def main():
    src = Path(sys.argv[1])
    work = ROOT / "raw" / src.stem
    work.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as z:
        z.extractall(work)
    csv_cp949 = next(work.glob("*.csv"))
    csv_utf8 = work / (csv_cp949.stem + "_utf8.csv")
    if not csv_utf8.exists():
        # DuckDB는 cp949를 직접 읽지 못한다 → utf-8로 스트리밍 변환 (400MB)
        with open(csv_cp949, "r", encoding="cp949", errors="replace", newline="") as fi, \
             open(csv_utf8, "w", encoding="utf-8", newline="") as fo:
            for chunk in iter(lambda: fi.read(1 << 20), ""):
                fo.write(chunk)
    con = duckdb.connect(str(DB))
    con.execute(f"""
        CREATE OR REPLACE TABLE apt_price AS
        SELECT 고유번호 AS pnu, 법정동코드 AS bjd_code, 법정동명 AS bjd_name,
               특수지구분코드 AS land_type_code, 특수지구분명 AS land_type, 지번 AS jibun,
               기준연도 AS base_year, 기준월 AS base_month,
               공동주택코드 AS complex_code, 공동주택구분명 AS housing_type,
               공동주택명 AS complex_name, 동명 AS dong, 층명 AS floor, 호명 AS unit,
               TRY_CAST(전용면적 AS DOUBLE) AS area_m2, TRY_CAST(공시가격 AS BIGINT) AS price,
               데이터기준일자 AS data_date
        FROM read_csv('{csv_utf8.as_posix()}', header=true, all_varchar=true)
    """)
    con.execute("""
        CREATE OR REPLACE VIEW apt_price_complex AS
        SELECT pnu, complex_name, housing_type, round(area_m2, 2) AS area_m2,
               count(*) AS units, min(price) AS price_min, round(avg(price)) AS price_avg, max(price) AS price_max
        FROM apt_price GROUP BY 1,2,3,4
    """)
    n = con.execute("SELECT count(*), count(DISTINCT pnu), count(DISTINCT complex_name) FROM apt_price").fetchone()
    print(f"apt_price: {n[0]:,}호 · 필지 {n[1]:,} · 단지명 {n[2]:,}")
    print(con.execute("SELECT housing_type, count(*) FROM apt_price GROUP BY 1 ORDER BY 2 DESC").fetchall())
    print(con.execute("SELECT base_year, base_month, data_date, count(*) FROM apt_price GROUP BY 1,2,3").fetchall())
    con.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
