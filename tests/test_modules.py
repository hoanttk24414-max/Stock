import unittest
import tempfile
import numpy as np
import pandas as pd
from src.technical_analysis import analyze_technical
from src.fundamental_analysis import analyze_fundamental
from src.valuation import analyze_valuation
from src.scoring import market_risk, score_all


class ModuleTests(unittest.TestCase):
    def make_df(self):
        rng = np.random.default_rng(42); n = 120
        close = 100*np.cumprod(1+rng.normal(.0005,.01,n)); op = close*(1+rng.normal(0,.002,n))
        return pd.DataFrame({'Date':pd.bdate_range('2026-01-01',periods=n), 'Open':op,
            'High':np.maximum(op,close)*1.01, 'Low':np.minimum(op,close)*.99,
            'Close':close, 'Volume':rng.integers(100000,1000000,n)})

    def test_technical_sample(self):
        with tempfile.TemporaryDirectory() as d:
            result = analyze_technical(self.make_df(), chart_dir=d)
            self.assertTrue(result['data_available']); self.assertTrue(0 <= result['score'] <= 100)
            self.assertEqual(len(result['charts']), 3)

    def test_debt_equity_normalized(self):
        r = analyze_fundamental({'returnOnEquity':.2,'debtToEquity':45.0,'currentRatio':1.5})
        self.assertAlmostEqual(r['metrics']['debt_to_equity'], .45)

    def test_valuation_components(self):
        r = analyze_valuation({'trailingPE':12.53,'priceToBook':2.74,'forwardPE':8.91})
        self.assertEqual(set(r['component_scores']), {'pe','pb','forward_pe'})

    def test_news_relevance(self):
        try:
            from src.news_analysis import _relevant
        except ModuleNotFoundError:
            self.skipTest('feedparser chưa có trong môi trường kiểm thử; requirements.txt có khai báo.')
        self.assertTrue(_relevant('FPT công bố kết quả kinh doanh', 'FPT', 'FPT Corporation'))
        self.assertFalse(_relevant('Novaland làm sao thế?', 'FPT', 'FPT Corporation'))

    def test_market_risk_has_drawdown(self):
        with tempfile.TemporaryDirectory() as d:
            tech = analyze_technical(self.make_df(), chart_dir=d)
            r = market_risk(tech)
            self.assertIn('max_drawdown_period', r['metrics'])

    def test_missing_component_no_total_score(self):
        d = {k:{'data_available':True,'score':50} for k in ['fundamental','valuation','technical','news','risk']}
        d['news'] = {'data_available':False,'score':None}
        self.assertIsNone(score_all(d)['score'])


if __name__ == '__main__':
    unittest.main()
