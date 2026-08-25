from pathlib import Path

def gs_print_program_limitations(input_dir: str, result_dir: str) -> None:
    result_dir_path = Path(result_dir).resolve()
    input_dir_path = Path(input_dir).resolve()
    
    print("NOX V1.0 (저장 파일 변환 프로그램 V1.0)")
    print("저장 파일 변환 프로그램 제한 사항")
    print("* 조건 범위를 벗어날 시 프로그램이 정상작동하지 않을 수 있습니다.")
    print("------------------------------------------------------------")
    print("- 최대 동시 처리 가능 동영상 파일 수 1 개")
    print("- 최대 해상도 FHD (1920 X 1080)")
    print("- 동영상 파일을 open 할때 최대 가능한 파일크기 500MB")
    print("- 동영상 입력데이터의 포맷 MP4")
    print("- 동영상 출력데이터의 포맷 MP4")
    print(f"입력 파일 폴더 경로 : {input_dir_path}")
    print(f"출력 파일 폴더 경로 : {result_dir_path}")
    print("------------------------------------------------------------")


def obj_print_program_limitations(input_dir: str, result_dir: str) -> None:
    result_dir_path = Path(result_dir).resolve()
    input_dir_path = Path(input_dir).resolve()
    
    print("NOX V2.0 (NOX + 객체인식 모델 변환 프로그램 V2.0)")
    print("저장 파일 변환 프로그램 제한 사항")
    print("* 조건 범위를 벗어날 시 프로그램이 정상작동하지 않을 수 있습니다.")
    print("------------------------------------------------------------")
    print("- 최대 동시 처리 가능 이미지 파일 수 1 개")
    print("- 최대 해상도 FHD (1920 X 1080)")
    print("- 이미지 입력데이터의 포맷 jpg, jpeg")
    print("- 이미지 출력데이터의 포맷 jpg")
    print(f"입력 파일 폴더 경로 : {input_dir_path}")
    print(f"출력 파일 폴더 경로 : {result_dir_path}")
    print("------------------------------------------------------------")
