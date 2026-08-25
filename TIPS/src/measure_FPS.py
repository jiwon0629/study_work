이 파일은 추론 결과가 저장된 JSON 파일(result.json 또는 result_video.json)을 읽어 시스템의 실시간 처리 속도(FPS)를 계산하고 보고서를 작성합니다.
import argparse
import json
import csv
import os

def parse_time(time_str):
    """시간 문자열을 float 타입으로 변환하며, 실패 시 0을 반환합니다."""
    try: return float(time_str)
    except: return 0

def process_json(json_path, mode='image'):
    """JSON 결과 파일에서 각 파일별 추론 시간을 읽어 FPS를 계산합니다."""
    if not os.path.exists(json_path):
        print(f"Error: File {json_path} not found.")
        return []
        
    with open(json_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    results = []
    for item in data:
        input_path = item.get("input_path", "")
        if mode == 'video':
            # [비디오 FPS] 총 프레임 수 / 전체 추론 시간
            frames = item.get("total_frames", 0)
            time = parse_time(item.get("total_inference_time", 0))
            fps = frames / time if time > 0 else 0
        else:
            # [이미지 FPS] 1 / 단일 이미지 추론 시간
            time = parse_time(item.get("AI_Inference_process_time", 0))
            fps = 1 / time if time > 0 else 0
            
        results.append({'input_path': input_path, 'time': time, 'fps': fps})
    return results

def format_time(seconds):
    """초 단위의 시간을 'HH:MM:SS.mmm' 형식으로 변환하여 가독성을 높입니다."""
    millis = int((seconds % 1) * 1000)
    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{millis:03d}"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', type=str, default='video', choices=['image', 'video'], 
                        help="이미지(result.json) 혹은 비디오(result_video.json) 모드 선택")
    parser.add_argument('--input_dir', type=str, default="./ob_testset/outputs")
    parser.add_argument('--output_csv', type=str, default="./ob_testset/fps_result.csv")
    args = parser.parse_args()

    # 모드에 따라 읽어올 JSON 파일 경로를 설정합니다.
    json_path = os.path.join(args.input_dir, "result.json" if args.mode == 'image' else "result_video.json")
    results = process_json(json_path, mode=args.mode)

    if not results:
        print("No data to process.")
        exit()

    # 전체 평균 시간 및 평균 FPS를 계산합니다.
    total_time = sum(r['time'] for r in results)
    avg_time = total_time / len(results) if results else 0
    avg_fps = sum(r['fps'] for r in results) / len(results) if results else 0

    # 계산된 결과를 CSV 파일로 저장하여 성능 보고서로 활용합니다.
    os.makedirs(os.path.dirname(args.output_csv), exist_ok=True)
    with open(args.output_csv, 'w', newline='') as csvfile:
        fieldnames = ['input_path', 'infer_time', 'average_fps']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        # 최상단에 전체 평균 데이터를 기록합니다.
        writer.writerow({'input_path': 'Average', 'infer_time': format_time(avg_time), 'average_fps': f"{avg_fps:.2f}"})
        # 각 파일별 개별 FPS 데이터를 기록합니다.
        for r in results:
            writer.writerow({'input_path': r['input_path'], 'infer_time': format_time(r['time']), 'average_fps': f"{r['fps']:.2f}"})

    print(f"\nAnalysis file '{args.output_csv}' has been created for mode: {args.mode}")
    print(f"Average FPS: {avg_fps:.2f}")