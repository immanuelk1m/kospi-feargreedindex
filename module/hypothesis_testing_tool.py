"""
코스피 공포탐욕지수 최적화를 위한 가설검증 툴

이 모듈은 다음 기능을 제공합니다:
- 백테스팅 프레임워크
- 파라미터 최적화 
- ROI 분석
- 성과 평가
- 실제 시스템 적용
"""

import pandas as pd
import numpy as np
import sqlite3
import itertools
import json
import logging
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
from scipy.optimize import differential_evolution, minimize
from sklearn.metrics import mean_squared_error
import warnings
warnings.filterwarnings('ignore')

from config.settings import DB_DIR, INDEX_PARAMS
from utils.db_utils import get_db_connection
from data.processor import DataProcessor

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HypothesisTestingTool:
    """
    코스피 공포탐욕지수 최적화를 위한 가설검증 툴
    """
    
    def __init__(self):
        self.data_frames = {}
        self.kgf_data = None
        self.kospi_data = None
        self.optimization_results = []
        self.best_params = None
        self.best_roi = -float('inf')
        
        # 파라미터 최적화 범위 정의
        self.param_ranges = {
            'junk_bond_aam_weight': (0.5, 1.0),
            'junk_bond_bbbp_weight': (0.0, 0.5),
            'breadth_short_window': (10, 30),
            'breadth_long_window': (25, 60),
            'pcr_ema_window': (3, 15),
            'vix_ema_window': (20, 100),
            'kospi_ema_window': (50, 200),
            'kospi_return_shift': (10, 40),
            'bond_ema_window': (10, 40),
            'scaling_window': (120, 480),
            'index_weight': (10.0, 20.0),
            'index_smoothing_window': (1, 10)
        }
        
        # 백테스팅 설정
        self.train_ratio = 0.7  # 70% 훈련, 30% 테스트
        self.lookback_period = 252  # 1년 백테스팅 기간
        
    def load_data(self):
        """데이터베이스에서 모든 필요한 데이터를 로드합니다."""
        logger.info("데이터 로드 시작")
        try:
            conn = get_db_connection()
            
            # 각 테이블별 데이터 로드
            tables = ['vix', 'ten_bond', 'junk_bond', 'pcr', 'breadth', 'kospi', 'stock_strength']
            
            for table in tables:
                query = f"SELECT * FROM {table} ORDER BY date"
                df = pd.read_sql(query, conn, parse_dates=['date'])
                df = df.set_index('date')
                self.data_frames[f'{table}_df'] = df
                logger.info(f"{table} 테이블 로드 완료: {len(df)}행")
            
            # KGF 인덱스 데이터 로드
            kgf_query = "SELECT * FROM kgf_index ORDER BY date"
            self.kgf_data = pd.read_sql(kgf_query, conn, parse_dates=['date'])
            self.kgf_data = self.kgf_data.set_index('date')
            logger.info(f"KGF 인덱스 데이터 로드 완료: {len(self.kgf_data)}행")
            
            # KOSPI 종가 데이터 추출
            if '종가' in self.data_frames['kospi_df'].columns:
                self.kospi_data = self.data_frames['kospi_df']['종가'].copy()
            elif 'close' in self.data_frames['kospi_df'].columns:
                self.kospi_data = self.data_frames['kospi_df']['close'].copy()
            else:
                raise KeyError("KOSPI 종가 데이터를 찾을 수 없습니다.")
            
            conn.close()
            logger.info("모든 데이터 로드 완료")
            
        except Exception as e:
            logger.error(f"데이터 로드 중 오류 발생: {e}")
            raise

    def _sanitize_params(self, params):
        """윈도우/시프트 등 정수형이 필요한 파라미터를 int로 변환"""
        int_keys = [
            'breadth_short_window', 'breadth_long_window', 'pcr_ema_window',
            'vix_ema_window', 'kospi_ema_window', 'kospi_return_shift',
            'bond_ema_window', 'scaling_window', 'index_smoothing_window'
        ]
        sanitized = params.copy()
        for key in int_keys:
            if key in sanitized:
                sanitized[key] = int(max(1, round(sanitized[key])))
        return sanitized

    def calculate_index_with_params(self, params, start_date=None, end_date=None):
        """
        주어진 파라미터로 공포탐욕지수를 재계산합니다.
        """
        try:
            # 윈도우/시프트 정수 보정
            params = self._sanitize_params(params)
            processor = DataProcessor(custom_params=params)
            
            # 날짜 범위 필터링
            filtered_data_frames = {}
            for key, df in self.data_frames.items():
                filtered_df = df.copy()
                if start_date:
                    filtered_df = filtered_df[filtered_df.index >= start_date]
                if end_date:
                    filtered_df = filtered_df[filtered_df.index <= end_date]
                filtered_data_frames[key] = filtered_df
            
            # 파생 컬럼 계산
            filtered_data_frames = processor.calculate_derived_columns(filtered_data_frames)
            
            # 지수 계산을 위한 컴포넌트 준비
            kospi_df = filtered_data_frames['kospi_df']
            breadth_df = filtered_data_frames['breadth_df']
            pcr_df = filtered_data_frames['pcr_df']
            vix_df = filtered_data_frames['vix_df']
            junkBond_df = filtered_data_frames['junk_bond_df']
            tenBond_df = filtered_data_frames['ten_bond_df']
            stock_strength_df = filtered_data_frames['stock_strength_df']
            
            # Safe Demand 계산
            safe_demand_df = pd.merge(
                tenBond_df['bond_ema'],
                kospi_df['return_20'],
                left_index=True,
                right_index=True,
                how='inner'
            )
            safe_demand_df['safe_spread'] = safe_demand_df['return_20'] - safe_demand_df['bond_ema']
            
            # 지수 구성 요소들 결합
            components = [
                kospi_df['ema_spread'],
                breadth_df['mcclenllan'],
                pcr_df['p_c_ema'].mul(-1),
                vix_df['vix_ema_spread'].mul(-1),
                safe_demand_df['safe_spread'],
                junkBond_df['junk_spread'].mul(-1)
            ]
            
            # 주가 강도 추가 (있는 경우)
            if not stock_strength_df.empty and 'strength_index' in stock_strength_df.columns:
                adjusted_strength = (stock_strength_df['strength_index'] - 50) / 50
                components.append(adjusted_strength)
            
            # 컴포넌트 데이터프레임 생성
            component_df = pd.concat(components, axis=1, join='inner')
            
            # 스케일링
            for i, column in enumerate(component_df.columns):
                rolling_min = component_df[column].rolling(window=params['scaling_window'], min_periods=20).min()
                rolling_max = component_df[column].rolling(window=params['scaling_window'], min_periods=20).max()
                
                # 예외 처리
                denominator = rolling_max - rolling_min
                zero_mask = (denominator == 0) | (denominator.isna())
                
                component_df[f'{column}_scaled'] = (component_df[column] - rolling_min) / denominator
                component_df.loc[zero_mask, f'{column}_scaled'] = 0.5
                component_df[f'{column}_scaled'] = component_df[f'{column}_scaled'].fillna(0.5)
            
            # 최종 지수 계산
            scaled_columns = component_df.filter(like='_scaled')
            index_series = scaled_columns.multiply(params['index_weight']).sum(axis=1)
            index_series = index_series.rolling(window=params['index_smoothing_window']).mean()
            
            return index_series.dropna()
            
        except Exception as e:
            logger.error(f"지수 계산 중 오류 발생: {e}")
            return pd.Series()
    
    def calculate_trading_signals(self, index_series, buy_threshold=25, sell_threshold=75):
        """
        공포탐욕지수를 바탕으로 매매 신호를 생성합니다.
        
        Args:
            index_series (pd.Series): 공포탐욕지수
            buy_threshold (float): 매수 임계값
            sell_threshold (float): 매도 임계값
            
        Returns:
            pd.DataFrame: 매매 신호와 수익률
        """
        signals = pd.DataFrame(index=index_series.index)
        signals['index'] = index_series
        signals['kospi_price'] = self.kospi_data.reindex(index_series.index, method='ffill')
        
        # 매매 신호 생성
        signals['position'] = 0  # 0: 현금, 1: 매수
        signals.loc[signals['index'] <= buy_threshold, 'position'] = 1  # 극도의 공포시 매수
        signals.loc[signals['index'] >= sell_threshold, 'position'] = 0  # 극도의 탐욕시 매도
        
        # 포지션 변화 감지
        signals['position_change'] = signals['position'].diff()
        
        # 수익률 계산
        signals['kospi_return'] = signals['kospi_price'].pct_change()
        signals['strategy_return'] = signals['kospi_return'] * signals['position'].shift(1)
        
        # 누적 수익률
        signals['kospi_cumret'] = (1 + signals['kospi_return']).cumprod()
        signals['strategy_cumret'] = (1 + signals['strategy_return']).cumprod()
        
        return signals
    
    def evaluate_performance(self, signals):
        """
        백테스팅 성과를 평가합니다.
        
        Args:
            signals (pd.DataFrame): 매매 신호 데이터
            
        Returns:
            dict: 성과 지표들
        """
        if len(signals) < 2:
            return {'total_return': 0, 'sharpe_ratio': 0, 'max_drawdown': 1, 'win_rate': 0}
        
        # 총 수익률
        total_return = signals['strategy_cumret'].iloc[-1] - 1
        kospi_return = signals['kospi_cumret'].iloc[-1] - 1
        
        # 샤프 비율
        strategy_returns = signals['strategy_return'].dropna()
        if len(strategy_returns) > 0 and strategy_returns.std() > 0:
            sharpe_ratio = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)
        else:
            sharpe_ratio = 0
        
        # 최대 낙폭
        peak = signals['strategy_cumret'].expanding().max()
        drawdown = (signals['strategy_cumret'] - peak) / peak
        max_drawdown = drawdown.min()
        
        # 승률 계산
        winning_trades = (strategy_returns > 0).sum()
        total_trades = len(strategy_returns[strategy_returns != 0])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # 거래 횟수
        trade_count = (signals['position_change'].abs() > 0).sum()
        
        return {
            'total_return': total_return,
            'kospi_return': kospi_return,
            'excess_return': total_return - kospi_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': abs(max_drawdown),
            'win_rate': win_rate,
            'trade_count': trade_count,
            'roi_score': total_return * 0.4 + sharpe_ratio * 0.3 - abs(max_drawdown) * 0.3
        }
    
    def objective_function(self, param_array):
        """
        최적화를 위한 목적 함수입니다.
        
        Args:
            param_array (np.array): 파라미터 배열
            
        Returns:
            float: 최적화 스코어 (음수로 반환하여 최소화 문제로 변환)
        """
        try:
            # 파라미터 배열을 딕셔너리로 변환
            param_keys = list(self.param_ranges.keys())
            raw_params = {key: param_array[i] for i, key in enumerate(param_keys)}
            params = self._sanitize_params(raw_params)
            
            # 정크본드 가중치 정규화
            total_junk_weight = params['junk_bond_aam_weight'] + params['junk_bond_bbbp_weight']
            if total_junk_weight > 0:
                params['junk_bond_aam_weight'] /= total_junk_weight
                params['junk_bond_bbbp_weight'] /= total_junk_weight
            
            # 훈련 기간 데이터로 지수 계산
            train_end_idx = int(len(self.kospi_data) * self.train_ratio)
            train_end_date = self.kospi_data.index[train_end_idx]
            
            index_series = self.calculate_index_with_params(params, end_date=train_end_date)
            
            if len(index_series) < 100:  # 최소 데이터 요구사항
                return 1000  # 큰 페널티
            
            # 매매 신호 생성 및 성과 평가
            signals = self.calculate_trading_signals(index_series)
            performance = self.evaluate_performance(signals)
            
            # ROI 스코어 반환 (음수로 변환하여 최소화 문제로)
            roi_score = performance['roi_score']
            
            return -roi_score  # 최소화를 위해 음수 반환
            
        except Exception as e:
            logger.error(f"목적 함수 계산 중 오류: {e}")
            return 1000  # 오류시 큰 페널티
    
    def grid_search_optimization(self, max_combinations=1000):
        """
        그리드 서치를 통한 파라미터 최적화
        
        Args:
            max_combinations (int): 최대 조합 수
        """
        logger.info("그리드 서치 최적화 시작")
        
        # 각 파라미터의 후보값 생성 (3~5개씩)
        param_candidates = {}
        for param, (min_val, max_val) in self.param_ranges.items():
            if isinstance(min_val, int):
                candidates = list(range(int(min_val), int(max_val) + 1, max(1, (int(max_val) - int(min_val)) // 4)))
            else:
                candidates = np.linspace(min_val, max_val, 5)
            param_candidates[param] = candidates
        
        # 전체 조합 수 계산
        total_combinations = np.prod([len(candidates) for candidates in param_candidates.values()])
        logger.info(f"총 {total_combinations}개의 조합 중 {min(max_combinations, total_combinations)}개 테스트")
        
        # 랜덤 샘플링으로 조합 수 제한
        param_keys = list(param_candidates.keys())
        all_combinations = list(itertools.product(*param_candidates.values()))
        
        if len(all_combinations) > max_combinations:
            np.random.seed(42)
            selected_combinations = np.random.choice(len(all_combinations), max_combinations, replace=False)
            combinations_to_test = [all_combinations[i] for i in selected_combinations]
        else:
            combinations_to_test = all_combinations
        
        best_score = float('inf')
        best_params_combo = None
        
        for i, combination in enumerate(combinations_to_test):
            params = {param_keys[j]: combination[j] for j in range(len(param_keys))}
            
            # 파라미터 배열로 변환하여 목적 함수 호출
            param_array = [params[key] for key in param_keys]
            score = self.objective_function(param_array)
            
            if score < best_score:
                best_score = score
                best_params_combo = params.copy()
                logger.info(f"새로운 최적 조합 발견 (조합 {i+1}): ROI 스코어 = {-score:.4f}")
            
            if (i + 1) % 100 == 0:
                logger.info(f"진행률: {i+1}/{len(combinations_to_test)} ({(i+1)/len(combinations_to_test)*100:.1f}%)")
        
        self.best_params = best_params_combo
        self.best_roi = -best_score
        logger.info(f"그리드 서치 완료. 최적 ROI 스코어: {self.best_roi:.4f}")
        
        return best_params_combo
    
    def differential_evolution_optimization(self, maxiter=100):
        """
        Differential Evolution을 통한 파라미터 최적화
        
        Args:
            maxiter (int): 최대 반복 횟수
        """
        logger.info("Differential Evolution 최적화 시작")
        
        # 파라미터 범위를 bounds 형식으로 변환
        bounds = [self.param_ranges[key] for key in self.param_ranges.keys()]
        
        # 최적화 실행
        result = differential_evolution(
            self.objective_function,
            bounds,
            maxiter=maxiter,
            popsize=15,
            seed=42,
            disp=True
        )
        
        # 결과 처리
        if result.success:
            param_keys = list(self.param_ranges.keys())
            optimized_params = {key: result.x[i] for i, key in enumerate(param_keys)}
            
            # 정크본드 가중치 정규화
            total_junk_weight = optimized_params['junk_bond_aam_weight'] + optimized_params['junk_bond_bbbp_weight']
            if total_junk_weight > 0:
                optimized_params['junk_bond_aam_weight'] /= total_junk_weight
                optimized_params['junk_bond_bbbp_weight'] /= total_junk_weight
            
            self.best_params = optimized_params
            self.best_roi = -result.fun
            
            logger.info(f"최적화 완료. 최적 ROI 스코어: {self.best_roi:.4f}")
            return optimized_params
        else:
            logger.error("최적화 실패")
            return None
    
    def backtest_optimized_params(self):
        """최적화된 파라미터로 전체 기간 백테스팅을 수행합니다."""
        if self.best_params is None:
            logger.error("최적화된 파라미터가 없습니다. 먼저 최적화를 실행하세요.")
            return None
        
        logger.info("최적화된 파라미터로 전체 기간 백테스팅 시작")
        
        # 전체 기간 지수 계산
        index_series = self.calculate_index_with_params(self.best_params)
        
        # 매매 신호 생성
        signals = self.calculate_trading_signals(index_series)
        
        # 성과 평가
        performance = self.evaluate_performance(signals)
        
        # 테스트 기간 성과도 별도 계산
        train_end_idx = int(len(self.kospi_data) * self.train_ratio)
        test_signals = signals.iloc[train_end_idx:]
        test_performance = self.evaluate_performance(test_signals)
        
        results = {
            'full_period': performance,
            'test_period': test_performance,
            'signals': signals,
            'index_series': index_series,
            'optimized_params': self.best_params
        }
        
        logger.info(f"백테스팅 완료")
        logger.info(f"전체 기간 ROI: {performance['total_return']:.2%}")
        logger.info(f"테스트 기간 ROI: {test_performance['total_return']:.2%}")
        logger.info(f"샤프 비율: {performance['sharpe_ratio']:.4f}")
        
        return results
    
    def apply_optimized_params(self):
        """최적화된 파라미터를 실제 시스템에 적용합니다."""
        if self.best_params is None:
            logger.error("최적화된 파라미터가 없습니다.")
            return False
        
        try:
            # 현재 설정 파일 백업
            import shutil
            backup_file = f"config/settings_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
            shutil.copy("config/settings.py", backup_file)
            logger.info(f"기존 설정 파일 백업: {backup_file}")
            
            # settings.py 파일 업데이트
            with open("config/settings.py", 'r', encoding='utf-8') as f:
                content = f.read()
            
            # INDEX_PARAMS 부분 찾아서 교체
            import re
            
            # 새로운 파라미터 딕셔너리 문자열 생성
            new_params_str = "INDEX_PARAMS = {\n"
            for key, value in self.best_params.items():
                if isinstance(value, float):
                    new_params_str += f"    '{key}': {value:.6f},\n"
                else:
                    new_params_str += f"    '{key}': {value},\n"
            new_params_str += "}"
            
            # INDEX_PARAMS 섹션 교체
            pattern = r'INDEX_PARAMS\s*=\s*\{[^}]*\}'
            updated_content = re.sub(pattern, new_params_str, content, flags=re.DOTALL)
            
            # 파일 쓰기
            with open("config/settings.py", 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            logger.info("최적화된 파라미터가 config/settings.py에 적용되었습니다.")
            
            # 최적화 결과 JSON 파일로 저장
            optimization_results = {
                'optimization_date': datetime.now().isoformat(),
                'best_params': self.best_params,
                'best_roi_score': self.best_roi,
                'param_ranges': self.param_ranges
            }
            
            with open("optimization_results.json", 'w', encoding='utf-8') as f:
                json.dump(optimization_results, f, indent=4, ensure_ascii=False)
            
            logger.info("최적화 결과가 optimization_results.json에 저장되었습니다.")
            return True
            
        except Exception as e:
            logger.error(f"파라미터 적용 중 오류 발생: {e}")
            return False
    
    def visualize_results(self, results):
        """백테스팅 결과를 시각화합니다."""
        try:
            import matplotlib.pyplot as plt
            plt.style.use('default')
            
            signals = results['signals']
            index_series = results['index_series']
            
            fig, axes = plt.subplots(3, 1, figsize=(15, 12))
            
            # 1. 누적 수익률 비교
            axes[0].plot(signals.index, signals['kospi_cumret'], label='KOSPI Buy & Hold', alpha=0.7)
            axes[0].plot(signals.index, signals['strategy_cumret'], label='Fear & Greed Strategy', alpha=0.7)
            axes[0].set_title('Cumulative Returns Comparison')
            axes[0].set_ylabel('Cumulative Return')
            axes[0].legend()
            axes[0].grid(True, alpha=0.3)
            
            # 2. 공포탐욕지수와 매매 신호
            axes[1].plot(index_series.index, index_series, label='Fear & Greed Index', color='blue', alpha=0.7)
            axes[1].axhline(y=25, color='green', linestyle='--', alpha=0.7, label='Buy Signal (25)')
            axes[1].axhline(y=75, color='red', linestyle='--', alpha=0.7, label='Sell Signal (75)')
            axes[1].fill_between(index_series.index, 0, 25, alpha=0.2, color='green', label='Fear Zone')
            axes[1].fill_between(index_series.index, 75, 100, alpha=0.2, color='red', label='Greed Zone')
            axes[1].set_title('Fear & Greed Index with Trading Signals')
            axes[1].set_ylabel('Index Value')
            axes[1].legend()
            axes[1].grid(True, alpha=0.3)
            
            # 3. 포지션과 KOSPI 가격
            axes[2].plot(signals.index, signals['kospi_price'], label='KOSPI Price', alpha=0.7)
            
            # 매수/매도 포인트 표시
            buy_points = signals[signals['position_change'] == 1]
            sell_points = signals[signals['position_change'] == -1]
            
            if not buy_points.empty:
                axes[2].scatter(buy_points.index, buy_points['kospi_price'], 
                              color='green', marker='^', s=100, label='Buy Signal', zorder=5)
            if not sell_points.empty:
                axes[2].scatter(sell_points.index, sell_points['kospi_price'], 
                              color='red', marker='v', s=100, label='Sell Signal', zorder=5)
            
            axes[2].set_title('KOSPI Price with Trading Signals')
            axes[2].set_ylabel('KOSPI Price')
            axes[2].set_xlabel('Date')
            axes[2].legend()
            axes[2].grid(True, alpha=0.3)
            
            plt.tight_layout()
            plt.savefig('optimization_results.png', dpi=300, bbox_inches='tight')
            plt.show()
            
            logger.info("시각화 결과가 optimization_results.png에 저장되었습니다.")
            
        except Exception as e:
            logger.error(f"시각화 중 오류 발생: {e}")
    
    def generate_report(self, results):
        """최적화 결과 리포트를 생성합니다."""
        if results is None:
            return
        
        report = f"""
=== 코스피 공포탐욕지수 최적화 결과 리포트 ===
생성 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

=== 최적화된 파라미터 ===
"""
        for key, value in self.best_params.items():
            if isinstance(value, float):
                report += f"{key}: {value:.6f}\n"
            else:
                report += f"{key}: {value}\n"
        
        report += f"""
=== 백테스팅 성과 (전체 기간) ===
총 수익률: {results['full_period']['total_return']:.2%}
KOSPI 수익률: {results['full_period']['kospi_return']:.2%}
초과 수익률: {results['full_period']['excess_return']:.2%}
샤프 비율: {results['full_period']['sharpe_ratio']:.4f}
최대 낙폭: {results['full_period']['max_drawdown']:.2%}
승률: {results['full_period']['win_rate']:.2%}
총 거래 횟수: {results['full_period']['trade_count']}
ROI 스코어: {results['full_period']['roi_score']:.4f}

=== 백테스팅 성과 (테스트 기간) ===
총 수익률: {results['test_period']['total_return']:.2%}
KOSPI 수익률: {results['test_period']['kospi_return']:.2%}
초과 수익률: {results['test_period']['excess_return']:.2%}
샤프 비율: {results['test_period']['sharpe_ratio']:.4f}
최대 낙폭: {results['test_period']['max_drawdown']:.2%}
승률: {results['test_period']['win_rate']:.2%}
총 거래 횟수: {results['test_period']['trade_count']}
ROI 스코어: {results['test_period']['roi_score']:.4f}

=== 추천 사항 ===
"""
        
        full_roi = results['full_period']['total_return']
        test_roi = results['test_period']['total_return']
        excess_return = results['full_period']['excess_return']
        
        if excess_return > 0.1:  # 10% 이상 초과수익
            report += "✅ 매우 우수한 성과: 최적화된 파라미터 적용을 강력히 권장합니다.\n"
        elif excess_return > 0.05:  # 5% 이상 초과수익
            report += "✅ 우수한 성과: 최적화된 파라미터 적용을 권장합니다.\n"
        elif excess_return > 0:
            report += "⚠️ 양호한 성과: 신중한 검토 후 적용을 고려하세요.\n"
        else:
            report += "❌ 성과 미흡: 추가 최적화가 필요합니다.\n"
        
        if abs(full_roi - test_roi) > 0.1:  # 10% 이상 차이
            report += "⚠️ 주의: 훈련/테스트 기간 성과 차이가 큽니다. 과적합 가능성을 검토하세요.\n"
        
        # 리포트 파일 저장
        with open("optimization_report.txt", 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(report)
        logger.info("최적화 리포트가 optimization_report.txt에 저장되었습니다.")

if __name__ == "__main__":
    # 사용 예시
    tool = HypothesisTestingTool()
    
    # 데이터 로드
    tool.load_data()
    
    # 최적화 실행 (원하는 방법 선택)
    print("최적화 방법을 선택하세요:")
    print("1. 그리드 서치 (빠르지만 제한적)")
    print("2. Differential Evolution (느리지만 정확)")
    
    choice = input("선택 (1 또는 2): ").strip()
    
    if choice == "1":
        tool.grid_search_optimization(max_combinations=500)
    elif choice == "2":
        tool.differential_evolution_optimization(maxiter=50)
    else:
        print("잘못된 선택입니다. 그리드 서치를 실행합니다.")
        tool.grid_search_optimization(max_combinations=500)
    
    # 백테스팅 실행
    results = tool.backtest_optimized_params()
    
    if results:
        # 결과 시각화
        tool.visualize_results(results)
        
        # 리포트 생성
        tool.generate_report(results)
        
        # 파라미터 적용 여부 확인
        apply = input("최적화된 파라미터를 실제 시스템에 적용하시겠습니까? (y/n): ").strip().lower()
        if apply == 'y':
            tool.apply_optimized_params()
            print("최적화 완료! 새로운 파라미터가 적용되었습니다.")
        else:
            print("최적화 결과는 저장되었지만 시스템에는 적용되지 않았습니다.") 