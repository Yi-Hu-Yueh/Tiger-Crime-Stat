"""Fixed historical context, researched 2026-10-05 from the linked primary sources.

Dates describe milestones unless date_note explicitly defines a period. Inclusion
is not a claim of district-level exposure, statistical relevance, or causation.
No runtime fetching, ingestion, or changes to validated crime observations.
"""

MAJOR_EVENTS_2016_2025 = {
    2016: {
        "global": [
            {
                "id": "global-zika-pheic-2016",
                "year": 2016,
                "start_date": "2016-02-01",
                "end_date": "2016-02-01",
                "scope": "global",
                "category": "public_health",
                "title": "WHO 宣布茲卡相關國際公衛緊急事件",
                "summary": "WHO 將茲卡病毒相關小頭症及神經系統疾病群聚列為國際關注公共衛生緊急事件。",
                "status": "public_health_measure",
                "source_title": "WHO response to Zika virus and associated complications",
                "source_url": "https://www.who.int/publications/i/item/who-s-response-to-zika-virus-and-its-associated-complications",
                "source_agency": "WHO",
                "relevance_tags": [
                    "public_health",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-brexit-referendum-2016",
                "year": 2016,
                "start_date": "2016-06-23",
                "end_date": "2016-06-23",
                "scope": "global",
                "category": "politics",
                "title": "英國舉行脫歐公投",
                "summary": "英國舉行歐盟會員資格公投，脫歐方取得多數；此為投票日，並非正式退出歐盟日期。",
                "status": "implemented",
                "source_title": "Official result of the EU referendum",
                "source_url": "https://www.electoralcommission.org.uk/media-centre/official-result-eu-referendum-declared-electoral-commission-manchester",
                "source_agency": "UK Electoral Commission",
                "relevance_tags": [
                    "politics",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-paris-agreement-2016",
                "year": 2016,
                "start_date": "2016-11-04",
                "end_date": "2016-11-04",
                "scope": "global",
                "category": "climate",
                "title": "巴黎協定生效",
                "summary": "巴黎協定達到生效條件，成為國際氣候治理的重要制度節點。",
                "status": "implemented",
                "source_title": "The Paris Agreement",
                "source_url": "https://www.unfccc.int/process-and-meetings/the-paris-agreement",
                "source_agency": "UNFCCC",
                "relevance_tags": [
                    "climate",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ],
        "taiwan": [
            {
                "id": "tw-meinong-earthquake-2016",
                "year": 2016,
                "start_date": "2016-02-06",
                "end_date": "2016-02-06",
                "scope": "taiwan",
                "category": "disaster",
                "title": "高雄美濃地震",
                "summary": "美濃地震造成南臺灣重大災害，為該年度防災與復原的重要背景。",
                "status": "natural_disaster",
                "source_title": "2016 天然災害紀實",
                "source_url": "https://den.ncdr.nat.gov.tw/media/5agoboek/2016%E5%A4%A9%E7%84%B6%E7%81%BD%E5%AE%B3%E7%B4%80%E5%AF%A6_%E5%85%A8%E6%96%87_%E5%90%ABisbn_0423.pdf",
                "source_agency": "國家災害防救科技中心",
                "relevance_tags": [
                    "disaster",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-inauguration-2016",
                "year": 2016,
                "start_date": "2016-05-20",
                "end_date": "2016-05-20",
                "scope": "taiwan",
                "category": "politics",
                "title": "第 14 任總統副總統就職",
                "summary": "蔡英文、陳建仁宣誓就職，完成第 14 任總統與副總統交接。",
                "status": "implemented",
                "source_title": "中華民國第14任總統副總統宣誓就職典禮",
                "source_url": "https://www.president.gov.tw/NEWS/20440",
                "source_agency": "總統府",
                "relevance_tags": [
                    "politics",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-megi-2016",
                "year": 2016,
                "start_date": "2016-09-27",
                "end_date": "2016-09-27",
                "scope": "taiwan",
                "category": "disaster",
                "title": "梅姬颱風登陸",
                "summary": "梅姬颱風於花蓮登陸，影響臺灣交通、供電及防災應變；日期為登陸日。",
                "status": "natural_disaster",
                "source_title": "梅姬颱風概況表（201617）",
                "source_url": "https://rdc28.cwa.gov.tw/TDB/public/typhoon_detail?typhoon_id=201617",
                "source_agency": "中央氣象署",
                "relevance_tags": [
                    "disaster",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ]
    },
    2017: {
        "global": [
            {
                "id": "global-wannacry-2017",
                "year": 2017,
                "start_date": "2017-05-12",
                "end_date": "2017-05-12",
                "scope": "global",
                "category": "cybersecurity",
                "title": "WannaCry 勒索軟體大規模攻擊",
                "summary": "WannaCry 勒索軟體開始在多國快速傳播，影響組織資訊系統與服務運作。日期標示攻擊爆發節點。",
                "status": "incident",
                "source_title": "NCCIC Year in Review 2017",
                "source_url": "https://www.cisa.gov/sites/default/files/Annual_Reports/NCCIC_Year_in_Review_2017_Final.pdf",
                "source_agency": "CISA / NCCIC",
                "relevance_tags": [
                    "cybersecurity",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-paris-withdrawal-announcement-2017",
                "year": 2017,
                "start_date": "2017-06-01",
                "end_date": "2017-06-01",
                "scope": "global",
                "category": "climate",
                "title": "川普宣布美國退出巴黎協定意向",
                "summary": "川普政府宣布退出巴黎協定；此處記錄政治宣布，不將宣布日視為正式退出生效日。",
                "status": "announced",
                "source_title": "President Trump Announces U.S. Withdrawal from the Paris Climate Accord",
                "source_url": "https://trumpwhitehouse.archives.gov/articles/president-trump-announces-u-s-withdrawal-paris-climate-accord/",
                "source_agency": "White House archive",
                "relevance_tags": [
                    "climate",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-unsc-2375-2017",
                "year": 2017,
                "start_date": "2017-09-11",
                "end_date": "2017-09-11",
                "scope": "global",
                "category": "international_security",
                "title": "聯合國安理會通過第 2375 號決議",
                "summary": "安理會對北韓核試採取進一步制裁，包括石油供應與紡織品貿易限制。",
                "status": "policy_change",
                "source_title": "Security Council imposes fresh sanctions on DPR Korea",
                "source_url": "https://press.un.org/en/2017/sc12983.doc.htm",
                "source_agency": "United Nations",
                "relevance_tags": [
                    "international_security",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ],
        "taiwan": [
            {
                "id": "tw-airport-mrt-2017",
                "year": 2017,
                "start_date": "2017-03-02",
                "end_date": "2017-03-02",
                "scope": "taiwan",
                "category": "transport",
                "title": "桃園機場捷運正式營運",
                "summary": "機場捷運開始正式營運，新增臺北與桃園機場間的大眾運輸連結。",
                "status": "implemented",
                "source_title": "桃園捷運運量統計（正式營運日期說明）",
                "source_url": "https://www.tymetro.com.tw/tymetro-new/tw/_pages/about/statistics.html",
                "source_agency": "桃園大眾捷運股份有限公司",
                "relevance_tags": [
                    "transport",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-interpretation748-2017",
                "year": 2017,
                "start_date": "2017-05-24",
                "end_date": "2017-05-24",
                "scope": "taiwan",
                "category": "law",
                "title": "司法院公布釋字第 748 號解釋",
                "summary": "大法官就同性二人婚姻自由與平等保障作成解釋，要求相關法律限期修正；此非專法施行日。",
                "status": "policy_change",
                "source_title": "釋字第748號解釋",
                "source_url": "https://cons.judicial.gov.tw/docdata.aspx?fid=100&id=310929&rn=13153",
                "source_agency": "司法院",
                "relevance_tags": [
                    "law",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-blackout-2017",
                "year": 2017,
                "start_date": "2017-08-15",
                "end_date": "2017-08-15",
                "scope": "taiwan",
                "category": "infrastructure",
                "title": "815 大規模停電",
                "summary": "大潭電廠機組跳脫後，全臺多處停電並實施分區輪流停電。",
                "status": "incident",
                "source_title": "815 大潭電廠機組跳脫及停電通報",
                "source_url": "https://disaster.tainan.gov.tw/News_Content.aspx?n=13736&s=196844",
                "source_agency": "臺南市政府",
                "relevance_tags": [
                    "infrastructure",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ]
    },
    2018: {
        "global": [
            {
                "id": "global-trump-section301-tariffs-2018",
                "year": 2018,
                "start_date": "2018-07-06",
                "end_date": "2018-07-06",
                "scope": "global",
                "category": "trade",
                "title": "川普政府首批對中 Section 301 關稅生效",
                "summary": "美國對約 340 億美元中國商品加徵 25% 關稅的首批措施生效；此為川普政府的 Section 301 行動。",
                "status": "implemented",
                "source_title": "USTR Releases Product Exclusion Process for Chinese Products",
                "source_url": "https://ustr.gov/about-us/policy-offices/press-office/press-releases/2018/july/ustr-releases-product-exclusion",
                "source_agency": "USTR",
                "relevance_tags": [
                    "trade",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-drc-ebola-outbreak-2018",
                "year": 2018,
                "start_date": "2018-08-01",
                "end_date": "2018-08-01",
                "scope": "global",
                "category": "public_health",
                "title": "剛果民主共和國宣布新一波伊波拉疫情",
                "summary": "剛果民主共和國宣布北基伍省伊波拉疫情。日期為疫情宣布節點，不代表疫情僅持續一天。",
                "status": "public_health_measure",
                "source_title": "Ebola virus disease – Democratic Republic of the Congo, 9 August 2018",
                "source_url": "https://www.who.int/emergencies/disease-outbreak-news/item/9-august-2018-ebola-drc-en",
                "source_agency": "WHO",
                "relevance_tags": [
                    "public_health",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-migration-compact-2018",
                "year": 2018,
                "start_date": "2018-12-10",
                "end_date": "2018-12-10",
                "scope": "global",
                "category": "migration",
                "title": "全球移民契約獲通過",
                "summary": "各國代表在馬拉喀什通過安全、有序和正常移民全球契約，作為非拘束性的國際合作框架。",
                "status": "policy_change",
                "source_title": "Global Compact for Migration adopted in Marrakech",
                "source_url": "https://press.un.org/en/2018/dev3375.doc.htm",
                "source_agency": "United Nations",
                "relevance_tags": [
                    "migration",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ],
        "taiwan": [
            {
                "id": "tw-hualien-earthquake-2018",
                "year": 2018,
                "start_date": "2018-02-06",
                "end_date": "2018-02-06",
                "scope": "taiwan",
                "category": "disaster",
                "title": "花蓮 0206 地震",
                "summary": "花蓮近海於深夜發生規模 6.2 地震，花蓮及宜蘭部分地區觀測到強烈震動。",
                "status": "natural_disaster",
                "source_title": "第022號有感地震報告（2018-02-06 23:50）",
                "source_url": "https://scweb.cwa.gov.tw/zh-tw/earthquake/imgs/2018020623504162022",
                "source_agency": "中央氣象署",
                "relevance_tags": [
                    "disaster",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-pension-reform-2018",
                "year": 2018,
                "start_date": "2018-07-01",
                "end_date": "2018-07-01",
                "scope": "taiwan",
                "category": "social_policy",
                "title": "軍公教退撫制度改革措施施行",
                "summary": "軍公教與政務人員退撫制度改革措施上路，調整退休所得與相關制度安排。",
                "status": "implemented",
                "source_title": "網傳年金改革錯誤資訊之澄清",
                "source_url": "https://pension.president.gov.tw/cp.aspx?n=62E690FE3873FDD4&s=10449324953E855A",
                "source_agency": "總統府國家年金改革委員會",
                "relevance_tags": [
                    "social_policy",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-puyuma-accident-2018",
                "year": 2018,
                "start_date": "2018-10-21",
                "end_date": "2018-10-21",
                "scope": "taiwan",
                "category": "transport",
                "title": "普悠瑪列車新馬站事故",
                "summary": "臺鐵第 6432 次普悠瑪列車於新馬站發生重大鐵道事故，引發鐵路安全調查。",
                "status": "incident",
                "source_title": "1021臺鐵第6432次車新馬站重大鐵道事故（補強）調查報告",
                "source_url": "https://www.ttsb.gov.tw/media/7291/1021%E8%87%BA%E9%90%B5%E7%AC%AC6432%E6%AC%A1%E8%BB%8A%E6%96%B0%E9%A6%AC%E7%AB%99%E9%87%8D%E5%A4%A7%E9%90%B5%E9%81%93%E4%BA%8B%E6%95%85-%E8%A3%9C%E5%BC%B7-%E8%AA%BF%E6%9F%A5%E5%A0%B1%E5%91%8A-%E7%AC%AC%E4%B8%80%E5%86%8A.pdf",
                "source_agency": "國家運輸安全調查委員會",
                "relevance_tags": [
                    "transport",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ]
    },
    2019: {
        "global": [
            {
                "id": "global-ebola-pheic-2019",
                "year": 2019,
                "start_date": "2019-07-17",
                "end_date": "2019-07-17",
                "scope": "global",
                "category": "public_health",
                "title": "剛果伊波拉疫情列為國際公衛緊急事件",
                "summary": "WHO 將剛果民主共和國伊波拉疫情列為國際關注公共衛生緊急事件。",
                "status": "public_health_measure",
                "source_title": "Ebola outbreak declared a public health emergency of international concern",
                "source_url": "https://www.afro.who.int/news/ebola-outbreak-democratic-republic-congo-declared-public-health-emergency-international",
                "source_agency": "WHO Africa",
                "relevance_tags": [
                    "public_health",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-wto-appeals-2019",
                "year": 2019,
                "start_date": "2019-12-11",
                "end_date": "2019-12-11",
                "scope": "global",
                "category": "trade",
                "title": "WTO 上訴機構無法正常審理新上訴",
                "summary": "因成員不足，WTO 上訴機構自此無法完整履行上訴審理職能，影響多邊貿易爭端解決機制。",
                "status": "institutional_change",
                "source_title": "WTO Deputy Director-General remarks on the multilateral trading system",
                "source_url": "https://www.wto.org/english/news_e/news20_e/ddgaw_05jun20_e.pdf",
                "source_agency": "WTO",
                "relevance_tags": [
                    "trade",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-phase-one-announced-2019",
                "year": 2019,
                "start_date": "2019-12-13",
                "end_date": "2019-12-13",
                "scope": "global",
                "category": "trade",
                "title": "美中宣布第一階段貿易協議",
                "summary": "美國宣布與中國就第一階段貿易協議達成共識；此為宣布節點，不是其後的簽署或生效日。",
                "status": "announced",
                "source_title": "United States and China Reach Phase One Trade Agreement",
                "source_url": "https://ustr.gov/about-us/policy-offices/press-office/press-releases/2019/december/united-states-and-china-reach",
                "source_agency": "USTR",
                "relevance_tags": [
                    "trade",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ],
        "taiwan": [
            {
                "id": "tw-minimum-wage-2019",
                "year": 2019,
                "start_date": "2019-01-01",
                "end_date": "2019-01-01",
                "scope": "taiwan",
                "category": "labour",
                "title": "基本工資調升",
                "summary": "每月基本工資調至新臺幣 23,100 元，每小時調至 150 元。",
                "status": "implemented",
                "source_title": "14-9 基本工資",
                "source_url": "https://statdb.mol.gov.tw/html/trend/107/51409.pdf",
                "source_agency": "勞動部",
                "relevance_tags": [
                    "labour",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-same-sex-marriage-2019",
                "year": 2019,
                "start_date": "2019-05-24",
                "end_date": "2019-05-24",
                "scope": "taiwan",
                "category": "law",
                "title": "同性婚姻專法施行",
                "summary": "司法院釋字第 748 號解釋施行法開始施行，規範相同性別二人永久結合的權利義務。",
                "status": "implemented",
                "source_title": "司法院釋字第748號解釋施行法5.24施行",
                "source_url": "https://www.judicial.gov.tw/tw/cp-1429-57760-61de7-1.html",
                "source_agency": "司法院",
                "relevance_tags": [
                    "law",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-nanfangao-bridge-2019",
                "year": 2019,
                "start_date": "2019-10-01",
                "end_date": "2019-10-01",
                "scope": "taiwan",
                "category": "transport",
                "title": "南方澳大橋斷裂",
                "summary": "宜蘭南方澳大橋橋面斷裂崩塌，造成重大公路及港區事故，後由運安會調查。",
                "status": "incident",
                "source_title": "南方澳大橋斷裂重大公路事故",
                "source_url": "https://www.ttsb.gov.tw/1243/22385/23235/post",
                "source_agency": "國家運輸安全調查委員會",
                "relevance_tags": [
                    "transport",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ]
    },
    2020: {
        "global": [
            {
                "id": "global-brexit-exit-2020",
                "year": 2020,
                "start_date": "2020-01-31",
                "end_date": "2020-01-31",
                "scope": "global",
                "category": "politics",
                "title": "英國正式退出歐盟",
                "summary": "英國正式退出歐盟並進入過渡安排，與先前的脫歐公投是不同制度節點。",
                "status": "implemented",
                "source_title": "Prime Minister address to the nation: 31 January 2020",
                "source_url": "https://www.gov.uk/government/speeches/pm-address-to-the-nation-31-january-2020",
                "source_agency": "UK Government",
                "relevance_tags": [
                    "politics",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-covid-pandemic-2020",
                "year": 2020,
                "start_date": "2020-03-11",
                "end_date": "2020-03-11",
                "scope": "global",
                "category": "public_health",
                "title": "WHO 將 COVID-19 描述為全球大流行",
                "summary": "WHO 評估 COVID-19 可被描述為全球大流行，提醒各國加強防疫應變。",
                "status": "public_health_measure",
                "source_title": "WHO Director-General media briefing, 11 March 2020",
                "source_url": "https://www.who.int/news-room/speeches/item/who-director-general-s-opening-remarks-at-the-media-briefing-on-covid-19---11-march-2020",
                "source_agency": "WHO",
                "relevance_tags": [
                    "public_health",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-great-lockdown-2020",
                "year": 2020,
                "start_date": "2020-04-14",
                "end_date": "2020-04-14",
                "scope": "global",
                "category": "economy",
                "title": "IMF 發布「大封鎖」經濟展望",
                "summary": "IMF 發布世界經濟展望，預測疫情及封鎖下的全球經濟衰退。此為當時的預測發布，非事後實現值。",
                "status": "announced",
                "source_title": "World Economic Outlook April 2020: The Great Lockdown",
                "source_url": "https://www.imf.org/en/publications/weo/issues/2020/04/14/world-economic-outlook-april-2020-the-great-lockdown-49306",
                "source_agency": "IMF",
                "relevance_tags": [
                    "economy",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ],
        "taiwan": [
            {
                "id": "tw-cecc-activated-2020",
                "year": 2020,
                "start_date": "2020-01-20",
                "end_date": "2020-01-20",
                "scope": "taiwan",
                "category": "public_health",
                "title": "COVID-19 中央流行疫情指揮中心成立",
                "summary": "疾管署宣布成立中央流行疫情指揮中心，統籌新型冠狀病毒肺炎防疫。",
                "status": "public_health_measure",
                "source_title": "疾管署宣布成立嚴重特殊傳染性肺炎中央流行疫情指揮中心",
                "source_url": "https://www.cdc.gov.tw/En/Category/ListContent/EmXemht4IT-IRAPrAnyG9A?uaid=32NPG1QXFhAmaOLjDOpNmg",
                "source_agency": "衛生福利部疾病管制署",
                "relevance_tags": [
                    "public_health",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-border-restrictions-2020",
                "year": 2020,
                "start_date": "2020-03-19",
                "end_date": "2020-03-19",
                "scope": "taiwan",
                "category": "public_health",
                "title": "非本國籍入境限制與入境檢疫上路",
                "summary": "非本國籍人士入境原則受限，事前申請核准者可放行；入境者須進行 14 天居家檢疫。日期為措施啟動日。",
                "status": "public_health_measure",
                "source_title": "限制非本國籍人士入境，所有入境者需居家檢疫14天",
                "source_url": "https://www.cdc.gov.tw/Bulletin/Detail/mwGBh07PQ_2FeJvl9xhfZw?typeid=9",
                "source_agency": "衛生福利部疾病管制署",
                "relevance_tags": [
                    "public_health",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-triple-vouchers-2020",
                "year": 2020,
                "start_date": "2020-07-15",
                "end_date": "2020-07-15",
                "scope": "taiwan",
                "category": "economy",
                "title": "振興三倍券開始領用",
                "summary": "振興三倍券開始領取及使用，為疫情期間的國內消費振興措施。",
                "status": "implemented",
                "source_title": "7月15日振興三倍券正式領用",
                "source_url": "https://www.president.gov.tw/NEWS/25424",
                "source_agency": "總統府",
                "relevance_tags": [
                    "economy",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ]
    },
    2021: {
        "global": [
            {
                "id": "global-covax-ghana-2021",
                "year": 2021,
                "start_date": "2021-02-24",
                "end_date": "2021-02-24",
                "scope": "global",
                "category": "public_health",
                "title": "COVAX 首批疫苗抵達迦納",
                "summary": "COVAX 首批供應疫苗運抵迦納，啟動其全球疫苗配送。",
                "status": "implemented",
                "source_title": "COVID-19 vaccine doses shipped by COVAX head to Ghana",
                "source_url": "https://www.who.int/news/item/24-02-2021-covid-19-vaccine-doses-shipped-by-the-covax-facility-head-to-ghana-marking-beginning-of-global-rollout",
                "source_agency": "WHO",
                "relevance_tags": [
                    "public_health",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-suez-ever-given-2021",
                "year": 2021,
                "start_date": "2021-03-23",
                "end_date": "2021-03-23",
                "scope": "global",
                "category": "transport",
                "title": "長賜輪於蘇伊士運河擱淺",
                "summary": "長賜輪擱淺阻塞蘇伊士運河航道，引發國際航運中斷；日期記錄擱淺日而非整段阻塞期間。",
                "status": "incident",
                "source_title": "MV Ever Given incident",
                "source_url": "https://www.imo.org/en/MediaCentre/SecretaryGeneral/Pages/MV-Ever-Given-incident.aspx",
                "source_agency": "IMO",
                "relevance_tags": [
                    "transport",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-cop26-2021",
                "year": 2021,
                "start_date": "2021-11-13",
                "end_date": "2021-11-13",
                "scope": "global",
                "category": "climate",
                "title": "COP26 達成格拉斯哥氣候協議",
                "summary": "COP26 會議通過氣候談判成果，推進減排及氣候資金等國際議題。",
                "status": "policy_change",
                "source_title": "Secretary-General statement on conclusion of COP26",
                "source_url": "https://unfccc.int/news/secretary-general-s-statement-on-the-conclusion-of-the-un-climate-change-conference-cop26",
                "source_agency": "UNFCCC / United Nations",
                "relevance_tags": [
                    "climate",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ],
        "taiwan": [
            {
                "id": "tw-taroko-accident-2021",
                "year": 2021,
                "start_date": "2021-04-02",
                "end_date": "2021-04-02",
                "scope": "taiwan",
                "category": "transport",
                "title": "太魯閣號清水隧道事故",
                "summary": "臺鐵第 408 次列車於清水隧道北口發生重大鐵道事故，運安會調查施工與營運安全。",
                "status": "incident",
                "source_title": "0402臺鐵第408次車清水隧道重大鐵道事故",
                "source_url": "https://www.ttsb.gov.tw/1243/22450/29476/post",
                "source_agency": "國家運輸安全調查委員會",
                "relevance_tags": [
                    "transport",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-drought-rationing-2021",
                "year": 2021,
                "start_date": "2021-04-06",
                "end_date": "2021-04-06",
                "scope": "taiwan",
                "category": "water_supply",
                "title": "臺中啟動供五停二分區供水",
                "summary": "旱災期間臺中市啟動供五停二分區供水，並設置取水及補水支援。日期為分區供水啟動日。",
                "status": "implemented",
                "source_title": "抗旱又防汛，志工動起來",
                "source_url": "https://www.wra.gov.tw/epaper/Article_Detail.aspx?n=30173&s=6822",
                "source_agency": "經濟部水利署",
                "relevance_tags": [
                    "water_supply",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-covid-level-3-2021",
                "year": 2021,
                "start_date": "2021-05-19",
                "end_date": "2021-07-26",
                "scope": "taiwan",
                "category": "public_health",
                "title": "全國 COVID-19 疫情警戒提升至第三級",
                "summary": "全國疫情警戒自 5 月 19 日升至第三級，其後延長至 7 月 26 日；期間部分措施調整。",
                "status": "public_health_measure",
                "source_title": "全國疫情警戒提升至第三級",
                "source_url": "https://www.cdc.gov.tw/Category/ListContent/EmXemht4IT-IRAPrAnyG9A?uaid=abDtRS-xzztQeAchjX9fqw",
                "source_agency": "衛生福利部疾病管制署／中央流行疫情指揮中心",
                "relevance_tags": [
                    "public_health",
                    "historical_context"
                ],
                "date_note": "全國第三級警戒期間；各項措施曾調整。",
                "confidence": "official",
                "sources": [
                    {
                        "title": "全國疫情警戒提升至第三級",
                        "url": "https://www.cdc.gov.tw/Category/ListContent/EmXemht4IT-IRAPrAnyG9A?uaid=abDtRS-xzztQeAchjX9fqw",
                        "agency": "衛生福利部疾病管制署／中央流行疫情指揮中心"
                    },
                    {
                        "title": "延長全國疫情警戒第三級至7月26日止",
                        "url": "https://www.cdc.gov.tw/Bulletin/Detail/aiGegg4ncYmMP9dTx4W_Zw?typeid=9",
                        "agency": "衛生福利部疾病管制署／中央流行疫情指揮中心"
                    }
                ]
            }
        ]
    },
    2022: {
        "global": [
            {
                "id": "global-ukraine-invasion-2022",
                "year": 2022,
                "start_date": "2022-02-24",
                "end_date": "2022-02-24",
                "scope": "global",
                "category": "international_security",
                "title": "俄羅斯全面入侵烏克蘭",
                "summary": "俄羅斯對烏克蘭展開全面軍事入侵。日期為全面入侵起點，不表示衝突於當日結束。",
                "status": "conflict",
                "source_title": "Statement by the Secretary-General – Ukraine",
                "source_url": "https://ukraine.un.org/en/173250-statement-secretary-general-%E2%80%93-ukraine",
                "source_agency": "United Nations",
                "relevance_tags": [
                    "international_security",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-fed-hike-2022",
                "year": 2022,
                "start_date": "2022-06-15",
                "end_date": "2022-06-15",
                "scope": "global",
                "category": "finance",
                "title": "美國聯準會宣布升息 75 個基點",
                "summary": "聯準會宣布將聯邦基金利率目標區間提高至 1.50%–1.75%，相關實施指示自次日生效。",
                "status": "announced",
                "source_title": "Implementation Note issued June 15, 2022",
                "source_url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20220615a1.htm",
                "source_agency": "Federal Reserve",
                "relevance_tags": [
                    "finance",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-mpox-pheic-2022",
                "year": 2022,
                "start_date": "2022-07-23",
                "end_date": "2022-07-23",
                "scope": "global",
                "category": "public_health",
                "title": "WHO 宣布 mpox 國際公衛緊急事件",
                "summary": "WHO 將多國 mpox 疫情列為國際關注公共衛生緊急事件。",
                "status": "public_health_measure",
                "source_title": "WHO Director-General declares monkeypox outbreak a PHEIC",
                "source_url": "https://www.who.int/europe/news-room/23-07-2022-who-director-general-declares-the-ongoing-monkeypox-outbreak-a-public-health-event-of-international-concern",
                "source_agency": "WHO",
                "relevance_tags": [
                    "public_health",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ],
        "taiwan": [
            {
                "id": "tw-anti-stalking-2022",
                "year": 2022,
                "start_date": "2022-06-01",
                "end_date": "2022-06-01",
                "scope": "taiwan",
                "category": "law",
                "title": "跟蹤騷擾防制法施行",
                "summary": "跟蹤騷擾防制法上路，導入書面告誡及保護令等制度，規範符合構成要件的跟蹤騷擾行為。",
                "status": "implemented",
                "source_title": "跟蹤騷擾防制法施行及執行情形",
                "source_url": "https://www.npa.gov.tw/ch/app/data/doc?detailNo=1135731844407365632&module=wg063&type=s",
                "source_agency": "內政部警政署",
                "relevance_tags": [
                    "law",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-chishang-earthquake-2022",
                "year": 2022,
                "start_date": "2022-09-18",
                "end_date": "2022-09-18",
                "scope": "taiwan",
                "category": "disaster",
                "title": "臺東池上地震",
                "summary": "臺東池上發生規模 6.8 地震，為東部重大震災事件。日期記錄主震日。",
                "status": "natural_disaster",
                "source_title": "第111號地震參數（2022-09-18 14:44）",
                "source_url": "https://scweb.cwa.gov.tw/zh-TW/earthquake/Parameters/2022091814441568111",
                "source_agency": "中央氣象署",
                "relevance_tags": [
                    "disaster",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-border-zero-seven-2022",
                "year": 2022,
                "start_date": "2022-10-13",
                "end_date": "2022-10-13",
                "scope": "taiwan",
                "category": "public_health",
                "title": "入境改採 0+7 自主防疫",
                "summary": "入境人員免除居家檢疫，改為 7 天自主防疫，並配合調整邊境管制措施。",
                "status": "public_health_measure",
                "source_title": "邊境穩健開放，自10月13日起入境人員免除居家檢疫",
                "source_url": "https://www.cdc.gov.tw/Category/ListContent/EmXemht4IT-IRAPrAnyG9A?uaid=z3z1B05CM20AZhwyD5EJ1A",
                "source_agency": "衛生福利部疾病管制署",
                "relevance_tags": [
                    "public_health",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ]
    },
    2023: {
        "global": [
            {
                "id": "global-turkiye-syria-earthquakes-2023",
                "year": 2023,
                "start_date": "2023-02-06",
                "end_date": "2023-02-06",
                "scope": "global",
                "category": "disaster",
                "title": "土耳其與敘利亞強震",
                "summary": "強震襲擊土耳其與敘利亞，造成重大災害並引發跨國人道救援。",
                "status": "natural_disaster",
                "source_title": "Türkiye and Syria earthquakes",
                "source_url": "https://www.who.int/europe/emergencies/situations/turkiye-and-syria-earthquakes",
                "source_agency": "WHO",
                "relevance_tags": [
                    "disaster",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-svb-failure-2023",
                "year": 2023,
                "start_date": "2023-03-10",
                "end_date": "2023-03-10",
                "scope": "global",
                "category": "finance",
                "title": "矽谷銀行倒閉並由 FDIC 接管",
                "summary": "美國監管機關關閉矽谷銀行，由 FDIC 擔任接管人，成為銀行業風險的重要事件。",
                "status": "incident",
                "source_title": "Silicon Valley Bank failure information",
                "source_url": "https://www.fdic.gov/resources/resolutions/bank-failures/failed-bank-list/silicon-valley.html",
                "source_agency": "FDIC",
                "relevance_tags": [
                    "finance",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-covid-pheic-end-2023",
                "year": 2023,
                "start_date": "2023-05-05",
                "end_date": "2023-05-05",
                "scope": "global",
                "category": "public_health",
                "title": "WHO 結束 COVID-19 國際緊急狀態",
                "summary": "WHO 判定 COVID-19 不再構成國際關注公共衛生緊急事件；這不代表疾病消失或風險歸零。",
                "status": "public_health_measure",
                "source_title": "Statement on the fifteenth COVID-19 Emergency Committee meeting",
                "source_url": "https://www.who.int/europe/news/item/05-05-2023-statement-on-the-fifteenth-meeting-of-the-international-health-regulations-%282005%29-emergency-committee-regarding-the-coronavirus-disease-%28covid-19%29-pandemic",
                "source_agency": "WHO",
                "relevance_tags": [
                    "public_health",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ],
        "taiwan": [
            {
                "id": "tw-cecc-deactivated-2023",
                "year": 2023,
                "start_date": "2023-05-01",
                "end_date": "2023-05-01",
                "scope": "taiwan",
                "category": "public_health",
                "title": "COVID-19 防疫降階及指揮中心解編",
                "summary": "COVID-19 調整為第四類傳染病，中央流行疫情指揮中心同日解編，轉由衛福部持續整備。",
                "status": "public_health_measure",
                "source_title": "2023年5月1日起防疫降階，指揮中心同日解編",
                "source_url": "https://www.cdc.gov.tw/Bulletin/Detail/W65sFwVgfFn8ak3VVoh57Q?typeid=9",
                "source_agency": "衛生福利部疾病管制署",
                "relevance_tags": [
                    "public_health",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-anti-fraud-1-5-2023",
                "year": 2023,
                "start_date": "2023-05-04",
                "end_date": "2023-05-04",
                "scope": "taiwan",
                "category": "law_enforcement",
                "title": "行政院說明打詐行動綱領 1.5 版",
                "summary": "行政院院會報告新世代打擊詐欺策略行動綱領 1.5 版，說明識詐、堵詐、阻詐、懲詐等工作。",
                "status": "announced",
                "source_title": "2023年5月4日行政院會後記者會（第3854次會議）",
                "source_url": "https://www.ey.gov.tw/Page/AF73D471993DF350/24038379-540b-4faa-ae34-a811c9a8c321",
                "source_agency": "行政院",
                "relevance_tags": [
                    "law_enforcement",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-haikui-2023",
                "year": 2023,
                "start_date": "2023-09-03",
                "end_date": "2023-09-03",
                "scope": "taiwan",
                "category": "disaster",
                "title": "海葵颱風登陸臺東",
                "summary": "海葵颱風在臺東東河登陸，穿越臺灣後於西南沿海徘徊；日期為首次登陸日。",
                "status": "natural_disaster",
                "source_title": "海葵颱風概況表（202311）",
                "source_url": "https://rdc28.cwa.gov.tw/TDB/public/typhoon_detail?typhoon_id=202311",
                "source_agency": "中央氣象署",
                "relevance_tags": [
                    "disaster",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ]
    },
    2024: {
        "global": [
            {
                "id": "global-biden-targeted-tariffs-2024",
                "year": 2024,
                "start_date": "2024-05-14",
                "end_date": "2024-05-14",
                "scope": "global",
                "category": "trade",
                "title": "拜登政府宣布調高特定中國產品關稅",
                "summary": "拜登指示對電動車、半導體等特定中國產品調高 Section 301 關稅；此記錄宣布，品項實施日期分批安排，不等同同日全面生效。",
                "status": "announced",
                "source_title": "USTR remarks on actions to increase China tariffs",
                "source_url": "https://ustr.gov/about-us/policy-offices/press-office/press-releases/2024/may/icymi-us-trade-representative-katherine-tai-delivers-remarks-her-actions-increase-china-tariffs",
                "source_agency": "USTR",
                "relevance_tags": [
                    "trade",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-eu-ai-act-2024",
                "year": 2024,
                "start_date": "2024-08-01",
                "end_date": "2024-08-01",
                "scope": "global",
                "category": "technology",
                "title": "歐盟 AI Act 生效",
                "summary": "歐盟人工智慧法生效，建立風險分級治理框架；各項義務依過渡期分階段適用。",
                "status": "implemented",
                "source_title": "AI Act enters into force",
                "source_url": "https://commission.europa.eu/news-and-media/news/ai-act-enters-force-2024-08-01_en",
                "source_agency": "European Commission",
                "relevance_tags": [
                    "technology",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-mpox-pheic-2024",
                "year": 2024,
                "start_date": "2024-08-14",
                "end_date": "2024-08-14",
                "scope": "global",
                "category": "public_health",
                "title": "WHO 再宣布 mpox 國際公衛緊急事件",
                "summary": "WHO 因非洲 mpox 疫情及跨境傳播風險宣布國際關注公共衛生緊急事件。",
                "status": "public_health_measure",
                "source_title": "WHO Director-General declares mpox outbreak a PHEIC",
                "source_url": "https://www.who.int/news/item/14-08-2024-who-director-general-declares-mpox-outbreak-a-public-health-emergency-of-international-concern",
                "source_agency": "WHO",
                "relevance_tags": [
                    "public_health",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ],
        "taiwan": [
            {
                "id": "tw-hualien-earthquake-2024",
                "year": 2024,
                "start_date": "2024-04-03",
                "end_date": "2024-04-03",
                "scope": "taiwan",
                "category": "disaster",
                "title": "花蓮 0403 強震",
                "summary": "花蓮地區清晨發生強震，形成當年度重大震災及復原背景。日期記錄主震日。",
                "status": "natural_disaster",
                "source_title": "第019號地震震度圖（2024-04-03 07:58）",
                "source_url": "https://scweb.cwa.gov.tw/en-US/earthquake/ShakeMap/EE2024040307580971019",
                "source_agency": "中央氣象署",
                "relevance_tags": [
                    "disaster",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-inauguration-2024",
                "year": 2024,
                "start_date": "2024-05-20",
                "end_date": "2024-05-20",
                "scope": "taiwan",
                "category": "politics",
                "title": "第 16 任總統副總統就職",
                "summary": "賴清德、蕭美琴宣誓就職，完成第 16 任總統與副總統交接。",
                "status": "implemented",
                "source_title": "中華民國第16任總統副總統宣誓就職典禮",
                "source_url": "https://www.president.gov.tw/NEWS/28424",
                "source_agency": "總統府",
                "relevance_tags": [
                    "politics",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-anti-fraud-act-2024",
                "year": 2024,
                "start_date": "2024-07-31",
                "end_date": "2024-07-31",
                "scope": "taiwan",
                "category": "law",
                "title": "詐欺犯罪危害防制條例公布",
                "summary": "總統公布詐欺犯罪危害防制條例，建立防詐相關制度。此日期為公布日，不等同所有條文同日施行。",
                "status": "promulgated",
                "source_title": "制定詐欺犯罪危害防制條例",
                "source_url": "https://www.president.gov.tw/Page/294/49561?SearchBy=%E5%88%B6%E5%AE%9A%E8%A9%90%E6%AC%BA%E7%8A%AF%E7%BD%AA%E5%8D%B1%E5%AE%B3%E9%98%B2%E5%88%B6%E6%A2%9D%E4%BE%8B",
                "source_agency": "總統府",
                "relevance_tags": [
                    "law",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ]
    },
    2025: {
        "global": [
            {
                "id": "global-myanmar-earthquake-2025",
                "year": 2025,
                "start_date": "2025-03-28",
                "end_date": "2025-03-28",
                "scope": "global",
                "category": "disaster",
                "title": "緬甸中部強震",
                "summary": "緬甸中部發生強震，造成重大人道與醫療應變需求；日期記錄主震日。",
                "status": "natural_disaster",
                "source_title": "Myanmar earthquake response 2025",
                "source_url": "https://www.who.int/southeastasia/outbreaks-and-emergencies/myanmar-earthquake-response-2025",
                "source_agency": "WHO",
                "relevance_tags": [
                    "disaster",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-trump-reciprocal-tariffs-2025",
                "year": 2025,
                "start_date": "2025-04-02",
                "end_date": "2025-04-02",
                "scope": "global",
                "category": "trade",
                "title": "川普簽署對等關稅行政命令",
                "summary": "川普政府簽署對等關稅命令，安排基準及個別稅率分階段實施；其後措施多次調整，此處不將宣布稅率視為永久稅率。",
                "status": "announced",
                "source_title": "Regulating Imports with a Reciprocal Tariff",
                "source_url": "https://www.whitehouse.gov/presidential-actions/2025/04/regulating-imports-with-a-reciprocal-tariff-to-rectify-trade-practices-that-contribute-to-large-and-persistent-annual-united-states-goods-trade-deficits/",
                "source_agency": "White House",
                "relevance_tags": [
                    "trade",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "global-pandemic-agreement-2025",
                "year": 2025,
                "start_date": "2025-05-20",
                "end_date": "2025-05-20",
                "scope": "global",
                "category": "public_health",
                "title": "世界衛生大會通過大流行協定",
                "summary": "世界衛生大會通過大流行協定，推進未來疫情合作；通過文本不等同已對各國生效。",
                "status": "policy_change",
                "source_title": "World Health Assembly adopts historic Pandemic Agreement",
                "source_url": "https://www.who.int/news/item/20-05-2025-world-health-assembly-adopts-historic-pandemic-agreement-to-make-the-world-more-equitable-and-safer-from-future-pandemics",
                "source_agency": "WHO",
                "relevance_tags": [
                    "public_health",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ],
        "taiwan": [
            {
                "id": "tw-carbon-fee-2025",
                "year": 2025,
                "start_date": "2025-01-01",
                "end_date": "2025-01-01",
                "scope": "taiwan",
                "category": "climate",
                "title": "碳費費率生效並開始計算年度排放",
                "summary": "碳費費率生效，以本年度溫室氣體排放量計算，於次年 5 月繳納；不是本年度即已完成首次收費。",
                "status": "implemented",
                "source_title": "碳費徵收費率公告",
                "source_url": "https://carbonfee.moenv.gov.tw/front/info/detail",
                "source_agency": "環境部",
                "relevance_tags": [
                    "climate",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official",
                "sources": [
                    {
                        "title": "碳費徵收費率公告",
                        "url": "https://carbonfee.moenv.gov.tw/front/info/detail",
                        "agency": "環境部"
                    },
                    {
                        "title": "碳費依2025年排放量於2026年5月繳納",
                        "url": "https://enews.moenv.gov.tw/moenv-news/zh-tw/News/2354",
                        "agency": "環境部"
                    }
                ]
            },
            {
                "id": "tw-dapu-earthquake-2025",
                "year": 2025,
                "start_date": "2025-01-21",
                "end_date": "2025-01-21",
                "scope": "taiwan",
                "category": "disaster",
                "title": "嘉義大埔地區強震",
                "summary": "臺南東北方、嘉義大埔地區發生規模 6.4 地震，影響南部地區。日期記錄主震日。",
                "status": "natural_disaster",
                "source_title": "第007號地震參數（2025-01-21 00:17）",
                "source_url": "https://scweb.cwa.gov.tw/zh-tw/earthquake/Parameters/EE2025012100172664007",
                "source_agency": "中央氣象署",
                "relevance_tags": [
                    "disaster",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            },
            {
                "id": "tw-danas-2025",
                "year": 2025,
                "start_date": "2025-07-06",
                "end_date": "2025-07-06",
                "scope": "taiwan",
                "category": "disaster",
                "title": "丹娜絲颱風登陸嘉義",
                "summary": "丹娜絲颱風於嘉義布袋登陸，影響西部地區防災與民生運作；日期為登陸日。",
                "status": "natural_disaster",
                "source_title": "2504 丹娜絲颱風災害個案",
                "source_url": "https://ocean.cwa.gov.tw/V2/event",
                "source_agency": "中央氣象署",
                "relevance_tags": [
                    "disaster",
                    "historical_context"
                ],
                "date_note": "日期為標題所述的事件／政策節點，不表示整段影響期間。",
                "confidence": "official"
            }
        ]
    },
}

