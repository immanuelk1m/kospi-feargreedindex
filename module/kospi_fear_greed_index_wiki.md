# KOSPI 공포-탐욕 지수(KOSPI Fear & Greed Index) 산출 방식

## 개요
KOSPI 공포-탐욕 지수는 한국 주식 시장의 투자자 심리를 수치화한 지표입니다. 이 지수는 다양한 시장 데이터를 분석하여 투자자들의 공포(Fear)와 탐욕(Greed) 정도를 0에서 100 사이의 값으로 표현합니다. 이 문서에서는 지수의 산출 방식과 관련된 모든 프로세스를 자세히 설명합니다.

## 지수 산출에 사용되는 데이터 소스

KOSPI 공포-탐욕 지수는 다음과 같은 다양한 데이터 소스를 활용합니다:

1. **VIX(변동성 지수)**: 시장의 불확실성과 변동성을 측정
2. **KOSPI**: 한국 종합주가지수 데이터
3. **채권 데이터**: 10년물 국채 수익률 및 정크본드 스프레드
4. **시장 너비(Market Breadth)**: 상승/하락 종목 비율
5. **PCR(Put-Call Ratio)**: 풋옵션 거래량 대비 콜옵션 거래량 비율
6. **주가 강도(Stock Strength)**: 개별 주식의 강도 지표

## 지수 계산 프로세스

### 1. 기초 데이터 준비

모든 데이터는 일별로 수집되며, 데이터베이스에 저장됩니다. 데이터 처리 전에 다음과 같은 기본 처리가 수행됩니다:

- 비숫자 값을 숫자로 변환 (errors='coerce')
- NaN 값을 보간법(linear interpolation)으로 처리
- 데이터의 타입 일관성 유지

### 2. 파생 지표 계산

#### 2.1 VIX 관련 지표
```python
vix_ema = vix_close.rolling(window=vix_ema_window, min_periods=1).mean()
vix_ema_spread = vix_close - vix_ema
```

- `vix_ema_window`: VIX 지표 계산에 사용되는 지수이동평균(EMA) 기간 (기본값: 50)

#### 2.2 KOSPI 관련 지표
```python
ema = 종가.rolling(window=kospi_ema_window).mean()
ema_spread = 종가 - ema
bf_20 = 종가.shift(kospi_return_shift)
return_20 = (종가 / bf_20 - 1) * 100
```

- `kospi_ema_window`: KOSPI 지표 계산에 사용되는 EMA 기간 (기본값: 125)
- `kospi_return_shift`: KOSPI 수익률 계산 시프트 기간 (기본값: 20)

#### 2.3 정크본드 스프레드 계산
```python
junk_spread = aam.mul(junk_bond_aam_weight) + bbbp.mul(junk_bond_bbbp_weight)
```

- `junk_bond_aam_weight`: AAM 채권 가중치 (기본값: 0.8333)
- `junk_bond_bbbp_weight`: BBBP 채권 가중치 (기본값: 0.1667)

#### 2.4 채권 EMA 계산
```python
bond_ema = ten_ratio.rolling(window=bond_ema_window).mean()
```

- `bond_ema_window`: 채권 EMA 계산 윈도우 (기본값: 20)

#### 2.5 시장 너비(Market Breadth) 계산
```python
short = diff.rolling(window=breadth_short_window, min_periods=1).mean()
long = diff.rolling(window=breadth_long_window, min_periods=1).mean()
mcclenllan = short - long
```

- `breadth_short_window`: 시장 너비 지표 단기 계산 윈도우 (기본값: 19)
- `breadth_long_window`: 시장 너비 지표 장기 계산 윈도우 (기본값: 39)

### 3. 지표 스케일링

각 지표는 과거 데이터를 기반으로 0~1 사이의 값으로 스케일링됩니다:

```python
for column in columns:
    rolling_min = column.rolling(window=scaling_window).min()
    rolling_max = column.rolling(window=scaling_window).max()
    column_scaled = (column - rolling_min) / (rolling_max - rolling_min)
```

- `scaling_window`: 지표 스케일링에 사용되는 과거 데이터 기간 (기본값: 240)

#### 특수 케이스 처리

스케일링 과정에서 발생할 수 있는 문제를 처리하기 위한 로직:

1. **분모가 0인 경우**: 
```python
if (denominator == 0).any():
    # 분모가 0인 위치는 기본값 0.5 사용
    column_scaled = 0.5
```

2. **NaN 값 처리**:
```python
if column_scaled.isna().any():
    # NaN 값을 0.5로 대체
    column_scaled = column_scaled.fillna(0.5)
```

### 4. 최종 지수 계산

스케일링된 각 지표에 가중치를 적용하고 합산하여 최종 지수를 계산:

```python
index = scaled_columns.multiply(index_weight).sum(axis=1)
index = index.rolling(window=index_smoothing_window).mean()
```

- `index_weight`: 각 지표의 가중치 (기본값: 16.66)
- `index_smoothing_window`: 최종 지수 평활화 윈도우 (기본값: 3)

## 파라미터 최적화

지수의 정확도를 향상시키기 위해 다음 파라미터들을 최적화할 수 있습니다:

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

## 지수 해석

KOSPI 공포-탐욕 지수는 0에서 100 사이의 값으로 표현됩니다:

- **0~25**: 극도의 공포 (Extreme Fear)
- **26~45**: 공포 (Fear)
- **46~55**: 중립 (Neutral)
- **56~75**: 탐욕 (Greed)
- **76~100**: 극도의 탐욕 (Extreme Greed)

투자자들은 이 지수를 시장 심리의 반대 지표로 활용할 수 있습니다. 즉, 극도의 공포 구간은 매수 기회를, 극도의 탐욕 구간은 매도 기회를 나타낼 수 있습니다.

## 지수 갱신 프로세스

1. 최신 데이터 수집
2. 파생 지표 계산
3. 지표 스케일링
4. 최종 지수 계산
5. 데이터베이스에 결과 저장
6. 시각화 및 웹 대시보드 업데이트

## 결론

KOSPI 공포-탐욕 지수는 다양한 시장 지표를 종합하여 투자자 심리를 수치화함으로써, 투자자들에게 시장의 과열 또는 침체 상태에 대한 통찰력을 제공합니다. 지수 산출에 사용되는 파라미터는 최적화를 통해 더 정확한 시장 상황 반영이 가능합니다. 