#!/usr/bin/env python3
"""
가설검증 툴 기본 기능 테스트

이 스크립트는 hypothesis_testing_tool의 주요 기능들이 정상 작동하는지 테스트합니다.
"""

import sys
import os
import traceback
from datetime import datetime

# 현재 디렉토리를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from hypothesis_testing_tool import HypothesisTestingTool
    from config.settings import INDEX_PARAMS
    print("✅ 모듈 임포트 성공")
except ImportError as e:
    print(f"❌ 모듈 임포트 실패: {e}")
    sys.exit(1)

def test_basic_functionality():
    """기본 기능 테스트"""
    print("=" * 50)
    print("🧪 가설검증 툴 기본 기능 테스트")
    print("=" * 50)
    
    try:
        # 1. 툴 초기화
        print("1. 툴 초기화 중...")
        tool = HypothesisTestingTool()
        print("   ✅ 초기화 완료")
        
        # 2. 데이터 로드
        print("2. 데이터 로드 중...")
        tool.load_data()
        print(f"   ✅ 데이터 로드 완료")
        print(f"   📊 KOSPI 데이터: {len(tool.kospi_data)}일치")
        print(f"   📅 데이터 기간: {tool.kospi_data.index.min().strftime('%Y-%m-%d')} ~ {tool.kospi_data.index.max().strftime('%Y-%m-%d')}")
        
        # 3. 기본 파라미터로 지수 계산 테스트
        print("3. 지수 계산 테스트 중...")
        test_params = INDEX_PARAMS.copy()
        
        # 최근 1년 데이터로 테스트
        end_date = tool.kospi_data.index.max()
        start_date = end_date - pd.Timedelta(days=365)
        
        index_series = tool.calculate_index_with_params(
            test_params, 
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d')
        )
        
        if len(index_series) > 0:
            print(f"   ✅ 지수 계산 완료: {len(index_series)}개 데이터 포인트")
            print(f"   📈 지수 범위: {index_series.min():.2f} ~ {index_series.max():.2f}")
        else:
            print("   ❌ 지수 계산 실패: 결과가 비어있음")
            return False
        
        # 4. 매매 신호 생성 테스트
        print("4. 매매 신호 생성 테스트 중...")
        signals = tool.calculate_trading_signals(index_series)
        
        if len(signals) > 0:
            print(f"   ✅ 매매 신호 생성 완료: {len(signals)}개 신호")
            buy_signals = (signals['position_change'] == 1).sum()
            sell_signals = (signals['position_change'] == -1).sum()
            print(f"   📊 매수 신호: {buy_signals}회, 매도 신호: {sell_signals}회")
        else:
            print("   ❌ 매매 신호 생성 실패")
            return False
        
        # 5. 성과 평가 테스트
        print("5. 성과 평가 테스트 중...")
        performance = tool.evaluate_performance(signals)
        
        print(f"   ✅ 성과 평가 완료")
        print(f"   📈 총 수익률: {performance['total_return']:.2%}")
        print(f"   📊 KOSPI 수익률: {performance['kospi_return']:.2%}")
        print(f"   🎯 초과 수익률: {performance['excess_return']:.2%}")
        print(f"   📏 샤프 비율: {performance['sharpe_ratio']:.4f}")
        print(f"   📉 최대 낙폭: {performance['max_drawdown']:.2%}")
        print(f"   🎲 승률: {performance['win_rate']:.2%}")
        
        # 6. 파라미터 범위 확인
        print("6. 파라미터 범위 확인...")
        print(f"   ✅ 최적화 대상 파라미터: {len(tool.param_ranges)}개")
        for param, (min_val, max_val) in list(tool.param_ranges.items())[:5]:
            print(f"   📋 {param}: {min_val} ~ {max_val}")
        if len(tool.param_ranges) > 5:
            print(f"   ... 및 {len(tool.param_ranges) - 5}개 더")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 테스트 실패: {e}")
        print("\n🔍 상세 오류 정보:")
        traceback.print_exc()
        return False

def test_small_optimization():
    """소규모 최적화 테스트"""
    print("\n" + "=" * 50)
    print("🔬 소규모 최적화 테스트")
    print("=" * 50)
    
    try:
        tool = HypothesisTestingTool()
        tool.load_data()
        
        print("1. 소규모 그리드 서치 테스트 (10개 조합)...")
        tool.grid_search_optimization(max_combinations=10)
        
        if tool.best_params is not None:
            print(f"   ✅ 최적화 완료")
            print(f"   🏆 최적 ROI 스코어: {tool.best_roi:.4f}")
            print(f"   📋 최적 파라미터 샘플:")
            for key, value in list(tool.best_params.items())[:3]:
                if isinstance(value, float):
                    print(f"      {key}: {value:.6f}")
                else:
                    print(f"      {key}: {value}")
            
            # 간단한 백테스팅
            print("2. 최적화된 파라미터로 백테스팅...")
            results = tool.backtest_optimized_params()
            
            if results:
                print(f"   ✅ 백테스팅 완료")
                print(f"   📈 전체 기간 ROI: {results['full_period']['total_return']:.2%}")
                print(f"   🧪 테스트 기간 ROI: {results['test_period']['total_return']:.2%}")
                return True
            else:
                print("   ❌ 백테스팅 실패")
                return False
        else:
            print("   ❌ 최적화 실패")
            return False
            
    except Exception as e:
        print(f"   ❌ 소규모 최적화 테스트 실패: {e}")
        print("\n🔍 상세 오류 정보:")
        traceback.print_exc()
        return False

def main():
    """메인 테스트 함수"""
    print("🚀 코스피 공포탐욕지수 최적화 툴 테스트")
    print(f"⏰ 테스트 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 기본 기능 테스트
    basic_test_passed = test_basic_functionality()
    
    if basic_test_passed:
        print("\n🎉 기본 기능 테스트 통과!")
        
        # 소규모 최적화 테스트
        optimization_test_passed = test_small_optimization()
        
        if optimization_test_passed:
            print("\n🎉 모든 테스트 통과!")
            print("\n✅ 가설검증 툴이 정상 작동합니다.")
            print("💡 이제 'python run_optimization.py'를 실행하여 본격적인 최적화를 시작할 수 있습니다.")
        else:
            print("\n⚠️ 기본 기능은 작동하지만 최적화에 문제가 있습니다.")
    else:
        print("\n❌ 기본 기능 테스트 실패!")
        print("💡 데이터베이스 파일과 설정을 확인해주세요.")
    
    print(f"\n⏰ 테스트 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    # pandas 임포트
    try:
        import pandas as pd
        print("✅ pandas 임포트 성공")
    except ImportError:
        print("❌ pandas가 설치되어 있지 않습니다. 'pip install pandas'를 실행하세요.")
        sys.exit(1)
    
    main() 