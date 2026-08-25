import cv2
import numpy as np
from typing import List, Union

def preprocess(
    image_list: List[np.ndarray], 
    dtype: Union[np.dtype, type] = np.float32,
    normalize_factor: float = 255.0, 
    channel_first: bool = True,
    batched: bool = True) -> List[np.ndarray]:
    
    processed_images: List[np.ndarray] = []  
    for image in image_list:
        image_normalized: np.ndarray = image.astype(dtype) / normalize_factor
        
        if channel_first:
            p_image: np.ndarray = image_normalized.transpose(2, 0, 1)
        else:
            p_image: np.ndarray = image_normalized
        
        if batched:
            result_image: np.ndarray = np.expand_dims(p_image, axis=0)
        else:
            result_image: np.ndarray = p_image
        
        processed_images.append(result_image)
    
    return processed_images
