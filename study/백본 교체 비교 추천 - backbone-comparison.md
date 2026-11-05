# 백본 교체 비교·추천 (2026-10-22 리서치, 사실 확인 기반)

> 서브에이전트 리서치 결과. 라이선스는 raw.githubusercontent.com LICENSE 원문 fetch로 확인. 수치는 논문/README 명시분만.

## ① 후보 비교표

| 후보 | Market-1501 mAP/R1 | MSMT17 mAP/R1 | 파라미터 | 코드 라이선스 | 가중치 라이선스 | 실시간성 | 어안 적합성 |
|---|---|---|---|---|---|---|---|
| OSNet x1.0 (현행) | 82.6 / 94.2 | 43.8 / 74.9 | 2.2M, 0.98 GF | MIT ✅ | 개별 명시 없음 — 미확인 | ◎ CPU 실시간 | 수평 데이터 학습, 무파인트 부적합 |
| CLIP-ReID (ViT-B/16) | 89.6 / 95.5 | 75.8 / 89.7 (재현 70.7) | ~86M | MIT ✅ | 미확인 | △ GPU 필요 | 교차도메인 급락 보고 |
| TransReID (ViT) | 89.0 / 95.1 | 67.8 / 85.3 | ~86M | MIT ✅ | 미확인 | △ GPU 필요 | SIE 카메라 인코딩은 유리하나 어안 미학습 |
| HAP (ViT-lem) | 93.8 / 96.4 | 78.1 | ~86M | **LICENSE 404 — 미확인** | 미확인 | △ GPU 필요 | 수평 데이터 |
| SapiensID | 68.3 / 88.2 (제로샷) | 31.0 / 67.3 | ViT-B+ | **CC BY-NC 4.0 — 상업 불가 ❌** | CC BY-NC-SA | ✕ | 탈락 |
| SOLIDER (Swin-T~B) | 91.6~93.9 / 96.1~96.9 | 77.1 / 90.7 | 28~88M | Apache-2.0 ✅ | 가중치 개별 조항 미확인 | △ | 사람 중심 사전학습, 전이 유리 |
| fast-reid BoT (R50) | 86.1 / 94.4 | — | 23.5M | Apache-2.0 ✅ | Model Zoo 별도 제한 없음 확인 | ○ GPU 1장 | 범용, 어안은 파인튜닝 전제 |
| fast-reid SBS (R50-ibn) | 89.8 / 95.8 | — | ~23.5M+ | Apache-2.0 ✅ | 동일 | ○ GPU 1장 | 동일 |

OSNet-AIR 경량판: 이번 라운드 수치 원문 미확인 — torchreid MODEL_ZOO 재조회 필요.

## ② 라이선스 원문 확인

- OSNet/deep-person-reid: "MIT License, Copyright (c) 2018 Kaiyang Zhou" ✅
- CLIP-ReID: "MIT License, Copyright (c) 2023 Syliz517" ✅
- TransReID: "MIT License, Copyright (c) 2021 heshuting555" ✅
- HAP: LICENSE 파일 부재(404) ⚠️
- SapiensID: "Attribution-NonCommercial 4.0 International" ❌ 상업 불가
- SOLIDER: Apache License 2.0 ✅ (가중치 파일 별도 조항은 미확인)
- fast-reid: Apache License 2.0 ✅, MODEL_ZOO 가중치에 별도 제한 조항 미발견 ✅

## ③ 추천 1순위: fast-reid BoT (ResNet50), 상향 시 SBS(R50-ibn)

근거:
1. 코드·가중치 모두 라이선스 리스크 없음(Apache-2.0 확인) 중 Market mAP 86.1~89.8% — 현행 OSNet(82.6) 대비 +3.5~7.2%p
2. ResNet50 23.5M·256×128 — GPU 1장이면 3대 스트림 여유, ONNX/TensorRT export 내장으로 배포 경로 짧음
3. CLIP 계열은 교차도메인 mAP -38~-50p 급락 보고(MDPI Sensors 2025) — 어안 도메인 파인튜닝 필수인 우리 환경에선 CNN 베이스가 실험 리스크 최소

**단, CPU-only 배포라면 현행 OSNet 유지가 정답** (CPU 실시간 가능한 유일 후보).

공통 주의: 모든 후보 학습 데이터는 수평 시점 보행자 — 어안 3대 성능은 현장 크롭 파인튜닝 후 측정 필수.

## ④ 출처

- torchreid MODEL_ZOO: https://kaiyangzhou.github.io/deep-person-reid/MODEL_ZOO
- CLIP-ReID: https://github.com/Syliz517/CLIP-ReID · https://arxiv.org/abs/2211.13977 · 재현 이슈 https://github.com/Syliz517/CLIP-ReID/issues/40
- TransReID: https://github.com/damo-cv/TransReID · ICCV 2021 paper
- HAP: https://github.com/junkunyuan/HAP · https://arxiv.org/abs/2310.20695
- SapiensID: https://github.com/mk-minchul/sapiensid · https://arxiv.org/abs/2504.04708
- SOLIDER: https://github.com/tinyvision/SOLIDER
- fast-reid MODEL_ZOO: https://github.com/JDAI-CV/fast-reid/blob/master/MODEL_ZOO.md
- 도메인갭: https://www.mdpi.com/1424-8220/25/2/363
