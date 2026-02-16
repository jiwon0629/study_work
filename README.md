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

### 🔄 Build & Run 루틴
```bash
# 1. 파일 생성 (requirements.txt가 없으면 빌드 에러!)
touch requirements.txt

# 2. 이미지 빌드 (마지막 점 '.'을 잊지 마세요!)
docker build -t my-server:1.0 .

# 3. 컨테이너 실행
docker run -d -p 18000:8000 --name my_running_app my-server:1.0
```
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
stat /bash: no such file...

원인: 경로를 잘못 입력함.

해결: /bash가 아니라 /bin/bash로 입력하세요.

No such file: requirements.txt

원인: 빌드 시 파일 누락.

해결: touch requirements.txt로 빈 파일 생성.

Last Updated: 2026-02-16

Maintainer: Your Name


---

### 💡 왜 이전에는 회색으로 나왔나요?
마크다운 문법에서 ` ```bash `는 **"여기서부터 코드가 시작된다"**는 신호입니다. 다시 ` ``` `를 써서 **"여기서 코드가 끝났다"**고 선언해주지 않으면, 깃허브는 그 아래 모든 글자를 코드로 간주해서 회색 박스에 넣어버립니다.

이제 위 코드를 복사해서 붙여넣으시면 🐍 **4. Python/Flask** 부분부터는 정상적으로 흰색 배경에 예쁜 레이아웃으로 보일 거예요!

**더 수정하고 싶은 디자인 포인트가 있으신가요?** 예를 들어 표의 색상을 바꾸거나 아이콘을 더 넣고 싶
