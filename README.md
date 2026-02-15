# study_work  


🐧 WSL 기반 Docker & Container 완벽 가이드이 문서는 Windows Subsystem for Linux (WSL) 환경에서 Docker를 효율적으로 활용하고, 컨테이너화된 애플리케이션을 관리하는 핵심 개념과 명령어를 정리합니다.1. 왜 WSL에서 Docker를 사용하는가?환경의 일치 (Parity): 대부분의 서버는 리눅스입니다. 개발 단계(WSL)부터 운영 환경과 동일한 리눅스 환경을 사용함으로써 "내 컴퓨터에선 되는데 서버에선 안 돼요"라는 문제를 원천 차단합니다.성능과 안정성: Windows용 Docker Desktop은 내부적으로 WSL 2 백엔드를 사용합니다. WSL을 직접 활용하면 파일 시스템 액세스 속도가 훨씬 빠르고 시스템 자원을 효율적으로 사용합니다.2. Docker 핵심 개념: 설계도와 실체구분개념비유특징Dockerfile텍스트 스크립트설명서환경 설정, 소스 복사, 실행 명령 정의Image실행 파일 패키지설명서로 만든 설계도불변성(Immutable), 버전 관리 가능Container실행 중인 프로세스설계도로 지은 실제 집격리성(Isolation), 가볍고 빠른 실행3. Docker 필수 명령어 및 옵션 요약💡 주요 옵션-t (Tag): 이미지에 이름과 버전을 부여 (예: my-app:1.0). 지정하지 않으면 <none>으로 표시되어 관리가 어렵습니다.-d (Detached): 컨테이너를 백그라운드에서 실행합니다.-p (Publish): 호스트포트:컨테이너포트. 외부(Windows 브라우저)에서 접속하기 위해 필수입니다.-it: -i(Interactive) + -t(TTY). 컨테이너 내부 터미널과 상호작용할 때 사용합니다.🔄 run vs execdocker run: 새로운 이미지로 새 컨테이너를 생성하고 실행합니다. (매번 실행 시 데이터 초기화 주의)docker exec: 이미 실행 중인 컨테이너 내부에서 명령어를 실행합니다. (점검 및 디버깅용)4. 이미지 빌드 및 실행 루틴 (Python/Flask 예시)① 파일 준비DockerfileDockerfileFROM python:3.8-slim      # 베이스 이미지 설정
WORKDIR /app              # 컨테이너 내 작업 폴더
RUN pip install -r requirements.txt  # 라이브러리 설치
COPY . .                  # 현재 폴더의 모든 파일을 컨테이너로 복사
EXPOSE 8000               # 8000번 포트 사용 예고
CMD ["python", "app.py"]  # 시작 명령
② 빌드 및 실행 프로세스Bash# 1. 빌드 (마지막 점 '.' 필수 - 현재 경로 의미)
docker build -t my-python-app:1.0 .

# 2. 실행 (Windows 18000포트 -> 컨테이너 8000포트 연결)
docker run -d -p 18000:8000 --name my_server my-python-app:1.0
5. 컨테이너 내부 관리 및 유지보수📂 파일 작업 (EOF 기법)에디터 없이 터미널에서 즉시 파일 생성:Bashcat > app.py << 'EOF'
from flask import Flask
app = Flask(__name__)
@app.route('/')
def hello(): return "Hello Docker!"
if __name__ == "__main__": app.run(host='0.0.0.0', port=8000)
EOF
🗄️ 데이터베이스 백업 (PostgreSQL)컨테이너 밖(WSL)으로 DB 덤프 파일 추출:Bashdocker exec postgres_db pg_dump -U [사용자명] -d [DB명] > backup.sql
🛠️ 기타 관리 명령어docker ps -a: 모든 컨테이너 상태 확인docker volume: 컨테이너 삭제 후에도 데이터를 보존하기 위한 저장소 관리docker stop / start / restart: 컨테이너 상태 제어docker exec -it [이름] /bin/bash: 컨테이너 내부 터미널 접속6. 트러블슈팅 (에러 해결)에러 메시지원인해결책stat /bash: no such file...경로 오류/bash 대신 /bin/bash 사용No such file: requirements.txt빌드 시 파일 누락touch requirements.txt로 빈 파일 생성 후 재빌드is not running컨테이너 중지됨docker start [이름] 실행Permission denied권한 부족명령어 앞 sudo 추가 또는 유저 그룹 설정 확인Tip: WSL 환경에서는 Windows 브라우저에서 localhost:18000으로 접속하면 포트 포워딩을 통해 컨테이너의 서비스에 바로 접근할 수 있습니다.
