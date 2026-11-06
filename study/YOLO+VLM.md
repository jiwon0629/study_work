# YOLO + VLM

VLM이 YOLO를 대신하는 게 아니라 **YOLO가 찾은 후보(박스)를 VLM이 다시 확인하는 2차 검증기**로 쓸 때 효과가 가장 분명했다. 성능 수치가 나온 사례들을 정리했다.

(참고: 이 세션에서는 웹 검색 기능이 조직 설정으로 막혀 있어서 arXiv만 검색했다. 회사 블로그나 산업 적용 사례는 빠져 있을 수 있다.)

### YOLO + VLM 2단계로 성능이 오른 사례

<figure class="table op-uc-figure_align-center op-uc-figure"><table class="op-uc-table"><thead class="op-uc-table--head"><tr class="op-uc-table--row"><th class="op-uc-table--cell op-uc-table--cell_head"><p class="op-uc-p">사례</p></th><th class="op-uc-table--cell op-uc-table--cell_head"><p class="op-uc-p">구조</p></th><th class="op-uc-table--cell op-uc-table--cell_head"><p class="op-uc-p">결과</p></th></tr></thead><tbody><tr class="op-uc-table--row"><td class="op-uc-table--cell"><p class="op-uc-p">AdaptiveDetector (대장 용종 검출, 2025.12)</p></td><td class="op-uc-table--cell"><p class="op-uc-p">1차 YOLOv11 → 2차 VLM 검증. VLM은 GRPO 강화학습으로 미세조정했고, 놓친 검출에 더 큰 벌점을 주도록 학습</p></td><td class="op-uc-table--cell"><p class="op-uc-p">화질이 나쁜 내시경 영상에서 재현율(recall)<strong> </strong>+14~22%p, 정밀도(precision)는 −0.7~+1.7%p로 거의 그대로</p></td></tr><tr class="op-uc-table--row"><td class="op-uc-table--cell"><p class="op-uc-p">CLOSER (로봇 물체 찾기, 2026.10)</p></td><td class="op-uc-table--cell"><p class="op-uc-p">1차 탐지기 → 미세조정한 VLM이 각 후보를 "목표 / 아님 / 불확실"로 판정. 여러 시점의 판정을 합침</p></td><td class="op-uc-table--cell"><p class="op-uc-p">소파를 침대로 아는 식의 오탐이 줄어 성공률<strong> </strong>+3.6%p</p></td></tr><tr class="op-uc-table--row"><td class="op-uc-table--cell"><p class="op-uc-p">YOLO-World + VLM True/False 검증 (지시 표현 이해(REC), 2025.09)</p></td><td class="op-uc-table--cell"><p class="op-uc-p">YOLO-World가 후보 박스를 만들고, VLM이 박스마다 "이게 맞나?"를 True/False로 답함</p></td><td class="op-uc-table--cell"><p class="op-uc-p">추가 학습 없이 RefCOCO 계열에서 GroundingDINO(REC 학습 버전 포함)보다 높음. "여러 후보 중 고르기"보다 박스별 개별 검증이 확실히 더 좋았음</p></td></tr><tr class="op-uc-table--row"><td class="op-uc-table--cell"><p class="op-uc-p">원격탐사 항공기 탐지 (2025.10)</p></td><td class="op-uc-table--cell"><p class="op-uc-p">YOLO에 LLaVA, ChatGPT, Gemini를 결합</p></td><td class="op-uc-table--cell"><p class="op-uc-p">항공기 개수 세기 오차(MAE) 평균 48.46% 개선. 화질이 나쁜 이미지에서 특히 효과가 큼</p></td></tr><tr class="op-uc-table--row"><td class="op-uc-table--cell"><p class="op-uc-p">BLPR (볼리비아 번호판, 2026.04)</p></td><td class="op-uc-table--cell"><p class="op-uc-p">YOLO가 탐지·인식하고, 신뢰도가 낮을 때만 Gemma3 4B를 호출</p></td><td class="op-uc-table--cell"><p class="op-uc-p">실제 도로 데이터에서 문자 단위 정확도 89.6%</p></td></tr><tr class="op-uc-table--row"><td class="op-uc-table--cell"><p class="op-uc-p">Clip2Safety (안전장비 착용 확인, 2024.08)</p></td><td class="op-uc-table--cell"><p class="op-uc-p">탐지 후 VLM이 세부 속성을 검증(예: 착용 상태가 기준에 맞는지)</p></td><td class="op-uc-table--cell"><p class="op-uc-p">질의응답형 VLM보다 정확도가 높고 속도는 약 200배 빠름</p></td></tr></tbody></table></figure>

### 공통적으로 효과가 있었던 패턴

1.  **VLM은 위치를 찾는 데 쓰지 않고 검증에만 씀.** VLM은 박스 위치를 잡는 능력이 약하고, 없는 물체를 있다고 하는 환각도 있다(BetterCheck 논문, 2025.07). 위치는 YOLO에 맡기고, VLM에는 잘라낸 영역(crop)에 대해 예/아니오 판정만 시키는 구조가 안정적이다.
    
2.  **신뢰도가 애매한 박스만 VLM으로 보냄.** 예를 들어 YOLO 신뢰도가 0.3~0.6인 박스만 보내면 지연 시간과 비용을 크게 줄일 수 있다(BLPR이 이 방식).
    
3.  **목표에 따라 쓰는 방법이 다름.**
    
    *   오탐 제거(정밀도↑)가 목표: 신뢰도가 높은 박스도 VLM이 걸러내게 한다.
        
    *   미탐 감소(재현율↑)가 목표: YOLO 임계값을 낮춰 후보를 많이 뽑고, VLM이 걸러낸다(AdaptiveDetector).
        
4.  **특수한 도메인에서는 VLM 미세조정이 거의 필수.** 의료나 산업 쪽은 범용 VLM을 그대로 쓰면 효과가 제한적이었다.
    

### 주의할 점

*   **속도:** VLM 호출은 박스당 수백 ms에서 수 초가 걸려 실시간 처리가 어렵다. 대상 박스를 줄이거나 작은 VLM(2~4B)을 써야 한다.
    
*   **효과가 큰 경우:** YOLO가 이미 데이터에 잘 맞춰져 있고 화질이 좋은 환경에서는 개선 폭이 작다. 화질 저하, 도메인 변화, 비슷하게 생긴 클래스 구분, 세부 속성 판단이 필요한 경우에 효과가 크다.
    

<br>

Sources:

*   [Adaptive Detector-Verifier Framework for Zero-Shot Polyp Detection (arXiv:2512.12492)](https://arxiv.org/abs/2512.12492)
    
*   [CLOSER: Evidence-Aware Active Visual Verification (arXiv:2610.28476)](https://arxiv.org/abs/2610.28476)
    
*   [Zero-Shot REC via Vision-Language True/False Verification (arXiv:2509.09958)](https://arxiv.org/abs/2509.09958)
    
*   [Efficient Few-Shot Learning in Remote Sensing: Fusing Vision and VLMs (arXiv:2510.13993)](https://arxiv.org/abs/2510.13993)
    
*   [BLPR: Confidence-Driven VLM Fallback (arXiv:2604.09927)](https://arxiv.org/abs/2604.09927)
    
*   [Clip2Safety: VLM for Safety Compliance Detection (arXiv:2408.07146)](https://arxiv.org/abs/2408.07146)
    
*   [BetterCheck: Safeguarding VLMs for Automotive Perception (arXiv:2507.17722)](https://arxiv.org/abs/2507.17722)
