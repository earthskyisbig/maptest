---
name: realestate-map-build
description: 부동산 멀티레이어 맵서비스 오케스트레이터. 경매물건·정비구역·공공주택·산업단지·생활인프라 5개 레이어를 수집·통합해 하나의 카카오/VWorld 지도로 만드는 에이전트 팀을 조율한다. "부동산 지도 만들어줘", "맵서비스 구축/갱신", "레이어 추가해줘", "지도 다시 만들어줘", "○○구 경매+인프라 지도", "레이어 재수집", 지도 업데이트/보완/부분 재실행 요청 시 반드시 사용. 단순 질문은 직접 응답 가능.
---

# realestate-map-build — 부동산 맵서비스 오케스트레이터

경매물건·정비구역·공공주택·산업단지·생활인프라 5개 레이어를 한 지도에 얹는 작업을 에이전트 팀으로 조율한다.

**실행 모드: 에이전트 팀** — 수집 3인 병렬(팬아웃) → 통합가(팬인) → QA. TaskCreate 의존성으로 순서를 강제하고, SendMessage로 실시간 조율한다.

## 팀 구성
| 에이전트 | 타입 | 역할 |
|---------|------|------|
| auction-collector | opus | 경매물건 → `layer_auction.geojson` |
| zone-layer-specialist | opus | 정비/공공주택/산단 → `layer_zone_*.geojson` |
| poi-collector | opus | 생활인프라 → `layer_infra.geojson` |
| map-integrator | opus | 레이어 병합 → `estate_map.html` |
| qa-validator | general-purpose | 스키마·좌표·정합 검증 → `qa_report.md` |

모든 산출은 `_workspace/`에 저장, 최종 `estate_map.html`만 사용자 지정 경로.

## Phase 0: 컨텍스트 확인
1. `_workspace/` 존재 여부 확인.
   - 미존재 → **초기 실행**(아래 전 Phase).
   - 존재 + 부분 수정 요청("정비구역만 다시", "인프라 갱신") → **부분 재실행**(해당 수집가만 재호출 → 재통합 → QA).
   - 존재 + 새 지역/새 입력 → **새 실행**(`_workspace/`를 `_workspace_prev/`로 이동 후 초기 실행).
2. 사용자로부터 대상 지역·활성 레이어·필터를 확인한다.

## Phase 1: 수집 (팬아웃, 병렬)
`TeamCreate`로 팀 구성 후, 세 수집가에 독립 작업을 `TaskCreate`한다(상호 의존 없음).
- auction-collector ← 지역·물건필터 → `layer-auction-collect` 스킬
- zone-layer-specialist ← 지역·구역종류 → `layer-zone-boundary` 스킬
- poi-collector ← bbox·카테고리 → `layer-infra-poi` 스킬

각 수집가는 레이어 완성 즉시 qa-validator에 SendMessage → **점진적 QA**가 병렬로 검증.

## Phase 2: 통합 (팬인)
map-integrator 작업은 세 수집 태스크에 **의존**(TaskCreate dependency). 세 레이어 완료 후 착수해 `map-render` 스킬로 `estate_map.html` 렌더. 누락 레이어는 빈 레이어로 처리.

## Phase 3: 최종 QA
qa-validator가 최종 HTML의 렌더 계약(토글↔레이어, category↔color)을 검증하고 `qa_report.md` 종합. 위반 시 담당 에이전트에 반려 → 1회 수정 → 재검증.

## 데이터 전달 프로토콜
- **태스크 기반**(조율): TaskCreate/Update로 의존성·진행상황 관리.
- **파일 기반**(산출물): `_workspace/layer_*.geojson` → `estate_map.html`. 규격은 `references/geojson-schema.md`.
- **메시지 기반**(실시간): 수집 완료·QA 반려를 SendMessage.
- 파일명: `_workspace/layer_{레이어}.geojson`, `_workspace/qa_report.md`. 중간 파일은 보존(감사 추적).

## 에러 핸들링
- 수집 실패 → 1회 재시도, 재실패 시 **해당 레이어 없이 진행**하고 `qa_report.md`·지도 UI에 "데이터 없음" 명시(전체 중단 금지).
- 상충/의심 데이터 → 삭제하지 않고 출처(`meta.source`) 병기.
- 스키마 위반 → qa-validator가 담당 에이전트에 구체적 필드·건수로 반려.
- 좌표계 오류(구역이 엉뚱한 위치) → zone-layer-specialist가 WGS84 재변환.

## 팀 크기
중규모(레이어 5 × 수집·통합·검증) → 5명, 팀원당 1~3 태스크. 적정.

## 테스트 시나리오
**정상 흐름**: "성남시 분당구 경매물건 + 정비구역 + 지하철 지도 만들어줘"
→ Phase 0 초기 실행 판정 → 3 수집가 병렬(경매·정비구역·subway POI) → 점진 QA 통과 → 통합가 렌더 → 최종 QA → `estate_map.html`. 산업단지·공공주택 레이어는 미요청이므로 빈 토글로 존재.

**에러 흐름**: 정비구역 WMS 응답 없음
→ zone-layer-specialist 1회 재시도 실패 → 공공데이터포털 대체 소스 실패 → 정비구역 레이어 없이 진행 → 통합가가 정비구역 토글을 "데이터 없음"으로 렌더 → `qa_report.md`에 누락·사유 명시 → 지도는 나머지 4개 레이어로 정상 산출.

## 후속 작업
- "인프라 갱신" → poi-collector만 재호출 → 재통합 → QA.
- "산업단지 레이어 추가" → zone-layer-specialist에 산단만 요청 → 통합가가 기존 스타일 유지하며 레이어 추가.
- "지도 색/토글 수정" → map-integrator만 재렌더(수집 생략).
