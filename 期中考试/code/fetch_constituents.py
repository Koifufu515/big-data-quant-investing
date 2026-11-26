#!/usr/bin/env python3
"""获取 BaoStock 中证500月末快照并与课程原始数据和公开证据核对。"""

import argparse
import hashlib
import importlib
import json
import re
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
followup = importlib.import_module("01_followup_audit")
first = followup.first
BAO_DOC = "https://www.baostock.com/mainContent?file=pythonAPI.md"
SSE = "https://www.sse.com.cn/market/sseindex/diclosure/c/"
RULE = followup.RULE
MERGER_TABLE = SSE + "10077967/files/d18a88b5ce8e4b04a8cce59875d723b6.xlsx"


def sources(root):
    with tarfile.open(root / "data.tar") as tar:
        assert set(tar.getnames()) == {first.STOCK, first.INDEX}
        with tar.extractfile(first.INDEX) as handle:
            index = pd.read_csv(handle, usecols=["trddt"])
        with tar.extractfile(first.STOCK) as handle:
            panel = pd.read_csv(handle, usecols=["stkcd", "trddt"], dtype={"stkcd": str},
                                encoding="gb18030", encoding_errors="surrogateescape")
    assert not panel.duplicated(["trddt", "stkcd"]).any()
    days = pd.Index(sorted(index.trddt))
    assert days.is_unique and set(days) == set(panel.trddt)
    pools = panel.groupby("trddt").stkcd.agg(frozenset)
    months = pd.Series(days).groupby(days.str[:7]).last().to_dict()
    months = {"2016-01": "2016-01-29", **months}
    return days, pools, months


def date_requests(days, pools, months):
    fridays = [d for d in pd.date_range(days[0], days[-1], freq="W-FRI")
               if d.month in (6, 12) and 8 <= d.day <= 14]
    regular = {days[days.searchsorted(d.strftime("%Y-%m-%d"), side="right")] for d in fridays}
    event_days = set(pools.index[pools.ne(pools.shift())]) - {days[0]}
    event_days |= regular
    requests = set(months.values()) | {"2016-01-04", "2016-02-01"}
    for d in event_days:
        at = days.get_loc(d)
        requests.update(days[max(0, at - 1): min(len(days), at + 7)])
    return sorted(requests), sorted(event_days), regular


def get_bao(dates, cache, offline):
    previous = json.loads(cache.read_text()) if cache.exists() else {}
    todo = [d for d in dates if d not in previous]
    if offline:
        assert not todo, f"缓存缺少 {len(todo)} 个查询日期"
    if not todo:
        return previous
    import baostock as bs

    retrieved = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    result = bs.login()
    if result.error_code != "0":
        raise RuntimeError(f"BaoStock login {result.error_code}: {result.error_msg}")
    try:
        for i, day in enumerate(todo):
            response = bs.query_zz500_stocks(date=day)
            rows = []
            while response.error_code == "0" and response.next():
                rows.append(dict(zip(response.fields, response.get_row_data())))
            previous[day] = dict(error_code=response.error_code, error=response.error_msg,
                                 retrieved=retrieved, rows=rows)
            if i % 10 == 0 or i + 1 == len(todo):
                staging = cache.with_suffix(".new")
                staging.write_text(json.dumps(previous, ensure_ascii=False), encoding="utf-8")
                staging.replace(cache)
                print(f"BaoStock {i + 1}/{len(todo)}，截至 {day}", flush=True)
    finally:
        bs.logout()
    return previous


def entry(raw, query_date):
    rows = raw["rows"]
    codes = [row.get("code", "") for row in rows]
    invalid = sum(re.fullmatch(r"(?:sh|sz|bj)\.[0-9]{6}", x) is None for x in codes)
    normalized = {c[-6:] for c in codes if re.fullmatch(r"(?:sh|sz|bj)\.[0-9]{6}", c)}
    updates = sorted({row.get("updateDate", "") for row in rows})
    dated = bool(updates) and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", x) and x <= query_date for x in updates)
    valid = raw["error_code"] == "0" and len(rows) == len(normalized) == 500 and not invalid and dated
    code_asof = {row["code"][-6:]: row for row in rows if re.fullmatch(r"(?:sh|sz|bj)\.[0-9]{6}", row.get("code", ""))}
    signature = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return dict(raw=raw, codes=normalized, rows=len(rows), invalid=invalid, signature=signature,
                duplicates=len(rows)-invalid-len(normalized), updates=updates, valid=valid, by_code=code_asof)


# 固定抄录基金财报中的完整「指数投资」名单，保留来源。
ETF_EXTRA = {
    "2017-12-29": """
        000006 000009 000012 000021 000025 000027 000028 000031 000039 000049 000050 000061 000062 000066
        000078 000089 000090 000099 000156 000158 000400 000401 000418 000426 000488 000501 000513 000519
        000528 000536 000541 000543 000547 000552 000563 000566 000572 000581 000587 000592 000596 000598
        000600 000612 000636 000652 000656 000661 000662 000667 000669 000680 000681 000685 000690 000703
        000712 000718 000727 000729 000732 000758 000761 000762 000766 000777 000778 000786 000806 000807
        000816 000825 000829 000830 000848 000860 000877 000878 000887 000897 000926 000930 000937 000939
        000960 000969 000970 000975 000977 000979 000981 000987 000988 000990 000997 000998 000999 001696
        002001 002002 002004 002005 002011 002013 002018 002019 002022 002028 002030 002032 002038 002041
        002048 002049 002050 002051 002056 002063 002064 002073 002078 002092 002093 002106 002118 002122
        002123 002127 002128 002131 002147 002152 002155 002176 002179 002183 002190 002191 002195 002221
        002223 002233 002242 002244 002249 002250 002251 002254 002261 002266 002268 002269 002271 002273
        002276 002277 002280 002281 002285 002299 002308 002311 002317 002325 002332 002340 002342 002344
        002345 002353 002354 002358 002359 002366 002368 002371 002373 002375 002384 002390 002392 002400
        002405 002407 002408 002410 002414 002416 002422 002428 002431 002434 002437 002439 002440 002444
        002463 002477 002479 002482 002489 002491 002503 002505 002506 002512 002517 002544 002551 002573
        002583 002588 002589 002603 002635 002640 002642 002657 002663 002665 002670 002672 002681 002690
        002699 002701 002707 002709 002745 002807 002815 002818 300001 300002 300010 300026 300032 300039
        300043 300055 300058 300088 300113 300115 300116 300133 300134 300146 300147 300159 300166 300182
        300197 300199 300202 300244 300253 300257 300266 300273 300274 300287 300291 300297 300324 300376
        300383 600004 600006 600017 600022 600026 600037 600039 600053 600056 600058 600059 600060 600062
        600064 600073 600079 600086 600094 600098 600108 600120 600122 600125 600126 600138 600141 600143
        600151 600155 600158 600160 600161 600166 600169 600171 600176 600179 600183 600184 600187 600195
        600201 600216 600240 600256 600259 600260 600266 600267 600270 600277 600280 600282 600284 600289
        600291 600292 600298 600300 600307 600312 600315 600316 600317 600325 600329 600335 600338 600346
        600348 600366 600380 600388 600392 600393 600395 600409 600410 600416 600418 600422 600426 600428
        600435 600438 600458 600460 600466 600478 600481 600499 600500 600503 600511 600516 600517 600521
        600525 600536 600545 600557 600563 600565 600566 600572 600575 600578 600580 600582 600584 600587
        600594 600597 600598 600600 600611 600614 600618 600623 600628 600633 600635 600639 600640 600642
        600643 600645 600648 600651 600655 600657 600664 600673 600687 600694 600717 600718 600729 600737
        600743 600748 600750 600751 600754 600755 600757 600759 600765 600770 600773 600776 600787 600801
        600808 600811 600823 600826 600835 600839 600848 600859 600862 600863 600869 600872 600874 600875
        600879 600880 600881 600884 600885 600894 600908 600917 600936 600939 600967 600970 600971 600978
        600993 600996 601000 601001 601002 601016 601020 601127 601128 601168 601200 601231 601233 601311
        601678 601689 601699 601717 601777 601811 601880 601928 601969 603000 603001 603019 603025 603077
        603169 603188 603198 603225 603228 603328 603355 603369 603377 603444 603515 603528 603556 603568
        603569 603589 603658 603766 603806 603816 603868 603877 603883 603888
    """,
    "2021-12-31": """
        000009 000012 000021 000027 000028 000031 000039 000046 000050 000060 000062 000089 000090 000156
        000158 000400 000401 000402 000415 000488 000513 000519 000528 000537 000540 000547 000553 000559
        000563 000581 000598 000623 000629 000630 000636 000656 000671 000685 000686 000690 000709 000717
        000718 000723 000728 000729 000733 000738 000739 000750 000758 000778 000807 000825 000830 000869
        000877 000878 000883 000887 000898 000930 000932 000937 000959 000960 000961 000967 000970 000975
        000983 000987 000988 000990 000997 000998 000999 001203 001872 001914 001965 002002 002004 002010
        002013 002019 002028 002030 002038 002048 002056 002065 002075 002078 002080 002081 002085 002092
        002110 002124 002127 002128 002131 002138 002146 002152 002153 002155 002156 002174 002180 002183
        002185 002191 002195 002203 002212 002221 002223 002233 002242 002244 002249 002250 002266 002268
        002273 002281 002294 002299 002302 002340 002353 002368 002372 002373 002375 002382 002384 002385
        002387 002390 002396 002399 002408 002409 002416 002422 002423 002424 002429 002430 002434 002439
        002440 002444 002458 002465 002468 002500 002505 002506 002507 002508 002511 002532 002557 002563
        002572 002595 002603 002653 002670 002673 002683 002690 002701 002705 002739 002745 002797 002815
        002831 002867 002901 002925 002926 002936 002939 002945 002946 002948 002958 002966 002985 003022
        003035 300001 300009 300017 300024 300026 300037 300058 300070 300072 300088 300115 300133 300136
        300146 300166 300168 300182 300212 300223 300244 300251 300253 300257 300271 300285 300296 300308
        300315 300357 300363 300376 300383 300418 300463 300474 300482 300618 300630 300699 300724 300741
        300751 300763 300869 600006 600008 600021 600022 600026 600027 600037 600038 600039 600056 600060
        600062 600064 600066 600095 600118 600120 600126 600131 600141 600153 600155 600157 600158 600160
        600166 600167 600170 600171 600177 600188 600195 600201 600208 600216 600233 600236 600256 600258
        600259 600266 600271 600282 600297 600298 600299 600307 600315 600316 600325 600329 600339 600348
        600350 600369 600372 600373 600376 600377 600380 600390 600392 600398 600399 600409 600415 600418
        600435 600446 600466 600482 600486 600487 600497 600498 600500 600507 600511 600516 600517 600521
        600522 600528 600529 600535 600536 600546 600549 600556 600563 600566 600567 600572 600580 600582
        600597 600598 600623 600637 600639 600642 600643 600648 600649 600657 600663 600667 600673 600699
        600704 600705 600707 600717 600718 600728 600729 600732 600733 600737 600739 600754 600755 600764
        600765 600776 600782 600787 600801 600803 600808 600811 600820 600823 600827 600835 600839 600859
        600862 600863 600867 600871 600875 600879 600884 600885 600895 600901 600903 600906 600908 600909
        600917 600928 600956 600959 600967 600968 600970 600985 600988 600998 601000 601003 601005 601016
        601077 601098 601106 601117 601118 601128 601139 601156 601168 601179 601187 601198 601200 601228
        601298 601333 601456 601555 601568 601577 601598 601608 601611 601615 601636 601665 601689 601699
        601717 601718 601778 601828 601860 601866 601869 601872 601880 601928 601958 601969 601975 601991
        601992 601997 603000 603056 603077 603127 603156 603198 603218 603225 603228 603267 603290 603317
        603355 603379 603444 603456 603515 603568 603589 603605 603613 603638 603650 603707 603708 603712
        603719 603786 603858 603866 603868 603883 603885 603893 603927 603983 605358 688002 688005 688006
        688029 688065 688088 688099 688188 688208 688289 688321 688521 688536
    """,
    "2022-12-30": """
        000009 000012 000021 000027 000031 000039 000050 000060 000062 000089 000155 000156 000400 000401
        000402 000415 000513 000519 000537 000540 000547 000553 000559 000563 000581 000591 000598 000623
        000629 000630 000636 000656 000683 000703 000709 000728 000729 000738 000739 000750 000778 000783
        000785 000807 000825 000830 000831 000869 000878 000883 000887 000898 000930 000932 000937 000959
        000960 000961 000967 000970 000975 000987 000988 000990 000997 000998 000999 001203 001227 001872
        001914 002002 002010 002019 002025 002028 002030 002048 002056 002065 002078 002080 002081 002092
        002110 002124 002127 002128 002131 002138 002146 002152 002153 002155 002156 002183 002185 002191
        002192 002195 002203 002212 002221 002223 002242 002244 002249 002250 002266 002268 002273 002281
        002294 002299 002326 002340 002353 002368 002372 002373 002384 002385 002396 002399 002407 002408
        002409 002416 002422 002423 002429 002430 002434 002439 002444 002465 002468 002497 002500 002505
        002506 002507 002508 002511 002531 002532 002557 002563 002568 002572 002595 002603 002624 002625
        002653 002670 002673 002683 002690 002701 002705 002738 002739 002745 002797 002831 002850 002867
        002901 002925 002926 002936 002939 002945 002948 002958 002966 002985 003035 300001 300003 300009
        300012 300017 300024 300026 300037 300058 300070 300072 300073 300088 300115 300136 300144 300146
        300168 300182 300212 300244 300251 300253 300257 300285 300296 300308 300357 300363 300373 300376
        300383 300390 300418 300463 300474 300482 300558 300568 300604 300618 300630 300676 300677 300682
        300699 300724 300741 300776 300832 300850 300861 300866 300869 300888 301029 600006 600008 600021
        600022 600026 600027 600032 600038 600056 600060 600062 600064 600066 600079 600095 600096 600109
        600118 600126 600131 600141 600143 600153 600155 600157 600160 600161 600166 600167 600170 600171
        600177 600195 600201 600208 600216 600258 600259 600271 600282 600297 600298 600299 600307 600315
        600316 600325 600329 600339 600348 600350 600352 600369 600372 600373 600376 600377 600378 600380
        600390 600392 600398 600399 600409 600415 600418 600435 600482 600486 600487 600489 600497 600498
        600499 600500 600507 600511 600516 600517 600521 600528 600529 600535 600536 600546 600549 600556
        600563 600566 600567 600580 600582 600597 600598 600623 600637 600642 600648 600655 600663 600667
        600673 600699 600704 600705 600707 600718 600728 600737 600739 600755 600764 600765 600782 600787
        600801 600808 600820 600827 600839 600848 600859 600862 600863 600867 600871 600873 600879 600885
        600895 600901 600906 600909 600917 600927 600928 600956 600959 600967 600968 600970 600985 600988
        600998 601000 601005 601016 601058 601077 601098 601106 601108 601118 601128 601139 601156 601158
        601162 601168 601179 601187 601198 601228 601231 601233 601298 601333 601456 601555 601568 601577
        601598 601607 601608 601611 601636 601665 601666 601696 601699 601717 601718 601778 601828 601866
        601869 601872 601880 601928 601958 601969 601990 601991 601992 601997 603000 603026 603056 603077
        603127 603156 603160 603218 603225 603228 603233 603267 603317 603345 603355 603379 603444 603456
        603517 603568 603589 603596 603605 603606 603613 603638 603650 603658 603688 603707 603712 603719
        603737 603786 603816 603858 603866 603868 603883 603885 603893 603927 603939 605358 688002 688006
        688009 688029 688063 688088 688099 688116 688122 688185 688188 688208 688256 688289 688301 688385
        688390 688521 688538 688567 688690 688772 688777 688779 688819 689009
    """,
}
ETF_SOURCES = {
    **followup.ETF_SOURCES,
    "2017-12-29": "https://www.sse.com.cn/disclosure/fund/announcement/c/2018-03-28/510500_2017_n.pdf",
    "2021-12-31": "https://www.sse.com.cn/disclosure/fund/announcement/c/new/2022-03-31/510500_20220331_1_3qPQoPDA.pdf",
    "2022-12-30": "https://pdf.dfcfw.com/pdf/H2_AN202303311584743601_1.pdf",
}
EARLY_EXAMPLES = {
    "2016-06-13": ("600682 000008", "000718 600797"),
    "2016-12-12": ("600315 600600", "000550 000088"),
    "2017-06-12": ("601928 600642", "000723 000959"),
    "2017-12-11": ("000981 002032", "002120 002460"),
    "2018-06-11": ("600760 603885", "002271 002032"),
}
DATE_SOURCES = {
    **followup.DATE_SOURCES,
    "2021-12-13": "https://www.cnfin.com/kx/detail/20211126/3467213_1.html",
    "2022-12-12": "https://www.cnfin.com/gs-lb/detail/20221125/3752600_1.html",
    "2019-01-18": "https://www.sse.com.cn/market/sseindex/diclosure/c/c_20181217_4694178.shtml",
}
EVIDENCE_DATE = "2026-11-26"


def event_audit(days, pools, entries, events, regular):
    result = []
    corrected = {}
    for day in events:
        pos = days.get_loc(day)
        pre = days[pos - 1]
        before, current = entries[pre], entries[day]
        window = days[pos:min(len(days), pos + 7)]
        old, new = before["codes"], current["codes"]
        vendor_in, vendor_out = new - old, old - new
        first_change = next((date for date in window if entries[date]["codes"] != old), "")
        known = followup.PUBLISHED_DELTAS.get(day)
        notice_url = DATE_SOURCES.get(day, RULE if day in regular else "")
        proof = "U_unverified"
        source_in, source_out = set(), set()
        reconstruction = ""
        if known:
            source_out, source_in = (set(c.split()) for c in known)
            candidate = (old - source_out) | source_in
            admissible = (before["valid"] and source_out <= old and not (source_in & old)
                          and len(candidate) == 500)
            reconstruction = "matches_bao_event_day" if admissible and candidate == new else "differs_from_bao_event_day"
            if admissible:
                corrected[day] = candidate
            proof = "B_reproduced_full_delta" if day == "2021-06-15" else "A_official_full_delta"
            notice_url = followup.DELTA_SOURCES[day]
        elif day in EARLY_EXAMPLES:
            source_in, source_out = (set(c.split()) for c in EARLY_EXAMPLES[day])
            proof = "A_official_examples_only"
            if (before["valid"] and current["valid"] and len(vendor_in) == len(vendor_out) == 50
                    and source_in <= vendor_in and source_out <= vendor_out):
                rebuilt = (old - vendor_out) | vendor_in
                assert rebuilt == new and len(rebuilt) == 500
                reconstruction = "bao_transition_supported_by_official_date_count_examples"
        elif day == "2024-06-17":
            source_in = set(followup.JUNE_2024_IN.split())
            proof = "B_reproduced_incoming_only"
            notice_url = followup.JUNE_2024_SOURCE
        elif day == "2019-01-18":
            source_in, source_out = {"601598"}, {"600270"}
            proof = "A_official_merger"
            if before["valid"] and source_out <= old and not (old & source_in):
                official_candidate = (old - source_out) | source_in
                reconstruction = "matches_first_later_bao" if first_change and entries[first_change]["codes"] == official_candidate else "timing_unresolved"
        elif day in regular:
            proof = "B_notice_or_schedule_date_only"
        if day in regular:
            date_status = ("same_day_vendor_change" if first_change == day else
                           "vendor_change_later" if first_change else "no_vendor_change_in_checked_window")
        elif day == "2019-01-18":
            date_status = "official_event_vendor_delayed" if first_change and first_change > day else "official_event_compare_codes"
        else:
            date_status = "nonregular_observed_change_not_officially_verified"
        result.append(dict(record_type="event", month=day[:7], query_date=day,
            source=BAO_DOC, retrieved_date=current["raw"]["retrieved"], evidence_grade=proof,
            vendor_payload_sha256=current["signature"],
            source_evidence_retrieved_date=EVIDENCE_DATE if notice_url else "",
            vendor_rows=current["rows"], vendor_unique=len(new), vendor_duplicates=current["duplicates"],
            vendor_update_dates="|".join(current["updates"]), date_audit=date_status,
            prior_query_date=pre, first_vendor_change_date=first_change,
            vendor_in_count=len(vendor_in), vendor_out_count=len(vendor_out),
            vendor_in=" ".join(sorted(vendor_in)), vendor_out=" ".join(sorted(vendor_out)),
            course_in_count=len(pools[day] - pools[pre]), course_out_count=len(pools[pre] - pools[day]),
            source_codes_in=" ".join(sorted(source_in)), source_codes_out=" ".join(sorted(source_out)),
            source_in_match_count=len(vendor_in & source_in) if source_in else "",
            source_out_match_count=len(vendor_out & source_out) if source_out else "",
            notice_url=notice_url, supplemental_source=MERGER_TABLE if day == "2019-01-18" else "",
            reconstruction_status=reconstruction))
    return result, corrected


def build_rows(months, pools, entries, events, corrected, regular):
    grade_etf = {day: set(c.split()) for day, c in {**followup.ETF_SNAPSHOTS, **ETF_EXTRA}.items()}
    assert all(len(codes) == 500 for codes in grade_etf.values())
    monthly, audit, names = [], [], {}
    for item in entries.values():
        for code, row in item["by_code"].items():
            names.setdefault(code, row)
    times = [(m, d, "month_end") for m, d in months.items()]
    times.extend((d[:7], d, "starting_snapshot") for d in ["2016-01-04", "2016-02-01"])
    previous_month, previous_pool = "", None
    for month, day, record_type in sorted(times, key=lambda r: r[1]):
        item = entries[day]
        vendor = item["codes"]
        etf = grade_etf.get(day)
        selected = vendor
        grade, status, source = "B_baostock", "vendor_snapshot", BAO_DOC
        detail = []
        if not item["valid"]:
            grade, status = "U_unverified", "unknown"
            detail.append("vendor_quality_failure")
        last_review = max((date for date in regular if date <= day), default="")
        stale = bool(item["updates"]) and max(item["updates"]) < last_review
        if stale:
            grade, status = "U_unverified", "unknown"
            detail.append("vendor_snapshot_predates_unreflected_scheduled_review")
            if month == "2021-06" and last_review in corrected:
                candidate = corrected[last_review]
                july = entries[months["2021-07"]]
                if july["valid"] and candidate == july["codes"]:
                    selected, grade, status = candidate, "B_reconstructed", "reconstructed_snapshot"
                    source = BAO_DOC + " | " + followup.DELTA_SOURCES[last_review]
                    detail.append("full_reproduced_delta_on_pre_event_bao_matches_july_crosscheck")
        if etf is not None:
            if selected == etf and status == "vendor_snapshot":
                grade = "B_baostock_etf_agree"
                source += " | " + ETF_SOURCES[day]
            elif status == "unknown":
                selected, grade, status, source = etf, "C_etf_proxy", "etf_proxy", ETF_SOURCES[day]
                detail.append("500_index_holdings_as_proxy_not_official_constituents")
            elif selected != etf:
                grade, status = "U_unverified", "unknown"
                detail.append("vendor_conflicts_with_etf")
        course = pools.get(day)
        course_only = course - selected if course is not None else None
        source_only = selected - course if course is not None else None
        vendor_only = vendor - course if course is not None else None
        course_not_vendor = course - vendor if course is not None else None
        event_rows = [e for e in events if e["month"] == month]
        event_note = "|".join(f'{e["query_date"]}:{e["date_audit"]}' for e in event_rows)
        if not event_rows:
            event_note = "no_review_or_course_change_in_window"
        on_use = status in {"vendor_snapshot", "reconstructed_snapshot"}
        compare = record_type == "month_end" and previous_pool is not None
        month_in = selected - previous_pool if compare else set()
        month_out = previous_pool - selected if compare else set()
        if not event_rows and (month_in or month_out):
            event_note = "month_end_set_changed_exact_effective_dates_unknown"
        audit.append(dict(record_type=record_type, month=month, query_date=day, source=source,
            retrieved_date=item["raw"]["retrieved"], evidence_grade=grade, snapshot_status=status,
            source_evidence_retrieved_date=EVIDENCE_DATE if source != BAO_DOC else "",
            vendor_rows=item["rows"], vendor_unique=len(vendor), vendor_duplicates=item["duplicates"],
            vendor_payload_sha256=item["signature"],
            vendor_invalid_code=item["invalid"], vendor_error_code=item["raw"]["error_code"],
            vendor_error=item["raw"]["error"], vendor_update_dates="|".join(item["updates"]),
            latest_scheduled_review_date=last_review,
            selected_rows=len(selected), source_count_ok=len(selected) == 500, research_snapshot_usable=on_use,
            course_count=len(course) if course is not None else "",
            intersection_count=len(selected & course) if course is not None else "",
            selected_only_count=len(source_only) if source_only is not None else "",
            course_only_count=len(course_only) if course_only is not None else "",
            selected_only_codes=" ".join(sorted(source_only or set())),
            course_only_codes=" ".join(sorted(course_only or set())),
            bao_only_count=len(vendor_only) if vendor_only is not None else "",
            course_not_bao_count=len(course_not_vendor) if course_not_vendor is not None else "",
            etf_only_vs_bao=len(etf-vendor) if etf is not None else "",
            bao_only_vs_etf=len(vendor-etf) if etf is not None else "",
            etf_source=ETF_SOURCES.get(day,""), date_audit=event_note, detail="|".join(detail),
            prior_month=previous_month if compare else "",
            month_end_in_count=len(month_in) if compare else "", month_end_out_count=len(month_out) if compare else "",
            month_end_in_codes=" ".join(sorted(month_in)), month_end_out_codes=" ".join(sorted(month_out))))
        if record_type == "month_end":
            previous_month, previous_pool = month, selected
        for code in sorted(selected) or [""]:
            vendor_row = item["by_code"].get(code)
            metadata = vendor_row or names.get(code, {})
            monthly.append(dict(record_type=record_type, month=month, query_date=day, stkcd=code,
                source_code=metadata.get("code", ""), security_name=metadata.get("code_name", ""),
                source_update_date=vendor_row.get("updateDate","") if vendor_row and status != "etf_proxy" else "",
                bao_payload_sha256=item["signature"],
                source=source, retrieved_date=EVIDENCE_DATE if status == "etf_proxy" else item["raw"]["retrieved"],
                evidence_grade=grade, snapshot_status=status,
                constituent_status="vendor_member" if on_use else "unknown",
                course_quote_present=code in course if course is not None and code else ""))
    return monthly, audit


def render(audit, events, archive_hash, requests_count):
    months = [r for r in audit if r["record_type"] == "month_end"]
    early = [r for r in months if r["month"] < "2018-11"]
    requested = [r for r in months if r["month"] >= "2018-11"]
    assert (len(months), len(early), len(requested)) == (108, 34, 74)
    early_events = [e for e in events if e["reconstruction_status"] == "bao_transition_supported_by_official_date_count_examples"]
    unknown = [r["month"] for r in months if r["snapshot_status"] == "unknown"]
    proxy = [r["month"] for r in months if r["snapshot_status"] == "etf_proxy"]
    valid = [r for r in months if r["research_snapshot_usable"]]
    comparison = [r for r in valid if r["course_count"] != ""]
    comparable_gaps = sum(r["selected_only_count"] for r in comparison)
    course_extra = sum(r["course_only_count"] for r in comparison)
    hist = first.table(("时期", "月数", "BaoStock 唯一代码 500", "选用名单或候选达到 500", "BaoStock 或证据重建可用",
                        "ETF 旁证", "unknown"),
        [(label,len(period),sum(r["vendor_unique"]==500 for r in period),
          sum(r["source_count_ok"] for r in period),sum(r["research_snapshot_usable"] for r in period),
          sum(r["snapshot_status"]=="etf_proxy" for r in period),sum(r["snapshot_status"]=="unknown" for r in period))
         for label,period in [("2016-01 至 2018-10",early),("2018-11 至 2024-12",requested),("全期",months)]])
    monthly_table = first.table(("月份","查询日","BaoStock 数","选用/候选数","状态","课程数","仅名单有","仅课程有"),
        [(r["month"],r["query_date"],r["vendor_unique"],r["selected_rows"],r["snapshot_status"],
          r["course_count"],r["selected_only_count"],r["course_only_count"]) for r in months])
    change_table = first.table(("应核对日","证据","首个可见变更日","当日调入","当日调出","日期结果"),
        [(r["query_date"],r["evidence_grade"],r["first_vendor_change_date"] or "—",r["vendor_in_count"],
          r["vendor_out_count"],r["date_audit"]) for r in events])
    earliest = next(r for r in audit if r["query_date"] == "2016-01-04")
    first_class = next(r for r in audit if r["query_date"] == "2016-02-01")
    return f"""# 中证 500 历史成分免费获取与对账

## 覆盖结论

使用 BaoStock 免费 `query_zz500_stocks(date=...)`，查验 2016 年 1 月至 2024 年 12 月的全部月末及调样窗口，共 {requests_count} 个请求日期。2018-11 至 2024-12 的 74 个目标月均实际查询。接口历史覆盖早于 2018-11。最早实测的 2016-01-04 完整起点有 {earliest["vendor_unique"]} 只且无重复，返回版本为 {earliest["vendor_update_dates"]}。课程数据从 2016-02-01 开始，在该日完整起始名单有 {first_class["selected_rows"]} 个代码，课程有 {first_class["course_count"]} 个，缺 {first_class["selected_only_count"]} 个且仅课程有 {first_class["course_only_count"]} 个。两个起点的完整代码均收入名单表。这两个起始截面来自直接公开查询，官方完整起始名册仍未取得。 [BaoStock 免费接口]({BAO_DOC})

{hist}

BaoStock 的 `updateDate` 是接口提供的名单更新日期，与调样实际生效日分列。仅返回 500 只不保证时点正确。2021-06 的原响应仍停在端午休市日 06-14 的旧名单，使用生效日前的完整 BaoStock 截面应用公开转载的 50 进、50 出代码，结果与 7 月接口截面一致，作为 B 级重建。7 月用于事后交叉核对。 [上交所 2021-06 调整日期]({followup.DATE_SOURCES["2021-06-15"]}) · [逐码转载附件]({followup.DELTA_SOURCES["2021-06-15"]})

{", ".join(proxy) or "无"} 各有 500 只 ETF 指数投资持仓作为旁证，官方资格仍标 `unknown`。其余 `unknown` 月份为 {", ".join(unknown) or "无"}，保留候选名单和原始差异。2021-09 BaoStock 只有 499 只，课程独有的 601868 当月已上市，但不能单凭课程补齐。2022-12 调样后，接口到 2023-02 仍返回 2022-08-01 的版本。ETF 年末名单的有效日不能自动外推到翌年两个月。 [中国能建上市公告]({followup.LISTING}) · [2021 年 ETF 完整年报]({ETF_SOURCES["2021-12-31"]}) · [2022 年 ETF 完整年报]({ETF_SOURCES["2022-12-30"]})

## 早期调样与独立核对

以实际返回的完整截面为起始证据。对每个早期调样，从生效日前一交易日的完整截面减去 BaoStock 显示的调出代码、加入调入代码，分别检查数量、通知生效日和已公开的示例代码。{len(early_events)} 个早期事件通过上述核验。保留全部代码的变更来源为 BaoStock，公告只有数量及示例时，其他代码及两次调样之间的临时变更证据仍有限。2017-12-29 的 BaoStock 截面与上交所披露的南方中证 500 ETF 年报中 500 只指数投资持仓逐码完全一致，可独立验证一个早期完整截面。 [2016 年 6 月公告]({DATE_SOURCES["2016-06-13"]}) · [2017 年 6 月公告]({DATE_SOURCES["2017-06-12"]}) · [2017 年 ETF 完整年报]({ETF_SOURCES["2017-12-29"]})

2019-01-18 中国外运上市替换外运发展有中证指数公司公告，BaoStock 在后续查询日才反映变更。2023-06、2023-12 和 2024-12 的完整调整附件用于逐码核对，2024-06 的转载仅提供调入代码。临时和规则日期匹配并列记录，七个交易日的观察窗内首次出现变化仅表示供应商可见，不作为实际生效日。以下覆盖 18 次规则定期调样及另外 13 个课程集合变化日，全期其他临时事件仍需逐份公告补证。 [调样规则]({RULE}) · [中国外运换股公告]({DATE_SOURCES["2019-01-18"]})

<details>
<summary>逐次调样检查</summary>

{change_table}

</details>

## 与课程月末行情的差异

在 {len(comparison)} 个有课程日且可作为 B 级研究截面的月份中，累计 {comparable_gaps:,} 个名单内代码月缺课程行情，累计 {course_extra:,} 个已见于课程却不在名单内的代码月。按两个集合的双向差集统计，不能据此认定停牌或采集问题。unknown 和 ETF 旁证月的数值仅供比对。2016-01 的查询日超出课程窗口，差异留空。每月及每次变动的证券代码和来源链接见审计表。月末间集合差异保留为观测结果，确切生效日须查对应变更公告。

{monthly_table}

## 字段、证据等级与复现

- A 级用于官方逐码附件、公告示例及公司换股事件。B 级表示结构完整且未发现当月冲突的 BaoStock 截面，含官方日期或独立 ETF 交叉验证，以及分别标明的公开名单重建。C 级是基金真实持仓旁证，不能单独确认指数资格。U 级表示冲突或数量、日期检查未通过。所有月份均保留供应商实际响应行数、去重数、重复数及日期版本。
- 名单表 `snapshot_status` 区分 BaoStock、调整重建、ETF 旁证和未知。C/U 的 `constituent_status` 为 `unknown`，需要研究样本时以审计表 `research_snapshot_usable` 筛出经本轮核验的供应商口径。B 级按供应商口径具备研究可用性，未获得指数公司全期逐日认证。代码保留六位，`security_name` 是供应商展示名，可能跨期更名，名称不参与匹配。
- 原始归档 SHA-256 为 `{archive_hash}`。在期中考试目录运行 `python3 -B code/fetch_constituents.py`，需要安装免费包 `baostock` 与 `pandas`。可用 `--cache /路径/bao.json` 保留接口原始响应，再加 `--offline` 重放。官方和基金名单证据固定在本脚本及第二轮核验脚本中。临时原始响应仅在验证时使用，正文数据与审计表包含逐条获取日期及来源。

[历史名单](historical_constituents.csv) · [月度与事件审计](constituent_source_audit.csv) · [获取脚本](../code/fetch_constituents.py)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    project = Path(__file__).resolve().parents[1]
    parser.add_argument("--project-dir", type=Path, default=project)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--cache", type=Path, help="可选 BaoStock 原始响应缓存")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if not __debug__:
        parser.error("请使用启用断言的 Python")
    root = args.project_dir.resolve(strict=True)
    output = args.output_dir.resolve() if args.output_dir else root / "output"
    archive = root / "data.tar"
    digest = first.sha256(archive)
    days, pools, months = sources(root)
    requests, event_days, regular = date_requests(days, pools, months)
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix="bao-csi500-") as temp:
        cache = args.cache.resolve() if args.cache else Path(temp) / "bao.json"
        values = get_bao(requests, cache, args.offline)
    entries = {d: entry(values[d], d) for d in requests}
    events, corrected = event_audit(days, pools, entries, event_days, regular)
    items, audit = build_rows(months, pools, entries, events, corrected, regular)
    source_df, audit_df = pd.DataFrame(items), pd.DataFrame(audit + events)
    assert not source_df.duplicated(["record_type", "query_date", "stkcd"]).any()
    assert all(r["vendor_rows"] >= r["vendor_unique"] for r in audit)
    assert sum(r["record_type"] == "month_end" for r in audit) == len(months)
    assert first.sha256(archive) == digest
    report = render(audit, events, digest, len(requests))
    output.mkdir(parents=True, exist_ok=True)
    names = ("historical_constituents.csv", "constituent_source_audit.csv", "constituent_coverage_report.md")
    for name in names:
        path = output / name
        assert not path.is_symlink() and (not path.exists() or not path.samefile(archive))
    source_df.to_csv(output / names[0], index=False, encoding="utf-8-sig")
    audit_df.to_csv(output / names[1], index=False, encoding="utf-8-sig")
    (output / names[2]).write_text(report, encoding="utf-8")
    print(f"已输出 {len(months)} 个月、{len(events)} 个事件、{len(items):,} 条名单记录")


if __name__ == "__main__":
    main()
