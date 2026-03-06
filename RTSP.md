```python
# 객체 탐지 내구성 테스트용 RTSP 다중 송출 프로그램
# 8554 포트 활용, 채널명 test1~30 확장
# 브라우저 확인: rtsp주소/test1 ~ rtsp주소/test30

import subprocess # 외부 프로세스(FFmpeg) 실행을 위한 모듈
import os         # 파일 경로 및 시스템 관리를 위한 모듈
import time       # 프로세스 실행 간격 조절을 위한 모듈

def start_durability_test(file_path, stream_name):
   
    rtsp_url = f"rtsp주소/{stream_name}"
    
    # FFmpeg 명령어 구성 (내구성 테스트를 위해 리소스 사용량 최적화)(리스트 형태로 작성하여 안정성 확보)
    command = [
        'ffmpeg',
        '-re',                          # [중요] 실시간 속도(Real-time)로 읽기. 없으면 순식간에 파일을 읽어버림
        '-stream_loop', '-1',           # 테스트를 위해 영상 무한 반복
        '-i', file_path,                # 입력 파일 경로 (로컬 8551번대 소스 등)
        '-c:v', 'libx264',              # 비디오 코덱을 H.264(x264)로 지정
        '-preset', 'ultrafast',         # CPU 사용량을 최소화하기 위해 가장 빠른 인코딩 설정 사용
        '-tune', 'zerolatency',         # 실시간 송출 시 발생하는 지연(Latency)을 최소화
        '-crf', '28',                   # 비트레이트보다 품질 지수 우선 (23~28 권장)
        '-maxrate', '1.5M',             # 채널당 최대 대역폭 제한(최대 비트레이트 제한 (네트워크 과부하 방지))
        '-bufsize', '3M',               # 버퍼 크기 설정 (안정적인 송출 유지)
        '-vf', 'scale=1280:720,fps=20', # 해상도와 프레임 살짝 하향 (30개 동시 송출용)
        '-f', 'rtsp',                   # 출력 형식을 RTSP 프로토콜로 지정
        '-rtsp_transport', 'tcp',       # 패킷 손실 방지를 위해 UDP 대신 안정적인 TCP 방식 사용
        rtsp_url                        # 최종 송출 주소
    ]
    
    # 프로세스를 백그라운드에서 실행하고 반환
    # subprocess.Popen: FFmpeg를 백그라운드 프로세스로 실행
    # stdout/stderr=DEVNULL: 터미널에 출력되는 방대한 로그 메시지를 무시 (성능 저하 방지)
    return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# --- 메인 실행부 (내구성 테스트 설정) ---
base_video = "input/fire/1.mp4" # 테스트에 사용할 기본 소스 파일
test_channels_count = 30        # 30개 채널 생성
processes = []                  # 생성된 프로세스들을 관리할 리스트

try:
    # 1번부터 30번까지 채널 생성 루프
    for i in range(1, test_channels_count + 1):
        channel_name = f"test{i}" # 채널 이름 설정 (test1, test2...)
        
        # 송출 프로세스 시작
        p = start_durability_test(base_video, channel_name)
        processes.append(p) # 나중에 한꺼번에 종료하기 위해 리스트에 저장
        
        print(f"[{i}/{test_channels_count}] 송출 중: rtsp주소/{channel_name}")
        
        # 서버 과부하 방지를 위해 실행 간격을 아주 짧게 둠
        time.sleep(0.1)

    print("\n모든 채널 송출 완료. 종료 : ctrl+C")
    
    # 모든 프로세스가 유지되도록 대기
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    for p in processes:
        p.terminate() # 모든 FFmpeg 프로세스 강제 종료

```



