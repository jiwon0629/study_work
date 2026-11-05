# Re-ID 관련 GitHub 레포 목록

> 2026-10-22 조사. 라이선스 세부는 `reid-licenses.md`.

| 레포 | 내용 | 상태/비고 |
|---|---|---|
| NirAharon/BoT-SORT | BoT-SORT 공식 | MIT, 1.3k★, 통합 쉬움 (Ultralytics 내장) |
| GerardMaggiolino/Deep-OC-SORT | Deep OC-SORT 공식 | MIT, boxmot에도 포함. 적응형 appearance 이식 원천 |
| noahcao/OC-SORT | OC-SORT 공식 | MIT, 안정 |
| Syliz517/CLIP-ReID | CLIP-ReID 공식 | MIT, fine-tune 필요 |
| damo-cv/TransReID | TransReID 공식 | MIT, pretrained 제공 |
| junkunyuan/HAP | HAP 백본 | 백본 교체 후보 (라이선스 확인 필요) |
| tinyalpha/SOLIDER | SOLIDER 백본 | 가중치 research-only 가능성 — 상업 부적합 |
| JDAI-CV/fast-reid | Re-ID 툴킷 | Apache 2.0, 성숙 |
| KaiyangZhou/deep-person-reid | Torchreid | MIT |
| mikel-brostrom/boxmot | MOT 통합 라이브러리 | AGPL-3.0 — 클로즈드 SaaS 부적합. 알고리즘 참조용만 |

사용 원칙: **MIT/Apache 코드는 직접 이식** (의존성 최소화), AGPL은 코드 참조만.
