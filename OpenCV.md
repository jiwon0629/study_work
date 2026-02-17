# 👁️ OpenCV: Open Source Computer Vision Library
> **컴퓨터 비전 및 머신러닝 작업을 위한 오픈 소스 소프트웨어 툴킷**

![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white)

---

## 📌 1. OpenCV란?
**OpenCV**는 시각 데이터를 효율적으로 처리하고 분석하기 위해 설계된 라이브러리입니다. 얼굴 인식, 자율주행 등 실시간 이미지 분석에 최적화되어 있으며, 계산 효율성을 최우선으로 설계되었습니다.

### 💻 컴퓨터가 이미지를 인식하는 방식
인간과 달리 컴퓨터는 이미지를 **수치 행렬**로 해석합니다.
* **픽셀 값 (Pixel Values)**: 모든 이미지는 색상과 밝기 값을 가진 픽셀로 구성됩니다.
* **행렬 표현 (Matrix)**: 이미지는 **NumPy 배열**로 저장됩니다. 회색조는 2차원, 컬러는 3차원 배열로 표현됩니다.
* **데이터 처리**: 알고리즘은 이 배열을 조작하여 에지 검출이나 객체 검출 등의 변환을 적용합니다.



---

## 🔄 2. 이미지 처리 워크플로우
OpenCV에서 일반적인 작업 흐름은 다음과 같습니다:

1. **이미지 불러오기**: `cv2.imread()`를 사용하거나 카메라 프레임을 캡처합니다.
2. **변환 적용**: 이미지의 특징을 향상시키거나 필터링, 감지 작업을 수행합니다.
3. **결과 출력**: 처리된 결과를 화면에 표시하거나 파일로 저장합니다.

---

## 🛠️ 3. 설치 및 실전 예제

### 🚀 설치 방법
```python
# 기본 라이브러리 설치
pip install opencv-python

# 고급 모듈(얼굴 인식 등) 지원이 필요한 경우
pip install opencv-contrib-python
```

## 🐍 Python 이미지 처리 실습
<details>
<summary>📂 <b>이미지 로드 및 흑백 변환 코드 (클릭하여 펼치기)</b></summary>
import cv2
import matplotlib.pyplot as plt

# 1. 이미지 로드 (기본 BGR 형식)
image_path = 'Sample_CV.jpg'
img = cv2.imread(image_path)

# 2. 색상 변환 (RGB 및 Gray)
img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# 3. 결과 표시
plt.figure(figsize=(12, 5))
plt.subplot(1, 2, 1)
plt.imshow(img_rgb)
plt.title("Original (RGB)")
plt.axis("off")

plt.subplot(1, 2, 2)
plt.imshow(img_gray, cmap='gray')
plt.title("Grayscale")
plt.axis("off")

plt.tight_layout()
plt.show()
</details>

## 🌟 4. 주요 기능 및 적용 사례
### ⚙️ 핵심 기능
입출력: 이미지 및 비디오 파일 읽기/저장.

이미지 처리: 크기 조정, 필터링, 색상 변환.

객체 감지: 얼굴, 도형 및 특징점 감지.

머신러닝: 분류 및 클러스터링 모델 적용.

### 🌍 실제 적용 사례
카메라 앱의 얼굴 및 사물 인식.

의료 영상 분석 (X선, CT, MRI).

로봇공학 및 자율 주행 차량 내비게이션.

생산 라인에서의 자동 품질 검사.

Maintainer: jiwon0629

Source: OpenCV Library Documentation & Workflow Guide
