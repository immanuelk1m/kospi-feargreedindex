from unittest.mock import Mock, patch

import pandas as pd

from data import scraper as scraper_module
from data.scraper import DataScraper


NAVER_XML = '''<?xml version="1.0" encoding="EUC-KR" ?>
<protocol>
  <chartdata symbol="KOSPI" name="코스피" count="3" timeframe="day" precision="2">
    <item data="20260512|7953.41|7999.67|7421.71|7643.15|1021136" />
    <item data="20260513|7513.65|7855.47|7402.36|7844.01|738739" />
    <item data="20260514|7873.91|7991.04|7842.72|7888.76|703411" />
  </chartdata>
</protocol>
'''.encode('euc-kr')


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


def test_fetch_naver_kospi_data_parses_and_filters_chart_xml():
    with patch.object(scraper_module.requests, 'get', return_value=FakeResponse(NAVER_XML)):
        df = DataScraper()._fetch_naver_kospi_data('2026-05-13', '2026-05-14')

    assert list(df.index) == ['2026-05-13 00:00:00', '2026-05-14 00:00:00']
    assert list(df.columns) == ['시가', '고가', '저가', '종가', '거래량']
    assert df.loc['2026-05-14 00:00:00', '종가'] == 7888.76
    assert df.loc['2026-05-14 00:00:00', '거래량'] == 703411


def test_scrape_kospi_data_uses_naver_without_pykrx_when_naver_has_rows():
    naver_df = pd.DataFrame(
        [{'date': '2026-05-14 00:00:00', '시가': 1.0, '고가': 2.0, '저가': 0.5, '종가': 1.5, '거래량': 10}]
    ).set_index('date')
    naver_df.index.name = 'date'
    scraper = DataScraper()

    with patch.object(scraper, '_fetch_naver_kospi_data', return_value=naver_df) as fetch_naver, \
         patch.object(scraper, '_fetch_pykrx_kospi_data') as fetch_pykrx, \
         patch.object(scraper_module, 'upsert_df_to_db') as upsert, \
         patch.object(scraper_module, 'get_table_as_df', return_value=naver_df):
        scraper.scrape_kospi_data('2026-05-14')

    fetch_naver.assert_called_once()
    fetch_pykrx.assert_not_called()
    upsert.assert_called_once()


def test_scrape_kospi_data_fails_fast_when_all_sources_empty():
    empty = pd.DataFrame(columns=['시가', '고가', '저가', '종가', '거래량'])
    scraper = DataScraper()

    with patch.object(scraper, '_fetch_naver_kospi_data', return_value=empty), \
         patch.object(scraper, '_fetch_pykrx_kospi_data', return_value=empty):
        try:
            scraper.scrape_kospi_data('2026-05-14')
        except ValueError as exc:
            assert 'KOSPI 데이터를 수집하지 못했습니다' in str(exc)
        else:
            raise AssertionError('expected ValueError when all KOSPI sources are empty')

if __name__ == '__main__':
    test_fetch_naver_kospi_data_parses_and_filters_chart_xml()
    test_scrape_kospi_data_uses_naver_without_pykrx_when_naver_has_rows()
    test_scrape_kospi_data_fails_fast_when_all_sources_empty()
    print('test_scraper_kospi.py PASS')
