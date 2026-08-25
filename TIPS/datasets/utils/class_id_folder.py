import os
import json
import shutil
from collections import defaultdict

def count_class_ids_and_copy(input_dir, target_class_ids, target_copy_dir):
    class_id_counts = defaultdict(int)
    target_files = defaultdict(list)

    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        learning_data_info = data.get("Learning_Data_Info.", {})
                        annotations = learning_data_info.get("Annotations", [])
                        found_target_class_id = False
                        for annotation in annotations:
                            class_id = annotation.get("Class_ID")
                            if class_id in target_class_ids:
                                class_id_counts[class_id] += 1
                            if class_id in target_class_ids:
                                found_target_class_id = True
                        if found_target_class_id:
                            target_files[root].append(file_path)
                    except json.JSONDecodeError as e:
                        print(f"Error decoding JSON from file: {file_path}, error: {e}")
                    except Exception as e:
                        print(f"Unexpected error with file: {file_path}, error: {e}")

    for folder, files in target_files.items():
        relative_folder_path = os.path.relpath(folder, input_dir)
        target_folder_path = os.path.join(target_copy_dir, relative_folder_path)
        if not os.path.exists(target_folder_path):
            os.makedirs(target_folder_path)
        for file in files:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                learning_data_info = data.get("Learning_Data_Info.", {})
                annotations = learning_data_info.get("Annotations", [])
                filtered_annotations = [annotation for annotation in annotations if annotation.get("Class_ID") in target_class_ids]
                if filtered_annotations:
                    data["Learning_Data_Info."]["Annotations"] = filtered_annotations
                    target_file_path = os.path.join(target_folder_path, os.path.basename(file))
                    with open(target_file_path, 'w', encoding='utf-8') as out_f:
                        json.dump(data, out_f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    input_dir = "/volume/028.저조도_환경_데이터/sample_Data"
    target_copy_dir = "/ai-video-converter/datasets/sample_Data/label"
    target_class_ids = {"Car", "Human"}
    
    count_class_ids_and_copy(input_dir, target_class_ids, target_copy_dir)
    print(f"'Car'와 'Human'이 포함된 JSON 파일들이 {target_copy_dir} 디렉토리에 복사되었습니다.")
