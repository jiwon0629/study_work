📊 1. 전체적인 코드 분석 (핵심 요약)
이 코드는 단순한 YOLO 객체 인식을 넘어, **실제 지하철 환경에서 발생하는 다양한 예외 상황(가려짐, 겹침, 고개 돌림, 이탈 등)을 완벽하게 방어하는 '하이브리드 추적(Tracking) 시스템'**입니다.

다중 추적 방식 (YOLO + 색상 히스토그램 + 템플릿 매칭):

기본적으로 YOLO의 botsort를 사용하지만, ID가 바뀌거나 끊길 경우를 대비해 **옷 색상(히스토그램)**과 거리/IOU를 계산하여 억울하게 끊긴 객체를 다시 이어줍니다 (Re-ID).

보행자 vs 착석자 지능형 판단 (관성 부여):

과거 15프레임 동안의 좌표 이동 거리(hx, hy)를 계산해 **'걷는 사람'**인지 **'앉아있는 사람'**인지 구분합니다.

걷는 사람이 기둥에 가려지면 원래 걷던 속도(vx, vy)만큼 블러를 앞으로 밀어주고(관성), 앉은 사람은 고개를 돌려 인식이 끊기면 즉시 그 자리에 얼음(고정)시킵니다.

데스존(Death Zone) 및 찌꺼기 청소:

화면 맨 아래, 양옆 문틀, 복도 끝점 등에서 오랫동안 인식이 안 되는 객체는 '화면 밖으로 나간 것'으로 간주하고 메모리에서 깔끔하게 삭제합니다.

중복 100% 사살 (몸통-얼굴 겹침 해결):

하나의 사람에 두 개의 박스(예: 얼굴, 몸통)가 겹쳤을 때, 더 작은 박스를 강제로 지워버려 블러가 두 개 생기는 현상을 막습니다.

🗺️ 2. 전체적인 순서도 (Flowchart)
[초기 세팅] 라이브러리 로드, YOLO 모델(CUDA) 로드, 폴더 및 저장 경로 생성.

[영상 읽기] videos 폴더 내의 영상을 하나씩 불러와 프레임 단위로 읽기 시작.

[YOLO 탐지] model.track()을 이용해 현재 프레임의 사람(객체) 인식 및 고유 ID 부여.

[Step 1: 정탐 및 매칭]

YOLO가 잡은 박스의 색상(히스토그램) 추출 및 템플릿(이미지 조각) 저장.

기존에 추적 중이던 객체와 비교하여 연결(Re-ID).

객체의 과거 좌표를 분석해 '걷는 사람'인지 판단하고 이동 속도(vx, vy) 계산.

[Step 1-2: 중복 사살]

화면에 있는 박스들끼리 겹치는 면적을 계산.

작은 박스가 큰 박스 안에 40% 이상 파묻혀 있으면 작은 박스 삭제.

[Step 2: 미탐 (가려짐/놓침) 처리]

YOLO가 객체를 놓쳤다면(is_lost), '데스존'에 있는지 확인하여 삭제.

안전지대라면, 직전 템플릿(얼굴/몸 이미지)으로 matchTemplate을 돌려 주변 픽셀 중 가장 비슷한 곳으로 좌표 강제 갱신 (0->1->2 덮어씌우기).

비슷한 곳도 없다면, '걷는 사람'은 이동하던 방향으로 밀어주고, '앉은 사람'은 제자리에 고정.

[Step 3: 렌더링 및 저장]

살아남은 모든 객체의 좌표에 맞춰 원형(가우시안) 블러를 그림.

완성된 프레임을 비디오 파일로 저장.

💻 3. 한 줄 한 줄 완벽 분석 주석 코드
```Python
import os                  # 파일 및 폴더 경로 관리를 위한 라이브러리
import cv2                 # 영상 처리 및 컴퓨터 비전(블러, 템플릿 매칭 등)을 위한 라이브러리
import numpy as np         # 행렬 계산 및 수학적 연산을 위한 라이브러리
import time                # 소요 시간 계산을 위한 라이브러리
from ultralytics import YOLO # YOLO 객체 탐지 모델을 사용하기 위한 라이브러리

# 1. 모델 및 경로 설정
model = YOLO('best_re_final.pt').to('cuda') # 학습된 YOLO 모델을 불러오고 GPU(cuda) 연산 모드로 설정
input_dir = 'videos'                        # 원본 영상들이 들어있는 입력 폴더 이름
output_dir = 'results/full'                 # 블러 처리된 최종 풀영상을 저장할 출력 폴더 이름
os.makedirs(output_dir, exist_ok=True)      # 출력 폴더가 없다면 새로 생성 (있으면 무시)

# [히스토그램 기반 Re-ID 로직]
# 객체의 색상 분포(히스토그램)를 추출하여 동일 인물인지 비교하기 위한 함수
def compute_circular_hist(frame, box):
    x1, y1, x2, y2 = map(int, box) # 소수점으로 나올 수 있는 박스 좌표를 정수로 변환
    x1, y1 = max(0, x1), max(0, y1) # 좌표가 화면 왼쪽/위쪽 밖으로 나가지 않도록 0으로 보정
    x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2) # 화면 오른쪽/아래쪽 밖으로 나가지 않도록 보정
    crop = frame[y1:y2, x1:x2]      # 화면에서 해당 박스 크기만큼 이미지를 잘라냄 (crop)
    
    # 잘라낸 이미지가 비정상적(크기가 0)이면 None 반환 후 종료
    if crop.size == 0 or crop.shape[0] == 0 or crop.shape[1] == 0: return None

    h, w = crop.shape[:2] # 잘라낸 이미지의 높이(h)와 너비(w)를 구함
    mask = np.zeros((h, w), dtype=np.uint8) # 히스토그램을 추출할 '원형 마스크'를 만들기 위해 까만 도화지 생성
    # 까만 도화지 정중앙에 하얀색(255) 꽉 찬 원을 그림 (박스 모서리 배경을 제외하고 사람 부분만 색상을 뽑기 위함)
    cv2.circle(mask, (w // 2, h // 2), min(w, h) // 2, 255, -1) 
    
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV) # 빛의 영향을 덜 받도록 BGR 색상을 HSV(색상, 채도, 명도)로 변환
    # 마스크 영역 내에서 H(색상)와 S(채도) 값의 분포(히스토그램)를 추출
    hist = cv2.calcHist([hsv], [0, 1], mask, [50, 60], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX) # 비교하기 쉽도록 히스토그램 값을 0~1 사이로 정규화
    return hist # 추출된 색상 히스토그램 반환

# 두 박스가 얼마나 겹치는지(Intersection Over Union) 비율을 구하는 함수
def get_iou(box1, box2):
    # 두 박스가 겹치는 사각형의 좌상단(x_left, y_top)과 우하단(x_right, y_bottom) 좌표 계산
    x_left, y_top = max(box1[0], box2[0]), max(box1[1], box2[1])
    x_right, y_bottom = min(box1[2], box2[2]), min(box1[3], box2[3])
    
    # 우하단 좌표가 좌상단 좌표보다 작으면 (즉, 아예 겹치지 않으면) 0 반환
    if x_right < x_left or y_bottom < y_top: return 0.0
    
    intersection = (x_right - x_left) * (y_bottom - y_top) # 겹치는 영역의 넓이 계산
    b1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])    # 첫 번째 박스의 넓이
    b2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])    # 두 번째 박스의 넓이
    # 겹치는 넓이 / (전체 합친 넓이 - 겹치는 넓이) 비율 반환
    return intersection / float(b1_area + b2_area - intersection)

# 두 객체의 색상 히스토그램이 얼마나 비슷한지 상관관계(Correlation)를 구하는 함수
def get_hist_similarity(hist1, hist2):
    if hist1 is None or hist2 is None: return 0.0 # 하나라도 히스토그램이 없으면 유사도 0 반환
    return cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL) # 1에 가까울수록 색상이 비슷함을 의미

# 두 박스의 중심점 사이의 직선 거리를 구하는 함수 (피타고라스 정리)
def get_center_dist(box1, box2):
    c1 = [(box1[0]+box1[2])/2, (box1[1]+box1[3])/2] # 박스1의 중심 좌표 (cx, cy)
    c2 = [(box2[0]+box2[2])/2, (box2[1]+box2[3])/2] # 박스2의 중심 좌표 (cx, cy)
    return np.sqrt((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2) # 두 점 사이의 거리 계산 후 반환

PREDICT_FRAMES = 15  # 모델이 인식을 놓쳤을 때, 보행자를 이동 방향으로 밀어줄(관성) 최대 프레임 수 (약 0.5초)

# input_dir 폴더 안에서 확장자가 .mp4 이거나 .ts 인 동영상 파일 목록만 추려냄
video_files = [f for f in os.listdir(input_dir) if f.lower().endswith(('.mp4', '.ts'))]

# 각 영상 파일에 대해 반복 작업 시작
for video_file in video_files:
    video_start_time = time.time() # 영상 처리를 시작한 현재 시간 기록 (나중에 소요시간 계산용)
    video_path = os.path.join(input_dir, video_file) # 처리할 영상의 완벽한 경로 조합
    cap = cv2.VideoCapture(video_path) # 영상을 읽어오기 위한 OpenCV 객체 생성
    
    w_vid, h_vid = int(cap.get(3)), int(cap.get(4)) # 영상의 너비(Width)와 높이(Height) 정보 가져오기
    fps = cap.get(cv2.CAP_PROP_FPS) or 30           # 영상의 초당 프레임 수(FPS) 가져오기, 실패 시 기본값 30
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) # 영상의 총 프레임 갯수 파악 (진행률 계산용)
    
    # 결과물을 저장할 파일 이름 및 경로 설정 (원본이름_full_video_final.mp4)
    save_path = os.path.join(output_dir, os.path.splitext(video_file)[0] + "_full_video_final.mp4")
    # 영상을 프레임 단위로 쓰기 위한 VideoWriter 객체 생성 (mp4v 코덱 사용)
    out = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w_vid, h_vid))

    print(f"\n[처리 시작] {video_file} ")
    
    track_states = {} # 현재 추적 중인 모든 객체들의 정보(상태, 템플릿, 속도 등)를 저장하는 딕셔너리
    id_map = {}       # YOLO가 부여한 ID가 중간에 바뀌더라도, 원래 내 ID로 연결해주기 위한 매핑 딕셔너리
    
    # 프레임을 하나씩 읽으며 끝날 때까지 무한 반복
    while True:
        ret, frame = cap.read() # 영상에서 프레임 1장을 읽어옴 (ret: 성공 여부, frame: 이미지 데이터)
        if not ret: break       # 더 이상 읽어올 프레임이 없다면(영상 끝) 반복문 탈출
            
        current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) # 현재 몇 번째 프레임을 읽고 있는지 번호 가져옴
        if current_frame % 30 == 0: # 30프레임(약 1초)마다 한 번씩 진행률을 화면에 출력
            print(f"\r진행률: {(current_frame / total_frames) * 100:.2f}%", end="")

        active_ids_this_frame = set() # '이번 프레임'에서 확실하게 살아있는(인식된) 객체들의 ID 모음
        
        # YOLO 모델로 현재 프레임의 사람을 찾고(conf=0.25 이상), botsort 알고리즘으로 추적(Track) 수행
        results = model.track(frame, persist=True, tracker="botsort.yaml", conf=0.25, verbose=False)
        r = results[0] # 탐지 결과들 중 첫 번째 이미지(현재 프레임)의 결과만 가져옴
        
        # ---------------------------------------------------------
        # [Step 1] 정탐(YOLO 인식) - 모델이 사람을 제대로 찾았을 때
        # ---------------------------------------------------------
        # 찾은 객체(박스)가 하나라도 있고, 그 객체에 추적 ID가 부여되었다면
        if r.boxes is not None and r.boxes.id is not None:
            boxes = r.boxes.xyxy.cpu().numpy() # 박스의 좌상단/우하단 좌표를 numpy 배열로 가져옴
            raw_ids = r.boxes.id.cpu().numpy().astype(int) # YOLO가 부여한 날것의(raw) ID를 정수로 가져옴
            
            # 탐지된 박스와 ID를 하나씩 짝지어서 반복
            for box, raw_id in zip(boxes, raw_ids):
                current_hist = compute_circular_hist(frame, box) # 현재 잡힌 박스의 색상 히스토그램 추출
                obj_id = id_map.get(raw_id, raw_id) # 이전에 매핑해둔 내 진짜 ID가 있다면 그걸 쓰고, 없으면 방금 받은 ID 사용
                
                # 박스 좌표를 안전하게 정수로 변환하고, 화면 밖으로 나가지 않도록 자름
                x1, y1, x2, y2 = map(int, box)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w_vid, x2), min(h_vid, y2)
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2 # 박스의 정중앙 좌표(cx, cy) 계산
                
                # 현재 박스 부분의 이미지를 복사하여 템플릿(조각 이미지)으로 저장 (나중에 가려졌을 때 찾기 위함)
                current_template = frame[y1:y2, x1:x2].copy()
                
                # 만약 이 객체가 내가 처음 보는 객체(추적 목록에 없는 ID)라면, 과거에 잃어버렸던 객체인지 확인(Re-ID)
                if obj_id not in track_states:
                    best_match_id = None
                    max_score = -1
                    
                    # 과거에 추적하다가 잃어버린(is_lost=True) 모든 객체들을 소환해서 현재 객체와 비교
                    for old_id, state in track_states.items():
                        if state['is_lost']:
                            iou = get_iou(state['last_box'], box)               # 예전 박스와 현재 박스의 겹침 정도
                            dist = get_center_dist(state['last_box'], box)      # 예전 위치와 현재 위치의 거리
                            sim = get_hist_similarity(state['last_hist'], current_hist) # 옷 색깔 일치율
                            
                            # 거리가 200픽셀 이내로 가깝거나 약간이라도 겹치면 동일 인물일 가능성 평가
                            if iou > 0.05 or dist < 200:
                                # 점수 계산: 겹침(가중치 높음) + 거리 가까움 + 색상 일치
                                score = (iou * 2.0) + (1.0 - dist/200.0) + sim
                                if score > max_score: # 가장 점수가 높은 잃어버렸던 객체를 찾음
                                    max_score = score
                                    best_match_id = old_id
                    
                    # 만약 잃어버렸던 객체와 일치한다고 판단되면, 새 ID를 버리고 예전 ID로 강제 편입
                    if best_match_id is not None:
                        id_map[raw_id] = best_match_id 
                        obj_id = best_match_id

                # 여전히 추적 목록에 없는 진짜 완전 새로운 객체라면, 추적 장부(track_states)에 새로 등록
                if obj_id not in track_states:
                    track_states[obj_id] = {
                        'last_box': box, 'last_hist': current_hist, 'lost_count': 0, 'is_lost': False,
                        'template': current_template, 'hx': [cx], 'hy': [cy], 'vx': 0, 'vy': 0,
                        'hit_count': 1, 'is_walker': False
                    }
                # 이미 추적 중이던 객체라면, 최신 정보로 상태 업데이트
                else:
                    state = track_states[obj_id]
                    state['hx'].append(cx) # X 좌표 궤적에 최신 X 좌표 추가
                    state['hy'].append(cy) # Y 좌표 궤적에 최신 Y 좌표 추가
                    
                    # 메모리 절약을 위해 궤적(히스토리)은 최근 15프레임(0.5초)치만 남기고 오래된 건 버림
                    if len(state['hx']) > 15: state['hx'].pop(0)
                    if len(state['hy']) > 15: state['hy'].pop(0)
                    
                    # [보행자 vs 착석자 판별 로직]
                    # 15프레임 전 위치와 현재 위치의 이동 거리를 계산
                    dist_moved = np.sqrt((state['hx'][-1] - state['hx'][0])**2 + (state['hy'][-1] - state['hy'][0])**2)
                    
                    # 50픽셀 이상 크게 이동했다면 '걷는 사람(Walker)'으로 확정
                    if dist_moved > 50:
                        state['is_walker'] = True
                    # 좌표가 15개나 모였는데도 15픽셀 미만으로 움직였다면 '앉아있는 사람(가만히 있는 사람)'으로 확정
                    elif dist_moved < 15 and len(state['hx']) >= 15: 
                        state['is_walker'] = False

                    # 좌표 히스토리가 3개 이상 모였다면, 최근 이동 속도(vx, vy)를 계산
                    if len(state['hx']) >= 3:
                        raw_vx = (state['hx'][-1] - state['hx'][-3]) / 2.0
                        raw_vy = (state['hy'][-1] - state['hy'][-3]) / 2.0
                    else:
                        raw_vx, raw_vy = 0, 0

                    # 속도가 너무 빠르면 블러가 튀어버리므로, 한 프레임당 최대 15픽셀까지만 이동하도록 제한(clip)
                    vx = np.clip(raw_vx, -15, 15)
                    vy = np.clip(raw_vy, -15, 15)

                    # 추적 장부(상태)를 현재 최신 정보로 덮어쓰기 (갱신)
                    track_states[obj_id].update({
                        'last_box': box, 'last_hist': current_hist, 'lost_count': 0, 'is_lost': False,
                        'template': current_template, 'vx': vx, 'vy': vy,
                        'hit_count': state.get('hit_count', 0) + 1 
                    })

                # 이번 프레임에서 이 객체는 확실히 살아있으므로 생존 신고 완료
                active_ids_this_frame.add(obj_id)

        # ---------------------------------------------------------
        # [Step 1-2] 중복 블러 무조건 병합 (얼굴/몸통 겹침 해결)
        # ---------------------------------------------------------
        # 현재 화면에 살아있는 객체 ID들을 리스트로 변환
        active_list = list(active_ids_this_frame)
        
        # 화면의 모든 박스들을 서로서로 1:1로 비교 (이중 반복문)
        for i in range(len(active_list)):
            for j in range(i + 1, len(active_list)):
                id1, id2 = active_list[i], active_list[j]
                
                # 둘 다 추적 장부에 살아있는 객체라면
                if id1 in track_states and id2 in track_states:
                    b1 = track_states[id1]['last_box'] # 첫 번째 박스
                    b2 = track_states[id2]['last_box'] # 두 번째 박스
                    area1 = (b1[2] - b1[0]) * (b1[3] - b1[1]) # 첫 번째 박스 넓이
                    area2 = (b2[2] - b2[0]) * (b2[3] - b2[1]) # 두 번째 박스 넓이
                    
                    # 두 박스가 겹치는 영역의 가로(inter_w)와 세로(inter_h) 계산
                    inter_w = max(0, min(b1[2], b2[2]) - max(b1[0], b2[0]))
                    inter_h = max(0, min(b1[3], b2[3]) - max(b1[1], b2[1]))
                    inter_area = inter_w * inter_h # 겹치는 넓이
                    
                    # ★ 핵심: 일반 IOU가 아니라, '둘 중 더 작은 박스 기준'으로 얼마나 파묻혔는지 비율 계산
                    # (예: 큰 몸통 안에 작은 얼굴 박스가 100% 쏙 들어가 있으면 io_min은 1.0이 됨)
                    io_min = inter_area / (min(area1, area2) + 1e-6)
                    
                    # 작은 박스가 큰 박스에 40% 이상 파묻혀 있다면 (겹침 감지)
                    if io_min > 0.4:
                        # 더 큰 박스는 살려두고, 더 작은 박스(얼굴 등)를 추적 장부에서 강제 삭제(사살)
                        if area1 > area2: track_states.pop(id2, None)
                        else: track_states.pop(id1, None)
        
        # 중복 사살 작업 후, 살아남은 진짜 객체들만 다시 생존 목록으로 최신화
        active_ids_this_frame = set([tid for tid in active_ids_this_frame if tid in track_states])

        # ---------------------------------------------------------
        # [Step 2] 미탐(가려짐/고개돌림) 시: 0->1->2 갱신 & 즉시 고정
        # ---------------------------------------------------------
        # 추적 장부에 등록된 모든 객체를 하나씩 확인
        for oid in list(track_states.keys()):
            state = track_states[oid]
            
            # 만약 장부에는 있는데 이번 프레임 생존 목록에는 없다면 = 모델이 객체를 놓침!
            if oid not in active_ids_this_frame:
                state['is_lost'] = True       # 놓침 상태로 변경
                state['lost_count'] += 1      # 놓친 프레임 누적 카운트 1 증가
                
                template = state.get('template') # 이 객체를 마지막으로 봤을 때의 모습(조각 이미지) 가져옴
                matched = False                  # 템플릿으로 다시 찾았는지 여부 (초기값: 못 찾음)
                
                # 마지막으로 목격된 박스 좌표와 속도, 중심점, 너비 가져오기
                px1, py1, px2, py2 = map(int, state['last_box'])
                vx, vy = state.get('vx', 0), state.get('vy', 0)
                cx = (px1 + px2) / 2
                cy = (py1 + py2) / 2
                bw = px2 - px1

                # [3대 데스존(Death Zone) 청소] - 오랫동안 놓쳤는데 특정 구역에 있다면 삭제
                if state['lost_count'] > 15: # 15프레임 이상(0.5초) 못 찾았을 때
                    if py2 > h_vid - 50: # 1. 화면 맨 아래로 내려감 (카메라 밑으로 사라짐)
                        del track_states[oid]
                        continue
                    if cx < 120 or cx > w_vid - 120: # 2. 화면 양옆 끝 (양쪽 문으로 내리거나 탄 사람)
                        del track_states[oid]
                        continue
                    if cy < h_vid * 0.4 and bw < 60: # 3. 화면 위쪽 중앙의 작아진 객체 (복도 저 멀리 걸어간 사람)
                        del track_states[oid]
                        continue

                # --- 0 -> 1 -> 2 순차적 템플릿 매칭 ---
                # 템플릿(과거 조각 이미지)이 있고, 놓친 지 1초(30프레임) 이내일 때만 주변 탐색 시도
                if template is not None and template.size > 0 and state['lost_count'] <= 30:
                    th, tw = template.shape[:2] # 템플릿의 높이와 너비
                    # 마지막 목격 위치에서 관성 속도(vx, vy)만큼 더 이동한 곳을 예상 위치로 잡음
                    pred_x1 = px1 + vx
                    pred_y1 = py1 + vy
                    pad = 30 # 예상 위치 주변 30픽셀을 탐색 반경(ROI)으로 설정
                    
                    # 화면 밖으로 탐색 반경이 넘어가지 않도록 보정
                    sx1, sy1 = max(0, int(pred_x1) - pad), max(0, int(pred_y1) - pad)
                    sx2, sy2 = min(w_vid, int(pred_x1 + tw) + pad), min(h_vid, int(pred_y1 + th) + pad)
                    
                    search_roi = frame[sy1:sy2, sx1:sx2] # 화면에서 탐색 반경(ROI)만큼 잘라냄
                    
                    # 자른 탐색 반경이 템플릿 크기보다 클 때만 픽셀 매칭(숨바꼭질) 시작
                    if search_roi.shape[0] >= th and search_roi.shape[1] >= tw:
                        # cv2.matchTemplate: 탐색 영역 안에서 템플릿 이미지와 가장 비슷한 구역을 찾아냄
                        res = cv2.matchTemplate(search_roi, template, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, max_loc = cv2.minMaxLoc(res) # 유사도 점수(max_val)와 위치(max_loc) 추출
                        
                        # ★ 핵심: 픽셀이 25% 이상(0.25) 일치할 때만 "찾았다!"고 인정하고 좌표 갱신 (배경 덮어씌우기 방지)
                        if max_val > 0.25: 
                            new_x1 = sx1 + max_loc[0] # 찾아낸 진짜 위치의 x좌표
                            new_y1 = sy1 + max_loc[1] # 찾아낸 진짜 위치의 y좌표
                            
                            # 객체의 좌표를 방금 템플릿 매칭으로 찾아낸 위치로 강제 갱신
                            new_box = np.array([new_x1, new_y1, new_x1 + tw, new_y1 + th])
                            state['last_box'] = new_box
                            matched = True            # 찾았다고 표시
                            state['lost_count'] = 0   # 놓침 카운트 초기화 (살려냄)
                            
                            # ★ 0->1->2 덮어씌우기: 방금 찾아낸 새로운 위치의 픽셀 조각을 새로운 기준 템플릿으로 업데이트
                            state['template'] = frame[int(new_y1):int(new_y1+th), int(new_x1):int(new_x1+tw)].copy()

                # --- 매칭 실패 시 (완전히 가려지거나 고개를 돌렸을 때): 보행자 관성 vs 착석자 즉시 고정 ---
                if not matched: # 픽셀 매칭으로도 못 찾았다면
                    is_walker_safe = state.get('is_walker', False) # 이 사람이 걷던 사람인지 확인
                    
                    if is_walker_safe:
                        # 걷던 사람이라면 기둥 뒤로 지나가고 있을 확률이 높으므로, 15프레임(0.5초) 동안은 속도(vx, vy)만큼 블러를 앞으로 계속 밀어줌 (관성)
                        if state['lost_count'] <= PREDICT_FRAMES: 
                            state['last_box'] = np.array([px1 + vx, py1 + vy, px2 + vx, py2 + vy])
                        # 0.5초가 넘도록 안 나타나면 벽 뒤로 사라졌거나 나간 것이므로 삭제
                        else:
                            del track_states[oid]
                            continue
                    else:
                        # 앉아있던 사람이라면 속도를 무조건 0으로 만들어서, 놓친 바로 그 자리에 영원히 얼음(고정)시킴!
                        state['vx'] = 0
                        state['vy'] = 0

            # ---------------------------------------------------------
            # [Step 3] 렌더링 (조건 전면 삭제, 무조건 즉시 그리기)
            # ---------------------------------------------------------
            # 객체가 추적 장부에 아직 살아있다면 (YOLO로 잡았든, 템플릿으로 매칭했든, 고정되었든 무관)
            if oid in track_states:
                
                x1, y1, x2, y2 = map(int, state['last_box']) # 박스 좌표를 가져옴
                bw = x2 - x1 # 박스의 너비 계산
                bh = y2 - y1 # 박스의 높이 계산
                
                cx = x1 + bw // 2 # 박스의 정중앙 x 좌표
                cy = y1 + bh // 2 # 박스의 정중앙 y 좌표
                
                # 블러의 원형 크기(반지름) 설정: 긴 쪽 길이에 0.65를 곱하여 넉넉하게 덮음
                radius = int(max(bw, bh) * 0.65) 
                
                # 얼굴/머리 쪽이 위로 치우쳐 있는 것을 감안해 블러 중심을 살짝 위쪽(-15%)으로 끌어올림
                cy = cy - int(bh * 0.15) 
                
                # 원형 블러가 들어갈 네모 영역(px1, py1 ~ px2, py2) 계산, 화면 밖으로 나가지 않도록 자름
                px1 = max(0, cx - radius)
                py1 = max(0, cy - radius)
                px2 = min(w_vid, cx + radius)
                py2 = min(h_vid, cy + radius)
                
                roi = frame[py1:py2, px1:px2] # 화면에서 블러를 칠할 영역 잘라냄
                # 자른 영역이 정상적일 때만 블러 처리 수행
                if roi.shape[0] > 0 and roi.shape[1] > 0:
                    blur_img = cv2.GaussianBlur(roi, (99, 99), 0) # 잘라낸 영역 전체에 강력한 가우시안 블러 적용
                    mask = np.zeros_like(roi)                     # 동그랗게 구멍을 뚫을 까만 도화지(마스크) 생성
                    
                    local_cx = cx - px1 # 잘라낸 이미지 기준의 상대적 x좌표
                    local_cy = cy - py1 # 잘라낸 이미지 기준의 상대적 y좌표
                    
                    # 마스크 정중앙에 하얀색(255) 꽉 찬 원을 그림
                    cv2.circle(mask, (local_cx, local_cy), radius, (255, 255, 255), -1)
                    
                    # np.where: 마스크가 하얀색(원 안)이면 블러 이미지를 씌우고, 까만색(원 밖 배경)이면 원래 이미지를 그대로 유지
                    frame[py1:py2, px1:px2] = np.where(mask == 255, blur_img, roi)

        out.write(frame) # 블러 처리가 모두 끝난 1장의 프레임을 비디오 파일에 합쳐서 기록

    # 영상 처리가 끝나면 메모리 반환
    cap.release()
    out.release()
    
    # 영상 하나를 다 처리하는 데 걸린 시간 계산 및 출력
    video_end_time = time.time()
    elapsed_time = video_end_time - video_start_time
    print(f"\n저장 완료: {save_path} (소요 시간: {elapsed_time/60:.2f}분)")
```
