import argparse # argparse의 ArgumentTypeError를 사용하여 잘못된 입력 시 사용자에게 정확한 오류 메시지를 전달하기 위해 사용합니다.

def argparse_type_bool(v: str) -> bool:
    """
    명령행 인자(CLI)로 들어온 문자열 값을 실제 Boolean 타입(True/False)으로 변환하는 함수입니다.
    단순히 bool()을 사용할 경우 비어있지 않은 모든 문자열이 True가 되는 문제를 방지합니다.
    """
    # 이미 값이 Boolean 타입인 경우(기본값 등)는 그대로 반환하여 불필요한 변환 과정을 생략합니다.
    if isinstance(v, bool):
        return v
    
    # 사용자가 입력할 수 있는 다양한 '긍정' 표현들을 정의합니다.
    # .lower()를 사용하여 대소문자 구분 없이(TRUE, True, true 모두 가능) 처리합니다.
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    
    # 사용자가 입력할 수 있는 다양한 '부정' 표현들을 정의합니다.
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    
    # 위 정의된 긍정/부정 리스트에 포함되지 않은 모호한 문자열이 들어온 경우,
    # argparse가 인식할 수 있는 전용 에러를 발생시켜 사용자에게 잘못된 입력임을 알립니다.
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')