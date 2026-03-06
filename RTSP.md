# 🚀 FFmpeg 기반 RTSP 다중 채널 스트리밍 테스트 시스템

이 프로젝트는 **객체 탐지(Object Detection)** 모델 및 분석 서버의 내구성 테스트를 위해 여러 개의 MP4 영상 파일을 실시간 **RTSP 스트림**으로 변환하여 송출하는 자동화 스크립트입니다.

## 📌 프로젝트 개요
* **목적**: 다수의 CCTV 채널이 가동되는 환경을 가상으로 구축하여 분석 시스템의 부하 및 안정성 테스트 수행.
* **주요 기능**:
  * 특정 폴더(`input/test/video_test`) 내의 MP4 파일을 자동 스캔 및 정렬.
  * FFmpeg 프로세스를 병렬로 실행하여 각 파일을 독립된 RTSP 채널(`test1`, `test2`...)로 송출.
  * 고효율 인코딩 설정을 통해 단일 시스템에서 저부하 다중 송출(10개 이상) 최적화.

## 🛠 시스템 구조 및 작동 원리


1. **송출부 (Python & FFmpeg)**: `subprocess`를 통해 FFmpeg를 제어하며, 영상을 H.264 코덱으로 실시간 인코딩하여 서버로 푸시(Push)합니다.
2. **중계부 (MediaMTX)**: 윈도우 호스트에서 실행되는 오픈소스 미디어 서버로, RTSP 데이터를 수신하여 관리합니다.
3. **수신부 (Web/VLC)**: 서버에 등록된 스트림을 WebRTC(포트 8889) 또는 RTSP(포트 8554) 프로토콜을 통해 실시간 모니터링합니다.

## 📋 사전 준비 사항
* **MediaMTX**: [공식 릴리즈](https://github.com/bluenviron/mediamtx/releases)에서 다운로드 후 실행 (`mediamtx.exe`).
* **FFmpeg**: 시스템 환경 변수에 등록되어 터미널에서 `ffmpeg` 명령어가 동작해야 합니다.
* **네트워크**: 도커 컨테이너에서 실행 시 호스트 IP 접근 권한 및 방화벽 설정이 필요합니다.

## 💻 코드 상세 설명

### 1. RTSP 송출 핵심 로직
`start_durability_test` 함수는 FFmpeg 명령어를 생성하고 백그라운드에서 실행합니다.

```python
def start_durability_test(file_path, stream_name):
    # 송출 대상 서버 주소 (윈도우 호스트 IP 및 RTSP 기본 포트 8554)
    rtsp_url = f"rtsp주소/{stream_name}"
    
    command = [
        'ffmpeg',
        '-re',                          # 실시간 속도(Real-time) 유지
        '-stream_loop', '-1',           # 영상 무한 반복 실행
        '-i', file_path,                # 입력 파일 경로
        '-c:v', 'libx264',              # H.264 비디오 코덱 지정
        '-preset', 'ultrafast',         # CPU 사용량 최소화를 위한 인코딩 프리셋
        '-tune', 'zerolatency',         # 스트리밍 지연 시간 제거
        '-b:v', '500k',                 # 비트레이트 제한 (500kbps)
        '-flags', '+global_header',     # 표준 RTSP 전송을 위한 헤더 설정
        '-crf', '28',                   # 품질 지수 설정 (저부하 최적화)
        '-vf', 'scale=640:360,fps=15',  # 해상도 축소 및 프레임 하향 조정
        '-f', 'rtsp',                   # 출력 포맷 지정
        '-rtsp_transport', 'tcp',       # 안정적인 전송을 위한 TCP 프로토콜 사용
        rtsp_url
    ]
    # 백그라운드 프로세스 실행 (로그 출력 제외로 성능 최적화)
    return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
```
## 💻 전체 코드
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


## ⚙️ 2. FFmpeg 주요 옵션 상세

다중 채널 송출 시 리소스 효율을 극대화하기 위해 다음과 같은 옵션을 사용합니다.

| 옵션 | 원리 및 역할 |
| :--- | :--- |
| **`-re`** | 원본 영상의 프레임 레이트(FPS)에 맞춰 데이터를 읽어 실시간 스트리밍 속도를 구현합니다. |
| **`-preset ultrafast`** | 인코딩 연산량을 최소로 줄여 30개 이상의 다중 채널 송출 시에도 CPU 부하를 방지합니다. |
| **`-vf scale=640:360`** | 고해상도 영상을 저해상도로 변환하여 네트워크 대역폭과 시스템 리소스를 크게 절약합니다. |
| **`-rtsp_transport tcp`** | 도커-호스트 간 가상 네트워크 환경에서 데이터 유실 없는 안정적인 송출을 보장합니다. |

---

## 🚀 실행 및 모니터링

시스템을 가동하고 스트리밍 상태를 확인하는 방법입니다.

1. **서버 실행**: 윈도우 터미널(CMD/PowerShell)에서 MediaMTX 폴더로 이동 후 실행합니다.
   ```bash
   ./mediamtx
   ```
   스크립트 실행: 컨테이너 내부 터미널에서 파이썬 스크립트를 실행합니다.

```bash
python RTSP.py
```
결과 확인:

WebRTC: 브라우저 주소창에 확인 주소/test1 입력 (실시간 확인)

RTSP: VLC 플레이어에서 rtsp://ip:port/test1 열기 (네트워크 스트림 확인)

## ⚠️ 주의 사항
성공적인 연결을 위해 다음 두 가지 사항을 반드시 확인하세요.

Localhost 이슈 (Network Isolation):

도커 컨테이너 내부에서 127.0.0.1은 컨테이너 자신을 가리킵니다.

윈도우 호스트에 있는 MediaMTX에 접속하려면 반드시 호스트 IP 또는 **host.docker.internal**을 사용해야 합니다.

윈도우 방화벽 설정:

윈도우 방화벽에서 MediaMTX가 사용하는 다음 포트들의 인바운드 허용이 필수적입니다.

8554 포트: RTSP 송수신용

8889 포트: WebRTC 웹 모니터링용

## 결과 사진
<img width="2262" height="1202" alt="RTSP_1" src="https://github.com/user-attachments/assets/c4196df9-a23f-42b4-aa39-d9dea1626ec0" />



