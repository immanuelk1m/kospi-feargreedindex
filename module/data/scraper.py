import pandas as pd
import numpy as np
from pykrx import stock
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import sqlite3
import time
import logging
import base64
import json
import zlib
import xml.etree.ElementTree as ET
from config.settings import KRX_URL, NICE_RATING_URL, INVESTING_URL, HEADERS, DB_DIR
from utils.helpers import date_range_f
from utils.db_utils import get_db_connection, get_table_as_df, get_last_date, upsert_df_to_db
from utils.krx_auth import install_pykrx_auth_proxy, krx_post_json

# 로거 가져오기
logger = logging.getLogger(__name__)

TE_10Y_MARKET_URL = "https://d3ii0wo49og5mi.cloudfront.net/markets/gvsk10yr:gov"
TE_CHART_DECODE_KEY = b"tradingeconomics-charts-core-api-key"
NAVER_INDEX_CHART_URL = "https://fchart.stock.naver.com/sise.nhn"
KOSPI_NAVER_SYMBOL = "KOSPI"
KOSPI_KRX_TICKER = "1001"
KOSPI_OHLCV_COLUMNS = ["시가", "고가", "저가", "종가", "거래량"]

class DataScraper:
    def __init__(self):
        install_pykrx_auth_proxy()
        self.vix_df = None
        self.tenBond_df = None
        self.junkBond_df = None
        self.pcr_df = None
        self.breadth_df = None
        self.kospi_df = None

    def load_data_from_db(self):
        """데이터베이스에서 각 테이블의 데이터를 로드합니다."""
        try:
            logger.info("데이터베이스에서 데이터 로드 시작")
            self.vix_df = get_table_as_df('vix')
            self.tenBond_df = get_table_as_df('ten_bond')
            self.junkBond_df = get_table_as_df('junk_bond')
            self.pcr_df = get_table_as_df('pcr')
            self.breadth_df = get_table_as_df('breadth')
            self.kospi_df = get_table_as_df('kospi')
            logger.info("데이터베이스에서 데이터 로드 완료")
        except Exception as e:
            logger.error(f"데이터베이스에서 데이터 로드 중 오류 발생: {e}")
            raise

    def scrape_kospi_data(self, start_date=None):
        """KOSPI 데이터를 수집합니다."""
        try:
            if start_date is None:
                # 가장 최근 날짜 가져오기
                last_date = get_last_date('kospi')
                if last_date:
                    start_date = last_date.strftime('%Y-%m-%d')
                else:
                    start_date = '2025-05-03'
            
            today = datetime.today().strftime('%Y-%m-%d')
            logger.info(f"KOSPI 데이터 수집 시작: {start_date} ~ {today}")
            
            # 현재 날짜와 start_date가 같은 경우 하루 전부터 시작하도록 설정
            if start_date == today:
                yesterday = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')
                start_date = yesterday
                logger.info(f"시작 날짜가 오늘과 같습니다. 어제부터 데이터를 가져옵니다: {start_date}")

            # External index sources can fail independently. Naver is the primary
            # source for scheduled refreshes; pykrx/KRX is a compatibility source
            # only when Naver yields no rows, and both-empty still fails fast below.
            new_kospi_df = self._fetch_naver_kospi_data(start_date, today)
            if new_kospi_df.empty:
                logger.warning("Naver KOSPI 수집 결과가 비어 있어 pykrx KRX 경로를 시도합니다.")
                new_kospi_df = self._fetch_pykrx_kospi_data(start_date, today)

            if new_kospi_df.empty:
                raise ValueError(f"KOSPI 데이터를 수집하지 못했습니다: {start_date} ~ {today}")
            
            # 중복되지 않은 새 데이터만 DB에 저장
            if not new_kospi_df.empty:
                logger.info(f"수집된 KOSPI 데이터 행 수: {len(new_kospi_df)}")
                
                # 날짜 형식을 '2025-03-17 00:00:00' 형식으로 변환
                new_kospi_df = new_kospi_df.reset_index()
                new_kospi_df['date'] = pd.to_datetime(new_kospi_df['date']).dt.strftime('%Y-%m-%d 00:00:00')
                new_kospi_df = new_kospi_df.set_index('date')
                
                upsert_df_to_db(new_kospi_df, 'kospi')
                
            # 전체 데이터 다시 로드
            self.kospi_df = get_table_as_df('kospi')
            logger.info("KOSPI 데이터 수집 및 저장 완료")
        except Exception as e:
            logger.error(f"KOSPI 데이터 수집 중 오류 발생: {e}")
            raise

    def _fetch_naver_kospi_data(self, start_date, end_date):
        """Naver 차트 API에서 KOSPI OHLCV 데이터를 수집합니다."""
        start_dt = pd.to_datetime(start_date).normalize()
        end_dt = pd.to_datetime(end_date).normalize()
        request_days = max((end_dt - start_dt).days + 10, 60)
        params = {
            "symbol": KOSPI_NAVER_SYMBOL,
            "timeframe": "day",
            "count": min(request_days, 5000),
            "requestType": 0,
        }
        headers = {
            "User-Agent": HEADERS.get("User-Agent", "Mozilla/5.0"),
            "Referer": "https://finance.naver.com/",
            "Accept": "text/xml,*/*",
        }

        try:
            response = requests.get(NAVER_INDEX_CHART_URL, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            xml_text = response.content.decode("euc-kr", errors="replace")
            xml_text = xml_text.replace('encoding="EUC-KR"', 'encoding="UTF-8"')
            root = ET.fromstring(xml_text.encode("utf-8"))
            rows = []
            for item in root.findall(".//item"):
                raw = item.attrib.get("data", "")
                parts = raw.split("|")
                if len(parts) < 6:
                    continue
                date = pd.to_datetime(parts[0], format="%Y%m%d", errors="coerce")
                if pd.isna(date) or date < start_dt or date > end_dt:
                    continue
                rows.append({
                    "date": date.strftime("%Y-%m-%d 00:00:00"),
                    "시가": float(parts[1]),
                    "고가": float(parts[2]),
                    "저가": float(parts[3]),
                    "종가": float(parts[4]),
                    "거래량": int(float(parts[5])),
                })

            if not rows:
                logger.warning(f"Naver KOSPI 데이터 없음: {start_date} ~ {end_date}")
                return self._empty_kospi_ohlcv_df()

            df = self._normalize_kospi_ohlcv_df(pd.DataFrame(rows))
            logger.info(f"Naver KOSPI 수집 성공: {start_date} ~ {end_date} ({len(df)}행)")
            return df
        except Exception as e:
            logger.error(f"Naver KOSPI 수집 실패: {start_date} ~ {end_date} - {e}")
            return self._empty_kospi_ohlcv_df()

    def _fetch_pykrx_kospi_data(self, start_date, end_date):
        """pykrx KRX 경로로 KOSPI 데이터를 수집합니다."""
        try:
            df = stock.get_index_ohlcv_by_date(start_date, end_date, KOSPI_KRX_TICKER)
            df.index.name = 'date'
            return df
        except Exception as e:
            logger.error(f"pykrx KOSPI 수집 실패: {start_date} ~ {end_date} - {e}")
            return self._empty_kospi_ohlcv_df()

    def _empty_kospi_ohlcv_df(self):
        """KOSPI 수집 실패를 나타내는 빈 OHLCV DataFrame을 반환합니다."""
        df = pd.DataFrame(columns=KOSPI_OHLCV_COLUMNS)
        df.index.name = "date"
        return df

    def _normalize_kospi_ohlcv_df(self, df):
        """KOSPI OHLCV DataFrame의 날짜 중복과 정렬을 표준화합니다."""
        if df.empty:
            return self._empty_kospi_ohlcv_df()

        normalized = df.drop_duplicates(subset=["date"], keep="last")
        normalized = normalized.sort_values("date").set_index("date")
        normalized.index.name = "date"
        return normalized[KOSPI_OHLCV_COLUMNS]

    def fetch_kospi_200_volatility_index(self):
        """KOSPI 200 변동성 지수 데이터를 가져옵니다."""
        try:
            end_date = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
            # 날짜 범위를 6일에서 10일로 확장
            start_date = (datetime.now() - timedelta(days=50)).strftime("%Y%m%d")
            
            logger.info(f"KOSPI 200 변동성 지수 데이터 요청: {start_date} ~ {end_date}")

            data = {
                "bld": "dbms/MDC/STAT/standard/MDCSTAT01402",
                "ddTp": "1D",
                "locale": "ko_KR",
                "indTpCd": "1",
                "idxIndCd": "300",
                "tboxidxCd_finder_drvetcidx0_0": "코스피 200 변동성지수",
                "idxCd": "1",
                "idxCd2": "300",
                "codeNmidxCd_finder_drvetcidx0_0": "코스피 200 변동성지수",
                "param1idxCd_finder_drvetcidx0_0": "",
                "csvxls_isNo": "false",
                "strtDd": start_date,
                "endDd": end_date
            }

            result = krx_post_json(KRX_URL, headers=HEADERS, data=data, timeout=30)
            logger.info("KOSPI 200 변동성 지수 데이터 요청 성공")
            return result
        except Exception as e:
            logger.error(f"KOSPI 200 변동성 지수 데이터 요청 중 오류 발생: {e}")
            return None

    def scrape_vix_data(self):
        """VIX 데이터를 수집합니다."""
        try:
            logger.info("VIX 데이터 수집 시작")
            result = self.fetch_kospi_200_volatility_index()
            if not result:
                logger.warning("VIX 데이터를 가져오지 못했습니다.")
                return
            
            # 결과 데이터 확인
            logger.info(f"VIX API 응답 결과: {len(result['output'])}개 항목")
            
            # 데이터 형식 확인 로깅
            if result['output'] and len(result['output']) > 0:
                logger.info(f"VIX 첫 번째 항목 샘플: {result['output'][0]}")
                
            new_vix_df = pd.DataFrame(result['output'])[['TRD_DD', 'CLSPRC_IDX']]
            new_vix_df.columns = ['date', 'vix_close']
            
            # 문자열 데이터 확인 및 전처리
            logger.info(f"원본 날짜 형식 샘플: {new_vix_df['date'].iloc[0] if not new_vix_df.empty else '데이터 없음'}")
            
            # 날짜 변환 전 빈 값 확인 및 제거
            if new_vix_df['date'].isna().any():
                empty_count = new_vix_df['date'].isna().sum()
                logger.warning(f"{empty_count}개의 빈 날짜 값이 제거됩니다.")
                new_vix_df = new_vix_df.dropna(subset=['date'])
            
            # vix_close 컬럼이 숫자형인지 확인
            new_vix_df['vix_close'] = pd.to_numeric(new_vix_df['vix_close'], errors='coerce')
            if new_vix_df['vix_close'].isna().any():
                na_count = new_vix_df['vix_close'].isna().sum()
                logger.warning(f"{na_count}개의 유효하지 않은 VIX 값이 제거됩니다.")
                new_vix_df = new_vix_df.dropna(subset=['vix_close'])
            
            # 날짜 변환 - 여러 형식 시도
            try:
                # 기본 형식 먼저 시도 (%Y/%m/%d)
                new_vix_df['date'] = pd.to_datetime(new_vix_df['date'], format='%Y/%m/%d')
            except ValueError:
                try:
                    # 다른 형식 시도 (%Y-%m-%d)
                    new_vix_df['date'] = pd.to_datetime(new_vix_df['date'], format='%Y-%m-%d')
                except ValueError:
                    # 자동 감지
                    logger.warning("표준 날짜 형식 변환 실패, 자동 감지로 시도합니다.")
                    new_vix_df['date'] = pd.to_datetime(new_vix_df['date'], errors='coerce')
                    if new_vix_df['date'].isna().any():
                        na_count = new_vix_df['date'].isna().sum()
                        logger.warning(f"{na_count}개의 변환 불가능한 날짜가 제거됩니다.")
                        new_vix_df = new_vix_df.dropna(subset=['date'])
            
            # 중복 날짜 확인 및 제거
            if new_vix_df['date'].duplicated().any():
                dup_count = new_vix_df['date'].duplicated().sum()
                logger.warning(f"{dup_count}개의 중복 날짜가 발견되어 첫 번째 값만 유지합니다.")
                new_vix_df = new_vix_df.drop_duplicates(subset=['date'], keep='first')
            
            # 날짜로 정렬
            new_vix_df = new_vix_df.sort_values('date')
            
            # 인덱스 설정
            new_vix_df = new_vix_df.set_index('date')
            
            logger.info(f"처리 후 VIX 데이터 행 수: {len(new_vix_df)}")
            logger.info(f"VIX 데이터 날짜 범위: {new_vix_df.index.min()} ~ {new_vix_df.index.max()}")
            
            # 기존 VIX 데이터 날짜 형식 확인을 위해 샘플 조회
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT date FROM vix LIMIT 1")
                date_sample = cursor.fetchone()
                conn.close()
                
                if date_sample:
                    logger.info(f"기존 VIX 테이블 날짜 형식 샘플: {date_sample[0]}")
                    # 기존 날짜에 시간 정보가 포함되어 있으면 새 데이터도 동일한 형식으로 유지
                    if ' 00:00:00' in date_sample[0]:
                        logger.info("기존 날짜 형식에 시간 정보가 포함되어 있어, 새 데이터도 동일한 형식으로 변환합니다.")
                        # 특정 형식으로 데이터베이스에 저장하기 위해 인덱스 리셋
                        new_vix_df = new_vix_df.reset_index()
                        # 날짜를 YYYY-MM-DD 00:00:00 형식으로 변환
                        new_vix_df['date'] = new_vix_df['date'].dt.strftime('%Y-%m-%d 00:00:00')
                        # 다시 인덱스 설정
                        new_vix_df = new_vix_df.set_index('date')
            except Exception as e:
                logger.warning(f"기존 VIX 날짜 형식 확인 중 오류 발생: {e}, 기본 형식을 사용합니다.")
                # 특정 형식으로 데이터베이스에 저장하기 위해 인덱스 리셋
                new_vix_df = new_vix_df.reset_index()
                # 날짜를 YYYY-MM-DD 형식의 문자열로 변환
                new_vix_df['date'] = new_vix_df['date'].dt.strftime('%Y-%m-%d')
                # 다시 인덱스 설정
                new_vix_df = new_vix_df.set_index('date')
            
            # 데이터베이스에 저장
            upsert_df_to_db(new_vix_df, 'vix')
            
            # 전체 데이터 다시 로드
            self.vix_df = get_table_as_df('vix')
            logger.info("VIX 데이터 수집 및 저장 완료")
        except Exception as e:
            logger.error(f"VIX 데이터 수집 중 오류 발생: {e}")
            raise

    def scrape_10ybond_data(self):
        """10년 국채 데이터를 수집합니다."""
        try:
            logger.info("10년 국채 데이터 수집 시작")
            te_ranges = self._get_10ybond_update_ranges()
            te_frames = []

            for start_date, end_date in te_ranges:
                te_df = self._fetch_tradingeconomics_10ybond_data(start_date, end_date)
                if not te_df.empty:
                    te_frames.append(te_df)

            if te_frames:
                new_tenBond_df = pd.concat(te_frames).sort_index()
                new_tenBond_df = new_tenBond_df[~new_tenBond_df.index.duplicated(keep='last')]
                logger.info(f"Trading Economics 10년 국채 데이터 행 수: {len(new_tenBond_df)}")
                upsert_df_to_db(new_tenBond_df, 'ten_bond')
                self.tenBond_df = get_table_as_df('ten_bond')
                logger.info("10년 국채 데이터 수집 및 저장 완료")
                return

            # Compatibility path: keep the existing Investing HTML parser as a
            # guarded secondary source when the chart API returns no rows. This
            # preserves prior behavior without fabricating missing bond values.
            response = requests.get(INVESTING_URL)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            table = soup.find('table')
            
            if not table:
                logger.warning("10년 국채 데이터 테이블을 찾을 수 없습니다.")
                return
                
            rows = table.find_all('tr')

            data = []
            for row in rows:
                cols = row.find_all('td')
                cols = [ele.text.strip() for ele in cols]
                data.append([ele for ele in cols if ele])

            new_tenBond_df = pd.DataFrame(data)
            
            if new_tenBond_df.empty or new_tenBond_df.shape[1] < 2:
                logger.warning("10년 국채 데이터가 없거나 형식이 잘못되었습니다.")
                return
                
            new_tenBond_df = new_tenBond_df.iloc[:, [0, 1]]
            new_tenBond_df.columns = ['date', 'ten_ratio']
            new_tenBond_df = new_tenBond_df.iloc[1:]
            
            # 날짜 변환 시 오류 처리
            try:
                new_tenBond_df['date'] = pd.to_datetime(new_tenBond_df['date'], format='%m월 %d, %Y')
                
                # ten_ratio를 숫자로 변환, 빈 값이나 변환 불가능한 값은 NaN으로
                new_tenBond_df['ten_ratio'] = pd.to_numeric(new_tenBond_df['ten_ratio'], errors='coerce')
                
                # NaN 값을 가진 행 제거
                if new_tenBond_df['ten_ratio'].isna().any():
                    nan_count = new_tenBond_df['ten_ratio'].isna().sum()
                    logger.warning(f"10년 국채 데이터에서 {nan_count}개의 누락된 값이 제거됩니다.")
                    new_tenBond_df = new_tenBond_df.dropna(subset=['ten_ratio'])
                
                # 날짜로 정렬
                new_tenBond_df = new_tenBond_df.sort_values('date')
                
                # 날짜 형식을 '2025-03-17 00:00:00' 형식으로 변환
                new_tenBond_df = new_tenBond_df.reset_index(drop=True)  # 기존 인덱스 제거
                new_tenBond_df['date'] = new_tenBond_df['date'].dt.strftime('%Y-%m-%d 00:00:00')
                new_tenBond_df = new_tenBond_df.set_index('date')
                logger.info(f"수집된 10년 국채 데이터 행 수: {len(new_tenBond_df)}")
                
                # 데이터베이스에 저장
                upsert_df_to_db(new_tenBond_df, 'ten_bond')
                
                # 전체 데이터 다시 로드
                self.tenBond_df = get_table_as_df('ten_bond')
                logger.info("10년 국채 데이터 수집 및 저장 완료")
            except Exception as e:
                logger.error(f"10년 국채 날짜 변환 중 오류 발생: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"10년 국채 데이터 요청 중 오류 발생: {e}")
        except Exception as e:
            logger.error(f"10년 국채 데이터 처리 중 오류 발생: {e}")
            raise

    def _get_10ybond_update_ranges(self):
        """DB의 큰 결측 구간과 최근 45일을 10년물 수집 대상 구간으로 계산합니다."""
        today = datetime.today().date()
        ranges = []
        try:
            ten_bond_df = get_table_as_df('ten_bond')
            if ten_bond_df.empty:
                return [(today - timedelta(days=45), today)]

            dates = pd.to_datetime(ten_bond_df.index).date
            dates = sorted(set(dates))
            for prev_date, next_date in zip(dates, dates[1:]):
                gap_days = (next_date - prev_date).days
                if gap_days > 10:
                    ranges.append((prev_date + timedelta(days=1), next_date - timedelta(days=1)))

            last_date = dates[-1]
            ranges.append((max(last_date - timedelta(days=45), dates[0]), today))
        except Exception as e:
            logger.warning(f"10년 국채 수집 구간 계산 중 오류 발생: {e}")
            ranges.append((today - timedelta(days=45), today))

        normalized_ranges = []
        for start_date, end_date in ranges:
            if start_date <= end_date:
                normalized_ranges.append((start_date, end_date))
        return normalized_ranges

    def _fetch_tradingeconomics_10ybond_data(self, start_date, end_date):
        """Trading Economics 차트 API에서 한국 10년물 데이터를 가져옵니다."""
        params = {
            "d1": start_date.strftime("%Y-%m-%d"),
            "d2": end_date.strftime("%Y-%m-%d"),
            "interval": "1d",
            "ohlc": "0",
        }
        headers = {
            "User-Agent": HEADERS.get("User-Agent", "Mozilla/5.0"),
            "Referer": "https://tradingeconomics.com/south-korea/government-bond-yield",
            "Accept": "application/json,*/*",
        }

        try:
            response = requests.get(TE_10Y_MARKET_URL, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            decoded = self._decode_tradingeconomics_payload(response.json())
            data = decoded.get("series", [{}])[0].get("data", [])
            rows = []
            for item in data:
                if len(item) < 2 or item[1] is None:
                    continue
                date = datetime.fromtimestamp(int(item[0]), timezone.utc).strftime("%Y-%m-%d 00:00:00")
                rows.append((date, float(item[1])))

            if not rows:
                logger.warning(f"Trading Economics 10년 국채 데이터 없음: {params['d1']} ~ {params['d2']}")
                return pd.DataFrame(columns=["ten_ratio"])

            df = pd.DataFrame(rows, columns=["date", "ten_ratio"])
            df = df.drop_duplicates(subset=["date"], keep="last").set_index("date")
            logger.info(f"Trading Economics 10년 국채 수집 성공: {params['d1']} ~ {params['d2']} ({len(df)}행)")
            return df
        except Exception as e:
            logger.error(f"Trading Economics 10년 국채 수집 실패: {params['d1']} ~ {params['d2']} - {e}")
            return pd.DataFrame(columns=["ten_ratio"])

    def _decode_tradingeconomics_payload(self, payload):
        """Trading Economics 차트 응답을 JSON으로 복호화합니다."""
        if not isinstance(payload, str):
            return payload

        encrypted = bytearray(base64.b64decode(payload))
        for idx in range(len(encrypted)):
            encrypted[idx] ^= TE_CHART_DECODE_KEY[idx % len(TE_CHART_DECODE_KEY)]

        decoded = zlib.decompress(bytes(encrypted), zlib.MAX_WBITS | 32).decode("utf-8")
        return json.loads(decoded)

    def scrape_pcr_data(self):
        """PCR 데이터를 수집합니다."""
        try:
            logger.info("PCR 데이터 수집 시작")
            bld = "dbms/MDC/STAT/standard/MDCSTAT13601"
            prod_id = "KRDRVOPK2I"
            end_date = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=50)).strftime("%Y%m%d")

            data = {
                "bld": bld,
                "locale": "ko_KR",
                "prodId": prod_id,
                "strtDd": start_date,
                "endDd": end_date,
                "share": "1",
                "csvxls_isNo": "false"
            }

            try:
                result = krx_post_json(KRX_URL, headers=HEADERS, data=data, timeout=30)
            except Exception as e:
                logger.error(f"PCR 데이터 요청 중 오류 발생: {e}")
                self.pcr_df = get_table_as_df('pcr')
                return

            new_pcr_df = pd.DataFrame(result['output'])
            new_pcr_df.columns = ['date', 'put', 'cal', 'p_c_ratio']
            new_pcr_df['put'] = new_pcr_df['put'].str.replace(',', '').astype(int)
            new_pcr_df['cal'] = new_pcr_df['cal'].str.replace(',', '').astype(int)
            
            # p_c_ratio 값 처리 로깅
            logger.debug("원본 p_c_ratio 값: %s", new_pcr_df['p_c_ratio'].tolist())

            # 쉼표 제거 및 숫자 변환 시도
            new_pcr_df['p_c_ratio'] = new_pcr_df['p_c_ratio'].str.replace(',', '').str.strip()
            logger.debug("쉼표 제거 후 p_c_ratio 값: %s", new_pcr_df['p_c_ratio'].tolist())

            # 숫자로 변환
            new_pcr_df['p_c_ratio'] = pd.to_numeric(new_pcr_df['p_c_ratio'], errors='coerce')

            # 값이 없는 경우 put/cal로 직접 계산
            mask = new_pcr_df['p_c_ratio'].isna()
            if mask.any():
                logger.warning(f"{mask.sum()}개의 p_c_ratio 값이 누락되어 직접 계산합니다.")
                # cal이 0인 경우 처리
                zero_cal_mask = (new_pcr_df['cal'] == 0)
                if zero_cal_mask.any():
                    logger.warning(f"{zero_cal_mask.sum()}개의 cal 값이 0입니다. 이 경우 p_c_ratio를 99로 설정합니다.")
                    new_pcr_df.loc[mask & zero_cal_mask, 'p_c_ratio'] = 99  # 매우 높은 값으로 설정
                    new_pcr_df.loc[mask & ~zero_cal_mask, 'p_c_ratio'] = new_pcr_df.loc[mask & ~zero_cal_mask, 'put'] / new_pcr_df.loc[mask & ~zero_cal_mask, 'cal']
                else:
                    new_pcr_df.loc[mask, 'p_c_ratio'] = new_pcr_df.loc[mask, 'put'] / new_pcr_df.loc[mask, 'cal']
            
            # 날짜를 datetime으로 변환
            new_pcr_df['date'] = pd.to_datetime(new_pcr_df['date'], format='%Y/%m/%d')
            
            # 날짜 순으로 정렬
            new_pcr_df = new_pcr_df.sort_values('date')
            
            # 날짜 형식 변환 및 인덱스 설정
            new_pcr_df = new_pcr_df.reset_index(drop=True)
            new_pcr_df['date'] = new_pcr_df['date'].dt.strftime('%Y-%m-%d 00:00:00')
            new_pcr_df = new_pcr_df.set_index('date')
            
            # 중복 날짜 제거 (가장 최근 값 유지)
            new_pcr_df = new_pcr_df[~new_pcr_df.index.duplicated(keep='last')]
            
            # 디버깅용 print문을 로그로 대체
            logger.debug("처리된 PCR 데이터:\n%s", new_pcr_df)

            logger.info(f"수집된 PCR 데이터 행 수: {len(new_pcr_df)}")
            
            # 데이터베이스에 저장
            upsert_df_to_db(new_pcr_df, 'pcr')
            
            # 전체 데이터 다시 로드
            self.pcr_df = get_table_as_df('pcr')
            logger.info("PCR 데이터 수집 및 저장 완료")
        except requests.exceptions.RequestException as e:
            logger.error(f"PCR 데이터 요청 중 오류 발생: {e}")
        except Exception as e:
            logger.error(f"PCR 데이터 처리 중 오류 발생: {e}")
            raise

    def scrape_breadth_data(self, last_date=None):
        """McClellan Volume Summation Index를 계산합니다."""
        try:
            logger.info("Breadth 데이터 수집 시작")
            # 마지막 날짜 확인
            if last_date is None:
                db_last_date = get_last_date('breadth')
                if db_last_date:
                    last_date = db_last_date
                else:
                    # 기본값 설정 (2022년 1월 3일)
                    last_date = datetime.strptime("2022-01-03", "%Y-%m-%d")
                    
            # 과거 계산용 날짜 (EMA를 위해 더 많은 과거 데이터 필요)
            # 19일과 39일 EMA를 위해 최소 100일 이상의 과거 데이터를 사용
            calc_start_date = (last_date - timedelta(days=120)).strftime("%Y%m%d")
            
            # 주식 데이터 DB 연결
            conn = sqlite3.connect(f'{DB_DIR}/stock_data.db')
            
            # 날짜 목록 가져오기
            try:
                # 새 데이터 수집을 위한 날짜
                new_date_list = self.scrape_stocks_info(last_date.strftime("%Y%m%d"))
                
                if not new_date_list:
                    logger.warning("처리할 새 주식 데이터가 없습니다.")
                    conn.close()
                    return
                
                # 기존 breadth 데이터 가져오기 - 연속성을 위해
                old_breadth_df = get_table_as_df('breadth')
                
                # 모든 주식 테이블 이름 가져오기
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'stock_%'")
                tables = [row[0] for row in cursor.fetchall()]
                
                if not tables:
                    logger.warning("주식 데이터 테이블이 없습니다.")
                    conn.close()
                    return
                
                # 각 테이블에서 데이터 수집 (계산용 과거 데이터 포함)
                dfs = []
                for table in tables:
                    query = f"""
                    SELECT date,
                           CASE WHEN close > open THEN trading_value ELSE 0 END as adv_value,
                           CASE WHEN close < open THEN trading_value ELSE 0 END as dec_value
                    FROM {table}
                    WHERE date >= '{calc_start_date}'
                    """
                    try:
                        df = pd.read_sql(query, conn)
                        dfs.append(df)
                    except Exception as e:
                        logger.error(f"테이블 {table}에서 데이터를 읽는 중 오류 발생: {e}")
                        continue

                # 모든 데이터를 하나로 결합
                all_data = pd.concat(dfs)

                # 날짜별 상승/하락 거래량 합계 계산
                daily_vol = all_data.groupby('date').sum().reset_index()

                # 일별 거래량 차이 계산
                daily_vol['diff'] = daily_vol['adv_value'] - daily_vol['dec_value']

                # 날짜순 정렬
                daily_vol['date'] = pd.to_datetime(daily_vol['date'])
                daily_vol = daily_vol.sort_values('date')

                # EMA 계산 (19일 및 39일)
                daily_vol['ema19'] = daily_vol['diff'].ewm(span=19, adjust=False).mean()
                daily_vol['ema39'] = daily_vol['diff'].ewm(span=39, adjust=False).mean()

                # McClellan Oscillator 계산
                daily_vol['oscillator'] = daily_vol['ema19'] - daily_vol['ema39']

                # 기존 summation_index 값 가져오기
                last_summation = 0
                if not old_breadth_df.empty:
                    oldest_date_in_new_data = daily_vol['date'].min()
                    
                    # 기존 데이터에서 가장 최근 날짜의 summation_index 값 찾기
                    old_data_before_new = old_breadth_df[old_breadth_df.index < oldest_date_in_new_data.strftime('%Y-%m-%d')]
                    if not old_data_before_new.empty:
                        last_summation = old_data_before_new['summation_index'].iloc[-1]
                        logger.info(f"이전 summation_index 시작점: {last_summation}")
                
                # McClellan Volume Summation Index 계산 - 기존 마지막 값에서 시작
                daily_vol['summation_index'] = daily_vol['oscillator'].cumsum() + last_summation

                # 새 데이터만 필터링 (last_date 이후 데이터)
                new_daily_vol = daily_vol[daily_vol['date'] > last_date]
                
                # 결과를 DB에 저장
                if not new_daily_vol.empty:
                    new_breadth_df = new_daily_vol.set_index('date')
                    # 날짜 형식을 'yyyy-mm-dd' 형식으로 변환
                    new_breadth_df = new_breadth_df.reset_index()
                    new_breadth_df['date'] = new_breadth_df['date'].dt.strftime('%Y-%m-%d')
                    new_breadth_df = new_breadth_df.set_index('date')
                    
                    logger.info(f"계산된 새 Breadth 데이터 행 수: {len(new_breadth_df)}")
                    upsert_df_to_db(new_breadth_df, 'breadth')
                    logger.info("McClellan Volume Summation Index 계산이 완료되었습니다.")
                else:
                    logger.info("새로 계산된 Breadth 데이터가 없습니다.")
                
            except Exception as e:
                logger.error(f"Breadth 데이터 처리 중 오류 발생: {e}")
            finally:
                conn.close()
            
            # 전체 데이터 다시 로드
            self.breadth_df = get_table_as_df('breadth')
            logger.info("Breadth 데이터 수집 및 저장 완료")
        except Exception as e:
            logger.error(f"Breadth 데이터 수집 중 오류 발생: {e}")
            raise

    def scrape_junkbond_data(self, last_date=None):
        """정크본드 데이터를 수집합니다."""
        try:
            logger.info("정크본드 데이터 수집 시작")
            # 마지막 날짜 확인
            if last_date is None:
                db_last_date = get_last_date('junk_bond')
                if db_last_date:
                    last_date = db_last_date
                else:
                    # 기본값 설정 (2022년 1월 3일)
                    last_date = datetime.strptime("2022-01-03", "%Y-%m-%d")
                    
            date_range = date_range_f(last_date.strftime("%Y-%m-%d"),
                                  datetime.today().strftime("%Y-%m-%d"))
                                  
            if not date_range:
                logger.warning("처리할 새 정크본드 데이터가 없습니다.")
                return
                
            logger.info(f"처리할 날짜 수: {len(date_range)}")

            date_list = []
            aam_list = []
            bbbp_list = []

            for d in date_range:
                try:
                    url = f'{NICE_RATING_URL}?strDate={d}'
                    response = requests.get(url)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.content, 'html.parser')
                    table = soup.find('table')
                    
                    if not table:
                        logger.warning(f"날짜 {d}에 대한 정크본드 테이블을 찾을 수 없습니다.")
                        continue
                        
                    rows = table.find_all('tr')

                    data = []
                    for row in rows:
                        cols = row.find_all('td')
                        cols = [ele.text.strip() for ele in cols]
                        data.append([ele for ele in cols if ele])

                    df = pd.DataFrame(data)
                    
                    if df.empty or df.shape[0] < 10 or df.shape[1] < 7:
                        logger.warning(f"날짜 {d}에 대한 정크본드 데이터가 없거나 형식이 잘못되었습니다.")
                        continue
                        
                    aam_list.append(df[6].iloc[5])
                    bbbp_list.append(df[6].iloc[9])
                    date_list.append(d)
                    logger.debug(f"날짜 {d}에 대한 정크본드 데이터 수집 성공")
                except requests.exceptions.RequestException as e:
                    logger.error(f"날짜 {d}에 대한 정크본드 데이터 요청 중 오류 발생: {e}")
                except Exception as e:
                    logger.error(f"날짜 {d}에 대한 정크본드 데이터 처리 중 오류 발생: {e}")

            if not date_list:
                logger.warning("수집된 정크본드 데이터가 없습니다.")
                return
                
            # 숫자로 변환
            try:
                aam_list = pd.to_numeric(pd.Series(aam_list), errors='coerce').astype(float).tolist()
                bbbp_list = pd.to_numeric(pd.Series(bbbp_list), errors='coerce').astype(float).tolist()

                new_junkBond_df = pd.DataFrame((zip(date_list, aam_list, bbbp_list)),
                                        columns=['date', 'aam', 'bbbp'])
                new_junkBond_df['date'] = pd.to_datetime(new_junkBond_df['date'],
                                                  format='%Y-%m-%d')
                                                  
                # 날짜 형식을 '2025-03-17 00:00:00' 형식으로 변환
                new_junkBond_df = new_junkBond_df.reset_index(drop=True)  # drop=True로 변경
                new_junkBond_df['date'] = new_junkBond_df['date'].dt.strftime('%Y-%m-%d 00:00:00')
                new_junkBond_df = new_junkBond_df.set_index('date')
                
                # 중복 제거를 위한 추가 코드
                new_junkBond_df = new_junkBond_df[~new_junkBond_df.index.duplicated(keep='last')]
                
                logger.info(f"수집된 정크본드 데이터 행 수: {len(new_junkBond_df)}")
                
                # 데이터베이스에 저장
                upsert_df_to_db(new_junkBond_df, 'junk_bond')
                
                # 전체 데이터 다시 로드
                self.junkBond_df = get_table_as_df('junk_bond')
                logger.info("정크본드 데이터 수집 및 저장 완료")
            except Exception as e:
                logger.error(f"정크본드 데이터 변환 및 저장 중 오류 발생: {e}")
        except Exception as e:
            logger.error(f"정크본드 데이터 수집 중 오류 발생: {e}")
            raise

    def scrape_stocks_info(self, last_date):
        # DB 연결
        conn = sqlite3.connect(f'{DB_DIR}/stock_data.db')
        cursor = conn.cursor()

        start_date = (datetime.strptime(last_date, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
        end_date = datetime.today().strftime("%Y%m%d")

        # 삼성전자(005930)의 거래 데이터를 기준으로 거래 가능한 날짜 확인
        samsung_ticker = "005930"
        logger.info(f"삼성전자({samsung_ticker})의 거래 데이터를 기준으로 거래 가능한 날짜 확인 중...")
        
        try:
            # 삼성전자 거래 데이터 가져오기
            samsung_df = stock.get_market_ohlcv(start_date, end_date, samsung_ticker)
            
            # 거래가 있는 날짜만 추출
            trading_dates = samsung_df.index.strftime("%Y%m%d").tolist()
            
            if not trading_dates:
                logger.info("거래 가능한 날짜가 없습니다.")
                conn.close()
                return []
                
            logger.info(f"총 {len(trading_dates)}개의 거래 가능한 날짜를 찾았습니다.")
        except Exception as e:
            logger.error(f"삼성전자 거래 데이터 조회 중 오류 발생: {e}")
            conn.close()
            return []

        # 데이터 수집 및 저장
        for date in trading_dates:
            try:
                logger.info(f"\n데이터 수집 중: {date}")
                
                # 해당 날짜의 상장 종목 목록 조회
                tickers = stock.get_market_ticker_list(date)
                logger.info(f"총 {len(tickers)}개 종목 처리 중...")
                
                # 진행상황 추적용 카운터
                processed_count = 0
                skipped_count = 0
                
                for ticker in tickers:
                    try:
                        # 종목별 테이블 생성
                        table_name = f"stock_{ticker}"
                        cursor.execute(f'''
                        CREATE TABLE IF NOT EXISTS {table_name} (
                            date TEXT PRIMARY KEY,
                            open INTEGER,
                            close INTEGER,
                            trading_value BIGINT
                        )
                        ''')
                        conn.commit()
                        
                        # 이미 해당 날짜의 데이터가 있는지 확인
                        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE date = ?", (date,))
                        exists = cursor.fetchone()[0] > 0
                        
                        if exists:
                            # 이미 데이터가 있으면 건너뜀
                            skipped_count += 1
                            processed_count += 1
                            continue
                        
                        # OHLCV 데이터 가져오기
                        df_ohlcv = stock.get_market_ohlcv(date, date, ticker)
                        
                        # 시가총액 데이터 가져오기
                        df_cap = stock.get_market_cap(date, date, ticker)
                        
                        if not df_ohlcv.empty and not df_cap.empty:
                            # 데이터 삽입
                            cursor.execute(f'''
                            INSERT OR REPLACE INTO {table_name} (date, open, close, trading_value)
                            VALUES (?, ?, ?, ?)
                            ''', (
                                date,
                                int(df_ohlcv.iloc[0]['시가']),
                                int(df_ohlcv.iloc[0]['종가']),
                                int(df_cap.iloc[0]['거래대금'] / 1000000)  # 백만 원 단위로 저장
                            ))
                            conn.commit()
                            
                        # 처리된 종목 수 증가
                        processed_count += 1
                        
                        # 100개 단위로 진행상황 로깅
                        if processed_count % 100 == 0:
                            logger.info(f"진행상황: {processed_count}/{len(tickers)} 종목 처리 완료 ({(processed_count/len(tickers)*100):.1f}%) - 건너뛴 종목: {skipped_count}개")
                            
                    except Exception as e:
                        logger.error(f"종목 {ticker} 처리 중 오류: {e}")
                        
                        # 오류가 발생해도 처리된 종목 수 증가
                        processed_count += 1
                        continue
                
                logger.info(f"{date} 날짜의 모든 종목 처리 완료 (총 {len(tickers)}개, 건너뛴 종목: {skipped_count}개)")
                
            except Exception as e:
                logger.error(f"날짜 {date} 처리 중 오류: {e}")
                continue
                
        conn.close()
        return trading_dates

    def calculate_stock_strength(self, days=20):
        """
        주가 강도(Stock Price Strength) 지표를 계산합니다.
        
        Args:
            days (int): 신고가/신저가 판단 기간 (기본값: 20일, 약 4주)
        """
        try:
            logger.info("주가 강도(Stock Price Strength) 계산 시작")
            
            # 마지막 계산 날짜 확인
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_strength'")
            if cursor.fetchone() is None:
                # 테이블이 없으면 생성
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
                conn.commit()
                
            # 마지막 계산 날짜 확인
            cursor.execute("SELECT MAX(date) FROM stock_strength")
            last_date = cursor.fetchone()[0]
            
            if last_date:
                start_date = (datetime.strptime(last_date, "%Y-%m-%d 00:00:00") + timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                # 기본 시작일 (2022년 1월 3일)
                start_date = "2022-01-03"
                
            end_date = datetime.today().strftime("%Y-%m-%d")
            logger.info(f"주가 강도 계산 기간: {start_date} ~ {end_date}")
            
            # 주식 데이터베이스 연결
            stock_conn = sqlite3.connect(f'{DB_DIR}/stock_data.db')
            stock_cursor = stock_conn.cursor()
            
            # 모든 주식 테이블 가져오기
            stock_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'stock_%'")
            stock_tables = [row[0] for row in stock_cursor.fetchall()]
            
            if not stock_tables:
                logger.warning("주식 데이터 테이블이 없습니다.")
                stock_conn.close()
                conn.close()
                return
                
            # 거래일 목록 가져오기 (삼성전자 기준)
            stock_cursor.execute("SELECT date FROM stock_005930 ORDER BY date")
            all_trading_days_data = stock_cursor.fetchall() # fetchall 결과를 변수에 저장
            logger.info(f'{all_trading_days_data}') # 저장된 변수를 로깅에 사용

            trading_days = [row[0] for row in all_trading_days_data] # 저장된 변수를 사용하여 리스트 생성

            logger.info(f"{trading_days} 거래일 수: {len(trading_days)}")
            if not trading_days:
                logger.warning("거래일 데이터가 없습니다.")
                stock_conn.close()
                conn.close()
                return
                
            # 분석 대상 거래일 필터링
            # 분석 대상 거래일 필터링 (날짜 형식 일치시켜 비교)
            start_date_ymd = datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y%m%d")
            end_date_ymd = datetime.strptime(end_date, "%Y-%m-%d").strftime("%Y%m%d")
            target_days = [day for day in trading_days if start_date_ymd <= day <= end_date_ymd]
            
            if not target_days:
                logger.info("분석 대상 기간에 거래일이 없습니다.")
                stock_conn.close()
                conn.close()
                return
                
            # 각 거래일에 대해 주가 강도 계산
            strength_data = []
            
            for target_day in target_days:
                logger.info(f"날짜 {target_day}의 주가 강도 계산 중...")
                
                # 해당 날짜 기준 4주(days일) 전 날짜 찾기
                current_day_idx = trading_days.index(target_day)
                if current_day_idx < days:
                    logger.warning(f"날짜 {target_day}에 대한 {days}일치 과거 데이터가 부족합니다. 건너뜁니다.")
                    continue
                    
                ref_day = trading_days[current_day_idx - days]
                
                high_count = 0
                low_count = 0
                total_count = 0
                
                # 각 종목마다 신고가/신저가 확인
                for table in stock_tables:
                    try:
                        # 현재 종가 확인
                        stock_cursor.execute(f"SELECT close FROM {table} WHERE date = ?", (target_day,))
                        current_close = stock_cursor.fetchone()
                        
                        if not current_close:
                            continue
                            
                        current_close = current_close[0]
                        
                        # 기준일(ref_day)부터 전일까지의 고가/저가 확인
                        stock_cursor.execute(f"""
                        SELECT MAX(close), MIN(close) FROM {table} 
                        WHERE date >= ? AND date < ?
                        """, (ref_day, target_day))
                        
                        max_close, min_close = stock_cursor.fetchone()
                        
                        if not max_close or not min_close:
                            continue
                            
                        # 신고가/신저가 판단
                        if current_close > max_close:
                            high_count += 1
                        if current_close < min_close:
                            low_count += 1
                            
                        total_count += 1
                        
                    except Exception as e:
                        logger.error(f"종목 {table} 처리 중 오류: {e}")
                        continue
                
                # 종목 수가 너무 적으면 결과가 왜곡될 수 있으므로 건너뜀
                if total_count < 100:
                    logger.warning(f"날짜 {target_day}의 분석 대상 종목 수({total_count})가 너무 적습니다. 건너뜁니다.")
                    continue
                
                # 주가 강도 계산
                strength_ratio = (high_count - low_count) / total_count
                strength_index = 50 + (50 * strength_ratio)
                
                # 범위 제한 (0-100)
                strength_index = max(0, min(100, strength_index))
                
                # 결과 저장
                formatted_date = datetime.strptime(target_day, "%Y%m%d").strftime("%Y-%m-%d 00:00:00")
                
                strength_data.append((
                    formatted_date,
                    high_count,
                    low_count,
                    total_count,
                    strength_ratio,
                    strength_index
                ))
                
                logger.info(f"날짜 {target_day} 주가 강도: {strength_index:.2f} (신고가: {high_count}, 신저가: {low_count}, 총: {total_count})")
                
            # 데이터 DB에 저장
            if strength_data:
                cursor.executemany("""
                INSERT OR REPLACE INTO stock_strength 
                (date, high_count, low_count, total_count, strength_ratio, strength_index)
                VALUES (?, ?, ?, ?, ?, ?)
                """, strength_data)
                conn.commit()
                logger.info(f"총 {len(strength_data)}일의 주가 강도 데이터가 저장되었습니다.")
            
            # 연결 종료
            stock_conn.close()
            conn.close()
            logger.info("주가 강도 계산 완료")
            
        except Exception as e:
            logger.error(f"주가 강도 계산 중 오류 발생: {e}")
            raise
