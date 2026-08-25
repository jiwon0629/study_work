# 해상도 체크
import argparse
import cv2
import csv
from pathlib import Path
from tqdm import tqdm

def classify_resolution(w, h):
    """í´ìë íì ë¶ë¥"""
    if w >= 1920 or h >= 1080:
        return "FHD"
    elif w >= 1280 or h >= 720:
        return "HD"
    else:
        return "SD"

def check_video_resolution(input_dir, output_csv):
    """ìì íì¼ í´ìë ì²´í¬ ë° CSV ì ì¥"""
    input_path = Path(input_dir)
    
    # ìì íì¼ íì¥ì ì ì
    video_extensions = ['*.mp4', '*.avi', '*.mov', '*.mkv']
    video_files = []
    for ext in video_extensions:
        video_files.extend(list(input_path.rglob(ext)))
    
    results = []
    
    for video_path in tqdm(video_files, desc="Checking video resolution"):
        try:
            # OpenCV VideoCaptureë¥¼ ì¬ì©íì¬ ìì ì ë³´ ë¡ë
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                results.append({
                    "filename": str(video_path),
                    "width": "N/A",
                    "height": "N/A",
                    "resolution_type": "Error",
                    "meets_fhd_threshold": "N/A"
                })
                cap.release()
                continue
            
            # ììì ê°ë¡, ì¸ë¡ í¬ê¸° ì¶ì¶
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            
            res_type = classify_resolution(w, h)
            # ì íí 1920x1080 ì´ìì¸ì§ íì¸
            meets_fhd = (w >= 1920 and h >= 1080)
            
            results.append({
                "filename": str(video_path.relative_to(input_path)),
                "width": w,
                "height": h,
                "resolution_type": res_type,
                "meets_fhd_threshold": "TRUE" if meets_fhd else "FALSE"
            })
        except Exception as e:
            results.append({
                "filename": str(video_path),
                "width": "N/A",
                "height": "N/A",
                "resolution_type": "Error",
                "meets_fhd_threshold": "N/A"
            })
    
    # ì ë ¬ ë¡ì§: FHD ë¯¸ë¬ íì¼ ì°ì ìì ë°°ì¹ (ê²ì í¸ìì±)
    def sort_key(x):
        if x["meets_fhd_threshold"] == "FALSE":
            return (0, -x["width"] * x["height"]) 
        else:
            return (1, 0)
    
    results.sort(key=sort_key)
    
    # CSV ì ì¥
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "filename", "width", "height", "resolution_type", "meets_fhd_threshold"
        ])
        writer.writeheader()
        writer.writerows(results)
    
    print(f"\nâ Video resolution check complete. Results saved to {output_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check video resolution and save to CSV")
    # ê¸°ë³¸ ìë ¥ ê²½ë¡ë¥¼ ìì í´ëë¡ ë³ê²½
    parser.add_argument("--input_dir", default="./ob_testset/inputs", type=str, help="Input directory containing videos")
    parser.add_argument("--output_csv", default="./video_resolution_check.csv", type=str, help="Output CSV file path")
    
    args = parser.parse_args()
    
    check_video_resolution(args.input_dir, args.output_csv)