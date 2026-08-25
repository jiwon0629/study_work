import os
from pathlib import Path
import pandas as pd

def save_process_time(
    csv_file_path: str, 
    input_path: str, 
    process_output_file_name: str, 
    process_time: str
) -> None:
    if os.path.exists(csv_file_path):
        df = pd.read_csv(csv_file_path)
    else:
        df = pd.DataFrame(columns=['Process File Name', 'Process Output File Name', 'Process Time'])
        
    new_row = pd.DataFrame([{
        'Process File Name': input_path, 
        'Process Output File Name': process_output_file_name, 
        'Process Time': process_time
    }])
    
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(csv_file_path, index=False)
