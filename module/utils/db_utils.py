import pandas as pd
import sqlite3
from pathlib import Path
import os
import logging
from datetime import datetime
from config.settings import DB_DIR

# 로깅 설정
# DB_PATH_OVERRIDE 환경 변수가 설정된 경우 로그 경로 조정
if os.environ.get("DB_PATH_OVERRIDE") == "true":
    log_path = "app.log"  # 현재 디렉토리에 로그 생성
else:
    log_path = f"{DB_DIR}/app.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def ensure_db_dir():
    """DB 디렉토리가 존재하는지 확인하고 없으면 생성합니다."""
    try:
        os.makedirs(DB_DIR, exist_ok=True)
        logger.info(f"DB 디렉토리 확인/생성 완료: {DB_DIR}")
    except Exception as e:
        logger.error(f"DB 디렉토리 생성 중 오류 발생: {e}")
        raise

def get_db_connection(db_name='kgf_data.db'):
    """데이터베이스 연결을 반환합니다."""
    try:
        # USE_LOCAL_DB 환경 변수가 설정된 경우 로컬 경로 사용
        if os.environ.get("USE_LOCAL_DB") == "true":
            local_db_path = os.environ.get("LOCAL_DB_PATH", ".")
            db_path = os.path.join(local_db_path, db_name)
            logger.info(f"로컬 DB 경로 사용: {db_path}")
            conn = sqlite3.connect(db_path)
            return conn
        else:
            # 기본 DB_DIR 경로 사용
            ensure_db_dir()
            conn = sqlite3.connect(f'{DB_DIR}/{db_name}')
            return conn
    except Exception as e:
        logger.error(f"DB 연결 중 오류 발생: {e}")
        raise

def is_db_initialized():
    """데이터베이스가 이미 초기화되어 있고 데이터가 있는지 확인합니다."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 필요한 모든 테이블이 존재하는지 확인
        tables = ['vix', 'ten_bond', 'junk_bond', 'pcr', 'breadth', 'kospi', 'kgf_index']
        for table in tables:
            cursor.execute(f"SELECT count(name) FROM sqlite_master WHERE type='table' AND name='{table}'")
            if cursor.fetchone()[0] != 1:
                conn.close()
                logger.info(f"데이터베이스 테이블 {table}이 존재하지 않습니다.")
                return False
                
            # 모든 테이블이 존재하는지만 확인하고 데이터 존재 여부는 검사하지 않음
        
        conn.close()
        logger.info("데이터베이스가 초기화되어 있음")
        return True
    except Exception as e:
        logger.error(f"데이터베이스 초기화 확인 중 오류 발생: {e}")
        return False

def initialize_db():
    """필요한 모든 테이블을 초기화합니다."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # VIX 테이블 생성
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS vix (
            date TEXT PRIMARY KEY,
            vix_close REAL,
            vix_ema REAL,
            vix_ema_spread REAL
        )
        ''')
        
        # 10년물 국채 테이블 생성
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS ten_bond (
            date TEXT PRIMARY KEY,
            ten_ratio REAL,
            bond_ema REAL
        )
        ''')
        
        # 정크본드 테이블 생성
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS junk_bond (
            date TEXT PRIMARY KEY,
            aam REAL,
            bbbp REAL,
            junk_spread REAL
        )
        ''')
        
        # PCR 테이블 생성 - 컬럼명 변경 'p/c_ratio' -> 'p_c_ratio'
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS pcr (
            date TEXT PRIMARY KEY,
            put REAL,
            cal REAL,
            p_c_ratio REAL,
            p_c_ema REAL
        )
        ''')
        
        # Breadth 테이블 생성
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS breadth (
            date TEXT PRIMARY KEY,
            adv_value REAL,
            dec_value REAL,
            diff REAL,
            ema19 REAL,
            ema39 REAL,
            oscillator REAL,
            summation_index REAL,
            mcclenllan REAL
        )
        ''')
        
        # KOSPI 테이블 생성
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS kospi (
            date TEXT PRIMARY KEY,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            ema REAL,
            ema_spread REAL,
            bf_20 REAL,
            return_20 REAL
        )
        ''')
        
        # 주가 강도 테이블 생성
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_strength (
            date TEXT PRIMARY KEY,
            high_count INTEGER,
            low_count INTEGER, 
            total_count INTEGER,
            strength_ratio REAL,
            strength_index REAL
        )
        ''')
        
        # KGF 인덱스 테이블 생성
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS kgf_index (
            date TEXT PRIMARY KEY,
            ema_spread_scaled REAL,
            mcclenllan_scaled REAL,
            p_c_ema_scaled REAL,
            vix_ema_spread_scaled REAL,
            safe_spread_scaled REAL,
            junk_spread_scaled REAL,
            stock_strength_scaled REAL,
            index_value REAL,
            kospi_close REAL
        )
        ''')
        
        conn.commit()
        conn.close()
        
        logger.info("데이터베이스 테이블이 초기화되었습니다.")
    except Exception as e:
        logger.error(f"데이터베이스 초기화 중 오류 발생: {e}")
        raise

def get_table_as_df(table_name):
    """지정된 테이블의 데이터를 DataFrame으로 반환합니다."""
    try:
        conn = get_db_connection()
        query = f"SELECT * FROM {table_name}"
        df = pd.read_sql(query, conn, parse_dates=['date'])
        df = df.set_index('date')
        
        # PCR 테이블인 경우 컬럼명 확인 및 필요시 변환
        if table_name == 'pcr':
            if 'p/c_ratio' in df.columns and 'p_c_ratio' not in df.columns:
                # p/c_ratio 컬럼을 p_c_ratio로 변환
                df['p_c_ratio'] = df['p/c_ratio']
                logger.info("PCR 테이블에서 'p/c_ratio' 컬럼을 'p_c_ratio'로 변환했습니다.")
        
        # 중복된 인덱스 제거
        duplicated = df.index.duplicated(keep='first')
        if duplicated.any():
            dup_count = duplicated.sum()
            logger.warning(f"테이블 {table_name}에서 {dup_count}개의 중복 인덱스가 발견되어 제거됩니다.")
            df = df[~duplicated]
        
        conn.close()
        logger.debug(f"테이블 {table_name}에서 {len(df)} 행의 데이터를 조회했습니다.")
        return df
    except Exception as e:
        logger.error(f"테이블 {table_name}에서 데이터 조회 중 오류 발생: {e}")
        raise

def get_last_date(table_name):
    """지정된 테이블의 가장 최근 날짜를 반환합니다."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT MAX(date) FROM {table_name}")
        last_date = cursor.fetchone()[0]
        conn.close()
        
        if last_date:
            try:
                # 날짜+시간 형식 시도
                date_obj = datetime.strptime(last_date, '%Y-%m-%d %H:%M:%S')
                logger.debug(f"테이블 {table_name}의 최근 날짜: {date_obj}")
                return date_obj
            except ValueError:
                try:
                    # 날짜만 있는 형식 시도
                    date_obj = datetime.strptime(last_date, '%Y-%m-%d')
                    logger.debug(f"테이블 {table_name}의 최근 날짜: {date_obj}")
                    return date_obj
                except ValueError:
                    # 다른 날짜 형식 처리
                    logger.warning(f"테이블 {table_name}에서 인식할 수 없는 날짜 형식입니다: {last_date}")
                    return None
        logger.debug(f"테이블 {table_name}에 날짜 데이터가 없습니다.")
        return None
    except Exception as e:
        logger.error(f"테이블 {table_name}의 최근 날짜 조회 중 오류 발생: {e}")
        return None
    
def save_df_to_db(df, table_name, if_exists='append'):
    """DataFrame을 데이터베이스 테이블에 저장합니다."""
    try:
        conn = get_db_connection()
        df.to_sql(table_name, conn, if_exists=if_exists, index=True)
        conn.close()
        logger.debug(f"테이블 {table_name}에 {len(df)} 행의 데이터를 저장했습니다. (방식: {if_exists})")
    except Exception as e:
        logger.error(f"테이블 {table_name}에 데이터 저장 중 오류 발생: {e}")
        raise

def upsert_df_to_db(df, table_name):
    """DataFrame을 데이터베이스에 UPSERT 방식으로 저장합니다."""
    try:
        # DataFrame이 비어있는 경우 처리하지 않음
        if df.empty:
            logger.warning(f"빈 DataFrame이 제공되어 {table_name}에 UPSERT를 수행하지 않습니다.")
            return
            
        # 인덱스가 date로 설정되어 있지 않은 경우 처리
        if df.index.name != 'date':
            logger.warning("DataFrame의 인덱스가 'date'가 아닙니다. 인덱스를 리셋합니다.")
            if 'date' in df.columns:
                df = df.set_index('date')
            else:
                logger.error("DataFrame에 'date' 컬럼이 없습니다. UPSERT를 수행할 수 없습니다.")
                return
                
        # 기존 테이블에서 데이터를 가져와 날짜 형식 확인
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT date FROM {table_name} LIMIT 1")
        date_format_sample = cursor.fetchone()
        
        # date를 문자열로 변환하여 컬럼으로 추가
        df = df.reset_index()
        if pd.api.types.is_datetime64_any_dtype(df['date']):
            # 기존 날짜 형식이 "2025-03-17 00:00:00"인 경우 동일하게 맞춤
            if date_format_sample and ' 00:00:00' in date_format_sample[0]:
                df['date'] = df['date'].dt.strftime('%Y-%m-%d 00:00:00')
            else:
                df['date'] = df['date'].dt.strftime('%Y-%m-%d')
        
        # NULL 값 제거 (선택적)
        numeric_columns = df.select_dtypes(include=['number']).columns
        if len(numeric_columns) > 0:
            df = df.dropna(subset=numeric_columns, how='all')
        
        # 테이블의 컬럼 정보 가져오기
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        
        # DataFrame에서 테이블에 존재하는 컬럼만 선택
        common_columns = [col for col in df.columns if col in columns]
        df = df[common_columns]
        
        # 각 행에 대해 UPSERT 수행
        for _, row in df.iterrows():
            date_val = row['date']
            
            # 해당 날짜의 데이터가 존재하는지 확인
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE date = ?", (date_val,))
            exists = cursor.fetchone()[0] > 0
            
            if exists:
                # 기존 데이터 업데이트
                # 모든 컬럼명을 따옴표로 묶어 특수문자 처리
                set_clause = ", ".join([f'"{col}" = ?' for col in common_columns if col != 'date'])
                values = [row[col] for col in common_columns if col != 'date']
                values.append(date_val)  # WHERE 조건
                
                if set_clause:  # 업데이트할 컬럼이 있는 경우만 수행
                    cursor.execute(f'UPDATE {table_name} SET {set_clause} WHERE date = ?', values)
                    logger.debug(f"테이블 {table_name}의 날짜 {date_val} 데이터를 업데이트했습니다.")
            else:
                # 새 데이터 삽입
                # 모든 컬럼명을 따옴표로 묶어 특수문자 처리
                columns_str = ", ".join([f'"{col}"' for col in common_columns])
                placeholders = ", ".join(["?" for _ in common_columns])
                values = [row[col] for col in common_columns]
                
                cursor.execute(f'INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})', values)
                logger.debug(f"테이블 {table_name}에 날짜 {date_val}의 새 데이터를 삽입했습니다.")
        
        conn.commit()
        conn.close()
        logger.info(f"테이블 {table_name}에 총 {len(df)} 행의 데이터를 UPSERT 방식으로 처리했습니다.")
    except Exception as e:
        logger.error(f"테이블 {table_name}에 UPSERT 중 오류 발생: {e}")
        raise 