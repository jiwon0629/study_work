import os
import random
import shutil
import json
import re
from collections import defaultdict

def count_class_files(label_dir, class_id):
    count = 0
    files_with_class = []
    for root, dirs, files in os.walk(label_dir):
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        annotations = data.get("Learning_Data_Info.", {}).get("Annotations", [])
                        if any(annotation.get("Class_ID") == class_id for annotation in annotations):
                            count += 1
                            img_file_name = os.path.splitext(file)[0] + '.jpg'
                            files_with_class.append(img_file_name)
                    except json.JSONDecodeError as e:
                        print(f"Error decoding JSON from file: {file_path}, error: {e}")
                    except Exception as e:
                        print(f"Unexpected error with file: {file_path}, error: {e}")
    return count, files_with_class

def copy_random_image_label_pairs(img_dir, label_dir, dst_img_dir, dst_label_dir, num_pairs=10):
    if not os.path.exists(dst_img_dir):
        os.makedirs(dst_img_dir)
    if not os.path.exists(dst_label_dir):
        os.makedirs(dst_label_dir)
    
    human_count, human_files = count_class_files(label_dir, 'Human')
    car_count, car_files = count_class_files(label_dir, 'Car')
    
    human_to_copy = min(num_pairs, human_count)
    car_to_copy = min(num_pairs, car_count)
    
    if human_to_copy < num_pairs:
        car_to_copy = min(car_to_copy + (num_pairs - human_to_copy), car_count)
    if car_to_copy < num_pairs:
        human_to_copy = min(human_to_copy + (num_pairs - car_to_copy), human_count)
    
    random_human_files = random.sample(human_files, human_to_copy)
    random_car_files = random.sample(car_files, car_to_copy)
    
    for img_file in random_human_files + random_car_files:
        img_src_path = os.path.join(img_dir, img_file)
        img_dst_path = os.path.join(dst_img_dir, img_file)
        shutil.copy(img_src_path, img_dst_path)
        
        json_file = os.path.splitext(img_file)[0] + '.json'
        json_src_path = os.path.join(label_dir, json_file)
        json_dst_path = os.path.join(dst_label_dir, json_file)
        shutil.copy(json_src_path, json_dst_path)
        
        print(f"Copied {img_src_path} to {img_dst_path}")
        print(f"Copied {json_src_path} to {json_dst_path}")

if __name__ == "__main__":
    img_dir = "/volume/028.저조도_환경_데이터/sample_Data/image/VL_학습데이터(Bounding_Box)_L01_역광_브라케팅1단계_A"
    label_dir = "/volume/028.저조도_환경_데이터/sample_Data/label/VL_학습데이터(Bounding_Box)_L01_역광_브라케팅1단계_A"
    dst_img_dir = "/ai-video-converter/datasets/sample_Data/image/L01/LEVEL_1/"
    dst_label_dir = "/ai-video-converter/datasets/sample_Data/label/L01/LEVEL_1/"
    
    copy_random_image_label_pairs(img_dir, label_dir, dst_img_dir, dst_label_dir)
    print("Random image-label pairs copying process completed.")
