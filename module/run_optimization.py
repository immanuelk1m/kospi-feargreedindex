#!/usr/bin/env python3
"""
코스피 공포탐욕지수 최적화 실행 스크립트

사용법:
    python run_optimization.py

이 스크립트는 다음을 수행합니다:
1. 데이터베이스에서 데이터 로드
2. 사용자가 선택한 최적화 방법 실행
3. 백테스팅 및 성과 평가
4. 결과 시각화 및 리포트 생성
5. 최적화된 파라미터를 실제 시스템에 적용 (선택사항)
"""

import sys
import os
import traceback
from datetime import datetime

# 현재 디렉토리를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hypothesis_testing_tool import HypothesisTestingTool

def print_banner():
    """배너 출력"""
    print("=" * 70)
    print("🚀 코스피 공포탐욕지수 최적화 도구")
    print("   KOSPI Fear & Greed Index Optimization Tool")
    print("=" * 70)
    print(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

def print_menu():
    """메뉴 출력"""
    print("🔧 최적화 방법을 선택하세요:")
    print("1. 그리드 서치 (Grid Search)")
    print("   - 빠른 실행 (10-30분)")
    print("   - 제한된 파라미터 조합 테스트")
    print("   - 초기 실험에 적합")
    print()
    print("2. Differential Evolution")
    print("   - 정밀한 최적화 (30-120분)")
    print("   - 전역 최적해 탐색")
    print("   - 최종 운영에 적합")
    print()
    print("3. 빠른 테스트 (Fast Test)")
    print("   - 기본 파라미터로 간단한 백테스팅")
    print("   - 1-5분 소요")
    print("   - 시스템 검증용")
    print()

def get_user_choice():
    """사용자 입력 받기"""
    while True:
        try:
            choice = input("선택하세요 (1, 2, 3): ").strip()
            if choice in ['1', '2', '3']:
                return int(choice)
            else:
                print("❌ 잘못된 입력입니다. 1, 2, 3 중 하나를 선택하세요.")
        except KeyboardInterrupt:
            print("\n\n👋 프로그램을 종료합니다.")
            sys.exit(0)

def run_fast_test(tool):
    """빠른 테스트 실행"""
    print("⚡ 빠른 테스트 모드")
    print("기본 파라미터로 백테스팅을 수행합니다...")
    
    # 기본 파라미터 사용
    from config.settings import INDEX_PARAMS
    tool.best_params = INDEX_PARAMS
    
    # 백테스팅 실행
    results = tool.backtest_optimized_params()
    return results

def run_grid_search(tool):
    """그리드 서치 실행"""
    print("🔍 그리드 서치 최적화")
    
    # 조합 수 선택
    print("테스트할 파라미터 조합 수를 선택하세요:")
    print("1. 빠른 탐색 (200개 조합, ~10분)")
    print("2. 보통 탐색 (500개 조합, ~20분)")
    print("3. 정밀 탐색 (1000개 조합, ~40분)")
    
    while True:
        try:
            combinations_choice = input("선택하세요 (1, 2, 3): ").strip()
            if combinations_choice == '1':
                max_combinations = 200
                break
            elif combinations_choice == '2':
                max_combinations = 500
                break
            elif combinations_choice == '3':
                max_combinations = 1000
                break
            else:
                print("❌ 잘못된 입력입니다.")
        except KeyboardInterrupt:
            print("\n\n👋 프로그램을 종료합니다.")
            sys.exit(0)
    
    print(f"🚀 {max_combinations}개 조합으로 그리드 서치를 시작합니다...")
    tool.grid_search_optimization(max_combinations=max_combinations)
    
    # 백테스팅 실행
    results = tool.backtest_optimized_params()
    return results

def run_differential_evolution(tool):
    """Differential Evolution 실행"""
    print("🧬 Differential Evolution 최적화")
    
    # 반복 횟수 선택
    print("최적화 정밀도를 선택하세요:")
    print("1. 빠른 최적화 (30회 반복, ~15분)")
    print("2. 보통 최적화 (50회 반복, ~30분)")
    print("3. 정밀 최적화 (100회 반복, ~60분)")
    
    while True:
        try:
            iterations_choice = input("선택하세요 (1, 2, 3): ").strip()
            if iterations_choice == '1':
                maxiter = 30
                break
            elif iterations_choice == '2':
                maxiter = 50
                break
            elif iterations_choice == '3':
                maxiter = 100
                break
            else:
                print("❌ 잘못된 입력입니다.")
        except KeyboardInterrupt:
            print("\n\n👋 프로그램을 종료합니다.")
            sys.exit(0)
    
    print(f"🚀 {maxiter}회 반복으로 DE 최적화를 시작합니다...")
    tool.differential_evolution_optimization(maxiter=maxiter)
    
    # 백테스팅 실행
    results = tool.backtest_optimized_params()
    return results

def show_results_summary(results):
    """결과 요약 출력"""
    if results is None:
        print("❌ 최적화 실패")
        return
    
    print("\n" + "=" * 50)
    print("📊 최적화 결과 요약")
    print("=" * 50)
    
    full_period = results['full_period']
    test_period = results['test_period']
    
    print(f"📈 전체 기간 성과:")
    print(f"   총 수익률: {full_period['total_return']:.2%}")
    kospi_ret = full_period.get('kospi_return', 0)
    print(f"   KOSPI 수익률: {kospi_ret:.2%}")
    print(f"   초과 수익률: {full_period['excess_return']:.2%}")
    print(f"   샤프 비율: {full_period['sharpe_ratio']:.4f}")
    print(f"   최대 낙폭: {full_period['max_drawdown']:.2%}")
    print(f"   승률: {full_period['win_rate']:.2%}")
    print(f"   거래 횟수: {full_period['trade_count']}")
    
    print(f"\n🧪 테스트 기간 성과:")
    print(f"   총 수익률: {test_period['total_return']:.2%}")
    print(f"   초과 수익률: {test_period['excess_return']:.2%}")
    print(f"   샤프 비율: {test_period['sharpe_ratio']:.4f}")
    
    # 성과 평가
    excess_return = full_period['excess_return']
    if excess_return > 0.1:
        print("\n✅ 매우 우수한 성과!")
        recommendation = "강력 추천"
    elif excess_return > 0.05:
        print("\n✅ 우수한 성과!")
        recommendation = "추천"
    elif excess_return > 0:
        print("\n⚠️ 양호한 성과")
        recommendation = "신중 검토"
    else:
        print("\n❌ 성과 미흡")
        recommendation = "재최적화 필요"
    
    print(f"📋 권장 사항: {recommendation}")

def ask_apply_params():
    """파라미터 적용 여부 확인"""
    print("\n" + "=" * 50)
    print("⚙️ 시스템 적용")
    print("=" * 50)
    print("최적화된 파라미터를 실제 시스템에 적용하시겠습니까?")
    print("(현재 설정은 자동으로 백업됩니다)")
    print()
    
    while True:
        try:
            apply = input("적용하시겠습니까? (y/n): ").strip().lower()
            if apply in ['y', 'yes']:
                return True
            elif apply in ['n', 'no']:
                return False
            else:
                print("❌ y 또는 n을 입력하세요.")
        except KeyboardInterrupt:
            print("\n\n👋 프로그램을 종료합니다.")
            return False

def main():
    """메인 함수"""
    try:
        print_banner()
        
        # 툴 초기화
        print("🔄 시스템 초기화 중...")
        tool = HypothesisTestingTool()
        
        # 데이터 로드
        print("📊 데이터 로드 중...")
        tool.load_data()
        print("✅ 데이터 로드 완료")
        print(f"   KOSPI 데이터: {len(tool.kospi_data)}일치")
        print(f"   데이터 기간: {tool.kospi_data.index.min().strftime('%Y-%m-%d')} ~ {tool.kospi_data.index.max().strftime('%Y-%m-%d')}")
        print()
        
        # 메뉴 출력 및 선택
        print_menu()
        choice = get_user_choice()
        
        print("\n" + "🚀 최적화 시작" + "=" * 40)
        start_time = datetime.now()
        
        # 선택에 따른 최적화 실행
        if choice == 1:
            results = run_grid_search(tool)
        elif choice == 2:
            results = run_differential_evolution(tool)
        elif choice == 3:
            results = run_fast_test(tool)
        
        end_time = datetime.now()
        elapsed_time = end_time - start_time
        
        print(f"⏱️ 소요 시간: {elapsed_time}")
        
        # 결과 처리
        if results:
            show_results_summary(results)
            
            # 시각화 및 리포트 생성
            print("\n📈 결과 시각화 중...")
            tool.visualize_results(results)
            
            print("📄 리포트 생성 중...")
            tool.generate_report(results)
            
            # 파라미터 적용 여부 확인
            if choice != 3:  # 빠른 테스트가 아닌 경우만
                if ask_apply_params():
                    if tool.apply_optimized_params():
                        print("✅ 파라미터가 성공적으로 적용되었습니다!")
                        print("💡 이제 'python main.py'를 실행하여 새로운 지수를 계산할 수 있습니다.")
                    else:
                        print("❌ 파라미터 적용에 실패했습니다.")
                else:
                    print("ℹ️ 파라미터가 적용되지 않았습니다.")
                    print("💡 나중에 optimization_results.json을 참조하여 수동으로 적용할 수 있습니다.")
        
        print("\n" + "=" * 70)
        print("🎉 최적화 완료!")
        print("📁 생성된 파일들:")
        print("   - optimization_results.png (시각화 결과)")
        print("   - optimization_report.txt (상세 리포트)")
        print("   - optimization_results.json (최적화 파라미터)")
        print("=" * 70)
        
    except KeyboardInterrupt:
        print("\n\n👋 사용자에 의해 프로그램이 중단되었습니다.")
    except Exception as e:
        print(f"\n❌ 오류가 발생했습니다: {e}")
        print("\n🔍 상세 오류 정보:")
        traceback.print_exc()
        print("\n💡 문제가 지속되면 데이터베이스 파일과 설정을 확인해주세요.")
    
    input("\n엔터를 눌러 종료하세요...")

if __name__ == "__main__":
    main() 