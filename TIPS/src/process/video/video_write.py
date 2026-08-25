import cv2
from multiprocessing import Queue, Event
from multiprocessing.connection import Connection
from typing import Any, Dict, Tuple, List

def video_write(
    queue: Queue,
    loop_event: Event,
    finish_event: Event,
    fps : float,
    out_shape : Tuple[int, int],
    output_path : str,
    
) -> None:
    try:
        fourcc: int = cv2.VideoWriter_fourcc(*'mp4v')
        video_out: cv2.VideoWriter = cv2.VideoWriter(output_path, fourcc, fps, out_shape)
        while True:
            if (not loop_event.is_set()) and queue.empty():
                break
            frame_BGR: Any = queue.get()
            resize_BGR = cv2.resize(frame_BGR, (out_shape[0], out_shape[1]))    
            frame_RGB = cv2.cvtColor(resize_BGR, cv2.COLOR_BGR2RGB)
            video_out.write(frame_RGB)
            
    except ValueError as e:
        print(f"video_write ERROR | {e}")  
    finally:
        video_out.release()
        finish_event.clear()
        return
