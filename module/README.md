# KOSPI Fear & Greed Index

KOSPI 공포/탐욕 지수 프로젝트

## 설치 방법

```bash
git clone https://github.com/yourusername/kospi-fear-greed.git
cd kospi-fear-greed
pip install -r requirements.txt
```

## 사용 방법

### 기본 실행

다음 명령어로 기본 설정값을 사용하여 데이터를 스크래핑하고 지수를 계산합니다:

```bash
python main.py
```

### 파라미터 조절 기능

지수 계산에 사용되는 파라미터를 조절하기 위한 여러 옵션이 있습니다:

#### 현재 파라미터 저장

현재 사용 중인 파라미터를 파일로 저장할 수 있습니다:

```bash
python main.py --save-params params/my_params.json
```

#### 사용자 정의 파라미터 사용

사용자 정의 파라미터 파일을 사용하여 지수를 계산할 수 있습니다:

```bash
python main.py --params params/my_params.json
```

#### 스크래핑 단계 건너뛰기

데이터 스크래핑 단계를 건너뛰고 기존 데이터를 사용하여 지수를 계산할 수 있습니다:

```bash
python main.py --skip-scrape
```

여러 옵션을 함께 사용할 수도 있습니다:

```bash
python main.py --params params/test_params.json --save-params params/used_params.json --skip-scrape
```

### 파라미터 파일 형식

파라미터 파일은 다음과 같은 JSON 형식을 가집니다:

```json
{
    "junk_bond_aam_weight": 0.8333,
    "junk_bond_bbbp_weight": 0.1667,
    "breadth_short_window": 19,
    "breadth_long_window": 39,
    "pcr_ema_window": 5,
    "vix_ema_window": 50,
    "kospi_ema_window": 125,
    "kospi_return_shift": 20,
    "bond_ema_window": 20,
    "scaling_window": 240,
    "index_weight": 16.66,
    "index_smoothing_window": 3
}
```

모든 파라미터를 포함할 필요는 없으며, 변경하고 싶은 파라미터만 포함시키면 됩니다. 나머지 파라미터는 기본값을 사용합니다.

### 주요 파라미터 설명

- `junk_bond_aam_weight`, `junk_bond_bbbp_weight`: 정크본드 스프레드 계산 비율
- `breadth_short_window`, `breadth_long_window`: 시장 너비 지표 계산 윈도우
- `pcr_ema_window`: PCR EMA 계산 윈도우
- `vix_ema_window`: VIX 지표 계산 윈도우
- `kospi_ema_window`: KOSPI 지표 계산 윈도우
- `kospi_return_shift`: KOSPI 수익률 계산 시프트 기간
- `bond_ema_window`: 채권 EMA 계산 윈도우
- `scaling_window`: 지표 스케일링 윈도우
- `index_weight`: 지수 가중치 (각 지표별 비중)
- `index_smoothing_window`: 지수 평활화 윈도우 