import os

# GitHub 설정
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = "kospi-feargreedindex"

# 파일 경로 설정
JSON_DIR = "./json"
DB_DIR = "./db"

# 데이터 관련 설정
Y_LIST = [
    'mcclenllan', 'p_c_ema', 'safe_spread', 
    'junk_spread', 'kospi', 'vix_close', 'stock_strength'
]

# 지수 계산 파라미터
INDEX_PARAMS = {
    # 정크본드 스프레드 계산 비율
    'junk_bond_aam_weight': 5/6,
    'junk_bond_bbbp_weight': 1/6,
    
    # 시장 너비 지표 계산 윈도우
    'breadth_short_window': 19,
    'breadth_long_window': 39,
    
    # PCR EMA 계산 윈도우
    'pcr_ema_window': 5,
    
    # VIX 지표 계산 윈도우
    'vix_ema_window': 50,
    
    # KOSPI 지표 계산 윈도우
    'kospi_ema_window': 125,
    'kospi_return_shift': 20,
    
    # 채권 EMA 계산 윈도우
    'bond_ema_window': 20,
    
    # 주가 강도(Stock Price Strength) 계산 기간 (단위: 거래일)
    'stock_strength_days': 20,
    
    # 스케일링 윈도우
    'scaling_window': 240,
    
    # 지수 가중치 fallback 값. 기본 산출은 factor 수에 따라 100 / factor_count를 사용합니다.
    'index_weight': 14.28,
    
    # 지수 평활화 윈도우
    'index_smoothing_window': 3
}

# API 관련 설정
KRX_URL = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
NICE_RATING_URL = "https://www.nicerating.com/disclosure/spreadRates.do"
INVESTING_URL = "https://kr.investing.com/rates-bonds/south-korea-10-year-bond-yield-historical-data"

# 헤더 설정
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
    "Content-Type": "application/x-www-form-urlencoded"
} 
