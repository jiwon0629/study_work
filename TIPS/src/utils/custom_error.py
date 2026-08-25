# 이 파일의 이름은 custom_error이지만, 실제로는 "사전 시스템 체크 및 파일 검증기(Pre-flight Check)" 역할을 합니다. 
# 딥러닝 모델은 로드하는 데 시간이 오래 걸리고 GPU 메모리를 많이 사용합니다. 
# 만약 모델을 다 로드한 후에 "입력 파일이 없네?" 혹은 "모델 파일 경로가 틀렸네?"라는 것을 알게 되면 시간과 자원이 낭비됩니다.
# 따라서 모델을 로드하기 전에 다음 사항들을 미리 확인하여, 문제가 있다면 즉시 프로그램을 종료시키고 사용자에게 정확한 원인을 알려주기 위해 사용합니다.
import os
from pathlib import Path

def custom_error(input_dir, result_dir, nox_apply, rtdetr_apply, yolo_apply, mAP, ini_dict, concat_apply):
    """
    프로그램 실행 전, 입력/출력 경로 및 모델 파일의 존재 여부를 미리 검증하여 
    불필요한 리소스 낭비(모델 로드 후 에러 발생 등)를 막는 유효성 검사 함수입니다.
    """
    try:
        # 1. 입력 디렉토리 검증
        # 입력 경로 자체가 존재하지 않으면 처리를 시작할 수 없으므로 즉시 False를 반환합니다.
        if not os.path.exists(input_dir):
            print(f"Error: Input directory not found: {input_dir}")
            return None, False
        
        # 2. 출력 디렉토리 생성
        # 결과물을 저장할 폴더가 없으면 생성합니다. (exist_ok=True로 이미 있어도 에러 없이 통과)
        os.makedirs(result_dir, exist_ok=True)

        # 3. NOX 모델 파일 확인
        # NOX 모델 사용 설정이 켜져 있다면, 설정 파일에 명시된 경로에 실제 모델 파일이 있는지 확인합니다.
        if nox_apply:
            nox_model_path = Path(ini_dict['NOX']['NOX_MODEL_PATH'])
            if not nox_model_path.exists():
                print(f"Error: NOX model file not found: {nox_model_path}")
                return None, False

        # 4. RT-DETR 모델 파일 확인
        # RT-DETR 모델 사용 설정이 켜져 있다면, 실제 모델 파일의 존재 여부를 확인합니다.
        if rtdetr_apply:
            rtdetr_model_path = Path(ini_dict['RTDETR']['RTDETR_MODEL_PATH'])
            if not rtdetr_model_path.exists():
                print(f"Error: RT-DETR model file not found: {rtdetr_model_path}")
                return None, False

        # 5. YOLO 모델 파일 확인 (현재는 주석 처리됨)
        # if yolo_apply:
        #     yolo_model_path = Path(ini_dict['YOLO']['YOLO_MODEL_PATH'])
        #     if not yolo_model_path.exists():
        #         print(f"Error: YOLO model file not found: {yolo_model_path}")
        #         return None, False

        # 6. 입력 파일 리스트 수집 및 검증
        # 이미지 전용 폴더('/image')가 있는지 확인하고, 지원하는 확장자(.jpg, .jpeg, .png) 파일만 수집합니다.
        image_dir = Path(input_dir) / 'image'
        if not image_dir.exists():
            print(f"Warning: Image directory not found in {input_dir}. Skipping images.")
            image_files = []
        else:
            image_files = list(image_dir.rglob('*.jpg')) + list(image_dir.rglob('*.jpeg')) + list(image_dir.rglob('*.png'))

        # 입력 루트 폴더에서 지원하는 비디오 확장자(.mp4, .avi, .mov, .mkv) 파일을 수집합니다.
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv']
        video_files = [f for f in Path(input_dir).glob('*') if f.suffix.lower() in video_extensions]

        # 수집된 이미지와 비디오 파일을 하나의 리스트로 합칩니다.
        all_files = image_files + video_files
        
        # 검증 결과, 처리할 파일이 하나도 없다면 실행 의미가 없으므로 False를 반환합니다.
        if not image_files and not video_files:
            print("Error: No valid input files found in the input directory.")
            return None, False

        # 모든 검증을 통과하면 수집된 파일 리스트와 함께 성공(True)을 반환합니다.
        return all_files, True

    except Exception as e:
        # 예상치 못한 시스템 에러(권한 문제 등) 발생 시 프로그램이 갑자기 꺼지지 않도록 예외 처리합니다.
        print(f"An unexpected error occurred during system check: {e}")
        return None, False