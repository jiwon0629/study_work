이 파일은 NOX 화질 개선 모델이 얼마나 원본(Ground Truth)에 가깝게 복원했는지 측정하는 SSIM(Structural Similarity Index) 지표를 계산합니다.
import warnings
# numpy 연산 중 발생하는 매우 작은 값(subnormal)에 대한 경고를 무시합니다.
warnings.filterwarnings('ignore', category=UserWarning)

import cv2
import os
import pandas as pd
import argparse
import glob # 하위 폴더까지 모든 이미지 파일을 찾기 위해 사용합니다.
from skimage import metrics # SSIM 계산을 위한 공식 메트릭 라이브러리입니다.
from tqdm import tqdm # 처리 과정을 프로그레스 바(Progress Bar)로 표시합니다.

def NOX_engine(
    input_dir : str,    # 화질 개선된 결과 이미지 폴더
    answer_dir : str,   # 정답(Ground Truth) 고화질 이미지 폴더
    output_csv : str,   # 결과 저장 CSV 경로
    ) -> float:

    # [파일 수집] recursive=True 옵션을 통해 하위 폴더 내의 모든 이미지 파일을 리스트업합니다.
    input_files = []
    for ext in ['*.jpg', '*.jpeg', '*.png']:
        input_files.extend(glob.glob(os.path.join(input_dir, "**", ext), recursive=True))

    results = []

    for input_path in tqdm(input_files, desc="Calculating SSIM"):
        # 파일 경로에서 파일명만 추출합니다.
        input_file = os.path.basename(input_path)
        
        # [파일명 매칭] NOX 결과물은 '파일명_NOX.jpg' 형태이므로, 정답 파일명과 매칭하기 위해 접미사를 제거합니다.
        base_name = input_file.replace('_NOX.jpg', '').replace('_NOX.jpeg', '').replace('.jpg', '').replace('.jpeg', '').replace('.png', '')
        
        # 정답 폴더에서 해당 파일명에 맞는 파일을 찾습니다 (확장자가 다를 수 있으므로 루프 수행).
        answer_path = None
        for ext in ['.png', '.jpg', '.jpeg']:
            potential_path = os.path.join(answer_dir, base_name + ext)
            if os.path.exists(potential_path):
                answer_path = potential_path
                break

        # 두 파일이 모두 존재할 때만 계산을 수행합니다.
        if os.path.exists(input_path) and answer_path and os.path.exists(answer_path):
            input_image = cv2.imread(input_path)
            answer_image = cv2.imread(answer_path)

            if input_image is None or answer_image is None:
                continue

            # [차원 일치] SSIM은 두 이미지의 크기가 정확히 같아야 합니다. 정답 이미지 크기에 맞춰 리사이즈합니다.
            if input_image.shape != answer_image.shape:
                input_image = cv2.resize(input_image, (answer_image.shape[1], answer_image.shape[0]))

            # [SSIM 계산] 구조적 유사도를 계산합니다. 
            # multichannel=True: 색상 채널(RGB)을 모두 고려하여 계산합니다.
            ssim_value = metrics.structural_similarity(input_image, answer_image, multichannel=True, channel_axis=-1)
            results.append({'input_image_path': input_path, 'answer_image_path': answer_path, 'ssim_value': ssim_value})

    # 수집된 결과를 pandas DataFrame으로 변환하여 통계 처리를 용이하게 합니다.
    df = pd.DataFrame(results)

    mean_ssim = 0
    if not df.empty:
        # 모든 이미지의 평균 SSIM 값을 계산합니다.
        mean_ssim = df['ssim_value'].mean()
        # 데이터프레임 최상단에 'Average' 행을 추가합니다.
        df.loc[-1] = ['Average', 'Average', mean_ssim]
        df.index = df.index + 1
        df = df.sort_index()

    # 결과를 CSV 파일로 저장합니다.
    df.to_csv(output_csv, index=False)

    print(f"\nAnalysis file '{output_csv}' has been created.")

    return mean_ssim

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_dir', type=str, default="./lle_testset/outputs/nox/")
    parser.add_argument('--answer_dir', type=str, default="./lle_testset/ground_truth")
    parser.add_argument('--output_csv', type=str, default="./lle_testset/ssim_result.csv")

    args = parser.parse_args()

    average_ssim = NOX_engine(args.input_dir, args.answer_dir, args.output_csv)

    print(f"\n--- Overall SSIM ---")
    print(f"Average SSIM: {average_ssim:.4f}")