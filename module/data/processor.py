import pandas as pd
import json
import logging
from datetime import datetime, timedelta
from config.settings import Y_LIST, INDEX_PARAMS
from utils.helpers import pre_val
from utils.db_utils import get_table_as_df, upsert_df_to_db, get_db_connection, get_last_date
import sqlite3
import os
import sys

# 상위 디렉토리를 import 경로에 추가하여 원본 모듈을 사용할 수 있게 함
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

# 로거 가져오기
logger = logging.getLogger(__name__)

class DataProcessor:
    def __init__(self, custom_params=None):
        self.f_kgf_df = None
        self.f_json_df = None
        # 사용자 정의 파라미터가 있으면 기본 파라미터와 병합
        self.params = INDEX_PARAMS.copy()
        if custom_params:
            self.params.update(custom_params)
            logger.info(f"사용자 정의 파라미터로 업데이트됨: {custom_params}")

    def process_data(self, data_frames=None):
        """데이터를 처리하고 지표를 계산합니다."""
        try:
            logger.info("데이터 처리 시작")
            
            # kgf_index 테이블 구조 확인 및 업데이트
            self.check_and_update_table_structure()
            
            # 데이터 프레임이 제공되지 않은 경우 DB에서 가져옴
            if data_frames is None:
                logger.info("데이터베이스에서 데이터 로드 중")
                data_frames = {
                    'vix_df': get_table_as_df('vix'),
                    'tenBond_df': get_table_as_df('ten_bond'),
                    'junkBond_df': get_table_as_df('junk_bond'),
                    'pcr_df': get_table_as_df('pcr'),
                    'breadth_df': get_table_as_df('breadth'),
                    'kospi_df': get_table_as_df('kospi'),
                    'stock_strength_df': get_table_as_df('stock_strength')  # 추가: 주가 강도 데이터
                }
                
                # 파생 컬럼 계산
                data_frames = self.calculate_derived_columns(data_frames)

            # 기존 kgf_index 테이블 로드
            existing_kgf_index = get_table_as_df('kgf_index')
            logger.info(f"기존 KGF 인덱스 데이터: {len(existing_kgf_index)}행")
            
            # 가장 최근 계산된 날짜 확인
            last_calculated_date = None
            if not existing_kgf_index.empty:
                last_calculated_date = existing_kgf_index.index.max()
                logger.info(f"마지막으로 계산된 날짜: {last_calculated_date}")
            
            # 정크본드 스프레드 계산
            logger.info("정크본드 스프레드 계산 중")
            data_frames['junkBond_df']['junk_spread'] = (
                data_frames['junkBond_df']['aam'].mul(self.params['junk_bond_aam_weight']) + 
                data_frames['junkBond_df']['bbbp'].mul(self.params['junk_bond_bbbp_weight'])
            )
            
            # 계산된 값을 DB에 업데이트
            junk_spread_df = data_frames['junkBond_df'][['junk_spread']]
            upsert_df_to_db(junk_spread_df, 'junk_bond')

            # 시장 너비 지표 계산
            logger.info("시장 너비 지표 계산 중")
            data_frames['breadth_df']['short'] = data_frames['breadth_df']['diff'].rolling(window=self.params['breadth_short_window']).mean()
            data_frames['breadth_df']['long'] = data_frames['breadth_df']['diff'].rolling(window=self.params['breadth_long_window']).mean()
            data_frames['breadth_df']['mcclenllan'] = data_frames['breadth_df']['short'] - data_frames['breadth_df']['long']
            
            # 계산된 값을 DB에 업데이트
            mcclenllan_df = data_frames['breadth_df'][['mcclenllan']]
            upsert_df_to_db(mcclenllan_df, 'breadth')

            # PCR EMA 계산
            logger.info("PCR EMA 계산 중")
            
            # 컬럼명 확인 및 변환 (p/c_ratio 또는 p_c_ratio)
            if 'p_c_ratio' in data_frames['pcr_df'].columns:
                pcr_column = 'p_c_ratio'
            elif 'p/c_ratio' in data_frames['pcr_df'].columns:
                pcr_column = 'p/c_ratio'
                # p/c_ratio 컬럼을 p_c_ratio로 복제
                data_frames['pcr_df']['p_c_ratio'] = data_frames['pcr_df']['p/c_ratio']
                logger.info("PCR 데이터프레임의 'p/c_ratio' 컬럼을 'p_c_ratio'로 변환했습니다.")
            else:
                logger.error("PCR 데이터프레임에 'p_c_ratio' 또는 'p/c_ratio' 컬럼이 없습니다.")
                raise KeyError("PCR ratio 컬럼을 찾을 수 없습니다")
                
            data_frames['pcr_df']['p_c_ema'] = data_frames['pcr_df'][pcr_column].rolling(window=self.params['pcr_ema_window']).mean()
            
            # 계산된 값을 DB에 업데이트
            p_c_ema_df = data_frames['pcr_df'][['p_c_ema']]
            upsert_df_to_db(p_c_ema_df, 'pcr')

            # VIX 지표 계산
            logger.info("VIX 지표 계산 중")
            
            # VIX 데이터가 숫자형인지 확인하고 변환
            try:
                # 빈 문자열이나 비숫자 값을 NaN으로 변환
                data_frames['vix_df']['vix_close'] = pd.to_numeric(data_frames['vix_df']['vix_close'], errors='coerce')
                
                # NaN 값을 가진 행 제거 또는 다른 값으로 대체
                if data_frames['vix_df']['vix_close'].isna().any():
                    count_null = data_frames['vix_df']['vix_close'].isna().sum()
                    logger.warning(f"VIX 데이터에서 {count_null}개의 비숫자 값이 발견되어 제거되었습니다.")
                    
                    # NaN 값을 가진 행 제거
                    # data_frames['vix_df'] = data_frames['vix_df'].dropna(subset=['vix_close'])
                    
                    # 또는 NaN 값을 전후 값의 평균으로 대체
                    data_frames['vix_df']['vix_close'] = data_frames['vix_df']['vix_close'].interpolate(method='linear')
                
                data_frames['vix_df']['vix_ema'] = data_frames['vix_df']['vix_close'].rolling(window=self.params['vix_ema_window']).mean()
                data_frames['vix_df']['vix_ema_spread'] = data_frames['vix_df']['vix_close'] - data_frames['vix_df']['vix_ema']
                
                # 계산된 값을 DB에 업데이트
                vix_derived_df = data_frames['vix_df'][['vix_ema', 'vix_ema_spread']]
                upsert_df_to_db(vix_derived_df, 'vix')
            except Exception as e:
                logger.error(f"VIX 데이터 처리 중 오류 발생: {e}")
                raise
            
            # KOSPI 지표 계산
            logger.info("KOSPI 지표 계산 중")
            
            # KOSPI 데이터가 숫자형인지 확인하고 변환
            try:
                # 필요한 컬럼을 숫자형으로 변환
                for col in ['close', 'open', 'high', 'low', 'volume']:
                    if col in data_frames['kospi_df'].columns:
                        data_frames['kospi_df'][col] = pd.to_numeric(data_frames['kospi_df'][col], errors='coerce')
                
                data_frames['kospi_df']['ema'] = data_frames['kospi_df']['종가'].rolling(window=self.params['kospi_ema_window']).mean()
                data_frames['kospi_df']['ema_spread'] = data_frames['kospi_df']['종가'] - data_frames['kospi_df']['ema']
                data_frames['kospi_df']['bf_20'] = data_frames['kospi_df']['종가'].shift(self.params['kospi_return_shift'])
                data_frames['kospi_df']['return_20'] = (data_frames['kospi_df']['종가'] / data_frames['kospi_df']['bf_20'] - 1) * 100
                
                # 계산된 값을 DB에 업데이트
                kospi_derived_df = data_frames['kospi_df'][['ema', 'ema_spread', 'bf_20', 'return_20']]
                upsert_df_to_db(kospi_derived_df, 'kospi')
            except Exception as e:
                logger.error(f"KOSPI 데이터 처리 중 오류 발생: {e}")
                raise

            # 채권 EMA 계산
            logger.info("채권 EMA 계산 중")
            data_frames['tenBond_df']['bond_ema'] = data_frames['tenBond_df']['ten_ratio'].rolling(window=self.params['bond_ema_window']).mean()
            
            # 계산된 값을 DB에 업데이트
            bond_ema_df = data_frames['tenBond_df'][['bond_ema']]
            upsert_df_to_db(bond_ema_df, 'ten_bond')

            # Safe Demand 계산
            logger.info("Safe Demand 계산 중")
            safe_demand_df = pd.merge(
                data_frames['tenBond_df']['bond_ema'],
                data_frames['kospi_df']['return_20'],
                left_index=True,
                right_index=True,
                how='inner'
            )
            safe_demand_df['safe_spread'] = safe_demand_df['return_20'] - safe_demand_df['bond_ema']

            # 최종 데이터프레임 생성
            logger.info("최종 데이터프레임 생성 중")
            
            # 각 데이터프레임에서 중복된 인덱스 제거
            for key, df in data_frames.items():
                if df is not None and not df.empty:
                    # 중복 인덱스 확인
                    duplicated = df.index.duplicated(keep='first')
                    if duplicated.any():
                        dup_count = duplicated.sum()
                        logger.warning(f"{key}에서 {dup_count}개의 중복 인덱스가 발견되어 제거됩니다.")
                        data_frames[key] = df[~duplicated]
            
            # safe_demand_df에서도 중복 인덱스 확인
            if not safe_demand_df.empty:
                duplicated = safe_demand_df.index.duplicated(keep='first')
                if duplicated.any():
                    dup_count = duplicated.sum()
                    logger.warning(f"safe_demand_df에서 {dup_count}개의 중복 인덱스가 발견되어 제거됩니다.")
                    safe_demand_df = safe_demand_df[~duplicated]
            
            # 주가 강도 데이터 확인
            if 'stock_strength_df' in data_frames and data_frames['stock_strength_df'] is not None and not data_frames['stock_strength_df'].empty:
                logger.info("주가 강도 데이터를 최종 계산에 포함")
                stock_strength_series = data_frames['stock_strength_df']['strength_index']
            else:
                logger.warning("주가 강도 데이터가 없어 인덱스 계산에서 제외됩니다.")
                stock_strength_series = None
            
            # 기존 지표들 결합
            kgf_component_dfs = [
                data_frames['kospi_df']['ema_spread'],
                data_frames['breadth_df']['mcclenllan'],
                data_frames['pcr_df']['p_c_ema'].mul(-1),
                data_frames['vix_df']['vix_ema_spread'].mul(-1),
                safe_demand_df['safe_spread'],
                data_frames['junkBond_df']['junk_spread'].mul(-1),
                data_frames['kospi_df']['종가']
            ]
            
            # 주가 강도 추가 (있는 경우)
            adjusted_strength = None  # 변수 미리 정의
            if stock_strength_series is not None:
                # 0-100 스케일에서 50이 중간값이므로, 50 미만은 공포, 50 초과는 탐욕
                adjusted_strength = (stock_strength_series - 50) / 50
                kgf_component_dfs.append(adjusted_strength)
            
            kgf_df = pd.concat(kgf_component_dfs, axis=1, join='inner')
            
            # JSON 시각화용 데이터프레임 구성
            json_component_dfs = [
                data_frames['kospi_df']['종가'],
                data_frames['kospi_df']['ema'],
                data_frames['breadth_df']['mcclenllan'],
                data_frames['pcr_df']['p_c_ema'],
                data_frames['vix_df']['vix_close'],
                data_frames['vix_df']['vix_ema'],
                safe_demand_df['safe_spread'],
                data_frames['junkBond_df']['junk_spread']
            ]
            
            # 주가 강도 추가 (있는 경우)
            if stock_strength_series is not None:
                json_component_dfs.append(stock_strength_series.rename('stock_strength'))
            
            json_df = pd.concat(json_component_dfs, axis=1, join='inner')
            json_df.rename(columns={'종가': 'kospi'}, inplace=True)
            
            # 마지막 계산 날짜 이후의 새 데이터만 처리
            if last_calculated_date is not None:
                new_data_dates = kgf_df.index[kgf_df.index > last_calculated_date]
                if len(new_data_dates) == 0:
                    logger.info("새로 계산할 데이터가 없습니다.")
                    # 기존 데이터를 그대로 사용
                    self.f_kgf_df = pd.concat([
                        existing_kgf_index[['index_value', 'kospi_close']].rename(columns={'index_value': 'index', 'kospi_close': '종가'}),
                        existing_kgf_index.filter(like='_scaled')
                    ], axis=1)
                    
                    # 최근 150일치 데이터만 사용
                    self.f_json_df = json_df.iloc[-150:]
                    logger.info("기존 인덱스를 사용합니다.")
                    
                    # 하지만 마지막 데이터가 최근 2일 이내가 아니면 새로운 데이터가 있는지 확인
                    last_date = pd.to_datetime(existing_kgf_index.index.max())
                    current_date = pd.to_datetime(datetime.today())
                    days_diff = (current_date - last_date).days
                    
                    if days_diff > 2:
                        logger.warning(f"마지막 데이터와 현재 날짜 사이에 {days_diff}일의 차이가 있습니다. 각 Factor를 확인하세요.")
                        
                        # 각 Factor의 마지막 날짜 체크
                        factors = {
                            'KOSPI': data_frames['kospi_df'].index.max() if not data_frames['kospi_df'].empty else None,
                            'VIX': data_frames['vix_df'].index.max() if not data_frames['vix_df'].empty else None,
                            'PCR': data_frames['pcr_df'].index.max() if not data_frames['pcr_df'].empty else None,
                            'Breadth': data_frames['breadth_df'].index.max() if not data_frames['breadth_df'].empty else None,
                            'JunkBond': data_frames['junkBond_df'].index.max() if not data_frames['junkBond_df'].empty else None,
                            'TenBond': data_frames['tenBond_df'].index.max() if not data_frames['tenBond_df'].empty else None
                        }
                        
                        logger.info(f"각 Factor 마지막 날짜: {factors}")
                        
                    return self.f_kgf_df, self.f_json_df
                
                logger.info(f"새로운 데이터: {len(new_data_dates)}일치")
                
                # 스케일링을 위해 필요한 과거 데이터 포함 (scaling_window 기간)
                window_start_date = new_data_dates.min() - timedelta(days=self.params['scaling_window'] * 1.5)  # 여유있게 1.5배
                working_df = kgf_df[kgf_df.index >= window_start_date].copy()
                
                # working_df가 정의된 후에 stock_strength 추가
                if adjusted_strength is not None:
                    working_df['stock_strength'] = adjusted_strength
                
                # 이미 계산된 지수 값
                calculated_kgf_df = pd.concat([
                    existing_kgf_index[['index_value', 'kospi_close']].rename(columns={'index_value': 'index', 'kospi_close': '종가'}),
                    existing_kgf_index.filter(like='_scaled')
                ], axis=1)
            else:
                # 첫 실행 또는 데이터 없음
                working_df = kgf_df.copy()
                working_df['index'] = None
                
                # working_df가 정의된 후에 stock_strength 추가
                if adjusted_strength is not None:
                    working_df['stock_strength'] = adjusted_strength
                
                calculated_kgf_df = None
                new_data_dates = working_df.index
            
            # 새 데이터에 대해서만 스케일링 및 인덱스 계산
            logger.info("새 데이터 스케일링 및 인덱스 계산 중")
            working_df['index'] = None
            
            for column in working_df.columns:
                if column == '종가' or column == 'index':
                    continue
                    
                working_df[column + '_scaled'] = None
                rolling_min = working_df[column].rolling(window=self.params['scaling_window'], min_periods=20).min()
                # NaN이면 전체 데이터의 최소값으로 대체
                if rolling_min.isna().any():
                    min_val = working_df[column].min()
                    rolling_min = rolling_min.fillna(min_val)
                    logger.info(f"{column} 컬럼의 rolling_min에 NaN이 있어 전체 최소값({min_val:.4f})으로 대체합니다.")
                rolling_max = working_df[column].rolling(window=self.params['scaling_window'], min_periods=20).max()
                # NaN이면 전체 데이터의 최대값으로 대체
                if rolling_max.isna().any():
                    max_val = working_df[column].max()
                    rolling_max = rolling_max.fillna(max_val)
                    logger.info(f"{column} 컬럼의 rolling_max에 NaN이 있어 전체 최대값({max_val:.4f})으로 대체합니다.")
                try:
                    # 분모가 0인 경우 체크
                    denominator = rolling_max - rolling_min
                    if (denominator == 0).any():
                        logger.warning(f"{column} 컬럼에서 분모가 0인 경우가 있습니다. 기본값 0.5를 사용합니다.")
                        # 분모가 0인 위치 찾기
                        zero_mask = (denominator == 0)
                        # 나머지 위치는 정상 계산
                        working_df[column + '_scaled'] = (working_df[column] - rolling_min) / denominator
                        # 분모가 0인 위치는 0.5로 설정
                        working_df.loc[zero_mask.index[zero_mask], column + '_scaled'] = 0.5
                    else:
                        working_df[column + '_scaled'] = (working_df[column] - rolling_min) / denominator
                    
                    # NaN 값을 0.5로 처리
                    if working_df[column + '_scaled'].isna().any():
                        logger.warning(f"{column}_scaled 컬럼에 NaN 값이 있습니다. 기본값 0.5로 대체합니다.")
                        working_df[column + '_scaled'] = working_df[column + '_scaled'].fillna(0.5)
                except Exception as e:
                    logger.error(f"{column} 스케일링 중 오류 발생: {e}")
                    # 오류 발생 시 기본값 0.5 사용
                    working_df[column + '_scaled'] = 0.5
            
            working_df['index'] = working_df.filter(like='_scaled').multiply(self.params['index_weight']).sum(axis=1)
            working_df['index'] = working_df['index'].rolling(window=self.params['index_smoothing_window']).mean()
            
            # 새로 계산된 지수에서 필요한 부분만 추출
            new_kgf_df = working_df.loc[new_data_dates].dropna(subset=['index'])
            
            if calculated_kgf_df is not None:
                # 이전 계산 결과와 새 계산 결과 병합
                final_kgf_df = pd.concat([calculated_kgf_df, new_kgf_df])
                # 중복 제거 (이전 데이터 우선)
                final_kgf_df = final_kgf_df[~final_kgf_df.index.duplicated(keep='first')]
            else:
                # 첫 실행시 충분한 데이터가 쌓일 때까지 기다림
                final_kgf_df = new_kgf_df.iloc[363:]
            
            # 새 계산 결과만 DB에 저장
            if not new_kgf_df.empty:
                columns_to_save = [
                    'ema_spread_scaled',
                    'mcclenllan_scaled',
                    'p_c_ema_scaled',
                    'vix_ema_spread_scaled',
                    'safe_spread_scaled',
                    'junk_spread_scaled',
                    'index_value',
                    'kospi_close'
                ]
                
                # 주가 강도 열이 있으면 추가
                if 'stock_strength_scaled' in new_kgf_df.columns:
                    columns_to_save.append('stock_strength_scaled')
                
                
                # 새로운 데이터프레임 생성 방식으로 변경
                new_kgf_index_df = pd.DataFrame()
                
                # index -> index_value, 종가 -> kospi_close로 컬럼 매핑
                new_kgf_index_df['index_value'] = new_kgf_df['index']
                new_kgf_index_df['kospi_close'] = new_kgf_df['종가']
                
                # 나머지 _scaled 컬럼들 추가
                for col in columns_to_save:
                    if col != 'index_value' and col != 'kospi_close' and col in new_kgf_df.columns:
                        new_kgf_index_df[col] = new_kgf_df[col]
                
                print(new_kgf_index_df)
                upsert_df_to_db(new_kgf_index_df, 'kgf_index')
                logger.info(f"새로운 KGF 인덱스 {len(new_kgf_index_df)}행을 DB에 저장 완료")
            
            self.f_kgf_df = final_kgf_df
            self.f_json_df = json_df.iloc[-150:]
            
            logger.info("데이터 처리 완료")
            return final_kgf_df, self.f_json_df
            
        except Exception as e:
            logger.error(f"데이터 처리 중 오류 발생: {e}")
            raise
            
    def update_params(self, new_params):
        """지수 계산 파라미터를 업데이트합니다."""
        try:
            if not new_params:
                logger.warning("업데이트할 파라미터가 없습니다.")
                return False
                
            self.params.update(new_params)
            logger.info(f"파라미터가 업데이트되었습니다: {new_params}")
            return True
        except Exception as e:
            logger.error(f"파라미터 업데이트 중 오류 발생: {e}")
            return False

    def get_current_params(self):
        """현재 사용 중인 파라미터를 반환합니다."""
        return self.params.copy()

    def test_stock_strength_update(self):
        """주가 강도 업데이트 기능을 테스트합니다."""
        try:
            logger.info("주가 강도 업데이트 테스트 시작")
            
            # 테이블 구조 확인 및 업데이트
            self.check_and_update_table_structure()
            
            # 주가 강도 데이터 불러오기
            stock_strength_df = get_table_as_df('stock_strength')
            
            if stock_strength_df.empty:
                logger.warning("주가 강도 데이터가 없습니다.")
                return False
                
            # 가장 최근 날짜의 데이터 확인
            latest_date = stock_strength_df.index.max()
            latest_strength = stock_strength_df.loc[latest_date, 'strength_index']
            
            logger.info(f"최근 주가 강도 데이터 ({latest_date}): {latest_strength}")
            
            # 임의의 주가 강도 스케일링 값 생성 (0-1 사이)
            # 실제로는 rolling window를 사용한 정규화가 수행되어야 함
            scaled_value = (latest_strength - 50) / 50  # 50을 기준으로 -1에서 1 사이로 변환
            
            # 테스트용 데이터 저장
            # 날짜 형식 확인 및 변환
            date_str = latest_date.strftime('%Y-%m-%d')
            logger.info(f"테스트 주가 강도 데이터 저장 중 (날짜: {date_str}, 값: {scaled_value:.5f})")
            
            # kgf_index 테이블에 업데이트
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # 해당 날짜 데이터 존재 여부 확인
            cursor.execute("SELECT 1 FROM kgf_index WHERE date = ?", (date_str,))
            exists = cursor.fetchone() is not None
            
            if exists:
                # 기존 데이터 업데이트
                cursor.execute(
                    "UPDATE kgf_index SET stock_strength_scaled = ? WHERE date = ?", 
                    (scaled_value, date_str)
                )
                logger.info(f"날짜 {date_str}의 주가 강도 데이터를 업데이트했습니다.")
            else:
                # 새 날짜에 대한 데이터 삽입 시도 (모든 값이 없으면 에러 발생 가능)
                logger.warning(f"날짜 {date_str}에 해당하는 kgf_index 레코드가 없습니다.")
                # 빈 레코드 추가
                try:
                    cursor.execute(
                        "INSERT INTO kgf_index (date, stock_strength_scaled) VALUES (?, ?)",
                        (date_str, scaled_value)
                    )
                    logger.info(f"날짜 {date_str}에 대한 새 주가 강도 데이터를 추가했습니다.")
                except Exception as e:
                    logger.error(f"새 날짜 추가 중 오류: {e}")
                    # 테이블에 다른 필수 컬럼이 있을 수 있음
            
            conn.commit()
            conn.close()
            
            logger.info("주가 강도 업데이트 테스트 완료")
            return True
        except Exception as e:
            logger.error(f"주가 강도 업데이트 테스트 중 오류 발생: {e}")
            return False

    def write_json(self):
        """JSON 파일들을 생성합니다."""
        try:
            logger.info("JSON 파일 생성 시작")
            # 값 상태 JSON 생성
            value_dict = {
                'current': round(self.f_kgf_df['index'].iloc[-1], 1),
                'current_s': pre_val(round(self.f_kgf_df['index'].iloc[-1], 1)),
                'week': round(self.f_kgf_df['index'].iloc[-7], 1),
                'week_s': pre_val(round(self.f_kgf_df['index'].iloc[-7], 1)),
                'month': round(self.f_kgf_df['index'].iloc[-30], 1),
                'month_s': pre_val(round(self.f_kgf_df['index'].iloc[-30], 1)),
                'year': round(self.f_kgf_df['index'].iloc[-300], 1),
                'year_s': pre_val(round(self.f_kgf_df['index'].iloc[-300], 1))
            }

            with open("./json/value.json", 'w') as f:
                json.dump(value_dict, f, indent=4)
            logger.info("value.json 파일 생성 완료")
            
            # factor_status.json 생성
            latest_record = get_table_as_df('kgf_index').iloc[-1]
            factor_status = {
                'ema_spread_scaled': latest_record['ema_spread_scaled'],
                'mcclenllan_scaled': latest_record['mcclenllan_scaled'],
                'p_c_ema_scaled': latest_record['p_c_ema_scaled'],
                'vix_ema_spread_scaled': latest_record['vix_ema_spread_scaled'],
                'safe_spread_scaled': latest_record['safe_spread_scaled'],
                'junk_spread_scaled': latest_record['junk_spread_scaled'],
                'stock_strength_scaled': latest_record['stock_strength_scaled']
            }
            
            with open("./json/factor_status.json", 'w') as f:
                json.dump(factor_status, f, indent=4)
            logger.info("factor_status.json 파일 생성 완료 (stock_strength_scaled 추가)")

            # 각 지표별 JSON 생성
            x_list = self.f_json_df.index.strftime('%Y-%m-%d')
            
            for y in Y_LIST:
                data = []
                for i in range(len(self.f_json_df.index)):
                    if y == 'kospi':
                        data.append({
                            'x': x_list[i],
                            'y': self.f_json_df[y].iloc[i],
                            'z': self.f_json_df['ema'].iloc[i]
                        })
                    elif y == 'vix_close':
                        data.append({
                            'x': x_list[i],
                            'y': self.f_json_df[y].iloc[i],
                            'z': self.f_json_df['vix_ema'].iloc[i]
                        })
                    else:
                        data.append({'x': x_list[i], 'y': self.f_json_df[y].iloc[i]})
                
                db = {'data': data}
                with open(f"./json/{y}.json", 'w') as f:
                    json.dump(db, f, indent=4)
                logger.info(f"{y}.json 파일 생성 완료")

            # 인덱스 JSON 생성
            index_data = []
            for i in range(len(self.f_kgf_df)):
                index_data.append({
                    'x': self.f_kgf_df.index.strftime('%Y-%m-%d')[i],
                    'y': self.f_kgf_df['종가'].iloc[i],
                    'z': self.f_kgf_df['index'].iloc[i]
                })

            index_db = {'data': index_data}
            with open("./json/index.json", 'w') as f:
                json.dump(index_db, f, indent=4)
            logger.info("index.json 파일 생성 완료")
            
            logger.info("JSON 파일 업데이트 완료")
        except Exception as e:
            logger.error(f"JSON 파일 생성 중 오류 발생: {e}")
            raise 

    
    def calculate_derived_columns(self, data_frames):
        """각 테이블의 파생 컬럼을 계산합니다."""
        try:
            logger.info("파생 컬럼 계산 중...")
            
            # VIX 테이블
            if 'vix_df' in data_frames and data_frames['vix_df'] is not None and not data_frames['vix_df'].empty:
                if 'vix_close' in data_frames['vix_df'].columns:
                    data_frames['vix_df']['vix_ema'] = data_frames['vix_df']['vix_close'].rolling(window=self.params['vix_ema_window'], min_periods=1).mean()
                    data_frames['vix_df']['vix_ema_spread'] = data_frames['vix_df']['vix_close'] - data_frames['vix_df']['vix_ema']
                    # NaN 처리
                    data_frames['vix_df']['vix_ema'] = data_frames['vix_df']['vix_ema'].fillna(method='ffill')
                    data_frames['vix_df']['vix_ema_spread'] = data_frames['vix_df']['vix_ema_spread'].fillna(0)
            
            # KOSPI 테이블
            if 'kospi_df' in data_frames and data_frames['kospi_df'] is not None and not data_frames['kospi_df'].empty:
                if '종가' in data_frames['kospi_df'].columns:
                    data_frames['kospi_df']['ema'] = data_frames['kospi_df']['종가'].rolling(window=self.params['kospi_ema_window'], min_periods=1).mean()
                    data_frames['kospi_df']['ema_spread'] = data_frames['kospi_df']['종가'] - data_frames['kospi_df']['ema']
                    data_frames['kospi_df']['bf_20'] = data_frames['kospi_df']['종가'].shift(self.params['kospi_return_shift'])
                    data_frames['kospi_df']['return_20'] = (data_frames['kospi_df']['종가'] / data_frames['kospi_df']['bf_20'] - 1) * 100
                    # NaN 처리
                    data_frames['kospi_df']['ema'] = data_frames['kospi_df']['ema'].fillna(method='ffill')
                    data_frames['kospi_df']['ema_spread'] = data_frames['kospi_df']['ema_spread'].fillna(0)
                    data_frames['kospi_df']['return_20'] = data_frames['kospi_df']['return_20'].fillna(method='ffill')
            
            # PCR 테이블
            if 'pcr_df' in data_frames and data_frames['pcr_df'] is not None and not data_frames['pcr_df'].empty:
                pcr_column = None
                if 'p_c_ratio' in data_frames['pcr_df'].columns:
                    pcr_column = 'p_c_ratio'
                elif 'p/c_ratio' in data_frames['pcr_df'].columns:
                    pcr_column = 'p/c_ratio'
                    data_frames['pcr_df']['p_c_ratio'] = data_frames['pcr_df']['p/c_ratio']
                
                if pcr_column:
                    data_frames['pcr_df']['p_c_ema'] = data_frames['pcr_df'][pcr_column].rolling(window=self.params['pcr_ema_window'], min_periods=1).mean()
                    # NaN 처리
                    data_frames['pcr_df']['p_c_ema'] = data_frames['pcr_df']['p_c_ema'].fillna(method='ffill')
            
            # Breadth 테이블
            if 'breadth_df' in data_frames and data_frames['breadth_df'] is not None and not data_frames['breadth_df'].empty:
                if 'diff' in data_frames['breadth_df'].columns:
                    data_frames['breadth_df']['short'] = data_frames['breadth_df']['diff'].rolling(window=self.params['breadth_short_window'], min_periods=1).mean()
                    data_frames['breadth_df']['long'] = data_frames['breadth_df']['diff'].rolling(window=self.params['breadth_long_window'], min_periods=1).mean()
                    data_frames['breadth_df']['mcclenllan'] = data_frames['breadth_df']['short'] - data_frames['breadth_df']['long']
                    # NaN 처리
                    data_frames['breadth_df']['mcclenllan'] = data_frames['breadth_df']['mcclenllan'].fillna(0)
            
            # Junk Bond 테이블
            if 'junkBond_df' in data_frames and data_frames['junkBond_df'] is not None and not data_frames['junkBond_df'].empty:
                if 'aam' in data_frames['junkBond_df'].columns and 'bbbp' in data_frames['junkBond_df'].columns:
                    data_frames['junkBond_df']['junk_spread'] = (
                        data_frames['junkBond_df']['aam'].mul(self.params['junk_bond_aam_weight']) + 
                        data_frames['junkBond_df']['bbbp'].mul(self.params['junk_bond_bbbp_weight'])
                    )
                    # NaN 처리
                    data_frames['junkBond_df']['junk_spread'] = data_frames['junkBond_df']['junk_spread'].fillna(method='ffill')
            
            # Ten Bond 테이블
            if 'tenBond_df' in data_frames and data_frames['tenBond_df'] is not None and not data_frames['tenBond_df'].empty:
                if 'ten_ratio' in data_frames['tenBond_df'].columns:
                    data_frames['tenBond_df']['bond_ema'] = data_frames['tenBond_df']['ten_ratio'].rolling(window=self.params['bond_ema_window'], min_periods=1).mean()
                    # NaN 처리
                    data_frames['tenBond_df']['bond_ema'] = data_frames['tenBond_df']['bond_ema'].fillna(method='ffill')
            
            logger.info("파생 컬럼 계산 완료")
            return data_frames
        except Exception as e:
            logger.error(f"파생 컬럼 계산 중 오류 발생: {e}")
            return data_frames

    def check_and_update_table_structure(self):
        """kgf_index 테이블 구조를 확인하고 필요한 경우 stock_strength_scaled 열을 추가합니다."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # 테이블이 존재하는지 확인
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='kgf_index'")
            if cursor.fetchone() is None:
                logger.info("kgf_index 테이블이 존재하지 않습니다. 초기화 중...")
                conn.close()
                return  # 테이블이 없으면 초기화 함수에서 생성될 것임
            
            # 테이블 구조 확인 (stock_strength_scaled 열이 있는지 확인)
            cursor.execute("PRAGMA table_info(kgf_index)")
            columns = [row[1] for row in cursor.fetchall()]
            
            # stock_strength_scaled 열이 없으면 추가
            if 'stock_strength_scaled' not in columns:
                logger.info("kgf_index 테이블에 stock_strength_scaled 열 추가 중...")
                try:
                    cursor.execute("ALTER TABLE kgf_index ADD COLUMN stock_strength_scaled REAL")
                    conn.commit()
                    logger.info("stock_strength_scaled 열 추가 완료")
                except sqlite3.OperationalError as e:
                    # 이미 열이 있는 경우 등의 오류 처리
                    logger.warning(f"열 추가 중 오류 발생: {e}")
            
            conn.close()
        except Exception as e:
            logger.error(f"테이블 구조 확인 중 오류 발생: {e}")
            if conn:
                conn.close() 