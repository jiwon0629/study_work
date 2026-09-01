내가 나눈 파티션과 용량 확인
```
df -h
```
메모리(RAM) 및 스왑(Swap) 상태 확인
```
free -m
```
연결된 디스크 구조를 나무 형태로 보기
```
lsblk
```
복사
```
cp [원본] [대상]
```
```
cp -r [폴더명] [복사할 폴더명] : 폴더 내부의 모든 것을 포함
```

이동
```
mv [원본] [대상]
```

??
```
netstat -na | more
```

용량 확인
```
du -sh .
```
파일 개수 확인
```
find . -type f | wc -l
```
GPU 확인
```
nvtop
```
윈도우에서 ssh 내부로 파일 옮길때
```
scp "윈도우 파일 경로" ID@IP주소:~/(ssh안의 파일 경로)
```
윈도우에서 ssh 내부로 폴더 옮길때
```
scp -r "윈도우 경로" ID@IP주소:~/(ssh안의 폴더 경로)
```

리눅스 서버(Host) → 도커 컨테이너로 파일 복사
```
docker cp ~/(리눅스 서버 파일 경로) (컨테이너 ID):/app/(도커 내의 경로)
```
용량 확인
```
ls -lh /app/(도커 내의 경로)
```

vi전체 선택 
```
shift + v + g
```
vi 전체 선택 후 삭제
```
d
```

GPU/VRAM 핵심 정보만 깔끔하게 출력(1초마다 사용 중인 VRAM / 전체 VRAM / GPU 사용률)
```
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv -l 1
```
앞 명령어의 실행 결과를 뒤 명령어의 입력으로 넘긴다.
두 개 이상의 명령어를 이어주는 역할
```
|(파이프)
```
글자나 단어를 검색하는 도구
```
grep
```
현재 위치
```
.
```
홈 디렉토리
```
~
```
찾기
```
find
```
