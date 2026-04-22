import os
import cv2
import numpy as np
import time
from ultralytics import YOLO

# 모델 및 경로 설정
model = YOLO('best_re_final.pt').to('cuda')
input_dir = 'videos'
output_dir = 'results/full' # 풀영상 저장 폴더
os.makedirs(output_dir, exist_ok=True)

# [히스토그램 기반 Re-ID 로직]
def compute_circular_hist(frame, box):
    x1, y1, x2, y2 = map(int, box)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0 or crop.shape[0] == 0 or crop.shape[1] == 0: return None

    h, w = crop.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(mask, (w // 2, h // 2), min(w, h) // 2, 255, -1)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], mask, [50, 60], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    return hist

def get_iou(box1, box2):
    x_left, y_top = max(box1[0], box2[0]), max(box1[1], box2[1])
    x_right, y_bottom = min(box1[2], box2[2]), min(box1[3], box2[3])
    if x_right < x_left or y_bottom < y_top: return 0.0
    intersection = (x_right - x_left) * (y_bottom - y_top)
    b1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    b2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
    return intersection / float(b1_area + b2_area - intersection)

def get_hist_similarity(hist1, hist2):
    if hist1 is None or hist2 is None: return 0.0
    return cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)

def get_center_dist(box1, box2):
    c1 = [(box1[0]+box1[2])/2, (box1[1]+box1[3])/2]
    c2 = [(box2[0]+box2[2])/2, (box2[1]+box2[3])/2]
    return np.sqrt((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2)

PREDICT_FRAMES = 15 

video_files = [f for f in os.listdir(input_dir) if f.lower().endswith(('.mp4', '.ts'))]

for video_file in video_files:
    video_start_time = time.time()
    video_path = os.path.join(input_dir, video_file)
    cap = cv2.VideoCapture(video_path)
    w_vid, h_vid = int(cap.get(3)), int(cap.get(4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    
    save_path = os.path.join(output_dir, os.path.splitext(video_file)[0] + "_full_video_final.mp4")
    out = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w_vid, h_vid))

    print(f"\n[처리 시작] {video_file} ")
    
    track_states = {}
    id_map = {} 
    
    while True:
        ret, frame = cap.read()
        if not ret: break
            
        current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
        if current_frame % 30 == 0:
            print(f"\r진행률: {(current_frame / total_frames) * 100:.2f}%", end="")

        active_ids_this_frame = set()
        
        results = model.track(frame, persist=True, tracker="botsort.yaml", conf=0.25, verbose=False)
        r = results[0]
        
        # ---------------------------------------------------------
        # [Step 1] 정탐(YOLO 인식)
        # ---------------------------------------------------------
        if r.boxes is not None and r.boxes.id is not None:
            boxes = r.boxes.xyxy.cpu().numpy()
            raw_ids = r.boxes.id.cpu().numpy().astype(int)
            
            for box, raw_id in zip(boxes, raw_ids):
                current_hist = compute_circular_hist(frame, box)
                obj_id = id_map.get(raw_id, raw_id)
                
                x1, y1, x2, y2 = map(int, box)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w_vid, x2), min(h_vid, y2)
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                
                current_template = frame[y1:y2, x1:x2].copy()
                
                if obj_id not in track_states:
                    best_match_id = None
                    max_score = -1
                    for old_id, state in track_states.items():
                        if state['is_lost']:
                            iou = get_iou(state['last_box'], box)
                            dist = get_center_dist(state['last_box'], box)
                            sim = get_hist_similarity(state['last_hist'], current_hist)
                            
                            # 인식 최우선 연결 (반경 200픽셀 내)
                            if iou > 0.05 or dist < 200:
                                score = (iou * 2.0) + (1.0 - dist/200.0) + sim
                                if score > max_score:
                                    max_score = score
                                    best_match_id = old_id
                    
                    if best_match_id is not None:
                        id_map[raw_id] = best_match_id 
                        obj_id = best_match_id

                if obj_id not in track_states:
                    track_states[obj_id] = {
                        'last_box': box, 'last_hist': current_hist, 'lost_count': 0, 'is_lost': False,
                        'template': current_template, 'hx': [cx], 'hy': [cy], 'vx': 0, 'vy': 0,
                        'hit_count': 1, 'is_walker': False
                    }
                else:
                    state = track_states[obj_id]
                    state['hx'].append(cx)
                    state['hy'].append(cy)
                    if len(state['hx']) > 15: state['hx'].pop(0)
                    if len(state['hy']) > 15: state['hy'].pop(0)
                    
                    # 걷는 사람 판별 (50픽셀 이상 이동 시)
                    dist_moved = np.sqrt((state['hx'][-1] - state['hx'][0])**2 + (state['hy'][-1] - state['hy'][0])**2)
                    if dist_moved > 50:
                        state['is_walker'] = True
                    elif dist_moved < 15 and len(state['hx']) >= 15: 
                        state['is_walker'] = False

                    if len(state['hx']) >= 3:
                        raw_vx = (state['hx'][-1] - state['hx'][-3]) / 2.0
                        raw_vy = (state['hy'][-1] - state['hy'][-3]) / 2.0
                    else:
                        raw_vx, raw_vy = 0, 0

                    vx = np.clip(raw_vx, -15, 15)
                    vy = np.clip(raw_vy, -15, 15)

                    track_states[obj_id].update({
                        'last_box': box, 'last_hist': current_hist, 'lost_count': 0, 'is_lost': False,
                        'template': current_template, 'vx': vx, 'vy': vy,
                        'hit_count': state.get('hit_count', 0) + 1 
                    })

                active_ids_this_frame.add(obj_id)

        # ---------------------------------------------------------
        # [Step 1-2] 중복 블러 무조건 병합 (얼굴/몸통 겹침 해결)
        # ---------------------------------------------------------
        active_list = list(active_ids_this_frame)
        for i in range(len(active_list)):
            for j in range(i + 1, len(active_list)):
                id1, id2 = active_list[i], active_list[j]
                if id1 in track_states and id2 in track_states:
                    b1 = track_states[id1]['last_box']
                    b2 = track_states[id2]['last_box']
                    area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
                    area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
                    inter_w = max(0, min(b1[2], b2[2]) - max(b1[0], b2[0]))
                    inter_h = max(0, min(b1[3], b2[3]) - max(b1[1], b2[1]))
                    inter_area = inter_w * inter_h
                    
                    io_min = inter_area / (min(area1, area2) + 1e-6)
                    if io_min > 0.4:
                        if area1 > area2: track_states.pop(id2, None)
                        else: track_states.pop(id1, None)
        
        active_ids_this_frame = set([tid for tid in active_ids_this_frame if tid in track_states])

        # ---------------------------------------------------------
        # [Step 2] 미탐(가려짐/고개돌림) 시: 0->1->2 갱신 & 즉시 고정
        # ---------------------------------------------------------
        for oid in list(track_states.keys()):
            state = track_states[oid]
            
            if oid not in active_ids_this_frame:
                state['is_lost'] = True
                state['lost_count'] += 1
                
                template = state.get('template')
                matched = False
                
                px1, py1, px2, py2 = map(int, state['last_box'])
                vx, vy = state.get('vx', 0), state.get('vy', 0)
                cx = (px1 + px2) / 2
                cy = (py1 + py2) / 2
                bw = px2 - px1

                # [3대 데스존(Death Zone) 청소] 
                if state['lost_count'] > 15:
                    if py2 > h_vid - 50: # 화면 하단 이탈
                        del track_states[oid]
                        continue
                    if cx < 120 or cx > w_vid - 120: # 문틀 유령
                        del track_states[oid]
                        continue
                    if cy < h_vid * 0.4 and bw < 60: # 복도 끝 찌꺼기
                        del track_states[oid]
                        continue

                # --- 0 -> 1 -> 2 순차적 템플릿 매칭 ---
                if template is not None and template.size > 0 and state['lost_count'] <= 30:
                    th, tw = template.shape[:2] 
                    pred_x1 = px1 + vx
                    pred_y1 = py1 + vy
                    pad = 30 
                    sx1, sy1 = max(0, int(pred_x1) - pad), max(0, int(pred_y1) - pad)
                    sx2, sy2 = min(w_vid, int(pred_x1 + tw) + pad), min(h_vid, int(pred_y1 + th) + pad)
                    
                    search_roi = frame[sy1:sy2, sx1:sx2]
                    
                    if search_roi.shape[0] >= th and search_roi.shape[1] >= tw:
                        res = cv2.matchTemplate(search_roi, template, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, max_loc = cv2.minMaxLoc(res)
                        
                        if max_val > 0.25: 
                            new_x1 = sx1 + max_loc[0]
                            new_y1 = sy1 + max_loc[1]
                            
                            new_box = np.array([new_x1, new_y1, new_x1 + tw, new_y1 + th])
                            state['last_box'] = new_box
                            matched = True
                            state['lost_count'] = 0 
                            state['template'] = frame[int(new_y1):int(new_y1+th), int(new_x1):int(new_x1+tw)].copy()

                # --- 매칭 실패 시: 보행자 관성 vs 착석자 즉시 고정 ---
                if not matched:
                    is_walker_safe = state.get('is_walker', False)
                    
                    if is_walker_safe:
                        # 걷는 사람은 0.5초(15프레임) 동안 기둥 통과를 위해 밀어줌
                        if state['lost_count'] <= PREDICT_FRAMES: 
                            state['last_box'] = np.array([px1 + vx, py1 + vy, px2 + vx, py2 + vy])
                        else:
                            del track_states[oid]
                            continue
                    else:
                        # 앉아있는 사람은 고개 돌리자마자 그 자리에 즉시 영원히 얼음(고정)!
                        state['vx'] = 0
                        state['vy'] = 0

            # ---------------------------------------------------------
            # [Step 3] 렌더링 (조건 전면 삭제, 무조건 즉시 그리기)
            # ---------------------------------------------------------
            if oid in track_states:
                
                
                x1, y1, x2, y2 = map(int, state['last_box'])
                bw = x2 - x1
                bh = y2 - y1
                
                cx = x1 + bw // 2
                cy = y1 + bh // 2
                
                radius = int(max(bw, bh) * 0.65) 
                cy = cy - int(bh * 0.15) 
                
                px1 = max(0, cx - radius)
                py1 = max(0, cy - radius)
                px2 = min(w_vid, cx + radius)
                py2 = min(h_vid, cy + radius)
                
                roi = frame[py1:py2, px1:px2]
                if roi.shape[0] > 0 and roi.shape[1] > 0:
                    blur_img = cv2.GaussianBlur(roi, (99, 99), 0)
                    mask = np.zeros_like(roi)
                    
                    local_cx = cx - px1
                    local_cy = cy - py1
                    
                    cv2.circle(mask, (local_cx, local_cy), radius, (255, 255, 255), -1)
                    frame[py1:py2, px1:px2] = np.where(mask == 255, blur_img, roi)

        out.write(frame)

    cap.release()
    out.release()
    
    # 처리 시간 계산
    video_end_time = time.time()
    elapsed_time = video_end_time - video_start_time
    print(f"\n저장 완료: {save_path} (소요 시간: {elapsed_time/60:.2f}분)")