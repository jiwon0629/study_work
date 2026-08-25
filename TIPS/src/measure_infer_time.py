import argparse
import json
import csv

def parse_time(time_str):
    try:
        total_seconds = float(time_str)
        return total_seconds
    except Exception as e:
        print(f"Error parsing time string: {time_str}, error: {e}")
        return 0

def process_json(json_path):
    with open(json_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    times = []
    for item in data:
        input_path = item.get("input_path", "")
        infer_time = item.get("AI_Inference_process_time", "")
        time_seconds = parse_time(infer_time)
        times.append((input_path, time_seconds))

    return times

def format_time(seconds):
    millis = int((seconds % 1) * 1000)
    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{millis:03d}"

def save_to_csv(times, output_csv_path):
    total_time = sum(time for _, time in times)
    average_time = total_time / len(times) if times else 0

    with open(output_csv_path, 'w', newline='') as csvfile:
        fieldnames = ['input_path', 'infer_time']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerow({'input_path': 'Average', 'infer_time': format_time(average_time)})

        for input_path, time in times:
            writer.writerow({'input_path': input_path, 'infer_time': format_time(time)})

if __name__ == "__main__":
    import os

    # Process ob_testset only (object detection)
    json_path = "./ob_testset/outputs/result.json"

    times = process_json(json_path)

    # Calculate average
    total_time = sum(time for _, time in times)
    total_frames = len(times)
    average_time = total_time / total_frames if total_frames > 0 else 0

    # Save CSV
    output_csv = "./ob_testset/infer_time_result.csv"
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)

    with open(output_csv, 'w', newline='') as csvfile:
        fieldnames = ['input_path', 'infer_time']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        # Average row
        writer.writerow({
            'input_path': 'Average',
            'infer_time': format_time(average_time)
        })

        # Individual entries
        for input_path, time in times:
            writer.writerow({
                'input_path': input_path,
                'infer_time': format_time(time)
            })

    print(f"\nAnalysis file '{output_csv}' has been created.")
    print(f"\n--- Overall Inference Time ---")
    print(f"Average Time: {format_time(average_time)}")
