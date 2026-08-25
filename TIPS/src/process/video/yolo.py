import numpy as np
import time
import multiprocessing as mp
from model.yolo_inference import YOLO_Model, yolo_predict

def yolo_detect(input_queue, output_queue, loop_event, ini_dict):
    """
    ë¹ëì¤ íë ì ì¶ë¡  ìì»¤ íë¡ì¸ì¤
    """
    # ì¤ì  ë¡ë
    yolo_model_path = ini_dict['YOLO']['YOLO_MODEL_PATH']
    gpu = ini_dict['CONFIG']['GPU']
    
    # ëª¨ë¸ ì´ê¸°í (íë¡ì¸ì¤ ìì ì í ë²ë§)
    model = YOLO_Model(model_path=yolo_model_path, device='cuda' if gpu >= 0 else 'cpu')
    
    # ë¼ë²¨ ë¦¬ì¤í¸ ë¡ë (ì´ë¯¸ì§ ì²ë¦¬ì ëì¼í ê²½ë¡/ë°©ì ì¬ì©)
    import yaml
    with open(ini_dict['RTDETR']['CONFIG_PATH'], 'r') as f:
        config = yaml.safe_load(f)
    label_list = config['label_list']

    while loop_event.is_set():
        if not input_queue.empty():
            try:
                # íìì íë ì ê°ì ¸ì¤ê¸°
                frame = input_queue.get(timeout=1)
                
                if frame is None: # ì¢ë£ ì í¸
                    output_queue.put(None)
                    break
                
                # YOLO ì¶ë¡  ìí (ë°ì¤ ê·¸ë¦¬ê¸° í¬í¨)
                # ë¹ëì¤ ê²°ê³¼ë¬¼ì ë³´íµ ë°ì¤ê° ê·¸ë ¤ì§ ì´ë¯¸ì§ê° íìí¨
                output_img, _, _ = yolo_predict(
                    frame, 
                    model, 
                    label_list, 
                    draw_boxes=True
                )
                
                # ê²°ê³¼ íì ë£ê¸°
                output_queue.put(output_img)
                
            except Exception as e:
                print(f"YOLO Detect Error: {e}")
                continue
        else:
            time.sleep(0.01)