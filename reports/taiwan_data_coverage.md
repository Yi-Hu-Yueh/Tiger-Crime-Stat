# Taiwan nationwide crime data coverage (Phase 3B)

## A. Administrative geography

- Counties/cities: 22 (南投縣、嘉義市、嘉義縣、基隆市、宜蘭縣、屏東縣、彰化縣、新北市、新竹市、新竹縣、桃園市、澎湖縣、臺中市、臺北市、臺南市、臺東縣、花蓮縣、苗栗縣、連江縣、金門縣、雲林縣、高雄市).
- Administrative units: 368.
- Dataset 7441 geometry validation: PASS; county+district keys and town codes are unique, names/codes are nonblank, and every geometry is a valid Polygon or MultiPolygon within the official territorial coordinate extent.
- Geometry was not simplified; the authoritative raw archive is unchanged.

## B. Crime source

- Target period: 2016–2025.
- Source: 40 already-verified national quarterly resources from Dataset 14200; exact existing bytes were reused without redownload or relocation.
- Total national Dataset 14200 source rows: 369521.
- Valid district-assigned rows: 335650.
- District-unassigned rows: 33740.
- All auditable rejected rows: 33871.
- `blank_county`: 8.
- `blank_district`: 33740.
- `invalid_date`: 47.
- `unknown_county`: 76.
- Legitimate duplicate-looking incident rows are preserved. No district/county imputation or incident-field deduplication was performed.

## C. Assignment coverage

- National assignment rate: 90.866022% (335650/369390).

### By county/city

| County/city | Assigned | Unassigned | Assignment rate |
|---|---:|---:|---:|
| 南投縣 | 7834 | 586 | 93.040380% |
| 嘉義市 | 5083 | 230 | 95.670996% |
| 嘉義縣 | 5045 | 324 | 93.965357% |
| 基隆市 | 10437 | 422 | 96.113823% |
| 宜蘭縣 | 6954 | 343 | 95.299438% |
| 屏東縣 | 13672 | 1168 | 92.129380% |
| 彰化縣 | 12413 | 653 | 95.002296% |
| 新北市 | 63140 | 5961 | 91.373497% |
| 新竹市 | 4587 | 1415 | 76.424525% |
| 新竹縣 | 8698 | 1348 | 86.581724% |
| 桃園市 | 49426 | 6962 | 87.653401% |
| 澎湖縣 | 795 | 67 | 92.227378% |
| 臺中市 | 31307 | 2913 | 91.487434% |
| 臺北市 | 37272 | 1718 | 95.593742% |
| 臺南市 | 22630 | 2366 | 90.534486% |
| 臺東縣 | 2507 | 423 | 85.563140% |
| 花蓮縣 | 5375 | 294 | 94.813900% |
| 苗栗縣 | 7740 | 797 | 90.664168% |
| 連江縣 | 77 | 16 | 82.795699% |
| 金門縣 | 747 | 36 | 95.402299% |
| 雲林縣 | 9385 | 686 | 93.188363% |
| 高雄市 | 30526 | 5012 | 85.896787% |

### By year

| Year | Assigned | Unassigned | Assignment rate |
|---:|---:|---:|---:|
| 2016 | 49087 | 7478 | 86.779811% |
| 2017 | 45749 | 6213 | 88.043185% |
| 2018 | 41008 | 4606 | 89.902223% |
| 2019 | 34209 | 3554 | 90.588671% |
| 2020 | 31867 | 2674 | 92.258475% |
| 2021 | 26407 | 2445 | 91.525717% |
| 2022 | 23807 | 2352 | 91.008831% |
| 2023 | 22960 | 2384 | 90.593434% |
| 2024 | 24182 | 2031 | 92.251936% |
| 2025 | 36374 | 3 | 99.991753% |

### By crime type

| Crime type | Assigned | Unassigned | Assignment rate |
|---|---:|---:|---:|
| 毒品 | 268352 | 36 | 99.986587% |
| 強盜 | 1615 | 0 | 100.000000% |
| 搶奪 | 1423 | 1 | 99.929775% |
| 住宅竊盜 | 21514 | 1 | 99.995352% |
| 汽車竊盜 | 13711 | 5 | 99.963546% |
| 機車竊盜 | 27206 | 33695 | 44.672501% |
| 強制性交 | 1769 | 2 | 99.887069% |
| 組織犯罪防制條例 | 60 | 0 | 100.000000% |

### Lowest county/year/crime assignment rates with source records

| Year | County/city | Crime type | Source | Assigned | Unassigned | Rate |
|---:|---|---|---:|---:|---:|---:|
| 2021 | 澎湖縣 | 機車竊盜 | 7 | 0 | 7 | 0.000000% |
| 2020 | 連江縣 | 機車竊盜 | 4 | 0 | 4 | 0.000000% |
| 2023 | 連江縣 | 機車竊盜 | 4 | 0 | 4 | 0.000000% |
| 2017 | 連江縣 | 機車竊盜 | 2 | 0 | 2 | 0.000000% |
| 2019 | 連江縣 | 機車竊盜 | 2 | 0 | 2 | 0.000000% |
| 2016 | 連江縣 | 機車竊盜 | 1 | 0 | 1 | 0.000000% |
| 2021 | 臺東縣 | 機車竊盜 | 38 | 4 | 34 | 10.526316% |
| 2019 | 澎湖縣 | 機車竊盜 | 7 | 1 | 6 | 14.285714% |
| 2022 | 澎湖縣 | 機車竊盜 | 7 | 1 | 6 | 14.285714% |
| 2023 | 苗栗縣 | 機車竊盜 | 88 | 14 | 74 | 15.909091% |
| 2019 | 苗栗縣 | 機車竊盜 | 77 | 14 | 63 | 18.181818% |
| 2021 | 苗栗縣 | 機車竊盜 | 97 | 19 | 78 | 19.587629% |
| 2023 | 臺東縣 | 機車竊盜 | 66 | 13 | 53 | 19.696970% |
| 2019 | 新竹市 | 機車竊盜 | 227 | 45 | 182 | 19.823789% |
| 2016 | 臺東縣 | 機車竊盜 | 118 | 25 | 93 | 21.186441% |
| 2020 | 臺東縣 | 機車竊盜 | 37 | 8 | 29 | 21.621622% |
| 2019 | 臺東縣 | 機車竊盜 | 46 | 10 | 36 | 21.739130% |
| 2022 | 新竹市 | 機車竊盜 | 128 | 28 | 100 | 21.875000% |
| 2022 | 苗栗縣 | 機車竊盜 | 82 | 18 | 64 | 21.951220% |
| 2022 | 臺東縣 | 機車竊盜 | 68 | 15 | 53 | 22.058824% |

## D. Population

- Source: 內政部戶政司 Dataset 8410 各鄉鎮市區人口密度.
- Dataset 8410 years: 2016–2025.
- Population rows: 3680 (10 years × 368 administrative units).
- Missing population keys: 0; unmatched accepted population keys: 0. Values are positive; there is no interpolation or fuzzy matching.

## E. Administrative crosswalk

- Fully matched geography ↔ population ↔ crime units: 368/368.
- Documented exceptions: 0.
- Unresolved units: 0.
- Matching uses exact county+district keys after surrounding-whitespace cleanup and deterministic 台→臺 normalization; no fuzzy or spatial-nearest matching is used.

## F. Crime-category coverage

- `complete` year/category combinations: 75.
- `partial` year/category combinations: 3.
- `unavailable` year/category combinations: 2.
- 組織犯罪防制條例 2016: `unavailable`.
- 組織犯罪防制條例 2017: `unavailable`.
- 組織犯罪防制條例 2018: `partial`.
- 組織犯罪防制條例 2019: `complete`.
- 組織犯罪防制條例 2020: `complete`.
- 組織犯罪防制條例 2021: `partial`.
- 組織犯罪防制條例 2022: `partial`.
- 組織犯罪防制條例 2023: `complete`.
- 組織犯罪防制條例 2024: `complete`.
- 組織犯罪防制條例 2025: `complete`.

## G. Official annual benchmark

- Verified county/year/category official annual values: 1540/1540.
- Unavailable or unverified values: 0.
- Values remain an independent county/city final layer. They are never scaled or distributed to districts.

## Observation semantics

- Analysis-panel rows: 29440.
- `observed_positive`: 13730.
- `observed_zero`: 13870.
- `partial_coverage`: 1104.
- `unavailable`: 736.

## H. Taichung regression

- Result: PASS
- 31,307 assigned; 2,913 unassigned; 29 districts; 290 population rows; 2,320 analysis-panel rows.
- 2023/2024 住宅竊盜 preliminary totals, 2019 強制性交 observed zeros, 2024 機車竊盜 assignment, incident multisets, and population keys/values were checked.

No safety, danger, risk, or composite crime ranking is produced.
