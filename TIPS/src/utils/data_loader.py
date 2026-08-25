import cv2
import numpy as np
from pathlib import Path
from typing import Tuple, Union
import warnings

warnings.filterwarnings("ignore", message="The value of the smallest subnormal for <class 'numpy.float32'> type is zero.")
warnings.filterwarnings("ignore", message="The value of the smallest subnormal for <class 'numpy.float64'> type is zero.")

def ReadFrame(cap: cv2.VideoCapture) -> Tuple[Union[np.ndarray, bool], Union[np.ndarray, bool]]:
    _, orig_img = cap.read()
    if orig_img is None:
        return False, False
    img_RGB = cv2.cvtColor(orig_img, cv2.COLOR_BGR2RGB)
    return img_RGB, orig_img

def video_metadata(input_path: Path, ini_dict: dict) -> Tuple[float, int, int]:
    nox_model_max_height : int = ini_dict['NOX']['NOX_MODEL_MAX_HEIGHT'] 
    nox_model_max_width : int  = ini_dict['NOX']['NOX_MODEL_MAX_WIDTH'] 
    nox_model_min_height : int = ini_dict['NOX']['NOX_MODEL_MIN_HEIGHT'] 
    nox_model_min_width : int  = ini_dict['NOX']['NOX_MODEL_MIN_WIDTH'] 
    
    cap = cv2.VideoCapture(str(input_path), cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {input_path}")

    org_fps: float = cap.get(cv2.CAP_PROP_FPS)
    org_w: int = round(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    org_h: int = round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    input_w: int = round(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    input_h: int = round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    if input_w < nox_model_min_width:
        input_w = nox_model_min_width
    elif input_w > nox_model_max_width:
        input_w = nox_model_max_width

    if input_h < nox_model_min_height:
        input_h = nox_model_min_height
    elif input_h > nox_model_max_height:
        input_h = nox_model_max_height

    cap.release()
    
    return org_fps, org_w, org_h, input_w, input_h


def image_metadata(input_path: Path, ini_dict: dict) ->None:
    nox_model_max_height : int = ini_dict['NOX']['NOX_MODEL_MAX_HEIGHT'] 
    nox_model_max_width : int  = ini_dict['NOX']['NOX_MODEL_MAX_WIDTH'] 
    nox_model_min_height : int = ini_dict['NOX']['NOX_MODEL_MIN_HEIGHT'] 
    nox_model_min_width : int  = ini_dict['NOX']['NOX_MODEL_MIN_WIDTH'] 
    
    img_BGR: np.ndarray = cv2.imread(str(input_path))
    if img_BGR is None:
        print(f"Failed to open image: {input_path}")
        return

    img_h, img_w = img_BGR.shape[:2]
    
    if img_w < nox_model_min_width:
        img_w = nox_model_min_width
    elif img_w > nox_model_max_width:
        img_w = nox_model_max_width

    if img_h < nox_model_min_height:
        img_h = nox_model_min_height
    elif img_h > nox_model_max_height:
        img_h = nox_model_max_height
    
    return img_BGR, img_w, img_h