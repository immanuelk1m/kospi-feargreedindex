import sqlite3
import pandas as pd
import numpy as np
from scipy.optimize import minimize
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import logging # 로깅 라이브러리 추가
import matplotlib.font_manager as fm # 한글 폰트 설정용

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 한글 폰트 설정 ---
try:
    # Windows 기준 나눔고딕 경로, 다른 OS나 폰트는 경로 수정 필요
    font_path = "c:/Windows/Fonts/NanumGothic.ttf" 
    # 또는 특정 경로에 있는 폰트 파일 직접 지정: "C:/Users/YourUser/AppData/Local/Microsoft/Windows/Fonts/NanumGothic.ttf"
    # font_path = 'NanumGothic.ttf' # 스크립트와 같은 폴더에 폰트 파일이 있는 경우
    if not fm.findfont(fm.FontProperties(fname=font_path)):
        logging.warning(f"지정된 경로에 폰트 파일이 없습니다: {font_path}. 시스템 기본 폰트를 사용합니다.")
        # 대체 폰트나 기본 설정 유지
        plt.rcParams['font.family'] = 'sans-serif' # 또는 'Malgun Gothic' 등 시스템에 있을 법한 폰트
    else:
        font_name = fm.FontProperties(fname=font_path).get_name()
        plt.rc('font', family=font_name)
        logging.info(f"한글 폰트 '{font_name}' 설정 완료.")
    plt.rcParams['axes.unicode_minus'] = False # 마이너스 부호 깨짐 방지
except Exception as e:
    logging.warning(f"한글 폰트 설정 중 오류 발생: {e}. 기본 폰트 사용.")


# 데이터베이스 경로
DB_PATH_KGF = 'kgf_data.db'

def load_and_merge_data(db_path):
    """여러 테이블에서 데이터를 로드하고 KOSPI 날짜 기준으로 병합합니다."""
    logging.info("데이터 로드 및 병합 시작...")
    conn = sqlite3.connect(db_path)
    try:
        # KOSPI 데이터 로드 (기준)
        kospi_df = pd.read_sql_query("SELECT date, 종가 AS kospi_close, ema_spread, return_20 FROM kospi", conn)
        kospi_df['date'] = pd.to_datetime(kospi_df['date'])
        kospi_df = kospi_df.set_index('date').sort_index()
        logging.info(f"KOSPI 데이터 로드 완료. Shape: {kospi_df.shape}")
        kospi_df = kospi_df.dropna(subset=['kospi_close']) # KOSPI 종가 없는 날 제거
        logging.info(f"KOSPI 데이터 (종가 NaN 제거 후). Shape: {kospi_df.shape}")


        # VIX 데이터 로드
        vix_df = pd.read_sql_query("SELECT date, vix_close FROM vix", conn)
        vix_df['date'] = pd.to_datetime(vix_df['date'])
        vix_df = vix_df.set_index('date').sort_index()
        logging.info(f"VIX 데이터 로드 완료. Shape: {vix_df.shape}")

        # 10년 국채 데이터 로드
        ten_bond_df = pd.read_sql_query("SELECT date, ten_ratio FROM ten_bond", conn)
        ten_bond_df['date'] = pd.to_datetime(ten_bond_df['date'])
        ten_bond_df = ten_bond_df.set_index('date').sort_index()
        logging.info(f"10년 국채 데이터 로드 완료. Shape: {ten_bond_df.shape}")

        # 정크본드 스프레드 데이터 로드
        junk_bond_df = pd.read_sql_query("SELECT date, junk_spread FROM junk_bond", conn)
        junk_bond_df['date'] = pd.to_datetime(junk_bond_df['date'])
        junk_bond_df = junk_bond_df.set_index('date').sort_index()
        logging.info(f"정크본드 데이터 로드 완료. Shape: {junk_bond_df.shape}")

        # PCR 데이터 로드
        pcr_df = pd.read_sql_query("SELECT date, p_c_ratio FROM pcr", conn)
        pcr_df['date'] = pd.to_datetime(pcr_df['date'])
        pcr_df['p_c_ratio'] = pd.to_numeric(pcr_df['p_c_ratio'], errors='coerce')
        pcr_df = pcr_df.set_index('date').sort_index()
        logging.info(f"PCR 데이터 로드 완료. Shape: {pcr_df.shape}")

        # 시장 폭 (Breadth) 데이터 로드
        breadth_df = pd.read_sql_query("SELECT date, mcclenllan, summation_index FROM breadth", conn)
        breadth_df['date'] = pd.to_datetime(breadth_df['date'])
        breadth_df = breadth_df.set_index('date').sort_index()
        logging.info(f"시장 폭 데이터 로드 완료. Shape: {breadth_df.shape}")
        
        # 주식 강도 데이터 로드
        stock_strength_df = pd.read_sql_query("SELECT date, strength_index, strength_ratio FROM stock_strength", conn)
        stock_strength_df['date'] = pd.to_datetime(stock_strength_df['date'])
        stock_strength_df = stock_strength_df.set_index('date').sort_index()
        logging.info(f"주식 강도 데이터 로드 완료. Shape: {stock_strength_df.shape}")

        # 데이터 병합 (KOSPI 기준 left join 후 ffill)
        merged_df = kospi_df
        data_frames_to_merge = {
            'vix': vix_df,
            'ten_bond': ten_bond_df,
            'junk_bond': junk_bond_df,
            'pcr': pcr_df,
            'breadth': breadth_df,
            'stock_strength': stock_strength_df
        }

        for name, df_to_merge in data_frames_to_merge.items():
            logging.info(f"'{name}' 데이터 병합 중...")
            df_to_merge = df_to_merge.add_prefix(name + '_')
            merged_df = merged_df.join(df_to_merge, how='left')
            logging.info(f"병합 후 merged_df Shape: {merged_df.shape}")
        
        logging.info(f"모든 데이터 병합 후 merged_df.head():\n{merged_df.head()}")
        logging.info(f"병합 후 NaN 현황:\n{merged_df.isnull().sum()}")

        # KOSPI 거래일 기준으로 데이터가 없는 경우 이전 값으로 채우기
        merged_df = merged_df.ffill()
        logging.info(f"ffill 후 merged_df.head():\n{merged_df.head()}")
        logging.info(f"ffill 후 NaN 현황:\n{merged_df.isnull().sum()}")
        
        initial_rows = len(merged_df)
        # 사용할 모든 컬럼에 대해 dropna(how='any')를 적용하여 데이터 시작점을 일치시킴
        # 이 컬럼들은 preprocess_features에서 사용될 컬럼들임
        required_raw_cols = [
            'kospi_close', 'ema_spread', 'return_20', # kospi
            'vix_vix_close', # vix
            'ten_bond_ten_ratio', # ten_bond
            'junk_bond_junk_spread', # junk_bond
            'pcr_p_c_ratio', # pcr
            'breadth_mcclenllan', # breadth
            'stock_strength_strength_index' # stock_strength
        ]
        # merged_df에 없는 컬럼은 제외 (오류 방지)
        valid_required_raw_cols = [col for col in required_raw_cols if col in merged_df.columns]
        
        merged_df = merged_df.dropna(subset=valid_required_raw_cols, how='any')
        logging.info(f"최종 병합 및 모든 필수 원본 컬럼 NaN 처리 후 merged_df Shape: {merged_df.shape}. (제거된 행: {initial_rows - len(merged_df)})")
        logging.info("데이터 로드 및 병합 완료.")
        return merged_df

    except sqlite3.Error as e:
        logging.error(f"데이터베이스 오류: {e}")
        return None
    finally:
        if conn:
            conn.close()

def preprocess_features(df):
    """근간 지표를 선택하고 F&G 지수에 맞게 전처리 (스케일링 및 방향성 통일)"""
    logging.info("지표 전처리 시작...")
    features = pd.DataFrame(index=df.index)
    scaler = MinMaxScaler() # 0~1 스케일링

    # 1. VIX (높을수록 공포 -> 낮을수록 탐욕으로 변환)
    col_name = 'vix_vix_close'
    if col_name in df.columns and not df[col_name].isnull().all():
        max_val = df[col_name].max()
        min_val = df[col_name].min()
        if max_val > min_val:
            features['vix_greed'] = (max_val - df[col_name]) / (max_val - min_val)
            logging.debug(f"'{col_name}' 처리: Max={max_val:.2f}, Min={min_val:.2f}")
        else:
            features['vix_greed'] = 0.5 
        logging.info(f"Feature 'vix_greed' 생성 완료. NaN 개수: {features['vix_greed'].isnull().sum()}")
    else:
        logging.warning(f"컬럼 '{col_name}'이 없거나 모든 값이 NaN입니다. 'vix_greed'는 생성되지 않습니다.")


    # 2. Put/Call Ratio (높을수록 공포 -> 낮을수록 탐욕으로 변환)
    col_name = 'pcr_p_c_ratio'
    if col_name in df.columns and not df[col_name].isnull().all():
        max_val = df[col_name].max()
        min_val = df[col_name].min()
        if max_val > min_val:
            features['pcr_greed'] = (max_val - df[col_name]) / (max_val - min_val)
            logging.debug(f"'{col_name}' 처리: Max={max_val:.2f}, Min={min_val:.2f}")
        else:
            features['pcr_greed'] = 0.5
        logging.info(f"Feature 'pcr_greed' 생성 완료. NaN 개수: {features['pcr_greed'].isnull().sum()}")
    else:
        logging.warning(f"컬럼 '{col_name}'이 없거나 모든 값이 NaN입니다. 'pcr_greed'는 생성되지 않습니다.")

    # 3. Junk Bond Spread (높을수록 공포 -> 낮을수록 탐욕으로 변환)
    col_name = 'junk_bond_junk_spread'
    if col_name in df.columns and not df[col_name].isnull().all():
        max_val = df[col_name].max()
        min_val = df[col_name].min()
        if max_val > min_val:
            features['junk_spread_greed'] = (max_val - df[col_name]) / (max_val - min_val)
            logging.debug(f"'{col_name}' 처리: Max={max_val:.2f}, Min={min_val:.2f}")
        else:
            features['junk_spread_greed'] = 0.5
        logging.info(f"Feature 'junk_spread_greed' 생성 완료. NaN 개수: {features['junk_spread_greed'].isnull().sum()}")
    else:
        logging.warning(f"컬럼 '{col_name}'이 없거나 모든 값이 NaN입니다. 'junk_spread_greed'는 생성되지 않습니다.")
            
    # 4. KOSPI Momentum (ema_spread 사용, 양수면 탐욕)
    col_name = 'ema_spread'
    if col_name in df.columns and not df[col_name].isnull().all():
        features['kospi_momentum_greed'] = scaler.fit_transform(df[[col_name]])
        logging.info(f"Feature 'kospi_momentum_greed' 생성 완료. NaN 개수: {features['kospi_momentum_greed'].isnull().sum()}")
    else:
        logging.warning(f"컬럼 '{col_name}'이 없거나 모든 값이 NaN입니다. 'kospi_momentum_greed'는 생성되지 않습니다.")

    # 5. McClellan Oscillator (양수일수록 탐욕)
    col_name = 'breadth_mcclenllan'
    if col_name in df.columns and not df[col_name].isnull().all():
        features['mcclellan_greed'] = scaler.fit_transform(df[[col_name]])
        logging.info(f"Feature 'mcclellan_greed' 생성 완료. NaN 개수: {features['mcclellan_greed'].isnull().sum()}")
    else:
        logging.warning(f"컬럼 '{col_name}'이 없거나 모든 값이 NaN입니다. 'mcclellan_greed'는 생성되지 않습니다.")
        
    # 6. Stock Strength Index (높을수록 탐욕)
    col_name = 'stock_strength_strength_index'
    if col_name in df.columns and not df[col_name].isnull().all():
        features['stock_strength_greed'] = scaler.fit_transform(df[[col_name]])
        logging.info(f"Feature 'stock_strength_greed' 생성 완료. NaN 개수: {features['stock_strength_greed'].isnull().sum()}")
    else:
        logging.warning(f"컬럼 '{col_name}'이 없거나 모든 값이 NaN입니다. 'stock_strength_greed'는 생성되지 않습니다.")

    # 7. Safe Haven Demand (10-year bond yield, 낮을수록 안전자산 선호/공포 -> 높을수록 위험자산 선호/탐욕으로 변환)
    col_name = 'ten_bond_ten_ratio'
    if col_name in df.columns and not df[col_name].isnull().all():
        max_val = df[col_name].max()
        min_val = df[col_name].min()
        if max_val > min_val:
            features['bond_yield_risk_on'] = (max_val - df[col_name]) / (max_val - min_val)
            logging.debug(f"'{col_name}' 처리 (risk-on): Max={max_val:.2f}, Min={min_val:.2f}")
        else:
            features['bond_yield_risk_on'] = 0.5
        logging.info(f"Feature 'bond_yield_risk_on' 생성 완료. NaN 개수: {features['bond_yield_risk_on'].isnull().sum()}")
    else:
        logging.warning(f"컬럼 '{col_name}'이 없거나 모든 값이 NaN입니다. 'bond_yield_risk_on'는 생성되지 않습니다.")

    initial_feature_rows = len(features)
    # 생성된 feature 컬럼들에 대해서만 dropna
    # 만약 특정 feature가 생성되지 않았다면, 해당 컬럼은 features DataFrame에 없으므로 dropna에 영향 없음
    features = features.dropna(how='any') 
    logging.info(f"전처리 후 NaN 제거된 feature Shape: {features.shape}. (제거된 행: {initial_feature_rows - len(features)})")
    logging.info("지표 전처리 완료.")
    return features

def calculate_future_returns(df, column_name='kospi_close', periods=20):
    logging.info(f"미래 수익률 계산 시작 (기준 컬럼: {column_name}, 기간: {periods}일)...")
    df[f'future_{periods}d_return'] = df[column_name].pct_change(periods=periods).shift(-periods)
    logging.info(f"미래 수익률 계산 완료. 컬럼 'future_{periods}d_return' 추가됨.")
    return df

def calculate_fg_index(data, weights, component_cols):
    logging.debug(f"calculate_fg_index 호출됨. Data shape: {data.shape}, Num weights: {len(weights)}, Num components: {len(component_cols)}")
    logging.debug(f"  Input weights: {weights}")
    logging.debug(f"  Component_cols: {component_cols}")


    if len(weights) != len(component_cols):
        logging.error("가중치와 컴포넌트 컬럼의 수가 일치하지 않습니다!")
        raise ValueError("가중치와 컴포넌트 컬럼의 수가 일치해야 합니다.")

    active_components = [col for col in component_cols if col in data.columns]
    if not active_components:
        logging.warning("F&G 계산에 사용할 수 있는 활성 컴포넌트가 없습니다. 기본값 50 반환.")
        return pd.Series(np.full(len(data), 50), index=data.index, name="fg_index_default")

    logging.debug(f"  Active components: {active_components}")

    active_weights_indices = [component_cols.index(col) for col in active_components]
    active_weights = np.array(weights)[active_weights_indices]

    logging.debug(f"  Active_weights_indices: {active_weights_indices}")
    logging.debug(f"  Active_weights: {active_weights}")

    sum_weights = np.sum(np.abs(active_weights))
    if sum_weights == 0:
        logging.warning("활성 가중치의 합이 0입니다. 기본값 50 반환.")
        return pd.Series(np.full(len(data), 50), index=data.index, name="fg_index_sum_zero")

    normalized_weights = active_weights / sum_weights
    logging.debug(f"  Normalized_weights: {normalized_weights}")

    weighted_sum_array = np.zeros(len(data))
    for i, col in enumerate(active_components):
        weighted_sum_array += data[col].values * normalized_weights[i]

    logging.debug(f"  Weighted_sum_array (first 5): {weighted_sum_array[:5]}")

    min_val = weighted_sum_array.min()
    max_val = weighted_sum_array.max()
    logging.debug(f"  Weighted_sum_array Min: {min_val:.4f}, Max: {max_val:.4f}")

    if max_val == min_val:
        logging.warning("Weighted_sum_array의 모든 값이 동일합니다. 스케일링된 F&G는 50으로 설정됩니다.")
        scaled_fg_values = np.full(len(weighted_sum_array), 50)
    else:
        scaled_fg_values = 100 * (weighted_sum_array - min_val) / (max_val - min_val)

    scaled_fg_series = pd.Series(scaled_fg_values, index=data.index, name="calculated_fg")
    logging.debug(f"  Scaled_fg_series (first 5): {scaled_fg_series.head().values}")
    logging.debug(f"calculate_fg_index 계산 완료. 반환 Series shape: {scaled_fg_series.shape}")
    return scaled_fg_series

# 최적화 호출 카운터
optimization_call_count = 0

def objective_function_threshold(weights, data_features, data_target_return, component_cols, fear_threshold=25, greed_threshold=75):
    # 목표 함수 변경: 고정 임계값 사용
    global optimization_call_count
    optimization_call_count += 1
    logging.info(f"\n--- Objective Function (Threshold) Call #{optimization_call_count} ---")
    logging.info(f"  Current weights: {[f'{w:.4f}' for w in weights]}")

    temp_data = data_features.copy()
    fg_index_series = calculate_fg_index(temp_data, weights, component_cols)
    temp_data['fg_index'] = fg_index_series

    logging.debug(f"  Objective: fg_index 계산됨. Min: {temp_data['fg_index'].min():.2f}, Max: {temp_data['fg_index'].max():.2f}, Mean: {temp_data['fg_index'].mean():.2f}")

    if isinstance(data_target_return, pd.Series):
        data_target_return_df = data_target_return.to_frame(name='target_return')
    else:
        data_target_return_df = data_target_return[['target_return']]

    combined_data = temp_data[['fg_index']].join(data_target_return_df, how='inner')
    combined_data_cleaned = combined_data.dropna()
    logging.debug(f"  Objective: Combined data for threshold. Shape: {combined_data_cleaned.shape}")

    if len(combined_data_cleaned) < 20:
        logging.warning(f"  Objective: 데이터 부족 ({len(combined_data_cleaned)}개). 패널티 1e9 반환.")
        return 1e9

    fear_returns = combined_data_cleaned[combined_data_cleaned['fg_index'] < fear_threshold]['target_return']
    greed_returns = combined_data_cleaned[combined_data_cleaned['fg_index'] > greed_threshold]['target_return']

    logging.debug(f"  Objective: Fear (F&G < {fear_threshold}) returns (N={len(fear_returns)}), Greed (F&G > {greed_threshold}) returns (N={len(greed_returns)})")

    if len(fear_returns) == 0 or len(greed_returns) == 0:
        # 두 구간 중 하나라도 데이터가 없으면, 차이를 극대화하기 어렵거나 의미가 없을 수 있음
        # 패널티를 주거나, 0을 반환하거나, 한 쪽만 있는 경우 그 값의 반대를 취하는 등 전략 필요
        # 여기서는 패널티를 부여
        logging.warning(f"  Objective: Fear 또는 Greed 구간 데이터 부족 (Fear: {len(fear_returns)}, Greed: {len(greed_returns)}). 패널티 1e9 반환.")
        return 1e9 # 이전과 동일하게 패널티

    mean_fear_return = fear_returns.mean()
    mean_greed_return = greed_returns.mean()
    logging.info(f"  Objective: Mean Fear Return: {mean_fear_return:.4f}, Mean Greed Return: {mean_greed_return:.4f}")

    difference = mean_fear_return - mean_greed_return
    logging.info(f"  Objective: Difference (Fear - Greed): {difference:.4f}")
    logging.info(f"  Objective: Returning {-difference:.4f} for minimization.")
    return -difference


# --- 메인 실행 로직 ---
if __name__ == "__main__":
    # 1. 데이터 로드 및 병합
    raw_merged_df = load_and_merge_data(DB_PATH_KGF)

    if raw_merged_df is None or raw_merged_df.empty:
        logging.critical("데이터 로드 및 병합 실패. 프로그램을 종료합니다.")
        exit()

    logging.info(f"초기 로드된 데이터 ('raw_merged_df'):\n{raw_merged_df.head()}")
    logging.info(f"raw_merged_df Shape: {raw_merged_df.shape}")
    
    # 2. KOSPI 미래 수익률 계산
    future_return_period = 20
    df_with_returns = calculate_future_returns(raw_merged_df.copy(), 'kospi_close', periods=future_return_period)
    target_return_col_name = f'future_{future_return_period}d_return'
    logging.info(f"미래 수익률 계산 후 df_with_returns.head():\n{df_with_returns.head()}")

    # 3. F&G 지수 후보 지표 전처리
    processed_features_df = preprocess_features(df_with_returns.copy()) 

    if processed_features_df.empty or len(processed_features_df.columns) == 0:
        logging.critical("지표 전처리 후 유효한 feature가 없습니다. 프로그램을 종료합니다.")
        exit()
        
    logging.info(f"\n전처리된 F&G 후보 지표 ('processed_features_df'):\n{processed_features_df.head()}")
    logging.info(f"processed_features_df Shape: {processed_features_df.shape}")
    
    component_columns_final = list(processed_features_df.columns)
    if not component_columns_final:
        logging.critical("최종 F&G 지수 구성 후보가 없습니다. 프로그램을 종료합니다.")
        exit()
    logging.info(f"\n최종 F&G 지수 구성 후보: {component_columns_final}")

    common_index = processed_features_df.index.intersection(df_with_returns.index)
    logging.info(f"Common index for optimization. Length: {len(common_index)}")
    
    optimization_features = processed_features_df.loc[common_index]
    optimization_target_return = df_with_returns.loc[common_index, target_return_col_name].rename('target_return')
    
    valid_indices = optimization_target_return.dropna().index
    optimization_features = optimization_features.loc[valid_indices]
    optimization_target_return = optimization_target_return.loc[valid_indices]

    if optimization_features.empty or optimization_target_return.empty:
        logging.critical("최적화를 위한 데이터가 충분하지 않습니다 (feature 또는 target return).")
        exit()

    logging.info(f"\n최적화에 사용될 feature 데이터 ('optimization_features'):\n{optimization_features.head()}")
    logging.info(f"optimization_features Shape: {optimization_features.shape}")
    logging.info(f"최적화에 사용될 target return 데이터 ('optimization_target_return'):\n{optimization_target_return.head()}")
    logging.info(f"optimization_target_return Shape: {optimization_target_return.shape}")


    # 4. 가중치 최적화
    num_components = len(component_columns_final)
    initial_weights = np.array([1.0 / num_components] * num_components)
    bounds = [(0, 1)] * num_components 

    logging.info("\n가중치 최적화를 시작합니다...")
    logging.info(f"  초기 가중치: {[f'{w:.4f}' for w in initial_weights]}")
    logging.info(f"  가중치 경계: {bounds}")
    logging.info(f"  사용될 컴포넌트: {component_columns_final}")
    logging.info(f"  최적화 방법: SLSQP, 목표함수: Threshold-based (Fear < 25, Greed > 75)")


    optimization_result = minimize(
        objective_function_threshold, # 변경된 목표 함수 사용
        initial_weights,
        args=(optimization_features, optimization_target_return, component_columns_final), # quantile_threshold 제거
        method='SLSQP', 
        bounds=bounds,
        options={'disp': True, 'maxiter': 200, 'ftol': 1e-8, 'eps': 1e-9} # eps 값 변경, maxiter 증가
    )

    if optimization_result.success:
        optimal_weights = optimization_result.x
        sum_abs_weights = np.sum(np.abs(optimal_weights))
        normalized_optimal_weights = optimal_weights / sum_abs_weights if sum_abs_weights > 0 else optimal_weights

        logging.info("\n최적화 성공!")
        logging.info("최적 가중치 (정규화됨):")
        for i, col in enumerate(component_columns_final):
            logging.info(f"  {col}: {normalized_optimal_weights[i]:.4f}")
        logging.info(f"최적화된 목표 함수 값 (최대화된 차이의 음수): {optimization_result.fun:.4f}")
        logging.info(f"최적화 반복 횟수: {optimization_result.nit}")
        logging.info(f"함수 호출 횟수: {optimization_result.nfev}")


        # 5. 최적화된 F&G 지수 계산 (전체 기간에 대해)
        logging.info("\n최적 가중치를 사용하여 전체 기간에 대한 F&G 지수 계산 중...")
        calculated_fg_series = calculate_fg_index(processed_features_df, optimal_weights, component_columns_final)
        # calculated_fg_series.name = 'optimal_fg_index' # calculate_fg_index 내부에서 이름 부여됨
        logging.info(f"계산된 F&G Series (calculated_fg_series):\n{calculated_fg_series.head()}")
        logging.info(f"calculated_fg_series Shape: {calculated_fg_series.shape}")


        df_final_analysis = df_with_returns.join(calculated_fg_series.rename('optimal_fg_index'), how='left') # join 시 이름 명시
        logging.info(f"F&G 지수 병합 후 df_final_analysis.head():\n{df_final_analysis.head()}")
        logging.info(f"df_final_analysis Shape: {df_final_analysis.shape}")
        logging.info(f"df_final_analysis NaN 현황 (optimal_fg_index): {df_final_analysis['optimal_fg_index'].isnull().sum()}")
        
        df_final_analysis_plot = df_final_analysis.dropna(subset=['optimal_fg_index', 'kospi_close'])
        logging.info(f"시각화를 위한 최종 데이터 ('df_final_analysis_plot') Shape: {df_final_analysis_plot.shape}")

        if df_final_analysis_plot.empty:
            logging.critical("시각화할 데이터가 없습니다.")
            exit()

        # 6. 결과 시각화
        logging.info("결과 시각화 시작...")
        fig, ax1 = plt.subplots(figsize=(15, 8))
        # plt.style.use('seaborn-v0_8-darkgrid') # 스타일은 그대로 사용

        color = 'tab:blue'
        ax1.set_xlabel('날짜') # 한글 레이블
        ax1.set_ylabel('KOSPI 종가', color=color) # 한글 레이블
        ax1.plot(df_final_analysis_plot.index, df_final_analysis_plot['kospi_close'], color=color, alpha=0.8, label='KOSPI 종가')
        ax1.tick_params(axis='y', labelcolor=color)
        
        ax2 = ax1.twinx()
        color = 'tab:red'
        ax2.set_ylabel('최적 KOSPI F&G 지수 (0-100)', color=color) # 한글 레이블
        ax2.plot(df_final_analysis_plot.index, df_final_analysis_plot['optimal_fg_index'], color=color, linewidth=1.5, label='최적 KOSPI F&G')
        ax2.tick_params(axis='y', labelcolor=color)
        
        # F&G 임계값으로 변경
        fear_display_threshold = 25
        greed_display_threshold = 75
        ax2.axhspan(0, fear_display_threshold, color='green', alpha=0.2, zorder=0)
        ax2.axhspan(greed_display_threshold, 100, color='red', alpha=0.2, zorder=0)

        lines, labels = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        from matplotlib.patches import Patch
        fear_patch = Patch(facecolor='green', alpha=0.2, label=f'극심한 공포 (F&G < {fear_display_threshold})') # 한글 레이블
        greed_patch = Patch(facecolor='red', alpha=0.2, label=f'극심한 탐욕 (F&G > {greed_display_threshold})') # 한글 레이블
        
        ax2.legend(lines + lines2 + [fear_patch, greed_patch], labels + labels2 + [f'극심한 공포 (F&G < {fear_display_threshold})', f'극심한 탐욕 (F&G > {greed_display_threshold})'], loc='lower center', bbox_to_anchor=(0.5, -0.30), ncol=2)

        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        fig.autofmt_xdate()
        plt.title('KOSPI 종가 vs. 최적 KOSPI 공포탐욕지수 (근간 데이터 기반)') # 한글 제목
        fig.tight_layout(rect=[0, 0.15, 1, 0.96])
        plt.show()
        logging.info("결과 시각화 완료.")


        # F&G 지수 구간별 미래 수익률 분석 (최적화 결과 검증)
        final_fg_analysis_data_for_stats = df_final_analysis_plot[[target_return_col_name, 'optimal_fg_index']].dropna()
        
        if not final_fg_analysis_data_for_stats.empty:
            # 고정 임계값 사용
            fear_returns_final = final_fg_analysis_data_for_stats[final_fg_analysis_data_for_stats['optimal_fg_index'] < fear_display_threshold][target_return_col_name]
            neutral_returns_final = final_fg_analysis_data_for_stats[
                (final_fg_analysis_data_for_stats['optimal_fg_index'] >= fear_display_threshold) & 
                (final_fg_analysis_data_for_stats['optimal_fg_index'] <= greed_display_threshold)
            ][target_return_col_name]
            greed_returns_final = final_fg_analysis_data_for_stats[final_fg_analysis_data_for_stats['optimal_fg_index'] > greed_display_threshold][target_return_col_name]

            logging.info("\n최적화된 F&G 지수 구간별 KOSPI 평균 미래 수익률 (고정 임계값 기준):")
            if not fear_returns_final.empty:
                 logging.info(f"  극심한 공포 (F&G < {fear_display_threshold}): {fear_returns_final.mean()*100:.2f}% (N={len(fear_returns_final)})")
            if not neutral_returns_final.empty:
                logging.info(f"  중립 ({fear_display_threshold} <= F&G <= {greed_display_threshold}): {neutral_returns_final.mean()*100:.2f}% (N={len(neutral_returns_final)})")
            if not greed_returns_final.empty:
                logging.info(f"  극심한 탐욕 (F&G > {greed_display_threshold}): {greed_returns_final.mean()*100:.2f}% (N={len(greed_returns_final)})")
        else:
            logging.warning("\nF&G 지수 구간별 미래 수익률 분석을 위한 데이터가 부족합니다.")

    else:
        logging.error("\n가중치 최적화 실패.")
        logging.error(f"  Status: {optimization_result.status}")
        logging.error(f"  Message: {optimization_result.message}")
        logging.error(f"  Number of iterations: {optimization_result.nit}")
        logging.error(f"  Number of function evaluations: {optimization_result.nfev}")
        if hasattr(optimization_result, 'jac') and optimization_result.jac is not None:
            logging.error(f"  Final gradient (Jacobian): {optimization_result.jac}")