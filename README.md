# study_work  


# 🐳 WSL & Docker Mastery Guide
> **Windows에서 Linux 환경 그대로, 완벽한 컨테이너 개발 환경 구축하기**

![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)
![Ubuntu](https://img.shields.io/badge/Ubuntu-E95420?style=for-the-badge&logo=ubuntu&logoColor=white)
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)

---

## 📌 1. 왜 WSL에서 Docker를 써야 할까?

단순히 유행이 아닙니다. **실제 서비스 환경과의 싱크(Sync)**가 핵심입니다.

* **환경 일치 (Parity):** "내 컴에선 됐는데?" 문제를 원천 차단. 
* **성능 폭발:** WSL 2의 가상화 기술로 리눅스 네이티브에 가까운 속도 보장.
* **도커의 고향:** 도커는 원래 리눅스 기술입니다. WSL 위에서 가장 안정적입니다.

---

## 🏗️ 2. 핵심 아키텍처 이해

| 구성 요소 | 역할 | 비유 | 특징 |
| :--- | :--- | :--- | :--- |
| **Dockerfile** | 빌드 스크립트 | **레시피** | 코드, 설정, 실행 명령을 순서대로 정의 |
| **Image** | 실행 패키지 | **밀키트** | 불변성(Immutable), 버전 관리, 배포 단위 |
| **Container** | 프로세스 | **요리 완성본** | 격리성, 효율성, 즉시 실행 및 삭제 가능 |



---

## 🛠️ 3. 실전 커맨드 북 (Cheat Sheet)

### 💡 주요 옵션 요약
- `-t` : **Tag.** 이름표를 붙입니다. (안 붙이면 `none` 지옥에 빠집니다.)
- `-d` : **Detached.** 백그라운드 실행. (터미널 점유 방지)
- `-p` : **Publish.** `윈도우포트:컨테이너포트`. (예: `18000:8000`)
- `-it`: **Interactive.** 컨테이너 내부 터미널로 들어갈 때 필수.

### 🔄 Build & Run 루틴
```bash
# 1. 파일 생성 (requirements.txt가 없으면 빌드 에러!)
touch requirements.txt

# 2. 이미지 빌드 (마지막 점 '.'을 잊지 마세요!)
docker build -t my-server:1.0 .

# 3. 컨테이너 실행
docker run -d -p 18000:8000 --name my_running_app my-server:1.0
🐍 4. Python/Flask 실전 예제
<details>
<summary>📂 <b>Dockerfile 작성 예시 (클릭하여 펼치기)</b></summary>

