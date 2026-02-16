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

Dockerfile
FROM python:3.8-slim

# 작업 디렉토리 설정
WORKDIR /app

# 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . .

# 실행 (Flask 기본 5000 또는 사용자 정의 8000)
EXPOSE 8000
CMD ["python", "app.py"]
</details>

<details>
<summary>💻 <b>컨테이너 내부 작업 (EOF 기법)</b></summary>

Bash
# 컨테이너 접속 없이 바로 파일 쓰기
cat > app.py << 'EOF'
from flask import Flask
app = Flask(__name__)
@app.route('/')
def hello(): return "Hello from Docker!"
if __name__ == "__main__": app.run(host='0.0.0.0', port=8000)
EOF

# 실행 중인 컨테이너 접속
docker exec -it my_running_app /bin/bash
</details>

🚨 5. 트러블슈팅 가이드 (에러 해결)
💡 에러는 성장의 발판입니다!

stat /bash: no such file...

원인: 경로를 잘못 입력함.

해결: /bash가 아니라 /bin/bash로 입력하세요.

No such file: requirements.txt

원인: 빌드할 때 폴더에 필요한 파일이 없음.

해결: touch requirements.txt로 빈 파일이라도 만들어 두세요.

Permission denied

해결: 명령어 앞에 sudo를 붙이거나, 현재 유저를 docker 그룹에 추가하세요.

💾 6. 데이터 관리 & 백업
DB 덤프: docker exec postgres_db pg_dump -U user -d dbname > backup.sql

데이터 보존: 컨테이너가 삭제되어도 데이터는 남아야 합니다. 반드시 Docker Volume을 활용하세요.

Last Updated: 2026-02-15
Maintainer: [Your Name/GitHub ID]


---

### 💡 팁: 깃허브에서 더 예쁘게 보여주는 방법
1.  **이미지 추가:** `` 부분에 실제 작동 구조 이미지를 구글링해서 넣거나 직접 그린 그림을 넣으면 훨씬 전문적입니다.
2.  **프로필 링크:** 맨 아래 `Maintainer` 부분에 본인의 깃허브 프로필 링크를 걸어보세요.
3.  **파일 구성:** 프로젝트 최상단에 이 내용을 `README.md`라는 이름으로 저장하면 깃허브 저장소 메인에 자동으로 나타납니다.

혹시 **배경 색상이 들어간 특정 레이아웃**이나 **다이어그램(순서도)** 같은 것이 더 필요하신가요? 말씀
