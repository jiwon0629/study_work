# RTSP 스트리밍 영상을 캔버스에 띄우기.   
실시간 영상을 위해 window.after 루프 구조를 적용

RTSP 스트리밍 캔버스 출력 코드
```Python
import cv2
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk

# 1. RTSP URL 설정 (제공해주신 주소)
rtsp_url = "rtsp://admin:qazwsx123!@192.168.0.36:554/0/H.264/media.smp"

# 2. 메인 윈도우 설정
window = tk.Tk()
window.title("PCI - RTSP Stream on Canvas")
window.geometry('1000x1000') # 소문자 x 사용

# 3. 캔버스 생성
canvas = tk.Canvas(window, width=1000, height=1000, background='gray')
canvas.place(x=0, y=0)

# 4. 영상 캡처 객체 생성
cap = cv2.VideoCapture(rtsp_url)

def update_frame():
    # A. 영상에서 프레임 한 장 읽기
    ret, frame = cap.read()
    
    if ret:
        # B. OpenCV(BGR) 이미지를 PIL(RGB) 형식으로 변환
        # OpenCV는 기본적으로 Blue, Green, Red 순서지만, 
        # 화면에 뿌릴 때는 Red, Green, Blue 순서여야 색이 제대로 나옵니다.
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # C. [PCI 실습 포인트] 여기서 이미지를 펴거나 크기를 조절합니다.
        # 예: 1000x1000 캔버스에 맞게 이미지 크기 조절
        frame = cv2.resize(frame, (1000, 1000))
        
        # D. Tkinter용 이미지 객체로 변환
        img = Image.fromarray(frame)
        tk_img = ImageTk.PhotoImage(image=img) # 소문자 k 확인
        
        # E. 캔버스에 이미지 업데이트
        canvas.create_image(0, 0, anchor=tk.NW, image=tk_img)
        
        # F. 가비지 컬렉션 방지 (참조 유지)
        canvas.image = tk_img
    else:
        print("프레임을 읽을 수 없습니다. 연결 상태를 확인하세요.")

    # G. 10ms 후에 이 함수를 다시 실행 (실시간 루프 생성)
    window.after(10, update_frame)

# 프로그램 시작 시 영상 업데이트 함수 최초 호출
update_frame()

# 창 유지 루프
window.mainloop() # mainloop 오타 수정 완료
코드의 핵심 포인트 설명
cv2.cvtColor(frame, cv2.COLOR_BGR2RGB):
```
OpenCV는 색상을 파란색(B) -> 초록색(G) -> 빨간색(R) 순으로 읽습니다.

하지만 윈도우 창(PIL, Tkinter)은 R -> G -> B 순서를 쓰기 때문에 이 변환을 안 해주면 사람 얼굴이 파랗게 보일 수 있습니다.

window.after(10, update_frame):

while 문을 쓰면 윈도우 창이 얼어버려서 마우스 클릭도 안 됩니다.

after는 "10밀리초 뒤에 다시 이 함수를 실행해줘"라고 예약하는 방식으로, 창이 부드럽게 작동하면서 영상도 계속 갱신되게 합니다.

cv2.resize(frame, (1000, 1000)):

카메라 원본 영상 크기가 캔버스 크기와 다를 수 있습니다. geometry에서 설정한 크기에 맞춰 강제로 늘리거나 줄여서 캔버스에 꽉 차게 만듭니다.

실행 전 체크리스트
네트워크: 이 코드를 실행하는 컴퓨터가 카메라와 동일한 WIFI/유선망에 연결되어 있나요?

라이브러리: 아까 설치한 opencv-python과 pillow가 잘 설치되어 있는지 다시 확인해 주세요.
