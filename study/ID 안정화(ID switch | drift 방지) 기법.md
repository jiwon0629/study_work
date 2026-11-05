# ID 안정화 (ID switch/drift 방지) 기법
2026-10-22 Alpha 리서치. 목적: 카메라 간 ID 변질 방지. 라이선스는 reid-licenses.md 참조.

1. 트래킹 연관 계열

| 구성 요소 | 역할 | 비유 |
| :--- | :--- | :--- |
| **Dockerfile** | 빌드 스크립트 | **레시피** |
| **Image** | 실행 패키지 | **밀키트** |
| **Container** | 프로세스 | **요리 완성본** |

||	arXiv 2206.14651|	ByteTrack + 카메라 모션 보정(CMC) + appearance. Ultralytics 내장. (2026 중반 TrackTrack으로 후속)|
Deep OC-SORT	ICCV 2023	모션 중심 유지, 적응형 appearance 가중치 — appearance가 신뢰 낮으면 모션 위주로 자동 전환. 가림·재등장에서 ID 유지 강함
Hybrid-SORT	AAAI 2024	weak cue(height, confidence 등) 모듈 결합
HeteroAssoc	2025	이기종 cue 계층 연관
3. 표준 실무 패턴 (본 프로젝트 적용 대상)
Embedding EMA: track별 대표 임베딩을 프레임마다 v = α·v + (1-α)·new 갱신 → 일시적 가림·조명 변화에서 대표 임베딩 오염 방지
Lost buffer / re-entry 관리: lost track을 N프레임 보존 후 같은 카메라 재등장 시 기존 ID 재부여 (거리·임베딩 게이트)
시공간 궤적 제약: 카메라 전이는 물리적 이동 시간 하한 존재 → cross-camera 매칭에 최소 전이 시간 게이트 추가
Offline refinement: 세션(배치) 단위 궤적 재클러스터링으로 온라인 오류 복원
4. 본 프로젝트 매핑 (2026-10-22 Haseo 승인 스프린트 6)
6.1 어안 왜곡 보정 + 시공간 제약 cross-camera 정합 — §2 시공간 게이트 + cv2 fisheye undistort 헬퍼 → cross_camera.py 연동
6.2 Embedding EMA + lost-buffer 재등장 관리 — tracker.py/tracklet.py
6.3 적응형 appearance 가중치 — Deep OC-SORT 방식 이식 (MIT 코드 기반)
5. 구현 현황 (Sprint 6 완료, 2026-10-21)
6.1 c18d758: fisheye.py + min travel time gate
6.2 5a283e2: Embedding EMA α=0.7 + lost-buffer re-entry
6.3 e2007bc: 적응형 appearance trust — 기본값 전부 하위호환

+-------+----+---+
| d    |   |   |
+---+----+---+
