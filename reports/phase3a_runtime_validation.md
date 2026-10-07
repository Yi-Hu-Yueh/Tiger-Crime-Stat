# Phase 3A runtime validation

- Validation date: 2026-10-04 (Asia/Taipei)
- Server: `python -m uvicorn app.main:app --host 127.0.0.1 --port 18082`
- Browser target: `http://127.0.0.1:18082/`
- Browser console: no warnings or errors during the smoke test
- Automated suite before runtime validation: `43 passed`

## Manual UI cases

| Case | Selection | Runtime result | Status |
|---|---|---|---|
| A | 2025 / 住宅竊盜 / 每十萬年底戶籍人口案件數 | All 29 SVG district paths rendered with numeric color fills (28 distinct fills); the default district detail loaded, and the 10-year trend contained rendered marks. Clicking 西屯區 changed the selected district and trend. | PASS |
| B | 2024 / 機車竊盜 | The global data-quality banner visibly showed the missing-district warning and `行政區可分配率：50.0%`; the detail panel also showed 50.0%. All 29 districts remained visible. | PASS |
| C | 2019 / 強制性交 | All 29 table rows showed incident count `0` and rate `0`; none showed unavailable or an em dash for the observation. The selected district detail showed a valid zero. | PASS |
| D | 2017 / 組織犯罪防制條例 | All 29 rows showed `未提供`, all count cells showed `—`, no count cell showed `0`, the map used the unavailable hatch, and the warning stated `此年度此案類資料未提供`. | PASS |
| E | 2018 / 組織犯罪防制條例 | All 29 rows showed `部分資料`, the map used the partial-data hatch, the selected count was labelled `(部分資料)`, the rate was not presented as a full-year numeric rate, and the visible warning advised against direct full-year comparison. | PASS |

## Additional runtime checks

- Switching the metric control to `案件數` updated the selected metric without horizontal page overflow.
- The map contained exactly 29 interactive district paths throughout the filter changes.
- The official annual city panel remained visually separate from the district preliminary layer.
- The browser console contained no warning or error entries.
