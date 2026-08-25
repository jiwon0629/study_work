import os
import json
import re
from collections import defaultdict
import pandas as pd

def count_car_and_human_json_files(input_dir, output_file):
    l_group_counts = defaultdict(lambda: {'Car': 0, 'Human': 0})

    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        learning_data_info = data.get("Learning_Data_Info.", {})
                        annotations = learning_data_info.get("Annotations", [])
                        contains_car = any(annotation.get("Class_ID") == 'Car' for annotation in annotations)
                        contains_human = any(annotation.get("Class_ID") == 'Human' for annotation in annotations)
                        
                        # Extract the L group from the path
                        match = re.search(r'L\d{2}', root)
                        if match:
                            l_group = match.group(0)
                            if contains_car:
                                l_group_counts[l_group]['Car'] += 1
                            if contains_human:
                                l_group_counts[l_group]['Human'] += 1

                    except json.JSONDecodeError as e:
                        print(f"Error decoding JSON from file: {file_path}, error: {e}")
                    except Exception as e:
                        print(f"Unexpected error with file: {file_path}, error: {e}")

    # Convert to DataFrame
    df = pd.DataFrame.from_dict(l_group_counts, orient='index').reset_index()
    df.rename(columns={'index': 'L_Group'}, inplace=True)
    
    # Ensure the output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Save to CSV
    df.to_csv(output_file, index=False)
    
    return df

# Assuming the directory path is provided
input_directory = "/ai-video-converter/datasets/sample_Data/label"
output_file = "/ai-video-converter/datasets/label_counts.csv"
df_counts = count_car_and_human_json_files(input_directory, output_file)

