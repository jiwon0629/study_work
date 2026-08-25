이 파일은 NOX-Detection-engine.py와 거의 동일하지만, 기본적으로 설정된 *입력/출력 경로(lle_testset)*가 다르며, 비디오 처리 과정에서 *예외 처리(try-except)*가 보강되어 있어 개별 비디오 파일의 오류가 전체 프로세스를 중단시키지 않도록 설계되었습니다.
import numpy as np
# Numpy 버전 호환성 패치
np.bool = bool
np.float = float

import argparse
import os
import shutil
import multiprocessing as mp
from pathlib import Path
from utils import obj_print_program_limitations, argparse_type_bool, custom_error, ConfigManager
from process import image_process, video_process
from model.nox import NOX_TRT_Model
from model.yolo_inference import YOLO_Model

class NOX_converter():
    """
    화질 개선 및 객체 탐지 파이프라인을 관리하는 엔진 클래스입니다.
    """
    def __init__(self,
                  input_dir,
                  result_dir,
                  nox_apply=True,
                  rtdetr_apply=False,
                  yolo_apply=False,
                  mAP_path=None,
                  mAP=False,
                  save_csv=False,
                  config_path="/ai-video-converter/src/config.ini",
                  concat_apply=False,
                  clean_output=True,
                  mode="both",
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
        
        # 설정 가져오기
        config = ConfigManager(config_path)
        self.ini_dict = config.get_config_dict()
        
        # 모델에 따른 JSON 경로 동적 설정
        if yolo_apply:
            self.ini_dict['CONFIG']['JSON_PATH'] = self.ini_dict['YOLO'].get('JSON_PATH', self.ini_dict['RTDETR']['JSON_PATH'])
        else:
            self.ini_dict['CONFIG']['JSON_PATH'] = self.ini_dict['RTDETR']['JSON_PATH']
            
        self.save_csv = self.ini_dict['CONFIG']['PROCESS_TIME_CSV_PATH'] if save_csv else None

        mp.set_start_method('spawn', force=True)
        self.mAP_List = []  

    def process_run(self):
        # [출력 정리] 결과 폴더 내 파일 및 하위 폴더를 삭제하여 이전 데이터와의 혼선을 방지합니다.
        if self.clean_output and self.result_dir.exists():
            print(f"Cleaning output directory: {self.result_dir}")
            result_json = self.result_dir / 'result.json'
            if result_json.exists():
                result_json.unlink()
                print(f"  - Removed {result_json}")

            for subdir in ['nox', 'labels', 'detections']:
                subdir_path = self.result_dir / subdir
                if subdir_path.exists():
                    shutil.rmtree(subdir_path)
                    print(f"  - Removed {subdir_path}")
            print("Output directory cleaned.\n")

        # 시스템 검증 및 파일 리스트 확보
        obj_print_program_limitations(self.input_dir, self.result_dir)
        file_list, success = custom_error(
            self.input_dir, self.result_dir, self.nox_apply, self.rtdetr_apply, self.yolo_apply, self.mAP, self.ini_dict, self.concat_apply,
        )
        if not success:
            return

        # GPU/모델 파라미터 설정
        gpu = self.ini_dict['CONFIG']['GPU']
        batch = self.ini_dict['CONFIG']['BATCH']
        channel = self.ini_dict['CONFIG']['CHANNEL']
        nox_width = 1920
        nox_height = 1080
        
        # TensorRT 기반 NOX 모델 로드
        nox_model = None
        if self.nox_apply:
            print("Loading NOX Model...")
            nox_model = NOX_TRT_Model(
                gpu=gpu,
                model_path=self.ini_dict['NOX']['NOX_MODEL_PATH'],
                input_shape=(batch, nox_height, nox_width, channel),
            )

        # YOLO 모델 로드
        yolo_model = None
        if self.yolo_apply:
            print("Loading  Model...")
            yolo_model = YOLO_Model(
                model_path=self.ini_dict['YOLO']['YOLO_MODEL_PATH'],
                device='cuda' if gpu >= 0 else 'cpu'
            )
        
        # [이미지 처리] 이미지 폴더 내의 파일을 순회하며 처리합니다.
        if self.mode in ['image', 'both']:
            image_dir = self.input_dir / 'image'
            if image_dir.exists():
                image_files = list(image_dir.rglob('*.jpg')) + list(image_dir.rglob('*.jpeg')) + list(image_dir.rglob('*.png'))
                total_files = len(image_files)
                print(f"Processing images (Mode: {self.mode})...")
                for idx, input_path in enumerate(image_files, start=1):
                    if input_path.is_file():
                        image_process(
                            self.ini_dict, input_path, self.input_dir, self.result_dir,
                            self.nox_apply, self.rtdetr_apply, self.yolo_apply,
                            self.save_csv, self.mAP, self.mAP_path, self.mAP_List,
                            self.concat_apply, nox_model=nox_model, yolo_model=yolo_model,
                            nox_width=nox_width, nox_height=nox_height
                        )
                        print(f"Processed {idx}/{total_files} images successfully")
            else:
                print(f"Warning: Image directory {image_dir} not found. Skipping images.")

        # [비디오 처리] 예외 처리가 강화된 비디오 루프입니다.
        if self.mode in ['video', 'both']:
            print(f"Processing videos (Mode: {self.mode})...")
            for input_path in file_list:
                path_obj = Path(input_path)
                ext = path_obj.suffix.lower()
                if ext in ['.mp4', '.avi', '.mov', '.mkv']:
                    print(f"--- Attempting to process video: {path_obj.name} (Ext: {ext}) ---")
                    try:
                        # 개별 비디오 처리 중 오류가 나도 전체 프로세스가 죽지 않도록 try-except로 감쌉니다.
                        video_process(
                            self.ini_dict, path_obj, self.input_dir, self.result_dir,
                            self.nox_apply, self.rtdetr_apply, self.yolo_apply,
                            self.save_csv, self.concat_apply,
                        )
                        print(f"✅ Successfully processed video: {path_obj.name}")
                    except Exception as e:
                        print(f"❌ Error processing video {path_obj.name}: {e}")

        print("Processed successfully")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # 기본 경로가 lle_testset으로 설정되어 있어 특정 테스트셋 전용으로 활용됩니다.
    parser.add_argument("--input_dir", default="./lle_testset/inputs", type=str)
    parser.add_argument("--result_dir", default="./lle_testset/outputs", type=str)
    parser.add_argument("--nox", type=argparse_type_bool, default=True)
    parser.add_argument("--rtdetr", type=argparse_type_bool, default=False)
    parser.add_argument("--new", type=argparse_type_bool, default=False)
    parser.add_argument("--mAP", default=None, type=str)
    parser.add_argument("--save_csv", type=argparse_type_bool, default=False)
    parser.add_argument("--config_path", default="/ai-video-converter/src/config.ini", type=str)
    parser.add_argument("--concat_apply", type=argparse_type_bool, default=False)
    parser.add_argument("--clean", type=argparse_type_bool, default=True, help="Clean output directory before processing (default: True)")
    parser.add_argument("--mode", default="both", choices=["image", "video", "both"], type=str)
    args = parser.parse_args()

    mAP = True if args.mAP else False
    v_loader = NOX_converter(
        input_dir=args.input_dir, result_dir=args.result_dir,
        nox_apply=args.nox, rtdetr_apply=args.rtdetr, yolo_apply=args.new,
        mAP_path=args.mAP, mAP=mAP, save_csv=args.save_csv,
        config_path=args.config_path, concat_apply=args.concat_apply, clean_output=args.clean,
        mode=args.mode,
    )
    v_loader.process_run()