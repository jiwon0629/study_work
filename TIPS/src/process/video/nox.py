import cv2
import numpy as np
import sys
from typing import Any, Dict, Tuple
from multiprocessing import Queue, Event
from multiprocessing.connection import Connection
import yaml
sys.path.append("../")
from model.nox import NOX_TRT_Model

def nox_predict(
    input_queue: Queue,
    output_queue: Queue,
    loop_event: Event,
    ini_dict: dict,
    org_w: int,
    org_h: int,
    model_input_w: int,
    model_input_h: int,
    concat_apply: bool,
) -> None:
     
    nox_model_path: str = ini_dict['NOX']['NOX_MODEL_PATH']  
    gpu: int = ini_dict['CONFIG']['GPU'] 
    batch: int = ini_dict['CONFIG']['BATCH'] 
    channel: int = ini_dict['CONFIG']['CHANNEL'] 
        
    nox_model = NOX_TRT_Model(
        gpu=gpu,
        model_path=nox_model_path,
        input_shape=(batch, model_input_h, model_input_w, channel),  
    )
    try:
        while loop_event.is_set():
            Read_Frame: np.ndarray  = input_queue.get()
            resized_img_BGR = cv2.resize(Read_Frame, (model_input_w, model_input_h))    
            float_image: np.ndarray = np.expand_dims(np.array(resized_img_BGR, dtype=np.float32) / 255, axis=0)
            output_RGB_float: np.ndarray = nox_model.predict(float_image)  
            output_RGB_int: np.ndarray = (output_RGB_float.squeeze() * 255).astype(np.int32)
            output_BGR: np.ndarray = cv2.convertScaleAbs(output_RGB_int)
            resized_img_BGR: np.ndarray  = cv2.resize(output_BGR, (org_w, org_h))
            
            if concat_apply:
                concat_frame: np.ndarray  = np.hstack((Read_Frame, resized_img_BGR))
                output_queue.put(concat_frame)
            else:
                output_queue.put(resized_img_BGR)

    except ValueError as e:
        print(f"nox_predict ERROR | {e}")  
    finally:
        loop_event.clear()
        return
