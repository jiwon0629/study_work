import os
import json
from pathlib import Path
from typing import List, Tuple

def answer_json_load(input_name: str, mAP_path: str) -> List[Tuple[int, List[int]]]:
    """
    ì ëµ ë¼ë²¨ JSON íì¼ì ë¡ëí©ëë¤. 
    ë ê±°ì(Learning_Data_Info) íìê³¼ ì ê·(detections) íìì ëª¨ë ì§ìí©ëë¤.
    """
    base_name = os.path.splitext(input_name)[0]  
    target_file_name = f"{base_name}.json"
    answer_data = []
    
    # í´ëì¤ ì´ë¦-ID ë§¤í ì ì
    class_mapping = {
        "Human": 0,
        "Car": 1
    }
    
    file_list = list(Path(mAP_path).glob('**/*'))
    if not file_list:
        return answer_data
    
    for file in file_list:
        if file.is_file() and file.name == target_file_name:
            with open(file, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    
                    # 1. ë ê±°ì íì ì²ë¦¬ (Learning_Data_Info.)
                    if "Learning_Data_Info." in data:
                        learning_data_info = data.get("Learning_Data_Info.", {})
                        annotations = learning_data_info.get("Annotations", [])
                        for annotation in annotations:
                            class_id = annotation.get("Class_ID")
                            type_value = annotation.get("Type_value")
                            class_id_num = class_mapping.get(class_id)
                            if class_id_num is not None and type_value is not None:
                                answer_data.append((class_id_num, type_value))
                    
                    # 2. ì ê· íì ì²ë¦¬ (detections)
                    elif "detections" in data:
                        detections = data.get("detections", [])
                        for det in detections:
                            class_id = det.get("class_id")
                            bbox = det.get("bbox")
                            class_id_num = class_mapping.get(class_id)
                            
                            if class_id_num is not None and bbox is not None:
                                # bbox ëìëë¦¬ë¥¼ [x_min, y_min, x_max, y_max] ë¦¬ì¤í¸ë¡ ë³í
                                bbox_list = [
                                    bbox.get("x_min"),
                                    bbox.get("y_min"),
                                    bbox.get("x_max"),
                                    bbox.get("y_max")
                                ]
                                # ëª¨ë  ì¢í ê°ì´ ì¡´ì¬íëì§ íì¸
                                if all(v is not None for v in bbox_list):
                                    answer_data.append((class_id_num, bbox_list))
                                    
                except Exception:
                    continue
    return answer_data