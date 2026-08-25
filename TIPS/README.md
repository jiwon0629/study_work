# Lenovo Server에서 NOX 모델 사용
## using docker images : hub.inbic.duckdns.org/dev-1-team/ai-video-converter:0.1

Lenovo Server에서 sample 영상 테스트나 NOX 모델 성능 테스트를 해보기 위해 input_video를 넣고 out_video로 저장시켜주는 코드

### 코드 실행
```
python main.py
# --result_dir : default="./outputs"
# --input_dir : default="./inputs" 
#--nox_path : "./models/NOX.pth"
# --concatenate true 하면 원본 이미지 옆 nox 이미지로 나옴
```

