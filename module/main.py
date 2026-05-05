import pandas as pd
import numpy as np
import logging
import argparse
import json
import os
from datetime import datetime
from data.scraper import DataScraper
from data.processor import DataProcessor
from github import Github
from config.settings import GITHUB_TOKEN, GITHUB_REPO, Y_LIST, INDEX_PARAMS, DB_DIR
from utils.db_utils import initialize_db, get_last_date, is_db_initialized

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"{DB_DIR}/app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class KGFManager:
    def __init__(self):
        self.scraper = DataScraper()
        self.processor = DataProcessor()
        self.data_frames = {}

    def initialize_database(self):
        """데이터베이스를 초기화합니다."""
        # 데이터베이스가 이미 초기화되어 있는지 확인
        if is_db_initialized():
            print("데이터베이스가 이미 초기화되어 있고 데이터가 있습니다.")
            return
        
        # DB 테이블 초기화
        try:
            initialize_db()
            print("데이터베이스 테이블이 성공적으로 초기화되었습니다.")
        except Exception as e:
            print(f"데이터베이스 초기화 중 오류 발생: {e}")
    
    def load_data_from_db(self):
        """데이터베이스에서 데이터를 로드합니다."""
        self.scraper.load_data_from_db()
        
        # 데이터 프레임 복사
        self.data_frames = {
            'vix_df': self.scraper.vix_df,
            'tenBond_df': self.scraper.tenBond_df,
            'junkBond_df': self.scraper.junkBond_df,
            'pcr_df': self.scraper.pcr_df,
            'breadth_df': self.scraper.breadth_df,
            'kospi_df': self.scraper.kospi_df
        }

    def update_all_data(self):
        """모든 데이터를 업데이트합니다."""
        # VIX 데이터 업데이트
        self.scraper.scrape_vix_data()
        
        # 10년물 국채 데이터 업데이트
        self.scraper.scrape_10ybond_data()
        
        # PCR 데이터 업데이트
        self.scraper.scrape_pcr_data()
        
        # Breadth 데이터 업데이트
        last_breadth_date = get_last_date('breadth')
        if last_breadth_date:
            self.scraper.scrape_breadth_data(last_breadth_date)
        else:
            self.scraper.scrape_breadth_data()
        
        # 정크본드 데이터 업데이트
        last_junkbond_date = get_last_date('junk_bond')
        if last_junkbond_date:
            self.scraper.scrape_junkbond_data(last_junkbond_date)
        else:
            self.scraper.scrape_junkbond_data()
        
        # KOSPI 데이터 업데이트
        last_kospi_date = get_last_date('kospi')
        if last_kospi_date:
            self.scraper.scrape_kospi_data(last_kospi_date.strftime('%Y-%m-%d'))
        else:
            self.scraper.scrape_kospi_data()
            
        # 주가 강도 데이터 업데이트
        self.scraper.calculate_stock_strength()
        
        # 데이터 프레임 갱신
        self.load_data_from_db()

    def update_github(self):
        """GitHub 저장소를 업데이트합니다."""
        g = Github(GITHUB_TOKEN)
        repo = g.get_user().get_repo(GITHUB_REPO)

        all_files = []
        contents = repo.get_contents("")
        while contents:
            file_content = contents.pop(0)
            if file_content.type == "dir":
                contents.extend(repo.get_contents(file_content.path))
            else:
                file = file_content
                all_files.append(str(file).replace('ContentFile(path="', '').replace('")', ''))

        y_list = Y_LIST + ['index', 'value', 'factor_status']
        git_prefix = 'assets/js/json/'

        for y in y_list:
            git_file = git_prefix + y + '.json'
            with open("./json/" + y + '.json', 'rb') as f:
                content = f.read()

            if git_file in all_files:
                contents = repo.get_contents(git_file)
                repo.update_file(contents.path, "committing files", content, contents.sha, branch="main")
                print(git_file + ' UPDATED')
            else:
                repo.create_file(git_file, "committing files", content, branch="main")
                print(git_file + ' CREATED')

def check_and_initialize_db():
    """데이터베이스가 초기화되어 있는지 확인하고, 필요한 경우 초기화합니다."""
    if not is_db_initialized():
        logger.info("데이터베이스 초기화 필요: 테이블을 초기화합니다.")
        initialize_db()
    else:
        logger.info("데이터베이스가 이미 초기화되어 있습니다.")

def load_custom_params(params_file):
    """사용자 정의 파라미터 파일을 로드합니다."""
    try:
        if not os.path.exists(params_file):
            logger.warning(f"파라미터 파일을 찾을 수 없습니다: {params_file}")
            return None
            
        with open(params_file, 'r') as f:
            custom_params = json.load(f)
            logger.info(f"사용자 정의 파라미터 로드됨: {params_file}")
            return custom_params
    except Exception as e:
        logger.error(f"파라미터 파일 로드 중 오류 발생: {e}")
        return None

def save_params_to_file(params, filename):
    """현재 파라미터를 파일로 저장합니다."""
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w') as f:
            json.dump(params, f, indent=4)
        logger.info(f"파라미터가 파일에 저장됨: {filename}")
        return True
    except Exception as e:
        logger.error(f"파라미터 저장 중 오류 발생: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='KOSPI 공포/탐욕 지수 데이터 처리 및 계산')
    parser.add_argument('--params', type=str, help='사용자 정의 파라미터 JSON 파일 경로')
    parser.add_argument('--save-params', type=str, help='현재 사용 중인 파라미터를 JSON 파일로 저장')
    parser.add_argument('--skip-scrape', action='store_true', help='스크래핑 단계 건너뛰기')
    parser.add_argument('--force-update', action='store_true', help='마지막 날짜와 관계없이 모든 데이터 업데이트 강제 실행')
    args = parser.parse_args()

    # 데이터베이스 초기화 확인
    check_and_initialize_db()

    # 사용자 정의 파라미터 로드
    custom_params = None
    if args.params:
        custom_params = load_custom_params(args.params)

    # 스크래핑 단계
    if not args.skip_scrape:
        logger.info("데이터 스크래핑 시작")
        scraper = DataScraper()
        scraper.load_data_from_db()
        
        # 모든 데이터에 대해 마지막 업데이트 날짜 확인
        last_update = {
            'kospi': get_last_date('kospi'),
            'vix': get_last_date('vix'),
            'ten_bond': get_last_date('ten_bond'),
            'pcr': get_last_date('pcr'),
            'breadth': get_last_date('breadth'),
            'junk_bond': get_last_date('junk_bond')
        }
        
        logger.info(f"마지막 데이터 업데이트 상태: {last_update}")
        
        # 현재 날짜
        today = datetime.now()
        
        # KOSPI 데이터 업데이트 (마지막 날짜가 오늘 이전이거나 강제 업데이트인 경우)
        if args.force_update or not last_update['kospi'] or last_update['kospi'].date() < today.date():
            if last_update['kospi']:
                start_date = last_update['kospi'].strftime('%Y-%m-%d')
                logger.info(f"KOSPI 데이터 업데이트: {start_date}부터")
                scraper.scrape_kospi_data(start_date)
            else:
                logger.info("KOSPI 데이터 전체 수집")
                scraper.scrape_kospi_data()
        else:
            logger.info("KOSPI 데이터가 이미 최신 상태입니다.")
        
        # VIX 데이터 업데이트 (마지막 날짜가 오늘 이전이거나 강제 업데이트인 경우)
        if args.force_update or not last_update['vix'] or last_update['vix'].date() < today.date():
            logger.info("VIX 데이터 업데이트")
            scraper.scrape_vix_data()
        else:
            logger.info("VIX 데이터가 이미 최신 상태입니다.")
        
        # 10년물 국채 데이터 업데이트
        if args.force_update or not last_update['ten_bond'] or last_update['ten_bond'].date() < today.date():
            logger.info("10년물 국채 데이터 업데이트")
            scraper.scrape_10ybond_data()
        else:
            logger.info("10년물 국채 데이터가 이미 최신 상태입니다.")
        
        # PCR 데이터 업데이트
        if args.force_update or not last_update['pcr'] or last_update['pcr'].date() < today.date():
            logger.info("PCR 데이터 업데이트")
            scraper.scrape_pcr_data()
        else:
            logger.info("PCR 데이터가 이미 최신 상태입니다.")
        
        # Breadth 데이터 업데이트
        if args.force_update or not last_update['breadth'] or last_update['breadth'].date() < today.date():
            if last_update['breadth']:
                logger.info(f"Breadth 데이터 업데이트: {last_update['breadth']}부터")
                scraper.scrape_breadth_data(last_update['breadth'])
            else:
                logger.info("Breadth 데이터 전체 수집")
                scraper.scrape_breadth_data()
        else:
            logger.info("Breadth 데이터가 이미 최신 상태입니다.")
        
        # 정크본드 데이터 업데이트
        if args.force_update or not last_update['junk_bond'] or last_update['junk_bond'].date() < today.date():
            if last_update['junk_bond']:
                logger.info(f"정크본드 데이터 업데이트: {last_update['junk_bond']}부터")
                scraper.scrape_junkbond_data(last_update['junk_bond'])
            else:
                logger.info("정크본드 데이터 전체 수집")
                scraper.scrape_junkbond_data()
        else:
            logger.info("정크본드 데이터가 이미 최신 상태입니다.")
        
        # 주가 강도 계산
        logger.info("주가 강도 데이터 계산")
        scraper.calculate_stock_strength()
        
        logger.info("데이터 스크래핑 완료")
    else:
        logger.info("스크래핑 단계 건너뜀")

    # 데이터 처리 및 지수 계산
    logger.info("데이터 처리 및 지수 계산 시작")
    processor = DataProcessor(custom_params)
    processor.process_data()
    processor.write_json()
    logger.info("데이터 처리 및 JSON 생성 완료")

    # 현재 파라미터 저장
    if args.save_params:
        save_params_to_file(processor.get_current_params(), args.save_params)

    # GitHub 업데이트
    kgf = KGFManager()
    kgf.update_github()

if __name__ == "__main__":
    main() 