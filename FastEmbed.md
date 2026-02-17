# 🚀 FastEmbed: Lightweight & Fast Vector Embedding
> **Qdrant에서 개발한 CPU 최적화 기반의 초고속 경량 임베딩 생성 라이브러리**

![FastEmbed](https://img.shields.io/badge/FastEmbed-0.2.7-orange?style=for-the-badge)
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![ONNX Runtime](https://img.shields.io/badge/ONNX-Runtime-blue?style=for-the-badge&logo=onnx)

---

## 📌 1. FastEmbed란?
**FastEmbed**는 Qdrant에서 개발한 가볍고 빠른 경량화된 벡터 임베딩 생성 라이브러리입니다. 주로 RAG(검색 증강 생성)나 의미 기반 검색 파이프라인에서 데이터를 벡터로 변환할 때 사용하며, 파이썬으로 구현되어 있습니다.

---

## 🏗️ 2. 왜 FastEmbed를 사용해야 하는가?

### ⚡ 1. 매우 빠른 속도 및 CPU 최적화
* **ONNX Runtime 기반**: PyTorch나 TensorFlow 같은 무거운 프레임워크 없이 최적화된 ONNX Runtime을 사용하여 CPU에서도 빠른 추론을 제공합니다.
* **병목 현상 해소**: 대규모 문서 처리 시 기존 Sentence Transformers 대비 약 50% 이상 빠른 속도를 보여줍니다.

### 📦 2. 가벼운 종속성 및 쉬운 배포
* **무거운 라이브러리 제거**: PyTorch 등의 라이브러리가 필요 없어 환경 설정이 간편하고 디스크 공간을 적게 차지합니다.
* **서버리스/엣지 최적화**: 가벼운 특성 덕분에 리소스가 제한된 서버리스 함수나 엣지 환경 실행에 적합합니다.

### 💰 3. 비용 절감 및 보안
* **API 비용 없음**: OpenAI 등 외부 API 호출이 필요 없어 비용이 발생하지 않습니다.
* **데이터 보안**: 데이터를 외부로 전송하지 않고 로컬 환경에서 직접 처리하므로 안전합니다.

### 🎯 4. 높은 성능과 품질
* **최신 모델 지원**: BGE-M3 등 성능이 입증된 모델을 지원하며, 양자화 기술 적용 후에도 원본과 유사한 성능(Cosine similarity 0.92 이상)을 유지합니다.
* **검증된 정확도**: OpenAI Ada-002 모델보다 우수한 정확도와 재현율을 보여줍니다.

---

## 🛠️ 3. 기술 사양 및 설치

### 🧬 핵심 기술
* **양자화(Quantization)**: 모델 가중치를 경량화하여 효율성을 높였습니다.
* **다국어 지원**: 한국어를 포함한 BGE-M3, Multilingual E5 등 다양한 다국어 모델을 지원합니다.



### 🚀 설치 방법
```bash
# 기본 설치
pip install fastembed

# GPU 가속 사용 (v0.2.7 이상)
pip install fastembed-gpu
```
📊 4. 성능 비교 요약
| 비교 항목 | 기존 Sentence Transformers | FastEmbed | 
| -- | -- | -- |
| 추론 속도 (CPU) | 보통 | 50% 이상 향상 | 
| 의존성 | 무거움 (PyTorch 등) | 가벼움 (ONNX) | 
주요 활용일반 워크스테이션서버리스 / 엣지 환경정확도모델별 상이OpenAI Ada-002 대비 우수

## 💡 결론

FastEmbed는 로컬 CPU 환경에서 비용 효율적으로 빠르게 대규모 문서를 임베딩하고 싶을 때 가장 적합한 도구입니다. 특히 Qdrant 벡터 데이터베이스와의 연동이 매우 쉽고 RAG 파이프라인 구축에 최적화되어 있습니다.
---
Maintainer: jiwon0629Reference: Qdrant FastEmbed Documentation
