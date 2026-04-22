```bash
pip install qrcode[pil]
```



```python
import qrcode

def create_qr_code(url, filename):
    # 1. QR 코드 객체 생성 및 설정
    qr = qrcode.QRCode(
        version=1, # 1(21x21)부터 40까지, 숫자가 클수록 복잡한 데이터 저장 가능
        error_correction=qrcode.constants.ERROR_CORRECT_L, # 오류 복원 능력 (L, M, Q, H)
        box_size=10, # QR 코드의 각 박스 크기 (픽셀)
        border=4,    # 테두리 두께 (기본값 4)
    )

    # 2. 데이터(URL) 추가
    qr.add_data(url)
    qr.make(fit=True)

    # 3. 이미지 파일로 생성 (RGB 형식)
    img = qr.make_image(fill_color="black", back_color="white")

    # 4. 파일 저장
    img.save(filename)
    print(f"QR 코드가 '{filename}'으로 저장되었습니다.")

# 실행부
if __name__ == "__main__":
    target_url = input("QR로 만들 URL을 입력하세요: ")
    save_name = "my_qrcode.png"
    
    create_qr_code(target_url, save_name)
```
참고 : https://wikidocs.net/262365
