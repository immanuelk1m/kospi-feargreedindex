from datetime import datetime, timedelta

def date_range_f(start, end):
    """
    주어진 시작일과 종료일 사이의 날짜 리스트를 반환합니다.
    """
    start = datetime.strptime(start, "%Y-%m-%d")
    end = datetime.strptime(end, "%Y-%m-%d")
    dates = [(start + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((end - start).days + 1)]
    return dates

def pre_val(score):
    """
    점수에 따른 등급을 반환합니다.
    """
    if score >= 80:
        em = "5"
    elif score >= 60:
        em = "4"
    elif score >= 40:
        em = "3"
    elif score >= 20:
        em = "2"
    else:
        em = "1"
    
    return em 