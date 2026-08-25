import cv2
import numpy as np
import sys
from typing import Any , Tuple
from multiprocessing import Queue,  Event
import yaml
sys.path.append("../")
from model.rtdetr import rtdetr_predict, RTDETR_TRT_Model

def rtdetr_detect(
    input_queue: Queue,
    output_queue: Queue,
    loop_event: Event,
    ini_dict: dict,
    ) -> None:
    
    rtdetr_model_path: str = ini_dict['RTDETR']['RTDETR_MODEL_PATH']
    detect_model_height : int = ini_dict['RTDETR']['RTDETR_MODEL_HEIGHT'] 
    detect_model_width : int = ini_dict['RTDETR']['RTDETR_MODEL_WIDTH'] 
    config_path: str = ini_dict['RTDETR']['CONFIG_PATH'] 
    
    gpu: int = ini_dict['CONFIG']['GPU'] 
    batch: int = ini_dict['CONFIG']['BATCH'] 
    channel: int = ini_dict['CONFIG']['CHANNEL'] 
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    label_list = config['label_list']
    
    detect_model = RTDETR_TRT_Model(
                gpu=gpu,
                model_path=rtdetr_model_path,
                input_shape=(batch, channel, detect_model_width, detect_model_height),
                datatype=np.float32,
            )
    try:
        while loop_event.is_set():
            NOX_Frame: Any = input_queue.get()
            
            OBJ_frame, postprocess_data, process_time = rtdetr_predict(
                NOX_Frame,
                detect_model,
                label_list,
                detect_model_width,
                detect_model_height,
            )            
            output_queue.put(OBJ_frame)
    except ValueError as e:
        print(f"rtdetr_detect ERROR | {e}")  
    finally:
        loop_event.clear()
        return
