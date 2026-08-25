import json
import os
from pathlib import Path

def result_json_to_coco(result_json_path, image_dir, output_path):
    """
    Converts result.json (predictions) to COCO JSON format.
    """
    with open(result_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    coco = {
        "images": [],
        "annotations": [],
        "categories": [
            {"id": 0, "name": "person"},
            {"id": 1, "name": "car"}
        ]
    }

    ann_id = 0
    for idx, item in enumerate(data):
        img_path = item['input_path']
        img_name = Path(img_path).name
        
        # Image entry
        coco["images"].append({
            "id": idx,
            "file_name": img_name,
            "width": 1920, # Default, will be updated if possible
            "height": 1080
        })

        # Annotations entry
        for res in item['results']:
            cls = res['class_id']
            if cls not in [0, 2]: continue
            mapped_cls = 0 if cls == 0 else 1 
            coords = res['coordinates']
            # COCO format: [x_min, y_min, width, height]
            width = coords['x_max'] - coords['x_min']
            height = coords['y_max'] - coords['y_min']
            
            coco["annotations"].append({
                "id": ann_id,
                "image_id": idx,
                "category_id": mapped_cls,
                "bbox": [coords['x_min'], coords['y_min'], width, height],
                "area": width * height,  # <--- ì´ ë¶ë¶ì ë°ëì ì¶ê°í´ì¼ í©ëë¤!
                "score": res['accuracy']
            })
            ann_id += 1

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(coco, f, indent=2)
    return output_path

def gt_to_coco(gt_folder, image_dir, output_path):
    """
    Converts Learning_Data_Info. labels to COCO JSON format.
    """
    gt_folder = Path(gt_folder)
    image_files = list(Path(image_dir).rglob('*.jpg')) + \
                  list(Path(image_dir).rglob('*.jpeg')) + \
                  list(Path(image_dir).rglob('*.png'))
    
    coco = {
        "images": [],
        "annotations": [],
        "categories": [
            {"id": 0, "name": "person"},
            {"id": 1, "name": "car"}
        ]
    }

    ann_id = 0
    for idx, img_path in enumerate(image_files):
        img_name = img_path.name
        coco["images"].append({
            "id": idx,
            "file_name": img_name,
            "width": 1920,
            "height": 1080
        })

        # Search for label file
        label_file = gt_folder / f"{img_path.stem}.json"
        if label_file.exists():
            with open(label_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                info = data.get("Learning_Data_Info.", {})
                annotations = info.get("Annotations", [])
                
                for ann in annotations:
                    cls_id = ann.get("Class_ID")
                    type_val = ann.get("Type_value", []) # [xmin, ymin, xmax, ymax]
                    
                    if cls_id == "Human": cls_num = 0
                    elif cls_id == "Car": cls_num = 1
                    else: continue
                    
                    width = type_val[2] - type_val[0]
                    height = type_val[3] - type_val[1]
                    
                    coco["annotations"].append({
                        "id": ann_id,
                        "image_id": idx,
                        "category_id": cls_num,
                        "bbox": [type_val[0], type_val[1], width, height],
                        "area": width * height,
                        "iscrowd": 0
                    })
                    ann_id += 1

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(coco, f, indent=2)
    return output_path