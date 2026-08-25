import json
import os

def save_to_json(
    label_list: list, 
    input_path: str,
    postprocess_data: list,
    json_path: str,
    AI_Inference_process_time: str,
) -> None:
        
    result_data = []

    for bbox in postprocess_data:
        class_id, score, x_min, y_min, x_max, y_max = bbox
        result_data.append({
            "class_id": class_id,
            "accuracy": score,
            "coordinates": {
                "x_min": x_min,
                "y_min": y_min,
                "x_max": x_max,
                "y_max": y_max
            }
        })
    

    record = {
        "input_path": input_path,
        "results": result_data,
        "AI_Inference_process_time": AI_Inference_process_time,
    }

    try:
        with open(json_path, 'r') as file:
            content = file.read().strip()
            if content:
                data = json.loads(content)
            else:
                data = []
    except (FileNotFoundError, json.JSONDecodeError) as e:
        # print(f"Error reading JSON file: {e}. Creating a new file.")
        data = []

    # Check for duplicates and update existing entry or append new one
    existing_index = None
    for i, item in enumerate(data):
        if item.get('input_path') == input_path:
            existing_index = i
            break

    if existing_index is not None:
        # Update existing entry
        data[existing_index] = record
    else:
        # Append new entry
        data.append(record)

    with open(json_path, 'w') as file:
        json.dump(data, file, indent=4)
