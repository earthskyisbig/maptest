#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""분당구 생활인프라 POI 수집 → layer_infra.geojson (Overpass API)"""
import json, time, sys
from datetime import datetime, timezone, timedelta
import requests

# 분당구 bbox: 위도 37.31–37.42, 경도 127.06–127.16
BBOX = (37.31, 127.06, 37.42, 127.16)  # (south, west, north, east)
OUT = r"C:\Users\m9938\maptest\_workspace\layer_infra.geojson"

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

CATS = {
    "school":   {"color": "#f39c12", "default": "학교",
                 "q": '(node["amenity"="school"](%s);way["amenity"="school"](%s);)'},
    "hospital": {"color": "#e74c3c", "default": "병원",
                 "q": '(node["amenity"~"^(hospital|clinic)$"](%s);way["amenity"~"^(hospital|clinic)$"](%s);)'},
    "mart":     {"color": "#16a085", "default": "마트",
                 "q": '(node["shop"~"^(supermarket|mall)$"](%s);way["shop"~"^(supermarket|mall)$"](%s);)'},
    "subway":   {"color": "#2980b9", "default": "역",
                 "q": '(node["railway"="station"](%s);way["railway"="station"](%s);)'},
}


def run_query(cat_q, bbox, timeout_s=60):
    s, w, n, e = bbox
    b = f"{s},{w},{n},{e}"
    body = f"[out:json][timeout:{timeout_s}];{cat_q % (b, b)};out center tags;"
    last_err = None
    for url in ENDPOINTS:
        try:
            r = requests.post(url, data={"data": body}, timeout=timeout_s + 30,
                              headers={"User-Agent": "poi-collector/1.0"})
            r.raise_for_status()
            return r.json().get("elements", [])
        except Exception as ex:
            last_err = ex
            print(f"    endpoint 실패 {url.split('/')[2]}: {ex}", file=sys.stderr)
            time.sleep(2)
    raise RuntimeError(f"모든 endpoint 실패: {last_err}")


def split_bbox(bbox):
    s, w, n, e = bbox
    mlat, mlon = (s + n) / 2, (w + e) / 2
    return [(s, w, mlat, mlon), (s, mlon, mlat, e),
            (mlat, w, n, mlon), (mlat, mlon, n, e)]


def collect_cat(cat, cfg):
    try:
        els = run_query(cfg["q"], BBOX)
    except Exception as ex:
        print(f"  {cat}: bbox 전체 실패({ex}) → 4분할 재시도", file=sys.stderr)
        els = []
        for sb in split_bbox(BBOX):
            try:
                els += run_query(cfg["q"], sb, timeout_s=45)
                time.sleep(1)
            except Exception as ex2:
                print(f"    분할 {sb} 실패: {ex2}", file=sys.stderr)
    return els


def main():
    kst = timezone(timedelta(hours=9))
    features, counts, seen = [], {}, set()
    s, w, n, e = BBOX

    for cat, cfg in CATS.items():
        print(f"수집: {cat} ...")
        els = collect_cat(cat, cfg)
        c = 0
        for el in els:
            if el["type"] == "node":
                lat, lon = el.get("lat"), el.get("lon")
            else:
                ctr = el.get("center") or {}
                lat, lon = ctr.get("lat"), ctr.get("lon")
            if lat is None or lon is None:
                continue
            # bbox 안 확인
            if not (s <= lat <= n and w <= lon <= e):
                continue
            tags = el.get("tags", {})
            name = tags.get("name") or tags.get("name:ko") or cfg["default"]
            fid = f"{cat}-{el['type'][0]}{el['id']}"
            if fid in seen:
                continue
            seen.add(fid)
            props = {
                "layer": "infra", "id": fid, "name": name,
                "category": cat, "color": cfg["color"],
            }
            brand = tags.get("brand") or tags.get("brand:ko")
            if brand:
                props["brand"] = brand
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                "properties": props,
            })
            c += 1
        counts[cat] = c
        print(f"  → {cat}: {c}개")
        time.sleep(1)

    fc = {
        "type": "FeatureCollection",
        "meta": {
            "layer": "infra",
            "source": "OpenStreetMap Overpass API",
            "collected_at": datetime.now(kst).isoformat(),
            "region": "성남시 분당구",
            "bbox": {"south": s, "west": w, "north": n, "east": e},
            "count": len(features),
            "category_counts": counts,
        },
        "features": features,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, indent=1)
    print(f"\n완료: {OUT}")
    print(f"총 {len(features)}개 | 카테고리별: {counts}")


if __name__ == "__main__":
    main()
