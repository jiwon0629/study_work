import os
import json

def extract_class_ids(input_dir, output_file):
    class_ids = set()

    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                # print(f"Processing file: {file_path}")
                with open(file_path, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        # print(json.dumps(data, indent=2, ensure_ascii=False))
                        learning_data_info = data.get("Learning_Data_Info.", {})
                        # print(learning_data_info)
                        annotations = learning_data_info.get("Annotations", [])
                        # print(f"Annotations extracted: {annotations}")  # Annotations 항목을 출력
                        for annotation in annotations:
                            class_id = annotation.get("Class_ID")
                            if class_id:
                                # print(f"Found Class_ID: {class_id}")
                                class_ids.add(class_id)
                    except json.JSONDecodeError as e:
                        print(f"Error decoding JSON from file: {file_path}, error: {e}")
                    except Exception as e:
                        print(f"Unexpected error with file: {file_path}, error: {e}")

    with open(output_file, 'w', encoding='utf-8') as f:
        for class_id in sorted(class_ids):
            f.write(f"{class_id}\n")

if __name__ == "__main__":
    input_dir = "/volume/028.저조도_환경_데이터/unzip_data"
    output_file = "class_id_check.txt"
    extract_class_ids(input_dir, output_file)
    print(f"Class_ID의 종류가 {output_file} 파일에 기록되었습니다.")
