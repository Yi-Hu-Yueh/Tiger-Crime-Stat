# Phase 3B Taichung runtime regression validation

- Validation date: 2026-10-04 (Asia/Taipei)
- Server command: `python -m uvicorn app.main:app --host 127.0.0.1 --port 18082`
- URL: `http://127.0.0.1:18082/`
- Automated suite before runtime validation: `58 passed`
- Browser console warnings/errors: none

| Case | Selection | Observed result | Status |
|---|---|---|---|
| A | 2025 / 住宅竊盜 / rate | 29 district paths and 29 table rows rendered; the selected district's trend contained rendered chart elements. | PASS |
| B | 2024 / 機車竊盜 | 29 districts remained visible and the page showed the missing-district warning with `行政區可分配率：50.0%`. | PASS |
| C | 2019 / 強制性交 | All 29 district rows displayed numeric zero; none displayed unavailable, no-data, or an em dash. | PASS |
| D | 2017 / 組織犯罪防制條例 | All 29 count cells displayed `—`, none displayed zero, and the unavailable warning was visible. | PASS |
| E | 2018 / 組織犯罪防制條例 | All 29 rows displayed `部分資料`; all 29 map paths used the partial-data pattern and the partial-year warning was visible. | PASS |

The dashboard was restored to its Phase 3A default state: 2025 / 住宅竊盜 / 每十萬年底戶籍人口案件數.
