#!/usr/bin/env python3
"""第二轮核验。Python 3.10+、pandas；复用第一轮只读解包与 CSV 读取。"""

import argparse
import hashlib
import importlib
import json
import logging
import platform
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

sys.dont_write_bytecode = True
first = importlib.import_module("00_data_audit")
START, END = first.START, first.END
INDEX_CODES = ("000905", "H00905")
BASE = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
DISCLOSURE = "https://www.sse.com.cn/market/sseindex/diclosure/c/"
RULE = "https://www.sse.com.cn/market/sseindex/calculation/c/10765000/files/fa4fc087fde8418d8f86265d511446bd.pdf"
HOLIDAY = "https://www.sse.com.cn/disclosure/announcement/general/c/c_20180606_4567900.shtml"
LISTING = "https://www.sse.com.cn/disclosure/announcement/listing/ipo/c/c_20210927_83094980.shtml"
DELISTING = "https://www.sse.com.cn/disclosure/announcement/general/c/c_20210910_5587127.shtml"
ANNEX = "https://oss-ch.csindex.com.cn/notice/{}-%E9%99%84%E4%BB%B6%EF%BC%9A%E9%83%A8%E5%88%86%E6%8C%87%E6%95%B0%E6%A0%B7%E6%9C%AC%E8%B0%83%E6%95%B4%E5%90%8D%E5%8D%95.pdf"

# 调出、调入代码次序与公告附件一致。2021-06 为公告转载的代码表。
PUBLISHED_DELTAS = {
    "2023-06-12": (
        "000062 000540 000656 000961 000990 000999 002002 002048 002124 002127 002146 002191 002212 002242 002396 002416 002434 002603 002701 002948 300072 300168 300376 300463 300630 300869 600006 600026 600064 600201 600216 600307 600376 600567 600648 600728 600787 600917 601333 601607 601699 601872 603345 603605 603606 603613 603719 688063 688088 688122",
        "000066 000423 000893 000933 000958 002008 002032 002240 002432 002463 002487 002518 002600 002608 002761 002791 300118 300395 300438 300442 300487 300529 300595 300748 600416 600481 600995 601136 601966 603338 603529 603826 603882 688052 688072 688082 688105 688107 688169 688200 688220 688234 688248 688276 688281 688295 688516 688520 688536 688778",
    ),
    "2023-12-11": (
        "000012 000415 000807 000869 002081 002110 002183 002221 002249 002250 002705 002745 002901 002985 300115 300182 300308 300442 300482 300618 300741 300832 600027 600171 600195 600259 600297 600372 600409 600487 600489 600507 600556 600623 600667 600705 600718 600782 601005 601136 601718 601869 601969 603638 688009 688116 688185 688256 688289 688777",
        "000539 000723 001286 002044 002064 002120 002262 002414 002472 002517 002558 002607 002756 002865 003022 003031 300114 300207 300394 300502 300601 301236 600004 600129 600583 600884 600925 600977 601061 601216 601933 603185 603305 603606 688005 688032 688063 688114 688120 688122 688153 688180 688297 688331 688348 688349 688375 688387 688425 688728",
    ),
    "2024-12-16": (
        "000031 000156 000630 000933 001872 002028 002497 002506 002518 002791 002865 002936 300088 300253 300296 300357 300394 300438 300502 300568 300682 300776 300861 301029 600022 600066 600315 600377 600399 600481 600827 600967 600985 601058 601077 601298 601828 603127 603218 603305 603317 603517 688006 688029 688063 688107 688169 688200 688348 688779",
        "000034 000403 000426 000733 002085 002318 002410 002603 002821 002841 300140 300142 300223 300339 300476 300496 300573 300751 300919 300957 301301 301308 301498 600007 600132 600295 600312 600487 600606 600685 600688 600720 601001 601061 601099 601918 603129 603341 603556 603605 603899 688047 688072 688249 688278 688361 688363 688469 688563 688578",
    ),
    "2021-06-15": (
        "000008 000301 000543 000600 002051 002064 002093 002217 002503 002544 002568 002589 002640 002791 002807 002920 002941 002957 300012 300134 300274 300324 300459 300496 300595 600053 600073 600079 600132 600143 600273 600277 600291 600338 600426 600545 600575 600664 600675 600748 600869 601799 601865 601966 603328 603338 603345 603806 603816 603882",
        "000671 000723 000799 000961 002065 002127 002146 002180 002422 002439 002532 002958 003022 003035 300037 300251 300253 300308 300383 300741 600027 600066 600068 600095 600177 600208 600271 600369 600377 600390 600487 600498 600536 600637 600663 600732 600803 600988 600998 601117 601187 601198 601568 601577 601636 601991 603156 603707 605358 688208",
    ),
}
DELTA_SOURCES = {
    "2023-06-12": ANNEX.format("20230526172747"),
    "2023-12-11": ANNEX.format("20231124170025"),
    "2024-12-16": ANNEX.format("20241129172348"),
    "2021-06-15": "https://www.lcaj.net/jingji/080530688.html",
}
DATE_SOURCES = {
    "2016-06-13": DISCLOSURE + "c_20160530_4121664.shtml",
    "2016-12-12": DISCLOSURE + "c_20161128_4207421.shtml",
    "2017-06-12": DISCLOSURE + "c_20170531_4318582.shtml",
    "2017-12-11": DISCLOSURE + "c_20171127_4424760.shtml",
    "2018-06-11": DISCLOSURE + "c_20180525_4561394.shtml",
    "2018-12-17": DISCLOSURE + "c_20181130_4684887.shtml",
    "2019-06-17": DISCLOSURE + "c_20190531_4830732.shtml",
    "2020-06-15": DISCLOSURE + "c_20200529_5114573.shtml",
    "2020-12-14": DISCLOSURE + "c_20201127_5268298.shtml",
    "2021-06-15": DISCLOSURE + "c_20210528_5476672.shtml",
    "2022-12-12": DISCLOSURE + "c_20221125_5712726.shtml",
    "2024-06-17": "https://jrj.sh.gov.cn/SCDT197/20240603/4d3202d0556a4cb2a0497a1f77c32897.html",
    "2024-12-16": "https://finance.sina.com.cn/money/fund/fundzmt/2024-11-29/doc-incxtqvq8682114.shtml",
}
SPECIAL = {
    "2017-01-18": ("单边出现，查 002670 首次可见与历史纳入", ""),
    "2017-02-14": ("有一进一出，尚无可逐码核实的 000905 公告", ""),
    "2017-07-03": ("000732 和 002118 同时消失，日期不合半年调样规则", ""),
    "2019-01-18": ("601598 首次可见，须核对公告和覆盖范围", ""),
    "2020-01-02": ("8 个代码同时恢复可见；与价格断点同日；无法证实数据拼接流程", ""),
    "2020-08-17": ("有一进一出，尚无可逐码核实的 000905 公告", ""),
    "2020-12-01": ("15 个代码同时消失，候选覆盖断点", ""),
    "2021-01-04": ("13 个代码出现，与 2020-12-01 缺口有大量重合，候选覆盖断点", ""),
    "2021-03-15": ("公告附件涉及上证系列，无 000905；仅说明风险警示背景，不能验证 2 进 2 出", DISCLOSURE + "c_20210303_5331150.shtml"),
    "2021-09-06": ("600068 提前消失；已知终止上市日为 09-13，指数和行情覆盖需分别核对", DELISTING),
    "2021-09-13": ("葛洲坝于当日终止上市；不能据此确认当日另一组 600297/600260 置换", DELISTING),
    "2021-09-28": ("601868 当日正式上市，吸收合并获证实，000905 临时调整本身待专属公告", LISTING),
    "2022-01-04": ("3 个代码同时消失，与 000998 价格断点同日，原因待核实", ""),
}

# 南方中证500ETF报告中「指数投资」部分的证券代码，按代码排序。
ETF_SNAPSHOTS = {
    "2023-12-29": """
        000009 000021 000027 000031 000039 000050 000060 000066 000089 000155 000156 000400 000401 000402
        000423 000513 000519 000537 000539 000547 000553 000559 000563 000581 000591 000598 000623 000629
        000630 000636 000683 000703 000709 000723 000728 000729 000738 000739 000750 000778 000783 000785
        000825 000830 000831 000878 000883 000887 000893 000898 000930 000932 000933 000937 000958 000959
        000960 000967 000970 000975 000987 000988 000997 000998 001203 001227 001286 001872 001914 002008
        002010 002019 002025 002028 002030 002032 002044 002056 002064 002065 002078 002080 002092 002120
        002128 002131 002138 002152 002153 002155 002156 002185 002192 002195 002203 002223 002240 002244
        002262 002266 002268 002273 002281 002294 002299 002326 002340 002353 002368 002372 002373 002384
        002385 002399 002407 002408 002409 002414 002422 002423 002429 002430 002432 002439 002444 002463
        002465 002468 002472 002487 002497 002500 002505 002506 002507 002508 002511 002517 002518 002531
        002532 002557 002558 002563 002568 002572 002595 002600 002607 002608 002624 002625 002653 002670
        002673 002683 002690 002738 002739 002756 002761 002791 002797 002831 002850 002865 002867 002925
        002926 002936 002939 002945 002958 002966 003022 003031 003035 300001 300003 300009 300012 300017
        300024 300026 300037 300058 300070 300073 300088 300114 300118 300136 300144 300146 300207 300212
        300244 300251 300253 300257 300285 300296 300357 300363 300373 300383 300390 300394 300395 300418
        300438 300474 300487 300502 300529 300558 300568 300595 300601 300604 300676 300677 300682 300699
        300724 300748 300776 300850 300861 300866 300888 301029 301236 600004 600008 600021 600022 600032
        600038 600056 600060 600062 600066 600079 600095 600096 600109 600118 600126 600129 600131 600141
        600143 600153 600155 600157 600160 600161 600166 600167 600170 600177 600208 600258 600271 600282
        600298 600299 600315 600316 600325 600329 600339 600348 600350 600352 600369 600373 600377 600378
        600380 600390 600392 600398 600399 600415 600416 600418 600435 600481 600482 600486 600497 600498
        600499 600500 600511 600516 600517 600521 600528 600529 600535 600536 600546 600549 600563 600566
        600580 600582 600583 600597 600598 600637 600642 600655 600663 600673 600699 600704 600707 600737
        600739 600755 600764 600765 600801 600808 600820 600827 600839 600848 600859 600862 600863 600867
        600871 600873 600879 600884 600885 600895 600901 600906 600909 600925 600927 600928 600956 600959
        600967 600968 600970 600977 600985 600988 600995 600998 601000 601016 601058 601061 601077 601098
        601106 601108 601118 601128 601139 601156 601158 601162 601168 601179 601187 601198 601216 601228
        601231 601233 601298 601456 601555 601568 601577 601598 601608 601611 601636 601665 601666 601696
        601717 601778 601828 601866 601880 601928 601933 601958 601966 601990 601991 601992 601997 603000
        603026 603056 603077 603127 603156 603160 603185 603218 603225 603228 603233 603267 603305 603317
        603338 603355 603379 603444 603456 603517 603529 603568 603589 603596 603606 603650 603658 603688
        603707 603712 603737 603786 603816 603826 603858 603866 603868 603882 603883 603885 603893 603927
        603939 605358 688002 688005 688006 688029 688032 688052 688063 688072 688082 688099 688105 688107
        688114 688120 688122 688153 688169 688180 688188 688200 688208 688220 688234 688248 688276 688281
        688295 688297 688301 688331 688348 688349 688375 688385 688387 688390 688425 688516 688520 688521
        688536 688538 688567 688690 688728 688772 688778 688779 688819 689009
    """,
    "2024-06-28": """
        000009 000021 000027 000031 000032 000039 000050 000060 000066 000155 000156 000400 000401 000423
        000513 000519 000537 000539 000559 000563 000591 000598 000623 000629 000630 000636 000683 000703
        000709 000723 000728 000729 000738 000739 000750 000778 000783 000785 000818 000825 000830 000831
        000878 000883 000887 000893 000898 000921 000932 000933 000937 000958 000959 000960 000967 000987
        000988 000997 000998 001203 001227 001286 001872 002008 002019 002025 002028 002044 002056 002064
        002065 002078 002080 002120 002128 002138 002152 002153 002155 002156 002185 002195 002202 002203
        002223 002240 002244 002261 002262 002266 002268 002273 002281 002294 002299 002340 002353 002368
        002372 002373 002384 002385 002407 002408 002409 002414 002423 002429 002430 002432 002436 002439
        002444 002465 002472 002487 002497 002500 002506 002507 002508 002517 002518 002531 002532 002557
        002558 002563 002568 002572 002595 002607 002608 002624 002625 002653 002670 002673 002683 002690
        002738 002739 002756 002791 002797 002831 002850 002865 002867 002926 002936 002939 002945 002958
        002966 002984 003022 003031 003035 300001 300002 300003 300009 300012 300017 300024 300037 300054
        300058 300070 300073 300088 300114 300118 300136 300144 300146 300207 300212 300251 300253 300285
        300296 300357 300373 300383 300390 300394 300395 300438 300474 300487 300502 300529 300558 300567
        300568 300595 300601 300604 300676 300677 300682 300699 300724 300748 300763 300765 300776 300803
        300861 300866 300888 301029 301165 301236 301267 301358 600004 600008 600021 600022 600032 600038
        600056 600060 600062 600066 600079 600095 600096 600098 600109 600118 600126 600129 600131 600141
        600143 600153 600155 600157 600166 600170 600177 600208 600258 600271 600282 600298 600299 600315
        600316 600325 600329 600339 600348 600350 600352 600361 600369 600373 600377 600378 600380 600390
        600392 600398 600399 600416 600418 600435 600481 600483 600486 600497 600498 600499 600500 600511
        600516 600517 600521 600528 600529 600535 600536 600546 600549 600563 600566 600578 600580 600582
        600583 600598 600612 600637 600642 600655 600663 600673 600699 600704 600707 600737 600739 600754
        600755 600763 600764 600765 600801 600808 600816 600820 600827 600839 600848 600859 600862 600863
        600867 600871 600872 600873 600879 600884 600885 600895 600901 600906 600909 600925 600927 600928
        600956 600959 600967 600968 600970 600977 600985 600988 600995 600998 601000 601016 601019 601058
        601077 601098 601106 601108 601118 601128 601139 601155 601156 601158 601162 601168 601179 601198
        601212 601216 601228 601231 601233 601298 601399 601456 601555 601567 601568 601577 601598 601608
        601611 601615 601636 601665 601666 601696 601717 601828 601858 601866 601880 601928 601933 601958
        601965 601966 601990 601991 601992 601997 603000 603056 603077 603087 603127 603156 603160 603179
        603185 603218 603225 603228 603233 603290 603298 603305 603317 603338 603345 603379 603444 603456
        603486 603517 603529 603568 603589 603596 603606 603650 603658 603688 603707 603712 603728 603737
        603786 603816 603826 603858 603868 603882 603883 603885 603893 603927 603939 603979 605358 688002
        688005 688006 688017 688029 688032 688052 688063 688065 688099 688107 688114 688120 688122 688153
        688169 688172 688180 688188 688200 688213 688220 688234 688248 688276 688281 688295 688297 688301
        688331 688348 688349 688375 688385 688387 688390 688425 688475 688516 688520 688521 688525 688536
        688538 688561 688567 688617 688772 688777 688778 688779 688819 689009
    """,
    "2024-12-31": """
        000009 000021 000027 000032 000034 000039 000050 000060 000066 000155 000400 000401 000403 000423
        000426 000513 000519 000537 000539 000559 000563 000591 000598 000623 000629 000636 000683 000703
        000709 000723 000728 000729 000733 000738 000739 000750 000778 000783 000785 000818 000825 000830
        000831 000878 000883 000887 000893 000898 000921 000932 000937 000958 000959 000960 000967 000987
        000988 000997 000998 001203 001227 001286 002008 002019 002025 002044 002056 002064 002065 002078
        002080 002085 002120 002128 002138 002152 002153 002155 002156 002185 002195 002202 002203 002223
        002240 002244 002261 002262 002266 002268 002273 002281 002294 002299 002318 002340 002353 002368
        002372 002373 002384 002385 002407 002408 002409 002410 002414 002423 002429 002430 002432 002436
        002439 002444 002465 002472 002487 002500 002507 002508 002517 002531 002532 002557 002558 002563
        002568 002572 002595 002603 002607 002608 002624 002625 002653 002670 002673 002683 002690 002738
        002739 002756 002797 002821 002831 002841 002850 002867 002926 002939 002945 002958 002966 002984
        003022 003031 003035 300001 300002 300003 300009 300012 300017 300024 300037 300054 300058 300070
        300073 300114 300118 300136 300140 300142 300144 300146 300207 300212 300223 300251 300285 300339
        300373 300383 300390 300395 300474 300476 300487 300496 300529 300558 300567 300573 300595 300601
        300604 300676 300677 300699 300724 300748 300751 300763 300765 300803 300866 300888 300919 300957
        301165 301236 301267 301301 301308 301358 301498 600004 600007 600008 600021 600032 600038 600056
        600060 600062 600079 600095 600096 600098 600109 600118 600126 600129 600131 600132 600141 600143
        600153 600155 600157 600166 600170 600177 600208 600258 600271 600282 600295 600298 600299 600312
        600316 600325 600329 600339 600348 600350 600352 600361 600369 600373 600378 600380 600390 600392
        600398 600416 600418 600435 600483 600486 600487 600497 600498 600499 600500 600511 600516 600517
        600521 600528 600529 600535 600536 600546 600549 600563 600566 600578 600580 600582 600583 600598
        600606 600612 600637 600642 600655 600663 600673 600685 600688 600699 600704 600707 600720 600737
        600739 600754 600755 600763 600764 600765 600801 600808 600816 600820 600839 600848 600859 600862
        600863 600867 600871 600872 600873 600879 600884 600885 600895 600901 600906 600909 600925 600927
        600928 600956 600959 600968 600970 600977 600988 600995 600998 601000 601001 601016 601019 601061
        601098 601099 601106 601108 601118 601128 601139 601155 601156 601158 601162 601168 601179 601198
        601212 601216 601228 601231 601233 601399 601456 601555 601567 601568 601577 601598 601608 601611
        601615 601636 601665 601666 601696 601717 601858 601866 601880 601918 601928 601933 601958 601965
        601966 601990 601991 601992 601997 603000 603056 603077 603087 603129 603156 603160 603179 603185
        603225 603228 603233 603290 603298 603338 603341 603345 603379 603444 603456 603486 603529 603556
        603568 603589 603596 603605 603606 603650 603658 603688 603707 603712 603728 603737 603786 603816
        603826 603858 603868 603882 603883 603885 603893 603899 603927 603939 603979 605358 688002 688005
        688017 688032 688047 688052 688065 688072 688099 688114 688120 688122 688153 688172 688180 688188
        688213 688220 688234 688248 688249 688276 688278 688281 688295 688297 688301 688331 688349 688361
        688363 688375 688385 688387 688390 688425 688469 688475 688516 688520 688521 688525 688536 688538
        688561 688563 688567 688578 688617 688772 688777 688778 688819 689009
    """,
}
ETF_SOURCES = {
    "2023-12-29": "https://www.sse.com.cn/disclosure/fund/announcement/c/new/2024-03-30/510500_20240330_LM9Y.pdf",
    "2024-06-28": "https://www.sse.com.cn/disclosure/fund/announcement/c/new/2024-08-31/510500_20240831_WXS0.pdf",
    "2024-12-31": "https://www.sse.com.cn/disclosure/fund/announcement/c/new/2025-03-31/510500_20250331_RRCI.pdf",
}
JUNE_2024_IN = """
    000032 000818 000921 002202 002261 002436 002984 300002 300054 300567
    300763 300765 300803 301165 301267 301358 600098 600361 600483 600578
    600612 600754 600763 600816 600872 601019 601155 601212 601399 601567
    601615 601858 601965 603087 603179 603290 603298 603486 603345 603728
    603979 688017 688065 688172 688213 688475 688525 688561 688617 688777
"""
JUNE_2024_SOURCE = "https://fund.eastmoney.com/a/202406033093798783.html"


def index_url(code):
    return BASE + "?" + urlencode(dict(indexCode=code, startDate="20160129", endDate="20241231"))


def reference(index, snapshot_dir):
    results = []
    for code in INDEX_CODES:
        url = index_url(code)
        if snapshot_dir:
            raw = (snapshot_dir / f"{code}.json").read_bytes()
        else:
            with urlopen(url, timeout=45) as response:
                raw = response.read()
        payload = json.loads(raw)
        assert payload["success"], code
        ref = pd.DataFrame(payload["data"])
        assert set(ref.indexCode) == {code} and ref.tradeDate.is_unique
        ref["trddt"] = pd.to_datetime(ref.tradeDate, format="%Y%m%d").dt.strftime("%Y-%m-%d")
        closed = ref.loc[ref.trddt.eq("2018-06-18")]
        assert len(closed) == 1 and closed.tradingVol.eq(0).all(), "核对上交所休市公告与官网额外记录"
        tradable = ref.loc[~ref.trddt.eq("2018-06-18")].sort_values("trddt").copy()
        assert tradable.close.gt(0).all()
        tradable["ref_ret"] = tradable.close.pct_change()
        in_window = tradable.trddt.between(START, END)
        assert set(tradable.loc[in_window, "trddt"]) == set(index.trddt)
        aligned = index.merge(tradable[["trddt", "ref_ret", "consNumber"]], on="trddt", validate="one_to_one")
        assert len(aligned) == len(index) and aligned.ref_ret.notna().all()
        error = aligned.ret.sub(aligned.ref_ret).abs()
        results.append(dict(code=code, n=len(error), within=int(error.le(.0001).sum()),
                            median=float(error.median() * 10000), max_error=float(error.max() * 10000),
                            counts=aligned.set_index("trddt").consNumber,
                            digest=hashlib.sha256(raw).hexdigest(), url=url))
    return results


def reconciliation(stock, index, counts):
    days = pd.Index(index.trddt)
    observed = stock.groupby("trddt").stkcd.agg(frozenset).reindex(days)
    assert observed.notna().all()
    second_fridays = [day for day in pd.date_range(START, END, freq="W-FRI")
                      if day.month in (6, 12) and 8 <= day.day <= 14]
    regular = {days[days.searchsorted(friday.strftime("%Y-%m-%d"), side="right")] for friday in second_fridays}
    switches = observed.ne(observed.shift())
    starts = list(observed.index[switches])
    assert regular.issubset(starts)
    rows = []
    for i, date in enumerate(starts):
        begin = days.get_loc(date)
        end = days.get_loc(starts[i + 1]) if i + 1 < len(starts) else len(days)
        current = observed[date]
        prior = observed.iloc[begin - 1] if i else frozenset()
        added, removed = current - prior, prior - current
        part = counts.loc[days[begin:end]]
        assert part.eq(500).all() and len(current) <= 500
        row = dict(date=date, prior_date=days[begin - 1] if i else "", interval_end=days[end - 1],
                   sessions=end - begin, panel_count=len(current), official_reported_count=int(part.iloc[0]),
                   count_shortfall=500 - len(current), observed_in_n=len(added),
                   observed_out_n=len(removed), observed_in=" ".join(sorted(added)),
                   observed_out=" ".join(sorted(removed)), evidence_status="", source="", official_in_n="",
                   official_out_n="", in_match_n="", out_match_n="", announced_in_absent="",
                   announced_out_absent_before="", announced_out_still_present="", observed_only_in="",
                   observed_only_out="", etf_check_date="", etf_index_holdings_n="",
                   etf_only="", observed_only_vs_etf="", etf_source="", note="")
        if date in PUBLISHED_DELTAS:
            out_text, in_text = PUBLISHED_DELTAS[date]
            expected_in, expected_out = set(in_text.split()), set(out_text.split())
            assert len(expected_in) == len(expected_out) == 50 and not expected_in & expected_out
            row.update(
                evidence_status="逐码核对（公告转载）" if date == "2021-06-15" else "逐码核对（官方附件）",
                source=" ".join(filter(None, [DELTA_SOURCES[date], DATE_SOURCES.get(date)])),
                official_in_n=len(expected_in), official_out_n=len(expected_out),
                in_match_n=len(added & expected_in), out_match_n=len(removed & expected_out),
                announced_in_absent=" ".join(sorted(expected_in - current)),
                announced_out_absent_before=" ".join(sorted(expected_out - prior)),
                announced_out_still_present=" ".join(sorted(expected_out & current)),
                observed_only_in=" ".join(sorted(added - expected_in)),
                observed_only_out=" ".join(sorted(removed - expected_out)),
                note="逐码对比仅覆盖此次公告的变更，存量名单仍待核对。",
            )
        elif date == "2024-06-17":
            expected_in = set(JUNE_2024_IN.split())
            assert len(expected_in) == 50
            row.update(evidence_status="逐码核对调入（转载），调出待核",
                       source=f"{DATE_SOURCES[date]} {JUNE_2024_SOURCE}",
                       official_in_n=len(expected_in), in_match_n=len(added & expected_in),
                       announced_in_absent=" ".join(sorted(expected_in - current)),
                       observed_only_in=" ".join(sorted(added - expected_in)),
                       note="转载仅刊登调入表，保留调出代码待核。")
        elif date in regular:
            row.update(evidence_status="定期规则日期吻合，名单待核",
                       source=" ".join(filter(None, [DATE_SOURCES.get(date), RULE])),
                       note="按第二个星期五收盘后的首个指数观测交易日复算。来源若仅涉及其他指数，作为共同日历旁证。")
        elif i:
            note, source = SPECIAL[date]
            row.update(evidence_status="非定期，有事件证据" if source else "非定期，未证实",
                       source=source, note=note)
        else:
            row.update(evidence_status="初始区间", note="需取得 2016-02-01 有效的完整初始快照。")
        snapshots = [day for day in ETF_SNAPSHOTS if date <= day <= days[end - 1]]
        assert len(snapshots) <= 1
        if snapshots:
            day = snapshots[0]
            holdings = set(ETF_SNAPSHOTS[day].split())
            assert len(holdings) == 500
            row.update(etf_check_date=day, etf_index_holdings_n=len(holdings),
                       etf_only=" ".join(sorted(holdings - current)),
                       observed_only_vs_etf=" ".join(sorted(current - holdings)),
                       etf_source=ETF_SOURCES[day])
        rows.append(row)
    return rows, days, observed, regular


def returns(stock, days, events):
    stock = stock.sort_values(["stkcd", "trddt"]).copy()
    grouped = stock.groupby("stkcd", sort=False)
    prev = grouped[["trddt", "close_adj", "ret", "volume", "amount"]].shift()
    positions = pd.Series(range(len(days)), index=days)
    left = prev.trddt.map(positions)
    right = stock.trddt.map(positions)
    gap = right - left - 1
    assert gap.dropna().ge(0).all()
    price_change = stock.close_adj.div(prev.close_adj).sub(1)
    error = price_change.sub(stock.ret)
    adjacent = gap.eq(0) & error.notna()
    outliers = adjacent & error.abs().gt(.0001)
    crossed = gap.gt(0)
    event_positions = [(positions[date], date) for date in events]
    details = []
    for idx in stock.index[outliers | crossed]:
        start_pos, stop_pos = int(left[idx]), int(right[idx])
        event_dates = [date for pos, date in event_positions if start_pos < pos <= stop_pos]
        assert not crossed[idx] or len(event_dates) >= 2, (stock.stkcd[idx], stock.trddt[idx])
        # 若价格四位小数、收益六位小数的舍入都取最不利方向，偏差仍远超过上界。
        low = (stock.close_adj[idx] - .00005) / (prev.close_adj[idx] + .00005) - 1
        high = (stock.close_adj[idx] + .00005) / (prev.close_adj[idx] - .00005) - 1
        rounding_bound = max(price_change[idx] - low, high - price_change[idx]) + .0000005
        details.append(dict(
            kind="相邻日偏差" if outliers[idx] else "跨交易日缺口", stkcd=stock.stkcd[idx],
            prev_date=prev.trddt[idx], date=stock.trddt[idx], skipped_sessions=int(gap[idx]),
            first_absent=days[start_pos + 1] if crossed[idx] else "",
            last_absent=days[stop_pos - 1] if crossed[idx] else "",
            set_change_at_exit=days[start_pos + 1] if crossed[idx] else "",
            set_change_at_return=stock.trddt[idx] if crossed[idx] else "",
            set_changes_crossed=" ".join(event_dates), prev_close_adj=prev.close_adj[idx],
            close_adj=stock.close_adj[idx], prev_ret=prev.ret[idx], ret=stock.ret[idx],
            prev_volume=prev.volume[idx], volume=stock.volume[idx], prev_amount=prev.amount[idx],
            amount=stock.amount[idx], price_change=price_change[idx], signed_difference=error[idx],
            abs_difference_bp=abs(error[idx]) * 10000,
            comparable_rounding_bound_bp=rounding_bound * 10000 if outliers[idx] else "",
            interpretation="相邻观测日，可比较，原因待确认" if outliers[idx] else "跨期价变与当日 ret 不可直接比较",
        ))
    assert len(details) == int(outliers.sum() + crossed.sum())
    detail = pd.DataFrame(details).sort_values(["kind", "date", "stkcd"])
    return detail, int(adjacent.sum()), error.loc[adjacent].abs()


def raw_quote_url(code):
    params = dict(secid=f"0.{code}", klt=101, fqt=0, beg="20191230", end="20241231",
                  fields1="f1,f2,f3,f4,f5,f6", fields2="f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61")
    return "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urlencode(params, safe=",")


def check_raw_quotes(details, snapshot_dir):
    for field in ("raw_prev_close", "raw_close", "raw_close_return", "ret_minus_raw_bp",
                  "prev_adj_to_raw", "adj_to_raw"):
        details[field] = float("nan")
    sources = []
    for code in sorted(details.loc[details.kind.eq("相邻日偏差"), "stkcd"].unique()):
        url = raw_quote_url(code)
        if snapshot_dir:
            raw = (snapshot_dir / f"{code}.raw.json").read_bytes()
        else:
            with urlopen(url, timeout=45) as response:
                raw = response.read()
        payload = json.loads(raw)["data"]
        assert payload["code"] == code
        quotes = [(line.split(",")[0], float(line.split(",")[2])) for line in payload["klines"]]
        closes = pd.Series(dict(quotes))
        assert len(closes) == len(quotes) and closes.gt(0).all()
        for idx, row in details.loc[details.kind.eq("相邻日偏差") & details.stkcd.eq(code)].iterrows():
            prev_close, close = closes[row.prev_date], closes[row.date]
            price_return = close / prev_close - 1
            details.loc[idx, ["raw_prev_close", "raw_close", "raw_close_return", "ret_minus_raw_bp",
                              "prev_adj_to_raw", "adj_to_raw"]] = [
                prev_close, close, price_return, (row.ret - price_return) * 10000,
                row.prev_close_adj / prev_close, row.close_adj / close,
            ]
        sources.append((code, url, hashlib.sha256(raw).hexdigest()))
    return sources


def monthly_coverage(stock, days, observed):
    month_ends = pd.Series(days).groupby(days.str[:7]).last().to_list()
    universe = stock.set_index(["stkcd", "trddt"]).sort_index()
    result = []
    for start, end in zip(month_ends, month_ends[1:]):
        future = days[days.get_loc(start) + 1:days.get_loc(end) + 1]
        candidates = sorted(observed[start])
        keys = pd.MultiIndex.from_product([candidates, future], names=universe.index.names)
        panel = universe[["close_adj", "ret", "volume", "amount"]].reindex(keys)
        next_day = future[0]
        next_rows = panel.xs(next_day, level="trddt")
        last_rows = panel.xs(end, level="trddt")
        full_returns = panel.ret.notna().groupby(level=0).all()
        result.append((start, next_day, end, len(candidates), int(next_rows.close_adj.notna().sum()),
                       int(last_rows.close_adj.notna().sum()), int(full_returns.sum()),
                       int(next_rows.volume.eq(0).sum()),
                       int((next_rows.close_adj.notna() & next_rows.volume.isna()).sum())))
    assert len(result) + 1 == len(month_ends)
    return result, month_ends[-1]


def report_constituents(rows, regular, stock, refs, digest):
    size = sum(row["sessions"] for row in rows if row["count_shortfall"])
    missing = sum(row["sessions"] * row["count_shortfall"] for row in rows)
    assert sum(row["sessions"] for row in rows) == refs[0]["n"]
    changes = sum(row["date"] != START for row in rows)
    checked = [row for row in rows if row["official_in_n"]]
    restored = next(row for row in rows if row["date"] == "2021-01-04")
    prior_cut = next(row for row in rows if row["date"] == "2020-12-01")
    overlap = set(restored["observed_in"].split()) & set(prior_cut["observed_out"].split())
    assert not stock.stkcd.eq("300114").any()
    summary = first.table(("起始日", "截至", "天数", "可见", "增加", "退出", "结果"),
                          [(r["date"], r["interval_end"], r["sessions"], r["panel_count"], r["observed_in_n"],
                            r["observed_out_n"], r["evidence_status"]) for r in rows])
    matched = first.table(("交易日", "调入匹配", "调出匹配", "公告调入但当日未见", "公告调出但前日未见", "证据"),
                          [(r["date"], f'{r["in_match_n"]}/{r["official_in_n"]}', (f'{r["out_match_n"]}/{r["official_out_n"]}' if r["official_out_n"] else "待核"),
                            r["announced_in_absent"] or "—", (r["announced_out_absent_before"] or "—") if r["official_out_n"] else "待核",
                            f'[样本变更名单]({DELTA_SOURCES.get(r["date"], JUNE_2024_SOURCE)})') for r in checked])
    snapshots = first.table(("交易日", "基金指数投资股票", "课程可见", "仅基金有", "仅课程有", "来源"),
        [(r["etf_check_date"], r["etf_index_holdings_n"], r["panel_count"], r["etf_only"] or "—",
          r["observed_only_vs_etf"] or "—", f'[510500 报告]({r["etf_source"]})')
         for r in rows if r["etf_check_date"]])
    return f"""# 第二轮数据核验 · 中证 500 历史成分股

## 结论

面板出现集合与历史调样存在明确联系。{changes} 次变化中，{len(regular)} 次逐日符合半年定期实施日，另有 {changes - len(regular)} 次发生在其他日期。取得 3 份中证指数公司原始名单和 1 份公告转载的完整变更表，已逐码对账。另逐码核对了 2024 年 6 月公示的调入表和三个南方中证 500 ETF 截面。差异证明面板存在遗漏，现有证据仍不足以复原 2016–2024 年完整的逐日官方股票池。

官网价格指数历史接口 `consNumber` 在课程 {refs[0]["n"]:,} 个交易日均为 500。课程文件有 {size:,} 日低于 500，合计少 {missing:,} 个代码日。这是**数量缺口下界**，如果可见集合含非成分代码，真实缺失可更多。官网样本数量本身不提供代码，也不能解释每个缺口的成因。 [中证指数官网历史行情]({refs[0]["url"]})

## 来源和构造方式

试卷写的是 `zz500_component_20230531`。桌面原始归档为 `data.tar`，成员是 `zz500_component_20241231.csv` 和 `index_zz500.csv`。归档 SHA-256 为 `{digest}`。试卷只把 CSMAR、锐思列为财务数据可选入口，未注明个股面板供应商、生成脚本或连接条件。第一版 GitHub 脚本提供的是审计逻辑，未提供数据生产流程。没有找到以这两个个股文件名为索引的可核验数据字典。

半年调样日期按 6 月和 12 月第二个星期五之后第一个指数交易日核对。遇节假日顺延，例如 2021-06-15 为 06-11 收盘后的首个观测交易日。公告日期吻合与逐证券匹配使用不同证据级别。 [中证指数样本规则]({RULE}) · [上交所与中证指数 2021 年 6 月公告]({DATE_SOURCES["2021-06-15"]})

## 逐码核对

{matched}

- **2023-06-12，000540**。官方名单列为调出证券，课程文件在调样前一交易日 2023-06-09 无该代码。它在归档只出现于 2021 年。深交所后来于 2023-06-30 公告终止登记服务，因此不能用早在 2021 年末已退市解释这个数据断点。公告直接证明调出记录无法在课程面板观察到，全段何时缺行情、何时不在成分内仍需补证。 [官方调样附件]({DELTA_SOURCES["2023-06-12"]}) · [深交所 000540 公告](https://www.szse.cn/disclosure/notice/general/t20230630_601499.html)
- **2023-12-11，300114**。官方名单列为调入，但全归档无该代码。可确认生效日课程面板缺一只公告调入股。国证指数公告确认其代码在考试窗口结束后才变为 302132。应查验课程导出是否用后来的代码或证券主表连接历史记录，具体遗漏环节仍待确认。 [官方调样附件]({DELTA_SOURCES["2023-12-11"]}) · [国证指数证券代码变更公告](https://www.cnindex.com.cn/zh_information/notices_news/2025/202502/P020250212310734081331.pdf)
- **2024-12-16**。公告的 50 进、50 出全部匹配，面板调整前后均为 499 只。年末 ETF 持仓对照把该缺额指向 300114，仍需当日官方全量名单确认。 [官方调样附件]({DELTA_SOURCES["2024-12-16"]})
- **2020 年末**。2020-12-01 同日消失 15 只，2021-01-04 新出现 13 只，其中 {len(overlap)} 只为同一批代码（{", ".join(sorted(overlap))}）。这是时间边界覆盖异常的线索，变更本身未经官方名册验证。
- **2021 年葛洲坝与中国能建**。600068 最后可见于 09-03 当天，09-06 起缺行，09-13 才终止上市。601868 在 09-28 首次可见，与上市日一致，该日 `ret` 为空。已核对上交所两份临时调样附件，2021 年 3 月及葛洲坝换股的附件都没有 000905 条目。因此仅能验证公司事件和样本变动的时间关系，000905 的临时调整仍待对应公告。另外，09-13 的 600297／600260 置换须独立核对。 [吸收合并及上证指数调整公告]({DISCLOSURE}c_20210830_5570656.shtml) · [葛洲坝终止上市通知]({DELISTING}) · [中国能建上市公告]({LISTING}) · [2021 年 3 月上证系列调样公告]({DISCLOSURE}c_20210303_5331150.shtml)

## 基金披露截面旁证

南方中证 500 ETF（510500）披露以完全复制法跟踪标的指数。取报告中的「指数投资」板块，排除积极投资股票，以相应报告期末最后一个交易日对齐。三个截面分别有 500 个证券代码，课程中 499 个可见代码全部匹配，唯一差异均为 300114。公开调入名单和三次独立截面对照共同支持 300114 解释 2023 年末及 2024 年的持续缺额。ETF 披露属于基金实际持仓，日度官方成员仍需由指数公司证明。

{snapshots}

## 全期逐次核对

每行代表日度集合维持不变的区间。首行为初始集合，后续 {changes} 行为每一次变化。CSV 保存所有调入／调出代码、与公开名单的差集、证据链接及未证实日期的说明。初始日及存量成分仍需分别用官方 500 股快照核实。

{summary}

覆盖缺口具有持续性，部分边界在非调样时点。已确认个别缺码，缺额清单及漏采、停牌、退市、换股和数据连接过滤的贡献还无法全量归因。零成交记录仍有行情行，不能用于填补上述缺行。后续用带生效时间的官方成员表与独立全市场行情分别做双向核对，然后确定可回测范围。

[逐次对账 CSV](05_constituent_reconciliation.csv) · [收益异常与缺口 CSV](06_return_consistency.csv) · [回测可行性与补数要求](07_followup_data_requirements.md)
"""


def report_requirements(index, refs, raw_sources, details, n_adj, errors, months, last_month):
    abnormal = details[details.kind.eq("相邻日偏差")]
    gaps = details[details.kind.eq("跨交易日缺口")]
    gap_stats = gaps.groupby(["first_absent", "date"]).size().sort_values(ascending=False).head(8)
    index_table = first.table(("官方参考", "对齐日", "偏差 ≤ 1bp", "偏差 > 1bp", "中位绝对偏差（bp）", "最大绝对偏差（bp）"),
        [(f'[{r["code"]}]({r["url"]})', r["n"], r["within"], r["n"] - r["within"],
          f'{r["median"]:.5f}', f'{r["max_error"]:.5f}') for r in refs])
    abnormal_table = first.table(("代码", "前一观测日", "日期", "昨复权价", "当日复权价", "相邻价变", "ret",
        "未复权价变", "绝对偏差（bp）", "昨复权／原价", "当日复权／原价"),
        [(r.stkcd, r.prev_date, r.date, f"{r.prev_close_adj:.4f}", f"{r.close_adj:.4f}", f"{r.price_change:.6%}",
          f"{r.ret:.6%}", f"{r.raw_close_return:.6%}", f"{r.abs_difference_bp:.2f}",
          f"{r.prev_adj_to_raw:.6f}", f"{r.adj_to_raw:.6f}") for r in abnormal.itertuples()])
    riskfree = index.riskfree
    month_missing = sum(r[3] != r[5] for r in months)
    month_incomplete = sum(r[3] != r[6] for r in months)
    next_missing = sum(r[3] - r[4] for r in months)
    end_missing = sum(r[3] - r[5] for r in months)
    full_missing = sum(r[3] - r[6] for r in months)
    month_table = first.table(("月末观察日", "下一指数日", "下月末", "当期可见", "次日有行", "下月末有行",
                               "全窗口 ret 非空", "次日零量", "次日量空白（有行）"), months)
    sources = [(r["code"], r["url"], r["digest"]) for r in refs] + raw_sources
    source_table = first.table(("序列", "公开接口", "核验快照 SHA-256"),
                               [(code, f"[源接口]({url})", f"`{digest}`") for code, url, digest in sources])
    return f"""# 第二轮数据核验 · 收益口径、回测可行性与补数要求

## 个股收益核验

严格按同股且相邻两个指数交易日比较 `close_adj[t] / close_adj[t-1] - 1` 与 `ret[t]`。{n_adj:,} 个可比对中有 {len(abnormal)} 条绝对偏差超过 1bp，绝对偏差中位数为 {errors.median() * 10000:.5f}bp。所有超阈值记录均列于下表。

{abnormal_table}

东方财富日线接口以 `fqt=0` 取未复权行情。五条原始收盘到收盘收益与课程 `ret` 的绝对差均小于 0.01bp，`close_adj` 相对未复权价的倍率却在这些日期突然变化。000998 的倍率在约 10.96981 与 11.26723 间反复切换。按课程价格显示至多四位小数、收益六位小数估算的最不利舍入误差也远小于这些偏差。证据支持五处异常来自价格倍率断点，具体生产原因仍需课程数据提供方的复权因子与生成过程。原始日线是独立复核来源。 [000078 未复权行情]({raw_quote_url("000078")}) · [000998 未复权行情]({raw_quote_url("000998")})

目前无法确认全表采用前复权或后复权、锚定日、分红再投资方式，也无法将五条证据外推为个股 `ret` 全期统一口径。即使是正确的复权价，也仅用于一致口径的收益计算，成交模拟取实际可交易未复权价格。

### 222 组跨交易日缺口

共有 {len(gaps)} 组、涉及 {gaps.stkcd.nunique()} 只股票，累计跨越 {gaps.skipped_sessions.sum():,} 个代码日，最大 {gaps.skipped_sessions.max():,} 日。其中 {int(gaps.skipped_sessions.eq(1).sum())} 组仅跨过一个交易日。每组缺口首日、末日和所有跨越的集合变化均已标在 [明细 CSV](06_return_consistency.csv)。按起止日期聚合后有 {len(gaps.groupby(["first_absent", "date"]))} 种区间，出现最多的见下表。

{first.table(("首个缺行日", "再现日", "代码数"), [(a,b,n) for (a,b),n in gap_stats.items()])}

所有缺口都跨过可见集合的退出和重返边界。这个性质来自面板缺行，不能单独验证成分迁移。多数跨期的价格变化包含缺口内变动，课程再现日 `ret` 仅作为当日字段保留。所有 {int(gaps.abs_difference_bp.gt(1).sum())} 条可见偏差超过 1bp 的缺口都不能据此定为收益字段错误。跨成分退出后仍持有时，必须补足从退出前到处置完成的独立行情。缺口统计只覆盖同股两条可见记录之间，完全缺失的证券及永久离开后的缺行另由成分核验处理。

## 指数收益与无风险利率

用中证指数官网历史收盘点位分别计算 000905 价格指数与 H00905 全收益指数的相邻交易日收益，含 2016-01-29 作为首日基期。两个接口各有一条 2018-06-18 零成交量记录（全收益点位仍有变化），按上交所端午节休市公告排除。余下窗口日期与课程表完全一致。 [上交所休市公告]({HOLIDAY})

{index_table}

课程 `ret` 与官方 000905 收盘到收盘价格收益高度一致，并能与 H00905 全收益口径区分。点位公开精度与课程收益精度允许微小偏差。指数两种收益口径的选择应对照试卷要求，并保持超额收益计算的口径一致。官网指数开盘点位仅供指数对齐，个股开盘成交价及指数策略的可交易载体另需数据。

`riskfree` 每个交易日都有一条记录，{len(riskfree):,} 条、{riskfree.nunique()} 个不同值，{int(riskfree.diff().dropna().ne(0).sum())} 次相邻变化，范围 {riskfree.min():.6f}–{riskfree.max():.6f}。试卷和归档只证明用途，无原始标的、期限、原始报价、单位、计息频率、日计数、复利方式、年化换算或可得时点。检索文件名和字段名未找到可与课程列直接溯源的元数据。逐日记录只反映存储频率，不足以认定它为日利率。Sharpe 计算等待来源说明或可核实的替代序列和频率转换。信息比率依赖相对基准的收益与跟踪误差，关键是基准口径及收益时间对齐。

## 月末覆盖与执行可行性

用每月最后一个指数交易日作为观察日，只做下月覆盖核对。共有 {len(months)} 个完整相邻月末区间，末月 {last_month} 的下一窗口超出样本。把观察日所有可见代码作为核对分母，{month_missing} 个区间至少有一只在下月末缺行，{month_incomplete} 个区间至少有一只的下一月日度 `ret` 链有断点。跨月累计有 {next_missing} 个观察代码在下一交易日缺行，{end_missing} 个在下月末缺行，{full_missing} 个的下月收益链未覆盖。计数只描述可见样本，不筛选标的，也不计算任何未来收益。

<details>
<summary>按月核对可见行和收益字段覆盖</summary>

{month_table}

</details>

| 场景 | 数据可行性 |
| --- | --- |
| 月度传统选股 | 月末日期和历史日频数据可用于研究准备。官方有效成分缺失、未来持有期行情中断、成分退出与退市处置不明，现有文件不足以完成考试要求的正式回测。 |
| 横截面机器学习 | 可检查特征和标签的覆盖条件。正式训练和样本外评估前要补齐历史成分和独立持有期收益，明确标签完整可得时点、样本外边界及重叠窗口隔离。仅保留下月仍有行情的股票会引入前视选择。 |
| 指数级机器学习 | 官方公开价格基准已核对，可支持指数预测口径的研究准备。投资效果验证仍需可交易 ETF 或其他合规载体、实际开收盘行情、费率与交易状态。 |
| 次日开盘执行 | 可按指数日历定位日期。材料无个股开盘价、开盘可交易状态或报价，无法模拟开盘成交。盘后才完整的月末价格和量额也无法用于同一收盘竞价。 |
| 费用和可交易状态 | 缺交易费率、卖出印花税历史制度、冲击与滑点数据。零量、量额空白、整行缺失各有不同含义。停复牌、涨跌停及一字板可成交性、上市与退市事件需交易所或可靠供应商字段。 |

## 补数与验收口径

1. **优先取得生效时点的完整股票池。** 补 2016-02-01 的完整起始名单，及至 2024-12-31 的每次定期与临时调整代码、公告时间和生效时点，或每日完整官方快照。与当前 CSV 按代码、交易日双向逐码匹配。向课程方索取实际导出查询和连接规则，先定位 000540、300114 及 2024-12-16 的持久缺额。
2. **补可交易行情和事件。** 取得完整未复权开高低收、前收、量额、停复牌、价格上下限、退市／换股，以及能覆盖离开成分后处置期的连续报价。补逐日因子、锚点、公司行动和含息收益口径。以两只股票五处断点及 222 个缺口回查源表。
3. **统一基准和利率口径。** 固定已核实的 000905 价格基准版本及交易日。和课程方确认 `riskfree` 原始序列、期限、发布时点、单位和转换公式，补充可核验参考序列与元数据。指数级策略需要另行确认执行载体、对应价格和费用。
4. **明确执行假设。** 获取按日期有效的佣金、交易税费及可支持滑点和流动性约束的数据。若采用基本面、行业或市值类输入，补历史披露时间、修订版本和成分有效时点，分别留出标签完成与可观测时间。

## 复现

```bash
python3 -B code/01_followup_audit.py --archive data.tar
```

脚本默认查询公开接口，可通过 `--evidence-dir` 使用保存的 `000905.json`、`H00905.json`、`000078.raw.json`、`000998.raw.json` 重放。快照取得于 2026-11-25，未放入 GitHub 提交。公告变更代码与 ETF 披露截面代码及其来源链接在脚本内，其他日期按公告、公式日期或公司事件分级。运行环境为 Python {platform.python_version()}、pandas {pd.__version__}。脚本核对原 TAR 的前后哈希，输出第二轮四份报告及表格，原始记录未经修改或填补。

{source_table}

[历史成分股核对](04_constituent_reconciliation.md) · [逐次对账 CSV](05_constituent_reconciliation.csv) · [收益异常与缺口 CSV](06_return_consistency.csv)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--archive", type=Path, default=root / "data.tar")
    parser.add_argument("--output-dir", type=Path, default=root / "output")
    parser.add_argument("--evidence-dir", type=Path, help="已下载 JSON 快照目录")
    args = parser.parse_args()
    if not __debug__:
        parser.error("请关闭 Python 优化以启用核验断言")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    archive = args.archive.resolve(strict=True)
    digest = first.sha256(archive)
    with TemporaryDirectory(prefix="zz500-followup-") as work:
        directory = Path(work)
        first.unpack(archive, directory)
        stock, _, bad_stock_date, bad_stock_code = first.read_csv(directory / first.STOCK)
        index, _, bad_index_date, bad_index_code = first.read_csv(directory / first.INDEX)
    assert bad_stock_date == bad_stock_code == bad_index_date == bad_index_code == 0
    assert not stock.duplicated(["stkcd", "trddt"]).any() and index.trddt.is_unique
    assert stock.close_adj.gt(0).all()
    index = index.sort_values("trddt")
    refs = reference(index, args.evidence_dir)
    assert refs[0]["counts"].equals(refs[1]["counts"])
    rows, days, observed, regular = reconciliation(stock, index, refs[0]["counts"])
    detail, valid_count, errors = returns(stock, days, [r["date"] for r in rows])
    assert len(rows) == 32 and len(regular) == 18
    assert valid_count == 1_059_131 and detail.kind.value_counts().to_dict() == {
        "跨交易日缺口": 222, "相邻日偏差": 5}
    assert refs[0]["within"] == refs[0]["n"]
    raw_sources = check_raw_quotes(detail, args.evidence_dir)
    abnormal = detail[detail.kind.eq("相邻日偏差")]
    assert abnormal.abs_difference_bp.gt(abnormal.comparable_rounding_bound_bp).all()
    assert abnormal.ret_minus_raw_bp.abs().lt(.01).all()
    months, last_month = monthly_coverage(stock, days, observed)
    assert first.sha256(archive) == digest
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    names = ("04_constituent_reconciliation.md", "05_constituent_reconciliation.csv",
             "06_return_consistency.csv", "07_followup_data_requirements.md")
    for name in names:
        target = output / name
        if target.is_symlink() or (target.exists() and target.samefile(archive)):
            parser.error(f"输出为符号链接或与原档案相同：{target}")
    (output / names[0]).write_text(report_constituents(rows, regular, stock, refs, digest), encoding="utf-8")
    first.write_csv(output / names[1], rows)
    detail.to_csv(output / names[2], index=False, encoding="utf-8-sig", float_format="%.12g")
    (output / names[3]).write_text(
        report_requirements(index, refs, raw_sources, detail, valid_count, errors, months, last_month),
        encoding="utf-8")
    logging.info("核验结束：%s 个面板区间，%s 条收益异常或缺口，原始 TAR SHA-256 %s",
                 len(rows), len(detail), digest)


if __name__ == "__main__":
    main()
