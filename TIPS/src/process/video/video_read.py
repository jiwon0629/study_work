import cv2
import sys
from multiprocessing import Queue,  Event
sys.path.append("../")
from utils import ReadFrame

def video_read(
    queue: Queue,
    loop_event: Event,
    input_path: str,
    ) -> None:
        
    try:
        cap = cv2.VideoCapture(str(input_path), cv2.CAP_FFMPEG)
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {input_path}")
    
        err_counter: int = 0
        err_threshold: int = 20
        while loop_event.is_set():
            img_RGB, img_BGR = ReadFrame(cap)
            if img_RGB is False:
                err_counter += 1
                if err_counter > err_threshold:
                    loop_event.clear()
                    break
                else:
                    continue
            queue.put(img_RGB)
            err_counter = 0

    except ValueError as e:
        print(f"video_read ERROR | {e}")  
    finally:
        cap.release()
        loop_event.clear()
        return
