# 비디오는 파일 크기가 매우 크고 프레임 수가 많기 때문에, 단순히 루프를 돌면 매우 느립니다. 그래서 이 파일은 멀티프로세싱 파이프라인(Producer-Consumer 패턴) 구조를 사용하여 속도를 극대화했습니다.
# 구조 설명: 
# 비디오 읽기(Process 1) -> 화질 개선(Process 2) -> 객체 탐지(Process 3) -> 비디오 쓰기(Process 4)가 동시에 돌아가며 큐(Queue)를 통해 데이터를 주고받습니다.
import cv2
import os
import json 
from pathlib import Path
from datetime import datetime
import multiprocessing as mp
import sys
from typing import Optional, Tuple

sys.path.append("../") # 상위 디렉토리의 모듈을 참조하기 위함
from process.video import video_read, video_write, rtdetr_detect, yolo_detect, nox_predict
from utils import save_process_time, video_metadata

def video_process(
    ini_dict: dict,
    input_path: str,
    input_dir: str,
    result_dir: str,
    nox_apply: bool,
    rtdetr_apply: bool,
    yolo_apply: bool, 
    save_csv: bool,
    concat_apply: bool,
) -> None:   
    
    # [경로 설정] 결과 비디오 파일의 저장 경로를 설정합니다.
    relative_path = Path(input_path).relative_to(input_dir)
    output_path = Path(result_dir) / relative_path.parent / (relative_path.stem + "_NOX.avi")
    
    os.makedirs(output_path.parent, exist_ok=True)
    output_file_path: str = f"{output_path.parent}/{output_path.name}"
    print(f"input file : {input_path} , output file : {output_path}")
    
    # [메타데이터] 비디오의 FPS, 너비, 높이 및 모델 입력 규격을 가져와서 출력 비디오 설정에 사용합니다.
    org_fps, org_w, org_h, model_input_w, model_input_h = video_metadata(Path(input_path), ini_dict)
    
    # [프레임 수] 전체 프레임 수를 파악하여 진행 상황을 관리하거나 로그를 남깁니다.
    cap = cv2.VideoCapture(str(input_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    # [화면 구성] concat_apply가 True면 원본-결과를 가로로 붙이기 위해 출력 너비를 2배로 설정합니다.
    if concat_apply:
        out_shape: Tuple[int, int] = (org_w * 2, org_h)
    else:
        out_shape: Tuple[int, int] = (org_w , org_h)
        
    output_path_str = str(f"{result_dir}/{output_path.name}")

    now_time: datetime = datetime.now()
    
    # [병렬 처리 큐] 각 프로세스 간 데이터를 전달하는 통로입니다. 
    # 큐 크기를 60으로 제한하여 메모리 부족(OOM) 현상을 방지합니다.
    read_queue: mp.Queue = mp.Queue(60)        # 읽기 -> 화질개선/탐지
    nox_prdict_queue: mp.Queue = mp.Queue(60)  # 화질개선 -> 탐지
    obj_detect_queue: mp.Queue = mp.Queue(60)  # 탐지 -> 쓰기
    
    # [동기화 이벤트] 프로세스들의 시작과 종료 상태를 제어하는 플래그입니다.
    loop_event: mp.Event = mp.Event()
    loop_event.set()
    finish_event: mp.Event = mp.Event()
    finish_event.set()
        
    print("File conversion is in progress. Please wait.")

    # --- 파이프라인 프로세스 구성 ---
    
    # 프로세스 1: 비디오 파일에서 프레임을 읽어 read_queue에 넣습니다. (Producer)
    video_read_p: mp.Process = mp.Process(
        target=video_read, 
        args=(read_queue, loop_event, input_path)
    )
    video_read_p.start()
    
    # 프로세스 2: read_queue에서 프레임을 가져와 NOX 화질 개선 후 nox_prdict_queue에 넣습니다.
    if nox_apply:
        nox_predict_p: mp.Process = mp.Process(
            target=nox_predict, 
            args=(read_queue, nox_prdict_queue, loop_event, ini_dict, org_w, org_h, model_input_w, model_input_h, concat_apply)
        )
        nox_predict_p.start()
    else:
        nox_predict_p = None
    
    # 프로세스 3: 이전 단계의 큐에서 프레임을 가져와 객체를 탐지하고 obj_detect_queue에 넣습니다.
    if rtdetr_apply:
        obj_detect_p: mp.Process = mp.Process(
            target=rtdetr_detect, 
            args=(nox_prdict_queue if nox_apply else read_queue, obj_detect_queue, loop_event, ini_dict)
        )
        obj_detect_p.start()
    elif yolo_apply:
        obj_detect_p: mp.Process = mp.Process(
            target=yolo_detect, 
            args=(nox_prdict_queue if nox_apply else read_queue, obj_detect_queue, loop_event, ini_dict)
        )
        obj_detect_p.start()
    else:
        obj_detect_p = None

    # 프로세스 4: 탐지가 완료된 프레임을 받아 최종 비디오 파일로 저장합니다. (Consumer)
    use_detect_queue = (rtdetr_apply or yolo_apply)
    video_write_p: mp.Process = mp.Process(
        target=video_write, 
        args=(obj_detect_queue if use_detect_queue else nox_prdict_queue, loop_event, finish_event, org_fps, out_shape, output_path_str)
    )
    video_write_p.start()

    # [프로세스 감시] 모든 프로세스가 정상 종료될 때까지 대기합니다. 
    # finish_event가 해제되면 모든 프로세스를 강제 종료하고 루프를 빠져나옵니다.
    while True:
        if not finish_event.is_set():
            video_read_p.terminate()
            if nox_apply: nox_predict_p.terminate()
            if obj_detect_p: obj_detect_p.terminate()
            video_write_p.terminate()
            break
            
    # 자원 회수를 위해 각 프로세스가 완전히 종료될 때까지 기다립니다.
    video_read_p.join()
    if nox_apply: nox_predict_p.join()
    if obj_detect_p: obj_detect_p.join()
    video_write_p.join()
    
    # [결과 기록] 처리 완료 후 총 소요 시간을 계산합니다.
    process_time_seconds = (datetime.now() - now_time).total_seconds()
    
    # 비디오 처리 결과(프레임 수, 시간 등)를 result_video.json에 리스트 형태로 누적 저장합니다.
    video_json_path = os.path.join(result_dir, "result_video.json")
    video_data = []
    if os.path.exists(video_json_path):
        with open(video_json_path, 'r') as f:
            try: video_data = json.load(f)
            except: video_data = []
            
    video_data.append({
        "input_path": input_path,
        "total_frames": total_frames,
        "total_inference_time": process_time_seconds
    })
    
    with open(video_json_path, 'w') as f:
        json.dump(video_data, f, indent=2)

    # 요청 시 파일별 비디오 처리 시간을 CSV에 기록합니다.
    if save_csv:  
        save_process_time(save_csv, str(input_path), output_file_path, str(datetime.now() - now_time))
        
    print("Video processed successfully")