from ultralytics import YOLO

# 1. 다운로드한 모델 파일 경로 (예: 'best.pt' 또는 'fire_model.pt')
MODEL_PATH = 'YOLOv10-FireSmoke-X.pt' 

try:
    # 2. 모델 로드 (파일을 직접 읽어옵니다)
    model = YOLO(MODEL_PATH)

    # 3. 모델 정보 출력
    print("\n" + "="*40)
    print(f"모델 파일명: {MODEL_PATH}")
    print(f"클래스 개수: {len(model.names)}개")
    print(f"클래스 구성: {model.names}")
    print("="*40 + "\n")

    # 4. 추가 정보 (모델 버전 및 아키텍처)
    # print(model.info()) # 상세 사양이 궁금할 때 주석 해제 후 실행
    
except Exception as e:
    print(f"모델 파일을 찾을 수 없거나 올바른 YOLO 형식이 아닙니다.\n({e})")
