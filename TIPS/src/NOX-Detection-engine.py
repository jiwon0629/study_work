# 이 파일은 표준적인 검출 파이프라인 컨트롤러입니다. 다양한 모델(NOX, RT-DETR, YOLO)을 선택적으로 사용할 수 있도록 설계되었으며, 이미지와 비디오 모드를 모두 지원합니다.
import numpy as np
# Numpy 1.24+ 버전에서 np.bool이 제거되어 발생하는 오류를 방지하기 위한 호환성 패치입니다.
np.bool = bool 

import argparse # 명령행 인자를 통해 입력/출력 경로, 모델 선택 등의 옵션을 유연하게 받기 위해 사용합니다.
import os
import shutil # 결과 폴더를 완전히 삭제하고 다시 생성하는 등 고수준 파일 작업을 수행합니다.
import multiprocessing as mp # GPU 연산 시 메모리 격리를 위해 'spawn' 방식의 멀티프로세싱을 제어합니다.
from pathlib import Path # OS에 상관없이 경로를 객체 형태로 안전하게 다루기 위해 사용합니다.

# [의존성] utils: 시스템 제약 출력, 불리언 타입 변환, 경로 검증, 설정 로드 함수를 가져옵니다.
from utils import obj_print_program_limitations, argparse_type_bool, custom_error, ConfigManager
# [의존성] process: 실제 이미지/비디오 처리 로직이 구현된 함수를 가져옵니다.
from process import image_process, video_process
# [의존성] model: 최적화된 TensorRT 모델 및 YOLO 모델 클래스를 가져옵니다.
from model.nox import NOX_TRT_Model
from model.yolo_inference import YOLO_Model

class NOX_converter():
    """
    이미지/비디오의 화질 개선 및 객체 탐지 전체 흐름을 제어하는 메인 클래스입니다.
    """
    def __init__(self,
                 input_dir,      # 데이터 입력 경로
                 result_dir,     # 결과 저장 경로
                 nox_apply=True, # NOX 화질 개선 적용 여부
                 rtdetr_apply=False, # RT-DETR 모델 적용 여부
                 yolo_apply=False,   # YOLO 모델 적용 여부
                 mAP_path=None,  # mAP 계산용 정답 데이터 경로
                 mAP=False,      # mAP 계산 수행 여부
                 save_csv=False, # 처리 시간 기록 여부
                 config_path="/ai-video-converter/src/config.ini", # 설정 파일 경로
                 concat_apply=False, # 결과 이미지 병합(원본+결과) 여부
                 clean_output=True,  # 실행 전 출력 폴더 정리 여부
                 mode="both",    # 처리 모드: 'image', 'video', 'both'
                 ):
        self.input_dir = Path(input_dir)
        self.result_dir = Path(result_dir)
        self.nox_apply = nox_apply
        self.rtdetr_apply = rtdetr_apply
        self.yolo_apply = yolo_apply
        self.mAP_path = Path(mAP_path) if mAP_path else None
        self.mAP = mAP
        self.concat_apply = concat_apply
        self.clean_output = clean_output
        self.mode = mode 
        
        # [설정 관리] 하드코딩을 방지하고 외부 .ini 파일에서 모든 하이퍼파라미터를 관리합니다.
        config = ConfigManager(config_path)
        self.ini_dict = config.get_config_dict()
        
        # 선택된 모델에 따라 JSON 설정 경로를 동적으로 업데이트하여 모델 간 설정 충돌을 막습니다.
        if yolo_apply:
            self.ini_dict['CONFIG']['JSON_PATH'] = self.ini_dict['YOLO'].get('JSON_PATH', self.ini_dict['RTDETR']['JSON_PATH'])
        else:
            self.ini_dict['CONFIG']['JSON_PATH'] = self.ini_dict['RTDETR']['JSON_PATH']
            
        self.save_csv = self.ini_dict['CONFIG']['PROCESS_TIME_CSV_PATH'] if save_csv else None

        # CUDA/GPU 환경에서 멀티프로세싱 사용 시 'fork' 방식은 데드락 위험이 크므로 'spawn'을 강제합니다.
        mp.set_start_method('spawn', force=True)
        self.mAP_List = []  

    def process_run(self):
        # [데이터 무결성] 이전 실행 결과가 섞여 분석 결과가 왜곡되는 것을 방지하기 위해 폴더를 비웁니다.
        if self.clean_output and self.result_dir.exists():
            print(f"Cleaning output directory: {self.result_dir}")
            result_json = self.result_dir / 'result.json'
            if result_json.exists():
                result_json.unlink()
            result_video_json = self.result_dir / 'result_video.json'
            if result_video_json.exists():
                result_video_json.unlink()
            for subdir in ['nox', 'labels', 'detections']:
                subdir_path = self.result_dir / subdir
                if subdir_path.exists():
                    shutil.rmtree(subdir_path)
            print("Output directory cleaned.\n")

        # 1. 시스템 제약 사항 출력 및 입력 데이터의 유효성을 미리 검사하여 Crash를 방지합니다.
        obj_print_program_limitations(self.input_dir, self.result_dir)
        file_list, success = custom_error(
            self.input_dir, self.result_dir, self.nox_apply, self.rtdetr_apply, self.yolo_apply, self.mAP, self.ini_dict, self.concat_apply
        )
        if not success:
            return

        # GPU 및 모델 입력 규격 설정
        gpu = self.ini_dict['CONFIG']['GPU']
        batch = self.ini_dict['CONFIG']['BATCH']
        channel = self.ini_dict['CONFIG']['CHANNEL']
        nox_width, nox_height = 1920, 1080 # NOX 모델의 고정 입력 해상도
        
        # [자원 효율성] 필요한 모델만 GPU 메모리에 올리기 위해 조건부 로딩을 수행합니다.
        nox_model = None
        if self.nox_apply:
            print("Loading NOX Model...")
            nox_model = NOX_TRT_Model(
                gpu=gpu,
                model_path=self.ini_dict['NOX']['NOX_MODEL_PATH'],
                input_shape=(batch, nox_height, nox_width, channel),
            )

        yolo_model = None
        if self.yolo_apply:
            print("Loading  Model...")
            yolo_model = YOLO_Model(
                model_path=self.ini_dict['YOLO']['YOLO_MODEL_PATH'],
                device='cuda' if gpu >= 0 else 'cpu'
            )
        
        # [이미지 프로세싱] 대량의 이미지 파일을 순회하며 개선 및 탐지를 수행합니다.
        if self.mode in ['image', 'both']:
            image_dir = self.input_dir / 'image'
            if image_dir.exists():
                image_files = list(image_dir.rglob('*.jpg')) + list(image_dir.rglob('*.jpeg')) + list(image_dir.rglob('*.png'))
                total_files = len(image_files)
                print(f"Processing images (Mode: {self.mode})...")
                for idx, input_path in enumerate(image_files, start=1):
                    if input_path.is_file():
                        # 개별 이미지 처리 로직을 캡슐화한 image_process 함수에 모든 파라미터를 전달합니다.
                        image_process(
                            ini_dict=self.ini_dict,
                            input_path=input_path, 
                            input_dir=self.input_dir,
                            result_dir=self.result_dir,
                            nox_apply=self.nox_apply,
                            rtdetr_apply=self.rtdetr_apply,
                            yolo_apply=self.yolo_apply,
                            save_csv=self.save_csv,
                            mAP=self.mAP,
                            mAP_path=self.mAP_path,
                            mAP_List=self.mAP_List,
                            concat_apply=self.concat_apply,
                            nox_model=nox_model,
                            yolo_model=yolo_model,
                            nox_width=nox_width,
                            nox_height=nox_height
                        )
                        print(f"Processed {idx}/{total_files} images processed successfully")
            else:
                print("Image directory not found, skipping images.")
        
        # [비디오 프로세싱] 비디오는 프레임 추출 과정이 필요하므로 전용 함수를 통해 처리합니다.
        if self.mode in ['video', 'both']:
            print(f"Processing videos (Mode: {self.mode})...")
            for input_path in file_list:
                if input_path.suffix.lower() in ['.mp4', '.avi', '.mov', '.mkv']:
                    video_process(
                        ini_dict=self.ini_dict, 
                        input_path=str(input_path), 
                        input_dir=str(self.input_dir), 
                        result_dir=str(self.result_dir),
                        nox_apply=self.nox_apply, 
                        rtdetr_apply=self.rtdetr_apply, 
                        yolo_apply=self.yolo_apply, 
                        save_csv=False, 
                        concat_apply=self.concat_apply
                    )
                    print(f"{input_path} video process finish")

        print("Processed successfully")

if __name__ == "__main__":
    # 터미널에서도 쉽게 설정을 바꿀 수 있도록 CLI 인자 구성을 제공합니다.
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", default="./ob_testset/inputs", type=str)
    parser.add_argument("--result_dir", default="./ob_testset/outputs", type=str)
    parser.add_argument("--nox", type=argparse_type_bool, default=True)
    parser.add_argument("--rtdetr", type=argparse_type_bool, default=True)
    parser.add_argument("--new", type=argparse_type_bool, default=False)
    parser.add_argument("--mAP", default=None, type=str)
    parser.add_argument("--save_csv", type=argparse_type_bool, default=False)
    parser.add_argument("--config_path", default="/ai-video-converter/src/config.ini", type=str)
    parser.add_argument("--concat_apply", type=argparse_type_bool, default=False)
    parser.add_argument("--clean", type=argparse_type_bool, default=True)
    parser.add_argument("--mode", default="both", choices=["image", "video", "both"], type=str)
    args = parser.parse_args()

    mAP = True if args.mAP else False
    # 컨트롤러 인스턴스 생성 및 파이프라인 실행
    v_loader = NOX_converter(
        input_dir=args.input_dir, result_dir=args.result_dir,
        nox_apply=args.nox, rtdetr_apply=args.rtdetr, yolo_apply=args.new,
        mAP_path=args.mAP, mAP=mAP, save_csv=args.save_csv,
        config_path=args.config_path, concat_apply=args.concat_apply, clean_output=args.clean,
        mode=args.mode, 
    )
    v_loader.process_run()