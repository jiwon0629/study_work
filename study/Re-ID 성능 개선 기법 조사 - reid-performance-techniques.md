# Re-ID 성능 개선 기법 조사

> 2026-10-22 Alpha 리서치 (서브에이전트). 라이선스는 `reid-licenses.md`, 레포는 `reid-repos.md` 참조.

## 1. 외형/백본 계열

| 기법 | 출처 | 핵심 아이디어 | 적용 난이도 |
|---|---|---|---|
| TransReID | ICCV 2021 | ViT 백본 + JPM(부분 마스킹) + side 정보 임베딩. 시점 변화 강건 | 중 |
| CLIP-ReID | AAAI 2023 | CLIP 시각-텍스트 정렬, ID별 learnable token 2단계 학습. SOTA급 | 중 (자체 데이터 fine-tune 필요) |
| SOLIDER | CVPR 2023 | 인간 중심 self-supervised 사전학습 백본 | 중상 (가중치 라이선스 주의) |
| HAP | NeurIPS 2023 | keypoint 구조 가이드 MML 사전학습 | 중상 |
| SapiensID | CVPR 2025 | Sapiens foundation model 기반 Re-ID | 고 |
| Training-Free Re-ID | CVPR 2025 | 학습 없이 feature centralization + 포즈 활용. 도메인 갭에 강함 | 저~중 |

## 2. 멀티카메라 / 크로스카메라

- **시공간 제약 + anchor 피처 계층 클러스터링** — CVPRW 2024 AI City Challenge 상위권 표준 접근. 카메라 간 ID 정합에 시간 전이 행렬 + 카메라별 anchor 임베딩 활용
- **Anchor-Guided Clustering** (arXiv 2304.09471) — 카메라별 anchor를 중심으로 계층 클러스터링
- **어안 특화** (arXiv 2212.11477 등) — top-view 어안은 원주 왜곡·상하 반전 보정을 전제로 시공간 융합. 문헌상 표준: cv2 fisheye undistort 캘리브레이션 1회 → 보정 좌표계에서 매칭

## 3. 보조 신호

- 의류 불변(clothing-invariant) / gait 보조 — 장기 재식별에 유효하나 **top-view 어안에서 gait 품질 저하** → 본 프로젝트 우선순위 낮음

## 4. 백본 비교 (상세)

→ 성능 지표·라이선스 사실 확인 기반 비교는 `backbone-comparison.md` (리서치 진행 후 작성)
