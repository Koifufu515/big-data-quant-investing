#!/usr/bin/env python3
"""T5: ingest cached or live BaoStock daily bars and audit research coverage."""
import argparse
import gzip
import json
import multiprocessing as mp
import os
import socket
import time
import sys
import importlib
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

START = "2015-01-01"
END = "2024-12-31"
FIELDS = "date,code,open,high,low,close,preclose,volume,amount,pctChg,adjustflag,tradestatus,isST,turn"
DOC = "https://www.baostock.com/mainContent?file=pythonAPI.md"
sys.dont_write_bytecode = True
prior = importlib.import_module("fetch_constituents")
first = prior.first
LOOKBACK = 252
FOCUS = {"2021-09", "2021-12", "2022-12", "2023-01", "2023-02"}


def download_batch(job):
    codes, cache = job
    import baostock as bs
    socket.setdefaulttimeout(15)
    connected = False
    retrieved = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    consecutive_failures = 0
    def response(rs):
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
        return dict(error_code=rs.error_code, error_msg=rs.error_msg, fields=rs.fields, rows=rows)
    for i, code in enumerate(codes):
        target = cache / f"{code}.json.gz"
        older = read_payload(target) if target.exists() else None
        if older and older["quote"]["error_code"] == "0":
            continue
        for attempt in range(2):
            try:
                if not connected:
                    login = bs.login()
                    if login.error_code != "0":
                        if login.error_code == "10001011":
                            print(f"BaoStock {login.error_code}: {login.error_msg}", flush=True)
                            return
                        raise RuntimeError(f"{login.error_code}: {login.error_msg}")
                    connected = True
                quote = response(bs.query_history_k_data_plus(code, FIELDS, START, END, "d", "3"))
                factor = response(bs.query_adjust_factor(code, START, END))
                if quote["error_code"] != "0" or factor["error_code"] != "0":
                    raise RuntimeError(f'{quote["error_code"]}/{factor["error_code"]}')
                basic = response(bs.query_stock_basic(code=code))
                break
            except (OSError, RuntimeError, AttributeError, IndexError, ValueError) as error:
                from baostock.common import context
                connection = getattr(context, "default_socket", None)
                if connection is not None:
                    connection.close()
                connected = False
                quote = dict(error_code="client_error", error_msg=str(error), fields=[], rows=[])
                factor = basic = quote
                time.sleep(attempt + 1)
        payload = dict(code=code, start=START, end=END, retrieved_date=retrieved, source=DOC,
                       package=getattr(bs, "__version__", "unknown"), quote=quote, factor=factor, basic=basic)
        if older:
            payload["prior_errors"] = older.get("prior_errors", []) + [{
                "retrieved_date": older["retrieved_date"], "error_code": older["quote"]["error_code"],
                "error_msg": older["quote"]["error_msg"],
            }]
        temp = target.with_suffix(f".{os.getpid()}.tmp")
        with gzip.open(temp, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(temp, target)
        consecutive_failures = consecutive_failures + 1 if quote["error_code"] != "0" else 0
        if consecutive_failures == 3:
            print(f"{os.getpid()} 服务连续失败，暂停该批次，保留缓存", flush=True)
            break
        if i % 30 == 0 or i+1 == len(codes):
            print(f"{os.getpid()} {i+1}/{len(codes)} {code}", flush=True)
    if connected:
        bs.logout()


def code_map(root):
    old = pd.read_csv(root / "output/historical_constituents.csv", dtype=str, keep_default_na=False)
    pairs = old.loc[old.source_code.str.fullmatch(r"(sh|sz|bj)\.[0-9]{6}"), ["stkcd", "source_code"]].drop_duplicates()
    assert pairs.stkcd.is_unique and pairs.source_code.str[-6:].eq(pairs.stkcd).all()
    return dict(zip(pairs.stkcd, pairs.source_code))


def fetch(root, cache, workers):
    codes = sorted(set(code_map(root).values()) | {"sh.601868"})
    cache.mkdir(parents=True, exist_ok=True)
    def needs_request(code):
        path = cache / f"{code}.json.gz"
        return not path.exists() or read_payload(path)["quote"]["error_code"] != "0"
    todo = [code for code in codes if needs_request(code)]
    if todo:
        panel = constituents(root, cache)
        _, stock = calendar_and_course(root, cache)
        at_signal = panel.merge(stock[["stkcd","trddt"]], left_on=["stkcd","signal_date"],
                                right_on=["stkcd","trddt"], how="left", indicator=True,
                                validate="one_to_one")
        priority = at_signal.loc[at_signal["_merge"].eq("left_only")].source_code.value_counts()
        todo.sort(key=lambda code: (-priority.get(code, 0), code))
        with mp.get_context("spawn").Pool(workers) as pool:
            pool.map(download_batch, [(todo[i::workers], cache) for i in range(workers)])
    pending = sum(needs_request(code) for code in codes)
    print(f"成功缓存 {len(codes)-pending}/{len(codes)} 只，待收录 {pending} 只", flush=True)


MEETING = {
    "2021-12": "https://www.cnfin.com/kx/detail/20211126/3467213_1.html",
    "2022-12": "https://www.cnfin.com/gs-lb/detail/20221125/3752600_1.html",
}
LISTING = "https://www.sse.com.cn/disclosure/announcement/listing/ipo/c/c_20210927_83094980.shtml"
MERGER = "https://www.sse.com.cn/market/sseindex/diclosure/c/c_20210830_5570656.shtml"
SINA_HISTORY = "https://vip.stock.finance.sina.com.cn/corp/go.php/vCI_CorpXiangGuan/stockid/601868.phtml"
CROSS_HISTORY = "https://github.com/unliftedq/index-constitution/blob/b724386d375f281fa693032772221f0d2e2a144f/history/csi500.csv"


def read_payload(file):
    with gzip.open(file, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def constituents(root, cache):
    old = pd.read_csv(root / "output/historical_constituents.csv", dtype=str, keep_default_na=False)
    old = old.loc[old.record_type.eq("month_end") & old.month.ge("2016-02")]
    evidence = read_payload(cache / "constituent_evidence.json.gz")
    sources = {day: prior.entry(raw, day) for day, raw in evidence.items()}
    early = sources["2021-09-30"]["codes"]
    october = sources["2021-10-08"]["codes"]
    assert len(early) == 499 and len(october) == 500 and october - early == {"601868"} and early <= october
    dec21 = set(prior.ETF_EXTRA["2021-12-31"].split())
    dec22 = set(prior.ETF_EXTRA["2022-12-30"].split())
    for dataset, before, later in [(dec21, "2021-11-30", "2022-01-28"), (dec22, "2022-11-30", "2023-03-31")]:
        previous = sources[before]["codes"]
        assert len(dataset - previous) == len(previous - dataset) == 50
        assert dataset == sources[later]["codes"] and sources[later]["valid"]
    assert {"603606", "688063"} <= dec22 - sources["2022-11-30"]["codes"]
    assert "601868" in sources["2021-11-30"]["codes"] and "601868" not in dec21
    assert all(sources[d]["codes"] == sources["2022-11-30"]["codes"]
               for d in ("2022-12-30", "2023-01-31", "2023-02-28"))
    dates = old.groupby("month").query_date.first().to_dict()
    pools = {
        "2021-09": (october, "C_provisional", DOC+" | "+LISTING+" | "+MERGER+" | "+SINA_HISTORY+" | "+CROSS_HISTORY,
                    "499 at 09-30; 601868 is sole addition in 10-08 query; official effective date unknown"),
        "2021-12": (dec21, "B_etf_delta_vendor_crosscheck", prior.ETF_SOURCES["2021-12-31"]+" | "+MEETING["2021-12"]+" | "+DOC,
                    "50 in/out vs November BaoStock; equals January 2022 BaoStock"),
        "2022-12": (dec22, "B_etf_delta_vendor_crosscheck", prior.ETF_SOURCES["2022-12-30"]+" | "+MEETING["2022-12"]+" | "+DOC,
                    "50 in/out vs November BaoStock; official examples match; equals March 2023 BaoStock"),
        "2023-01": (dec22, "C_provisional", prior.ETF_SOURCES["2022-12-30"]+" | "+DOC,
                    "December ETF and March BaoStock agree; January effective list unknown"),
        "2023-02": (dec22, "C_provisional", prior.ETF_SOURCES["2022-12-30"]+" | "+DOC,
                    "December ETF and March BaoStock agree; February effective list unknown"),
    }
    codes = code_map(root)
    rows = []
    for r in old.loc[~old.month.isin(FOCUS)].itertuples():
        assert r.constituent_status == "vendor_member"
        rows.append((r.month, r.query_date, r.stkcd, codes[r.stkcd], r.evidence_grade,
                     "research_supported", "research_member", r.source, r.retrieved_date, r.snapshot_status))
    retrieved = max(row["retrieved"] for row in evidence.values())
    for month, (pool, grade, url, note) in pools.items():
        for code in sorted(pool):
            supported = grade.startswith("B_")
            status = "research_member" if supported or (month == "2021-09" and code in early) else "unknown"
            rows.append((month, dates[month], code, codes[code], grade,
                         "research_supported" if supported else "provisional", status, url, retrieved, note))
    panel = pd.DataFrame(rows, columns=[
        "month", "signal_date", "stkcd", "source_code", "evidence_grade", "pool_status",
        "membership_status", "source", "retrieved_date", "evidence_note",
    ]).sort_values(["month", "stkcd"], ignore_index=True)
    assert panel.month.nunique() == 107 and panel.groupby("month").size().eq(500).all()
    assert not panel.duplicated(["month", "stkcd"]).any()
    return panel


def calendar_and_course(root, cache):
    with tarfile.open(root / "data.tar") as tar:
        with tar.extractfile(first.INDEX) as handle:
            course_days = pd.read_csv(handle, usecols=["trddt"]).trddt.sort_values()
        with tar.extractfile(first.STOCK) as handle:
            stock = pd.read_csv(handle, encoding="gb18030", encoding_errors="surrogateescape",
                                dtype={"stkcd": str}, float_precision="round_trip",
                                usecols=["stkcd", "trddt", "ret", "close_adj", "volume", "amount"])
    assert not stock.duplicated(["stkcd", "trddt"]).any()
    evidence = json.loads((cache/"calendar.json").read_text())
    vendor_days = pd.Index(sorted(r["calendar_date"] for r in evidence if str(r["is_trading_day"]) == "1"))
    assert vendor_days.is_unique and course_days.is_unique
    assert set(course_days) == set(vendor_days[vendor_days >= course_days.iloc[0]])
    return vendor_days, stock


def scheduled_windows(panel, days):
    signals = panel[["month", "signal_date"]].drop_duplicates().reset_index(drop=True)
    signals["start"] = days.get_indexer(signals.signal_date)
    assert signals.start.ge(LOOKBACK-1).all()
    signals["end"] = signals.start.shift(-1, fill_value=-1).astype(int)
    return panel.merge(signals, on=["month", "signal_date"], validate="many_to_one")


def mark_windows(length, starts, ends):
    diff = np.zeros(length + 1, dtype=np.int32)
    np.add.at(diff, starts, 1)
    np.add.at(diff, ends + 1, -1)
    return diff[:-1].cumsum() > 0


def numeric_ret(values):
    return np.isfinite(values) & (values >= -1)


def metrics_for_code(code, candidates, course, days, cache):
    path = cache / f"{code}.json.gz"
    if path.exists():
        payload = read_payload(path)
    else:
        absent = dict(error_code="not_requested", error_msg="no saved response", fields=[], rows=[])
        payload = dict(code=code, start=START, end=END, retrieved_date="", quote=absent, factor=absent, basic=absent)
    assert (payload["code"], payload["start"], payload["end"]) == (code, START, END)
    q, factors, basic = (payload[k] for k in ("quote", "factor", "basic"))
    fields = FIELDS.split(",")
    assert not q["rows"] or q["fields"] == fields
    bars_source = pd.DataFrame(q["rows"], columns=fields).set_index("date")
    assert bars_source.index.is_unique and bars_source.index.isin(days).all()
    assert bars_source.code.eq(code).all() and bars_source.adjustflag.eq("3").all()
    raw = bars_source.reindex(days)
    observed = raw.code.notna().to_numpy()
    stock = course.reindex(days)
    has_course = stock.close_adj.notna().to_numpy()
    ret = stock.ret.to_numpy()
    numeric = raw[["pctChg","open","close","preclose","volume","amount"]].apply(pd.to_numeric, errors="coerce")
    provider_ret = numeric.pctChg.to_numpy()/100
    vendor_usable = observed & numeric_ret(provider_ret)
    teacher_usable = has_course & numeric_ret(ret)
    course_complete = stock[["close_adj","volume","amount"]].notna().all(axis=1).to_numpy() & teacher_usable
    
    starts = candidates.start.to_numpy()
    ends = candidates.end.to_numpy()
    in_range = ends >= 0
    feature = mark_windows(len(days), starts - LOOKBACK + 1, starts)
    hold = mark_windows(len(days), starts[in_range], ends[in_range])
    next_open = np.zeros(len(days), dtype=bool)
    next_open[starts[in_range] + 1] = True
    target = feature | hold
    missing_rows = target & ~has_course
    missing_fields = target & ~course_complete
    export = observed & (missing_fields | next_open)
    bars = raw.loc[export, fields[1:]].copy()
    bars.insert(0, "trddt", days[export])
    bars.insert(0, "stkcd", code[-6:])
    bars["feature_window"] = feature[export]
    bars["hold_window_including_anchor"] = hold[export]
    bars["next_open_candidate"] = next_open[export]
    bars["course_row_present"] = has_course[export]
    bars["course_fields_incomplete"] = missing_fields[export]
    bars["ret_baostock_decimal"] = provider_ret[export]
    bars["source"] = "BaoStock"
    bars["retrieved_date"] = payload["retrieved_date"]
    action_cols = ["foreAdjustFactor","backAdjustFactor","adjustFactor"]
    action = pd.DataFrame(factors["rows"], columns=factors["fields"] if factors["rows"] else ["code","dividOperateDate",*action_cols])
    assert action.dividOperateDate.is_unique and action.code.eq(code).all()
    bars = bars.merge(action[["dividOperateDate", *action_cols]], left_on="trddt", right_on="dividOperateDate",
                      how="left", validate="one_to_one")
    assert len(bars) == export.sum()

    meta = dict(zip(basic["fields"], basic["rows"][0])) if basic["rows"] else {}
    ipo, delist = meta.get("ipoDate",""), meta.get("outDate","")
    lifecycle_source = "BaoStock.query_stock_basic" if meta else ""
    if code == "sz.000540" and not delist:
        delist = "2023-06-30"
        lifecycle_source = "https://www.szse.cn/disclosure/notice/general/t20230630_601499.html"
    gap = missing_fields & ~observed
    before_ipo = gap & (days < ipo) if ipo else np.zeros(len(days), bool)
    after_delist = gap & (days >= delist) if delist else np.zeros(len(days), bool)
    non_lifecycle_gap = gap & ~(before_ipo | after_delist)
    failed = non_lifecycle_gap if q["error_code"] not in {"0","not_requested"} else np.zeros(len(days), bool)
    not_requested = non_lifecycle_gap if q["error_code"] == "not_requested" else np.zeros(len(days), bool)
    gap_other = gap & ~(before_ipo | after_delist | failed | not_requested)
    overlap = teacher_usable & vendor_usable
    ret_gap = np.abs(ret[overlap] - provider_ret[overlap])
    vol_overlap = observed & stock.volume.notna().to_numpy() & numeric.volume.notna().to_numpy()
    amt_overlap = observed & stock.amount.notna().to_numpy() & numeric.amount.notna().to_numpy()
    open_seen = observed & numeric.open.gt(0).to_numpy()
    open_trading = open_seen & raw.tradestatus.eq("1").to_numpy()
    in_course_range = np.asarray(days >= "2016-02-01")
    comparable_pct = observed & numeric.close.gt(0).to_numpy() & numeric.preclose.gt(0).to_numpy() & vendor_usable
    calc_pct = (numeric.close / numeric.preclose - 1).to_numpy()
    audit = dict(record_type="code", stkcd=code[-6:], source_code=code,
        retrieved_date=payload["retrieved_date"], quote_error=q["error_code"], quote_message=q["error_msg"],
        factor_error=factors["error_code"], factor_rows=len(action), stock_basic_error=basic["error_code"],
        ipodate=ipo, outdate=delist, lifecycle_source=lifecycle_source, source_daily_rows=int(observed.sum()), target_rows=int(target.sum()),
        course_missing_rows=int(missing_rows.sum()), course_missing_rows_filled=int((missing_rows & observed).sum()),
        course_missing_rows_remaining=int((missing_rows & ~observed).sum()),
        course_range_missing_rows=int((missing_rows & in_course_range).sum()),
        course_range_remaining_rows=int((missing_rows & in_course_range & ~observed).sum()),
        before_course_range_missing_rows=int((missing_rows & ~in_course_range).sum()),
        before_course_range_remaining_rows=int((missing_rows & ~in_course_range & ~observed).sum()),
        vendor_pct_formula_comparable=int(comparable_pct.sum()),
        vendor_pct_formula_within_bp=int((np.abs(calc_pct[comparable_pct]-provider_ret[comparable_pct]) <= .0001).sum()),
        course_feature_missing_rows=int((feature & ~has_course).sum()),
        combined_feature_missing_rows=int((feature & ~(has_course | observed)).sum()),
        course_hold_missing_rows=int((hold & ~has_course).sum()),
        combined_hold_missing_rows=int((hold & ~(has_course | observed)).sum()),
        open_candidates=int(next_open.sum()), open_observed=int((next_open & open_seen).sum()),
        open_positive_trading_status=int((next_open & open_trading).sum()),
        course_missing_fields=int(missing_fields.sum()), missing_fields_no_external_row=int(gap.sum()),
        external_return_missing_on_reported_row=int((missing_fields & observed & ~vendor_usable).sum()),
        external_gap_return_blank_dates=" ".join(days[missing_fields & observed & ~vendor_usable]),
        course_gaps_with_baostock_suspended=int((missing_fields & observed & raw.tradestatus.eq("0").to_numpy()).sum()),
        prior_listing_gaps=int(before_ipo.sum()), at_or_after_delisting_gaps=int(after_delist.sum()),
        otherwise_no_external_row=int(gap_other.sum()),
        request_failed_gaps=int(failed.sum()), not_requested_gaps=int(not_requested.sum()),
        request_failed_dates=" ".join(days[failed]), not_requested_dates=" ".join(days[not_requested]),
        before_listing_dates=" ".join(days[before_ipo]),
        delisting_dates=" ".join(days[after_delist]), unexplained_dates=" ".join(days[gap_other]),
        ret_overlap=len(ret_gap), ret_within_one_bp=int((ret_gap <= .0001).sum()),
        vol_overlap=int(vol_overlap.sum()), vol_equal=int((numeric.volume.to_numpy()[vol_overlap] == stock.volume.to_numpy()[vol_overlap]).sum()),
        amount_overlap=int(amt_overlap.sum()),
        amount_within_relative_1e4=int(np.isclose(numeric.amount.to_numpy()[amt_overlap], stock.amount.to_numpy()[amt_overlap],
                                                rtol=.0001, atol=.01).sum()), exported_rows=len(bars))

    combined = teacher_usable | vendor_usable
    vendor_anchor = observed & numeric.close.gt(0).to_numpy()
    monthly = []
    for row in candidates.itertuples():
        if row.end < 0:
            continue
        inside = slice(row.start+1, row.end+1)
        monthly.append(dict(month=row.month, pool_status=row.pool_status, code=code[-6:], count=1,
            before=int(has_course[row.start] and teacher_usable[inside].all()),
            after=int((has_course[row.start] or vendor_anchor[row.start]) and combined[inside].all()),
            vendor_only=int(vendor_anchor[row.start] and vendor_usable[inside].all()),
            holding_days=row.end-row.start, course_missing_holding_days=int((~teacher_usable[inside]).sum()),
            combined_missing_holding_days=int((~combined[inside]).sum())))
    return bars, audit, monthly


def constituent_report(panel):
    tally = panel.drop_duplicates("month").pool_status.value_counts()
    proof = first.table(("月份","结果","证据边界"), [
        ("2021-09", "499 只供应商证据，601868 暂列候选",
         "9 月 28 日上市，9 月末 BaoStock 无该股，10 月 8 日查询首次见其作为唯一新增。该区间内的正式调入日尚未获得 000905 专属公告"),
        ("2021-12", "500 只，B 级重建", "完整 ETF 指数投资持仓相对 11 月 BaoStock 恰好 50 进、50 出，逐码等于次年 1 月 BaoStock"),
        ("2022-12", "500 只，B 级重建", "年末 ETF 对 11 月 BaoStock 恰好 50 进、50 出，公告公开示例 603606 与 688063 均属调入，逐码等于次年 3 月 BaoStock"),
        ("2023-01", "500 只候选，C 级", "2022 年末与 2023 年 3 月截面相同，期间临时调整与当月有效名单待证实"),
        ("2023-02", "500 只候选，C 级", "2022 年末与 2023 年 3 月截面相同，期间临时调整与当月有效名单待证实"),
    ])
    return f"""# T5 · 历史成分股核验

2016-02 至 2024-12 共 **107 个候选月末股票池，每月 500 个不同代码**。其中 **{tally["research_supported"]} 个月为 B 级研究截面**，其余 **{tally["provisional"]} 个月为 C 级候选**。正式研究筛选依据是 `pool_status=research_supported`。B 级由供应商或多源重建支持，指数公司完整逐日名册仍有缺口。C 级月份及其无法证实的成分资格留有显式标记。

{proof}

601868 的上市日、接口可见日和正式指数生效日分别看待。上交所吸收合并附件没有 000905 条目。新浪 000905 关联记录列调入日为 09-28，公开整理档列 09-29，两者的生效日口径及完整性未核实。2023 年 1–2 月定向检索公开调样公告未取得能还原该区间全部临时调整的证据，年末名单仅作为候选。2021 年 12 月和 2022 年 12 月的交易日起点分别为 12 月 13 日和 12 月 12 日。官方公告确认调样日及数量，逐码变更来自前截面与完整 ETF 持仓的差集，另用后续 BaoStock 完整截面交叉验证。 [601868 上市公告]({LISTING}) · [吸收合并公告]({MERGER}) · [新浪关联记录]({SINA_HISTORY}) · [公开整理档]({CROSS_HISTORY}) · [2021-12 调样公告转述]({MEETING["2021-12"]}) · [2022-12 调样公告转述]({MEETING["2022-12"]}) · [2021 ETF 年报]({prior.ETF_SOURCES["2021-12-31"]}) · [2022 ETF 年报]({prior.ETF_SOURCES["2022-12-30"]})

完整 53,500 行保留证券代码、证据等级、来源及获取日期。2021-09 仅 601868 的个别资格为 `unknown`，整个截面仍为 C；2023 年两个月的个股资格均为 `unknown`。这些月份纳入报价查缺，收益覆盖报告单列。 [逐月名单](../processed/monthly_constituents.csv)
"""


def quote_report(code_audit, monthly, digest, start_day, end_day, access):
    total = code_audit.select_dtypes(include="number").sum()
    row_before = int(total.course_missing_rows)
    row_after = int(total.course_missing_rows_remaining)
    factors = int(total.factor_rows)
    pct = lambda n, d: f"{n/d:.2%}" if d else "—"
    rates = []
    for name, frame in [("B 级研究截面", monthly[monthly.pool_status.eq("research_supported")]),
                        ("C 级候选截面", monthly[monthly.pool_status.eq("provisional")]),
                        ("全部候选", monthly)]:
        n, before, after, vendor = frame[["count","before","after","vendor_only"]].sum()
        rates.append((name,n,f"{before:,} / {pct(before,n)}",f"{after:,} / {pct(after,n)}",
                      f"{vendor:,} / {pct(vendor,n)}"))
    benchmark = first.table(("重叠字段","可比行","一致或在阈值内","比例"),
        [("课程 ret 与 BaoStock pctChg÷100（1bp）",int(total.ret_overlap),int(total.ret_within_one_bp),pct(total.ret_within_one_bp,total.ret_overlap)),
         ("成交量（精确）",int(total.vol_overlap),int(total.vol_equal),pct(total.vol_equal,total.vol_overlap)),
         ("成交额（相对容差 0.01%，绝对容差 0.01 元）",int(total.amount_overlap),
          int(total.amount_within_relative_1e4),pct(total.amount_within_relative_1e4,total.amount_overlap))])
    access_note = (f'本次单连接复测在 {access["retrieved_date"]} 收到登录拒绝 {access["error_code"]}（{access["error_msg"]}）。'
                   "行情交付采用此前成功的响应，缺失的证券待免费服务恢复后补取。"
                   if access and not code_audit.quote_error.eq("0").all()
                   else "当前缓存状态详见按证券审计。")
    special = code_audit.loc[code_audit.stkcd.isin(["000540","300114","601868"])]
    unresolved = code_audit.loc[code_audit.course_missing_rows_remaining.gt(0)].sort_values(
        "course_missing_rows_remaining",ascending=False).head(12)
    return f"""# T5 · 免费日线补充与收益链审计

## 数据覆盖

BaoStock 免费日线查询覆盖 {START} 至 {END}，交易日历 {start_day} 至 {end_day}。候选池涉及 **{len(code_audit):,} 只证券**，成功响应 {int(code_audit.quote_error.eq("0").sum()):,} 只、请求失败 {int((~code_audit.quote_error.isin(["0","not_requested"])).sum()):,} 只、无响应缓存 {int(code_audit.quote_error.eq("not_requested").sum()):,} 只。已取得 {int(total.source_daily_rows):,} 行外部日线和 {factors:,} 条复权因子记录。课程源档 SHA-256 为 `{digest}`。

{access_note}

按每个信号月末在候选池内的证券，取截至当月末的 {LOOKBACK} 个交易日作为历史特征窗口，再取该月至下月末作为持有窗口。退出现有池后若仍在这段候选持有窗口，继续索取行情。对每只代码合并重叠窗口后去重，共 {int(total.target_rows):,} 个目标股票日。期末信号的未来持有窗口超出 2024 年样本边界。

{first.table(("目标窗口","课程缺行","得到外部日线后仍无行"),[
    ("全部目标键去重",f"{row_before:,}",f"{row_after:,}"),
    ("课程期内目标键",f"{int(total.course_range_missing_rows):,}",f"{int(total.course_range_remaining_rows):,}"),
    ("2016-02-01 前的目标键",f"{int(total.before_course_range_missing_rows):,}",f"{int(total.before_course_range_remaining_rows):,}"),
    ("历史特征窗口",f"{int(total.course_feature_missing_rows):,}",f"{int(total.combined_feature_missing_rows):,}"),
    ("候选持有窗口（含期初锚点）",f"{int(total.course_hold_missing_rows):,}",f"{int(total.combined_hold_missing_rows):,}"),
])}

补充表输出 {int(total.exported_rows):,} 行。内容为目标缺失行、课程量额或收益字段不全而有外部记录的行，以及下一观测交易日的开盘候选行。完整外部响应保存在 `cache/baostock_t5`，包括重叠行情、公司状态、复权因子及证据查询缓存。下一交易日开盘候选 {int(total.open_candidates):,} 个，有正开盘价 {int(total.open_observed):,} 个，其中交易状态正常 {int(total.open_positive_trading_status):,} 个。有效报价及正常状态仍需结合涨跌停和成交约束独立评估。

## 持有期收益完整性

期初要求存在股票日行情；下一月每个交易日须有有限且不低于 −100% 的日收益。课程前值使用原始 `ret`。补充后仅衡量缺失位置是否有 BaoStock 日涨跌幅可读，另列纯 BaoStock 同口径收益链。此处统计覆盖完整性，未将两源收益混接生成可用标签。含失败样本的分母为所有候选股月，2024-12 信号因缺下一窗口而排除。B/C 分开列示。

{first.table(("股票池","候选股月","课程完整","课程加外部覆盖完整","纯 BaoStock 完整"),rates)}

## 口径与重叠一致性

{benchmark}

内部验算涉及 {int(total.vendor_pct_formula_comparable):,} 个可比外部日收益，{int(total.vendor_pct_formula_within_bp):,} 个与收盘价除以前收盘价减一相差不超过 1bp。BaoStock `adjustflag=3` 为未复权，OHLC 和前收价为元，成交量为股、成交额为人民币元，`pctChg` 及 `turn` 单位为百分比，`ret_baostock_decimal=pctChg/100`。除权除息日的前收通常为交易所除权参考价，不能简单用前一交易日原始收盘替代。课程 `close_adj` 已确认存在倍率断点，绝对值不与未复权价比较。课程量额的单位仅由重叠证据支持，供应商元数据仍待确认。 [BaoStock 字段及除权说明](https://github.com/zxygithub/baostock/blob/master/docs/pythonAPI.md#历史行情指标参数)

复权因子为 BaoStock 独立事件字段，只在有对应日期的行附上，无事件时留空，未将未复权价格改写成复权行情。停牌行保留 `tradestatus=0`，原字段为空时不填入零。课程量额或收益不全的目标键中，有 {int(total.course_gaps_with_baostock_suspended):,} 个外部停牌行。退市后无行情继续留空。日涨跌幅可用与可成交状态独立判断，重叠差异不擅自调平。

## 剩余缺口

在课程字段不完整的目标键中，{int(total.missing_fields_no_external_row):,} 个也没有外部行情行。其中已知上市前 {int(total.prior_listing_gaps):,} 个，已知摘牌日及以后 {int(total.at_or_after_delisting_gaps):,} 个，供应商成功响应但无法从已知上市或摘牌日期解释的 {int(total.otherwise_no_external_row):,} 个，网络或接口请求失败 {int(total.request_failed_gaps):,} 个，无响应缓存 {int(total.not_requested_gaps):,} 个。另有 {int(total.external_return_missing_on_reported_row):,} 个目标外部行存在但日收益字段为空或无效。

{first.table(("代码","剩余缺行","上市前","摘牌日起","无外部行原因未证实","接口状态"),
[(r.stkcd,r.course_missing_rows_remaining,r.prior_listing_gaps,r.at_or_after_delisting_gaps,
  r.otherwise_no_external_row,r.quote_error) for r in unresolved.itertuples()])}

{first.table(("重点代码","成功取得的完整响应行","已补目标缺行","仍缺目标行","行情请求状态"),
[(r.stkcd,r.source_daily_rows,r.course_missing_rows_filled,r.course_missing_rows_remaining,r.quote_error)
 for r in special.itertuples()])}

000540 的摘牌日另有交易所公告支持。它仍缺活动交易期的外部响应。300114 和 601868 以当时证券代码查询；从供应商成功获取的行情只证明价格覆盖。 [000540 摘牌公告](https://www.szse.cn/disclosure/notice/general/t20230630_601499.html)

按证券的缺行日期、状态代码、上市及摘牌日、复权因子数量和重叠核对结果均可查审计表。脚本默认使用免费接口补缓存；`--offline` 用保存的响应复跑。已有证据缓存 `constituent_evidence.json.gz` 与 `calendar.json` 放在同一目录。缓存以 `code.json.gz` 保存原字段、数据、错误码、查询区间和获取日期。

[补充行情](../processed/supplementary_quotes.csv) · [行情核验表](13_quote_supplement_audit.csv) · [处理脚本](../code/04_complete_market_data.py)
"""


def process(root, cache, destination):
    archive = root / "data.tar"
    digest = first.sha256(archive)
    assert digest == "2bac5bed1488cb181b7b29757f02199d6d2d4f91171847817fdd1214d222e0ea"
    panel = constituents(root, cache)
    days, original = calendar_and_course(root, cache)
    jobs = scheduled_windows(panel, days)
    lookup = {c: group.drop(columns="stkcd").set_index("trddt") for c, group in original.groupby("stkcd")}
    empty = original.iloc[:0].drop(columns="stkcd").set_index("trddt")
    out, by_code, by_month = [], [], []
    for code, group in jobs.groupby("source_code"):
        bars, detail, period = metrics_for_code(code, group, lookup.get(code[-6:],empty), days, cache)
        out.append(bars)
        by_code.append(detail)
        by_month.extend(period)
    quotes = pd.concat(out, ignore_index=True).sort_values(["stkcd","trddt"], ignore_index=True)
    audit = pd.DataFrame(by_code)
    months = pd.DataFrame(by_month).groupby(["month","pool_status"], as_index=False).sum(numeric_only=True)
    assert not quotes.duplicated(["stkcd","trddt"]).any()
    assert quotes.adjustflag.eq("3").all() and len(quotes) == audit.exported_rows.sum()
    assert months["count"].sum() == 53000 and months["after"].ge(months["before"]).all()
    assert audit.course_missing_rows.sum() == audit.course_missing_rows_filled.sum()+audit.course_missing_rows_remaining.sum()
    assert first.sha256(archive) == digest
    expected = ("processed/monthly_constituents.csv","processed/supplementary_quotes.csv",
                "output/13_quote_supplement_audit.csv","output/12_constituent_final_report.md",
                "output/14_quote_supplement_report.md")
    for name in expected:
        target = destination / name
        assert not target.is_symlink() and (not target.exists() or not target.samefile(archive))
    for folder in ("output","processed"):
        (destination / folder).mkdir(parents=True, exist_ok=True)
    panel.to_csv(destination/"processed/monthly_constituents.csv", index=False, encoding="utf-8-sig")
    quotes.to_csv(destination/"processed/supplementary_quotes.csv", index=False, encoding="utf-8-sig")
    pd.concat([audit, months.assign(record_type="month")], ignore_index=True).to_csv(
        destination/"output/13_quote_supplement_audit.csv", index=False, encoding="utf-8-sig")
    (destination/"output/12_constituent_final_report.md").write_text(constituent_report(panel), encoding="utf-8")
    access_path = cache / "access_audit.json"
    access = json.loads(access_path.read_text()) if access_path.exists() else {}
    (destination/"output/14_quote_supplement_report.md").write_text(
        quote_report(audit, months, digest, days[0], days[-1], access), encoding="utf-8")
    print(f"107 个月、{len(quotes):,} 行补充报价、{len(audit):,} 只证券完成。", flush=True)



EVIDENCE_REQUESTS = ("2021-09-27","2021-09-28","2021-09-30","2021-10-08",
    "2021-11-30","2021-12-31","2022-01-28","2022-11-30","2022-12-30",
    "2023-01-31","2023-02-28","2023-03-31")


def fetch_evidence(cache):
    cache.mkdir(parents=True, exist_ok=True)
    evidence = cache / "constituent_evidence.json.gz"
    if not evidence.exists():
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            values = prior.get_bao(EVIDENCE_REQUESTS, Path(temp)/"bao.json", False)
        with gzip.open(evidence, "wt", encoding="utf-8") as handle:
            json.dump(values, handle, ensure_ascii=False, separators=(",",":"))
    calendar = cache / "calendar.json"
    if not calendar.exists():
        import baostock as bs
        login = bs.login()
        assert login.error_code == "0", login.error_msg
        try:
            response = bs.query_trade_dates(START, END)
            rows = []
            while response.error_code == "0" and response.next():
                rows.append(dict(zip(response.fields, response.get_row_data())))
            assert response.error_code == "0" and rows
            calendar.write_text(json.dumps(rows),encoding="utf-8")
        finally:
            bs.logout()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--fetch-only", action="store_true")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if not __debug__ or args.workers < 1:
        parser.error("请启用断言并指定正整数并发数")
    root = args.project_dir.resolve(strict=True)
    cache = args.cache.resolve() if args.cache else root / "cache" / "baostock_t5"
    if not args.offline:
        fetch_evidence(cache)
        fetch(root, cache, args.workers)
    if not args.fetch_only:
        process(root, cache, args.destination or root)


if __name__ == "__main__":
    main()
