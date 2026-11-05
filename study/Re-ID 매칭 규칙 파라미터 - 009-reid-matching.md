﻿# 009 — Re-ID 매칭 규칙·파라미터 (CrossCameraMatcher 사양)

- 날짜: 2026-10-20 정리 (커밋 메시지·결정로그에 흩어진 매칭 지식의 단일화)
- 코드: `src/reid/cross_camera.py`, `src/reid/appearance.py`, `src/reid/osnet_embedder.py`
- 테스트: `tests/test_cross_camera.py`, `tests/test_osnet_embedder.py`

## 1. 매칭 판단 조건 — 4중 게이트 (모두 통과 시에만 기존 신원 병합)

1. **외형 유사도**: 정규화 임베딩 코사인 ≥ `sim_threshold`
2. **토폴로지**: 직전 관측 카메라와 인접 (CameraGraph.link). 같은 카메라는 travel=0
3. **시간 창**: 물리 이동 시간 기반
   - 타카메라: `travel × min_time_ratio`(하한, 너무 빠르면 물리 불가) ~ `travel × time_slack`(상한)
   - 같은 카메라 재감지: `stay_window` 이내
4. **배타성**: 후보 tid가 **다른 카메라에서 `presence_window` 이내 관측 중이면 기각** — 한 사람은 동시에 두 카메라에 존재할 수 없음. (2026-10-20 Haseo 리뷰 지적 "동시 존재인데 같은 번호 병합" 사고의 차단책)

어떤 후보도 통과 못 하면 새 tid 발급(단조 증가).

## 2. 파라미터 (기본값)

| 파라미터 | 기본값 | 의미 |
|---|---|---|
| sim_threshold | 0.85 | 병합 최소 코사인 유사도 (OSNet 사용 시 데모에선 0.60) |
| time_slack | 1.5 | typical travel 대비 허용 상한 배수 |
| min_time_ratio | 0.2 | typical travel 대비 물리 하한 비율 |
| stay_window | 30.0s | 같은 카메라 내 재감지 허용 시간 |
| presence_window | 0.6s | 타카메라 '접근 관측' 판정 창 (배타성) |

- 튜닝은 AI City 등 평가 데이터셋으로 (006). 고정 정답 아님
- 임베딩 정규화는 matcher 내부에서 강제 — 호출자가 비정규 벡터를 줘도 안전

## 3. 임베딩 어댑터 (교체 가능 인터페이스)

`embed(crop: HxWx3 BGR) → L2 정규화 1D 벡터` 인터페이스 (003 §인터페이스):

- **v0 ColorHistEmbedder** — HSV 히스토그램. 조명 보정 전제, 옷 색 비슷한 사람 구별 약함 (동시 존재 오판 원인이었음)
- **현행 OSNetEmbedder** — torchreid osnet_x1_0 (market1501 학습 가중치 의도). 256×128 리사이즈, BGR→RGB, ImageNet 정규화, 512d
- 교체 시 매처 코드 변경 불요 — 어댑터만 교체

## 4. 카메라 내 추적과 전역 신원의 분리

- 카메라 내 프레임 간 ID 유지 = Tracker(Tracker.tid)
- 카메라 간 신원 = CrossCameraMatcher(t Matcher tid)
- 데모·웹앱은 트랙에 매처 tid를 덮어써 표시 — 두 계층 ID 체계가 섞이지 않게 주의

## 5. 임베딩 갱신 + 데모 파라미터 (2026-10-20 Haseo 리뷰 피드백 반영)

- **update_embedding(tid, t, emb)**: 첫 판정 시점의 작은 크롭 임베딩이 박제되는 문제 해결 — 트랙 생존 중 최신 크롭으로 갱신, 시간도 함께 갱신(시간 창 판정이 최신 위치 기준). TDD: refresh 테스트 3건
- **트랙별 1회 판정 + 3프레임 지연**: 가장자리 부분 크롭에서 판정하지 않도록 트랙 3프레임 후 결정. 결정 후 갱신은 update_embedding으로
- **분할 화면 데모 파라미터**: travel_seconds=0.3(즉시 횡단), min_time_ratio=0, presence_window=-1(배타성 비활성 — 같은 프레임 갱신·판정이 0초 간격이라 상시 차단됨). 실제 별도 CCTV에서는 기본값(§2) 사용
- 검증 로그: t=1.52 B 판정 sim 0.701 → tid1 병합 성공, t=7.20 A 판정 sim 0.803 → tid2 병합 성공. 좌우 패널 번호 유지 확인 (demo-cross-camera-v2.mp4)

## 6. 핸드오프 허용치 (handoff_tolerance, 2026-10-21 확정)

- 배타성 검사에서 "시간 겹침 = 다른 사람"으로 기각할 때, **검출 지연으로 생기는 짧은 겹침은 허용**해야 한다
- 실측: 분할 경계 횡단 시 트랙 겹침 ~1.6초 → 허용치 1.8초 (검출 지연 1.6 < 1.8 < 진짜 동시 존재 2.0+)
- 미만: 횡단 시 ID 분리(오판) / 초과: 동시 존재하는 다른 사람 병합(오판). 실환경 배치 시 검출 지연 실측으로 튜닝
- 트랙별 1회 판정 + update_embedding 갱신과 조합해 횡단 ID 유지 확인 (demo-cross-camera-v3.mp4)
