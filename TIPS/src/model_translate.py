from ultralytics import YOLO
from pathlib import Path


def convert_yolo_to_onnx(pt_path: str, onnx_path: str = None) -> str:
    """
    YOLO 모델(.pt)을 ONNX로 변환
    
    Args:
        pt_path: source .pt model path
        onnx_path: output .onnx path (optional, auto-generated if None)
    
    Returns:
        str: converted ONNX model path
    """
    if onnx_path is None:
        pt_path = Path(pt_path)
        onnx_path = str(pt_path.with_suffix('.onnx'))
    
    print(f'Loading model from {pt_path}...')
    model = YOLO(pt_path)
    
    print(f'Exporting to ONNX: {onnx_path}...')
    model.export(
        format='onnx',
        imgsz=640,
        dynamic=True,
        opset=12,
        simplify=True
    )
    
    print(f'Conversion completed: {onnx_path}')
    return onnx_path


if __name__ == '__main__':
    pt_file = 'src/model/model1.pt'
    onnx_file = convert_yolo_to_onnx(pt_file)
    print(f'Saved: {onnx_file}')
