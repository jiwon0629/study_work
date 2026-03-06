```python
import subprocess 
import os         
import time       

def start_durability_test(file_path, stream_name):
   
    rtsp_url = f"rtsp://192.168.0.24:8554/{stream_name}"
    
    # FFmpeg 명령어 구성 (내구성 테스트를 위해 리소스 사용량 최적화)
    command = [
        'ffmpeg',
        '-re',                          # 실시간 속도 유지
        '-stream_loop', '-1',           # 테스트를 위해 영상 무한 반복
        '-i', file_path,                # 입력 파일 경로 (로컬 8551번대 소스 등)
        '-c:v', 'libx264',              # H.264 인코딩
        '-preset', 'ultrafast',         # CPU 부하 최소화 (30개 동시 송출 위함)
        '-tune', 'zerolatency',         # 지연 시간 최소화
        '-b:v', '500k',
        '-flags', '+global_header',
        '-crf', '28',                   # 비트레이트보다 품질 지수 우선 (23~28 권장)
        '-maxrate', '500k',             # 채널당 최대 대역폭 제한
        '-bufsize', '1M',               
        '-vf', 'scale=640:360,fps=15', # 해상도와 프레임 살짝 하향 (30개 동시 송출용)
        '-f', 'rtsp',                   # 송출 포맷
        '-rtsp_transport', 'tcp',       # 안정적인 TCP 전송
        rtsp_url                        # 최종 송출 주소
    ]
    
    return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


video_path = "input/test/video_test" 
video_files = [f for f in os.listdir(video_path) if f.endswith('mp4')]
video_files.sort()
test_channels_count = min(len(video_files), 10)
processes = []

try:
    for i in range(test_channels_count):
        file_name = video_files[i]
        full_path = os.path.join(video_path, file_name)
        channel_name = f"test{i+1}" 
        
        
        p = start_durability_test(full_path, channel_name)
        processes.append(p)
        
        print(f"[{i}/{test_channels_count}] 송출 중: http://192.168.0.24:8889/{channel_name}")
        
       
        time.sleep(0.1)

    print("\n송출 완료. 종료 : ctrl+C")
    
    
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    for p in processes:
        p.terminate()
```



