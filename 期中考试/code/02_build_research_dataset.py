#!/usr/bin/env python3
"""从原始 TAR 和前两轮审计证据生成研究面板。Python 3.10+、pandas、NumPy。"""

import argparse
import importlib
import logging
import os
import platform
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
followup = importlib.import_module("01_followup_audit")
first = followup.first

KEY = ["stkcd", "trddt"]
FOCUS = ("000540", "300114")
UNKNOWN = "unknown"
MEMBER_QUOTE = "member_with_quote"
MEMBER_ABSENT = "member_no_quote"
NONMEMBER = "nonmember"
RISKFREE_STATUS = "unverified"
PRIMARY_DATES = ("2023-06-12", "2023-12-11", "2024-12-16")
SUSPENSION = "https://static.cninfo.com.cn/finalpage/2023-05-19/1216852113.PDF"
DELISTING = "https://www.szse.cn/disclosure/notice/general/t20230630_601499.html"
COMPANY_DELISTING = "https://money.finance.sina.com.cn/corp/view/vCB_AllBulletinDetail.php?id=9317506&stockid=000540"
ARCHIVE_HASH = "2bac5bed1488cb181b7b29757f02199d6d2d4f91171847817fdd1214d222e0ea"


def stock_pool_evidence(days):
    rows = []
    for event_date, (removed, added) in followup.PUBLISHED_DELTAS.items():
        previous = days[days.get_loc(event_date) - 1]
        source_type = "official_delta" if event_date in PRIMARY_DATES else "reproduced_delta"
        for day, inside, outside in [(previous, removed, added), (event_date, added, removed)]:
            rows.extend((code, day, claim, source_type, event_date)
                        for codes, claim in [(inside, "in"), (outside, "out")] for code in codes.split())
    rows.extend((code, "2024-06-17", "in", "reproduced_delta", "2024-06-17")
                for code in followup.JUNE_2024_IN.split())
    rows.extend(("000540", day, "out", "szse_delisted", "2023-06-30")
                for day in days[days >= "2023-06-30"])
    evidence = pd.DataFrame(rows, columns=[*KEY, "membership_claim", "membership_evidence",
                                           "membership_event_date"])
    assert not evidence.duplicated(KEY).any()
    etf = pd.DataFrame(
        [(code, day) for day, codes in followup.ETF_SNAPSHOTS.items() for code in codes.split()],
        columns=KEY,
    )
    assert not etf.duplicated(KEY).any() and etf.groupby("trddt").size().eq(500).all()
    return evidence, etf.assign(etf_index_holding=True)


def price_break_evidence(path, stock, days):
    audit = pd.read_csv(path, encoding="utf-8-sig", dtype={"stkcd": str})
    breaks = audit.loc[audit.kind.eq("相邻日偏差"), ["stkcd", "date", "prev_date", "ret", "close_adj",
        "prev_close_adj", "raw_prev_close", "raw_close", "raw_close_return", "ret_minus_raw_bp",
        "prev_adj_to_raw", "adj_to_raw", "abs_difference_bp"]].rename(columns={"date": "trddt"})
    assert len(breaks) == 5 and not breaks.duplicated(KEY).any()
    by_key = stock.set_index(KEY)
    targets = breaks.set_index(KEY)
    previous = pd.MultiIndex.from_frame(breaks[["stkcd", "prev_date"]])
    np.testing.assert_allclose(by_key.loc[targets.index, "ret"], targets.ret, rtol=0, atol=1e-12)
    np.testing.assert_allclose(by_key.loc[targets.index, "close_adj"], targets.close_adj, rtol=0, atol=1e-9)
    np.testing.assert_allclose(by_key.loc[previous, "close_adj"], targets.prev_close_adj, rtol=0, atol=1e-9)
    assert all(days.get_loc(date) == days.get_loc(prev) + 1
               for date, prev in zip(breaks.trddt, breaks.prev_date))
    computed = (breaks.close_adj / breaks.prev_close_adj - 1 - breaks.ret).abs() * 10000
    np.testing.assert_allclose(computed, breaks.abs_difference_bp, rtol=0, atol=1e-8)
    assert computed.gt(1).all() and breaks.ret_minus_raw_bp.abs().lt(.01).all()
    return breaks


def build_daily(stock, index, breaks, evidence, etf):
    days = pd.Index(index.trddt)
    focus = pd.MultiIndex.from_product([FOCUS, days], names=KEY).to_frame(index=False)
    panel = stock.assign(stock_row_present=True).merge(evidence, how="outer", on=KEY, validate="one_to_one")
    panel = panel.merge(etf, how="outer", on=KEY, validate="one_to_one")
    panel = panel.merge(focus, how="outer", on=KEY, validate="one_to_one")
    panel["stock_row_present"] = panel.stock_row_present.notna()
    panel["etf_index_holding"] = np.select(
        [panel.etf_index_holding.notna(), panel.trddt.isin(followup.ETF_SNAPSHOTS)],
        ["yes", "no"], default="",
    )
    verified = panel.membership_evidence.isin(["official_delta", "szse_delisted"])
    member = verified & panel.membership_claim.eq("in")
    panel["membership_status"] = np.select(
        [member & panel.stock_row_present, member, verified & panel.membership_claim.eq("out")],
        [MEMBER_QUOTE, MEMBER_ABSENT, NONMEMBER], default=UNKNOWN,
    )
    trading_span = panel.stkcd.eq("000540") & panel.trddt.between("2023-04-17", "2023-05-18")
    suspension = panel.stkcd.eq("000540") & panel.trddt.between("2023-05-19", "2023-06-29")
    delisted = panel.membership_evidence.eq("szse_delisted")
    panel["stock_market_event"] = np.select([trading_span, suspension, delisted],
        ["issuer_reported_trading", "issuer_announced_suspension", "szse_delisted"], default="")

    # GB18030 不可解码处以转义显示，并在异常行附该字段完整原始字节。
    bad_names = panel.name.str.contains(r"[\udc80-\udcff]", na=False)
    panel["name_raw_hex"] = ""
    names = panel.loc[bad_names, "name"]
    panel.loc[bad_names, "name_raw_hex"] = names.map(lambda name: name.encode("gb18030", "surrogateescape").hex())
    panel.loc[bad_names, "name"] = names.map(lambda name: name.encode("utf-8", "backslashreplace").decode())
    panel["name_encoding_issue"] = bad_names
    panel["quote_state"] = np.select(
        [~panel.stock_row_present, panel.volume.isna() | panel.amount.isna(),
         panel.volume.eq(0) & panel.amount.eq(0)],
        ["no_row", "volume_or_amount_missing", "zero_volume_and_amount"], default="reported",
    )
    panel["ret_input_valid"] = panel.stock_row_present & np.isfinite(panel.ret) & panel.ret.ge(-1)
    anomaly_keys = pd.MultiIndex.from_frame(breaks[KEY])
    panel["close_adj_break"] = pd.MultiIndex.from_frame(panel[KEY]).isin(anomaly_keys)
    index_fields = index[["trddt", "ret", "riskfree"]].rename(columns={"ret": "index_ret", "riskfree": "riskfree_raw"})
    panel = panel.merge(index_fields, on="trddt", validate="many_to_one")
    panel["riskfree_status"] = RISKFREE_STATUS
    assert panel.stock_row_present.sum() == len(stock)
    assert not panel.duplicated(KEY).any() and panel.close_adj_break.sum() == len(breaks)
    columns = [*KEY, "stock_row_present", "membership_status", "membership_claim", "membership_evidence",
               "membership_event_date", "etf_index_holding", "stock_market_event", "quote_state",
               "close_adj", "close_adj_break", "ret", "ret_input_valid", "volume", "amount", "name",
               "name_encoding_issue", "name_raw_hex", "index_ret", "riskfree_raw", "riskfree_status"]
    return panel[columns].sort_values(["trddt", "stkcd"], ignore_index=True)


def monthly_calendar(index):
    dates = index.assign(month=index.trddt.str[:7], gross=1.0 + index.ret)
    assert np.isfinite(dates.ret).all() and dates.ret.ge(-1).all()
    cal = dates.groupby("month").agg(
        first_date=("trddt", "first"), end_date=("trddt", "last"),
        expected_sessions=("trddt", "size"), index_gross=("gross", "prod"),
    )
    cal["start_anchor_date"] = cal.end_date.shift()
    cal["window_period"] = np.where(cal.first_date.lt(first.SPLIT), "development", "out_of_sample")
    return cal


def build_monthly(daily, index):
    cal = monthly_calendar(index)
    codes = sorted(daily.stkcd.unique())
    grid = pd.MultiIndex.from_product([codes, cal.index], names=["stkcd", "month"])
    stock = daily.loc[daily.stock_row_present, [*KEY, "ret", "ret_input_valid", "close_adj_break", "quote_state"]].copy()
    stock["month"] = stock.trddt.str[:7]
    stock["gross"] = (1.0 + stock.ret).where(stock.ret_input_valid)
    stock["ret_missing"] = stock.ret.isna()
    stock["zero_quote"] = stock.quote_state.eq("zero_volume_and_amount")
    stock["quote_fields_missing"] = stock.quote_state.eq("volume_or_amount_missing")
    grouped = stock.groupby(["stkcd", "month"], sort=False)
    observed = grouped.agg(stock_sessions=("trddt", "size"), valid_ret_sessions=("ret_input_valid", "sum"),
        missing_ret_on_rows=("ret_missing", "sum"), zero_quote_sessions=("zero_quote", "sum"),
        missing_quote_fields_sessions=("quote_fields_missing", "sum"),
        price_break_sessions=("close_adj_break", "sum"))
    counts = list(observed.columns)
    monthly = observed.reindex(grid, fill_value=0)
    monthly["candidate_gross"] = grouped.gross.prod(min_count=1).reindex(grid)
    monthly = monthly.reset_index().merge(cal.reset_index(), on="month", validate="many_to_one")
    day_context = daily[[*KEY, "stock_row_present", "membership_status", "etf_index_holding"]]
    for prefix, date_col in [("anchor", "start_anchor_date"), ("end", "end_date")]:
        endpoint = day_context.rename(columns={"trddt": date_col, "stock_row_present": f"{prefix}_row_present",
            "membership_status": f"{prefix}_membership_status", "etf_index_holding": f"{prefix}_etf_index_holding"})
        monthly = monthly.merge(endpoint, on=["stkcd", date_col], how="left", validate="many_to_one")
        monthly[f"{prefix}_row_present"] = monthly[f"{prefix}_row_present"].eq(True)
        monthly[f"{prefix}_membership_status"] = monthly[f"{prefix}_membership_status"].fillna(UNKNOWN)
    monthly["missing_stock_sessions"] = monthly.expected_sessions - monthly.stock_sessions
    monthly["invalid_ret_on_rows"] = monthly.stock_sessions - monthly.valid_ret_sessions - monthly.missing_ret_on_rows
    reasons = {
        "no_anchor_in_archive": monthly.start_anchor_date.isna(),
        "missing_anchor_stock_row": monthly.start_anchor_date.notna() & ~monthly.anchor_row_present,
        "no_stock_rows_in_month": monthly.stock_sessions.eq(0),
        "missing_stock_sessions": monthly.stock_sessions.gt(0) & monthly.missing_stock_sessions.gt(0),
        "missing_ret_on_rows": monthly.missing_ret_on_rows.gt(0),
        "invalid_ret_on_rows": monthly.invalid_ret_on_rows.gt(0),
    }
    reason = pd.Series("", index=monthly.index, dtype=object)
    for label, mask in reasons.items():
        reason.loc[mask] += label + "|"
    monthly["return_invalid_reason"] = reason.str.rstrip("|")
    monthly["return_valid"] = monthly.return_invalid_reason.eq("")
    monthly["holding_return"] = (monthly.candidate_gross - 1.0).where(monthly.return_valid)
    monthly["index_holding_return"] = (monthly.index_gross - 1.0).where(monthly.start_anchor_date.notna())
    monthly["riskfree_status"] = RISKFREE_STATUS
    valid = monthly.return_valid
    assert len(monthly) == len(codes) * len(cal) and not monthly.duplicated(["stkcd", "month"]).any()
    assert monthly.stock_sessions.sum() == len(stock) and monthly.price_break_sessions.sum() == 5
    assert monthly.missing_stock_sessions.ge(0).all() and monthly.invalid_ret_on_rows.ge(0).all()
    assert monthly.loc[valid, "expected_sessions"].eq(monthly.loc[valid, "valid_ret_sessions"]).all()
    assert np.isfinite(monthly.loc[valid, "holding_return"]).all()
    assert monthly.holding_return.notna().eq(valid).all()
    assert monthly.loc[valid, "anchor_row_present"].all()
    audit = monthly[["month", "return_valid", "return_invalid_reason", "stock_sessions",
        "valid_ret_sessions", "price_break_sessions", "zero_quote_sessions",
        "missing_quote_fields_sessions"]].copy()
    for label, mask in reasons.items():
        audit[f"reason_{label}"] = mask
    audit["month_has_stock_row"] = audit.stock_sessions.gt(0)
    audit["confirmed_member_at_anchor_and_return_valid"] = valid & monthly.anchor_membership_status.eq(MEMBER_QUOTE)
    sums = [field for field in audit.columns if field not in {"month", "return_invalid_reason"}]
    audit = audit.groupby("month").agg(stock_months=("return_valid", "size"),
                                      **{field: (field, "sum") for field in sums})
    audit = audit.rename(columns={"return_valid": "valid_stock_months"})
    audit["invalid_stock_months"] = audit.stock_months - audit.valid_stock_months
    audit["invalid_stock_months_with_observation"] = audit.month_has_stock_row - audit.valid_stock_months
    audit = cal[["start_anchor_date", "first_date", "end_date", "expected_sessions", "window_period"]].join(audit)
    assert audit.valid_stock_months.sum() == valid.sum()
    columns = ["stkcd", "month", "window_period", "start_anchor_date", "first_date", "end_date",
               "expected_sessions", *counts, "missing_stock_sessions", "invalid_ret_on_rows",
               "anchor_row_present", "anchor_membership_status", "anchor_etf_index_holding",
               "end_row_present", "end_membership_status", "end_etf_index_holding", "holding_return",
               "return_valid", "return_invalid_reason", "index_holding_return", "riskfree_status"]
    return monthly[columns].sort_values(["month", "stkcd"], ignore_index=True), audit.reset_index()


def processing_report(daily, monthly, audit, index, breaks, digest, evidence_digest):
    visible = daily.loc[daily.stock_row_present]
    by_day = visible.groupby("trddt").size()
    assert len(by_day) == len(index) and by_day.le(500).all()
    missing = daily.membership_status.eq(MEMBER_ABSENT)
    status_rows = []
    for status in [MEMBER_QUOTE, MEMBER_ABSENT, NONMEMBER, UNKNOWN]:
        selected = daily.membership_status.eq(status)
        status_rows.append((status, int(selected.sum()), int((selected & daily.stock_row_present).sum()),
                            int((selected & ~daily.stock_row_present).sum())))
    state_table = first.table(("资格状态", "行数", "有原行情行", "无原行情行"), status_rows)

    focus_dates = {
        "000540": ["2023-04-17", "2023-05-18", "2023-05-19", "2023-06-09", "2023-06-12", "2023-06-30"],
        "300114": ["2023-12-08", "2023-12-11", *sorted(followup.ETF_SNAPSHOTS)],
    }
    focus_rows = []
    for code, dates in focus_dates.items():
        selections = daily.loc[daily.stkcd.eq(code) & daily.trddt.isin(dates)]
        focus_rows.extend((r.stkcd, r.trddt, "有" if r.stock_row_present else "无",
                           r.membership_status, r.stock_market_event or "—", r.etf_index_holding or "—")
                          for r in selections.itertuples())
    focus_table = first.table(("代码", "日期", "课程行情", "资格状态", "交易事件", "ETF 截面持有"), focus_rows)
    abnormal_table = first.table(("代码", "前一交易日", "日期", "课程 ret", "复权价变与 ret 相差（bp）",
        "未复权收盘价变", "前日倍率 → 当日倍率"),
        [(r.stkcd, r.prev_date, r.trddt, f"{r.ret:.6%}", f"{r.abs_difference_bp:.2f}",
          f"{r.raw_close_return:.6%}", f"{r.prev_adj_to_raw:.6f} → {r.adj_to_raw:.6f}")
         for r in breaks.itertuples()])
    valid = monthly[monthly.return_valid]
    period_names = {"development": "开发期", "out_of_sample": "样本外"}
    result_rows = []
    for period, group in [("全部", monthly), *monthly.groupby("window_period")]:
        usable = group[group.return_valid]
        result_rows.append((period_names.get(period, period), group.month.nunique(), len(group),
            int(group.stock_sessions.gt(0).sum()), usable.stkcd.nunique(), len(usable),
            int((~group.return_valid & group.stock_sessions.gt(0)).sum())))
    month_summary = first.table(("区间", "月份", "股票月网格行", "月内有行情行的股票月", "至少 1 个有效月的股票",
                                "收益有效股票月", "月内有行情但收益无效的股票月"), result_rows)
    main_source = followup.DELTA_SOURCES["2023-06-12"]
    entry_source = followup.DELTA_SOURCES["2023-12-11"]
    return f"""# 第三轮 · 期中考试数据整理与可用性处理

## 结论

课程数据已整理为可复跑的日频和月频研究面板。原始表有 {len(visible):,} 行、{visible.stkcd.nunique():,} 个代码。衍生日频面板增加 {len(daily) - len(visible):,} 行无行情的证据或重点代码记录。全期 **{valid.stkcd.nunique():,} 只股票有至少一个有效月，共 {len(valid):,} 个收益有效股票月**。这里的有效指日收益覆盖完整并有期初观测锚点。正式月末选股还需验证成分资格及可成交性。

## 一、历史股票池

课程面板每日可见 {by_day.min()}–{by_day.max()} 只股票，{by_day.lt(500).sum():,} 个交易日少于 500，按官网报告的 500 只计数至少差 {(500 - by_day).sum():,} 个代码日。现有原始官方调样附件可直接支持 {int(missing.sum()):,} 个已识别的成分股缺行情代码日。其余缺额缺乏完整官方名单，少于 500 的现象不能整体归因于停牌、漏采、连接过滤或导出遗漏。2020-12-01 的同步消失及随后恢复仍是覆盖边界线索。 [第二轮成分股核验](04_constituent_reconciliation.md)

日频表保留所有原始行情键，补充已有证据涉及的股票日，并全期保留 000540 和 300114 的位置。依据原始调样附件，只标注生效交易日和紧邻前一交易日的更替关系，日期区间保持未知。退市后的 000540 按深交所摘牌事实标记为非成分。转载调样表仅保留声明和来源。ETF 持仓只在对应截面记入旁证列，面板的出现集合仅衡量观察覆盖。未出现在日面板的其他代码日没有单独建行，其成分状态为未知。表内状态统计是已建行覆盖范围内的统计。

{state_table}

`quote_state` 分别标记整行缺失、量额字段缺失、零量零额和一般可见行。状态里的 quote 指有课程行情行，零量行仍属该类。零量不能证实可成交或通过官方停牌核验。

### 000540 与 300114

{focus_table}

- **000540**。课程记录仅见于 2021 年。公司公告确认 2023-04-17 至 2023-05-18 有交易，课程对应段完全无行，2023-05-19 起才停牌，因此停牌不能解释全部历史缺行。官方调出边界把 2023-06-09 定位为调出前应有的成分股位置，其当日处于停牌期，课程无行情行。6 月 12 日起的调出事实与 6 月 30 日摘牌分别记录，期间没有逐日官方证据的日期保持未知。 [官方调样附件]({main_source}) · [停牌公告]({SUSPENSION}) · [公司终止上市公告]({COMPANY_DELISTING}) · [深交所终止登记服务公告]({DELISTING})
- **300114**。2023-12-11 官方调入，当日和整个归档都无该代码行情。2023 年末、2024 年中和 2024 年末 ETF 的 500 只指数投资持仓与课程 499 只可见股逐码对照，缺少的均为 300114。该证据支持持续缺额的解释，三个 ETF 截面仍单独标为旁证。302132 的代码变更发生在考试窗口之后，发生遗漏的上游步骤仍无法确定。 [官方调样附件]({entry_source}) · [ETF 截面核验](04_constituent_reconciliation.md#基金披露截面旁证) · [代码变更公告](https://www.cnindex.com.cn/zh_information/notices_news/2025/202502/P020250212310734081331.pdf)

## 二、个股收益与价格字段

- `ret` 保留老师提供的原字段数值。档案内相邻交易日的一致性和五个外部未复权对照支持按日小数收益使用。供应商字段定义、分红或再投资处理、统一含息口径仍待证实。统一约定把这一条原始序列在持有窗口内连乘，投资组合的个股收益输入和机器学习未来收益标签应共用此口径。现阶段产物是股票持有期收益和适用性标记。
- `close_adj` 保留原值，内部证据支持它是经倍率调整的收盘序列。具体前复权、后复权与基准锚点未知。可用于无断点、连续区间内对价格尺度不敏感的相对形态研究，例如区间内相对位置或相对均线距离。前提是单个特征窗口的价格口径连续且信息可得时间合规。绝对价格水平不宜做跨股比较，跨缺口和下列断点应隔离，实际成交价和持有期收益使用各自对应的行情和收益字段。
- 五条价格异常逐一写入 `close_adj_break`，月面板统计 `price_break_sessions`。第二轮未复权对照证明异常来自价格倍率跳变，五条日 `ret` 与外部价变均相差小于 0.01 个基点，所以这些标记本身不使原始 `ret` 失效。 [第二轮收益核验明细](06_return_consistency.csv)

{abnormal_table}

## 三、月度收益口径与完整性

月份键表示**持有期所在月**。期初锚点为上月最后一个观测交易日的收盘，期末为本月最后一个观测交易日的收盘。股票月收益为 `prod(1 + ret[t]) - 1`，连乘本月首个到最后一个指数交易日之间的所有原始日收益。上月末仅要求有个股行情行作为期初观测锚点，不计入其当日收益。首月在原档内没有期初锚点，该月保留为无效。2024 年 12 月内收益可计算，2024-12-31 形成信号所需的下一期收益超出范围。

`return_valid` 同时要求期初行情锚点存在、本月每个指数交易日都有个股行，且各日 `ret` 非空、有限并且不低于 −100%。本月无行情、缺部分行情、有行但 `ret` 空白或非法等原因可以叠加，逐股月记录在 `return_invalid_reason`。缺收益保留空白。零量日的课程原始收益照录，月面板另外保留零量和量额缺失计数，收益链有效仅表明可计算收盘估值口径。全期已知代码与全部月份的笛卡尔积仅用于审计，因此早于首次可见、退出后及完全缺失月份也被保留。

{month_summary}

在现有严格成分证据下，期初为已核实成分且收益有效的股票月为 **{audit.confirmed_member_at_anchor_and_return_valid.sum():,}**。公告的证据集中在月中，ETF 截面仍是旁证。阶段按持有期月份归属，2021 年 1 月持有期属于样本外，虽然期初锚点在 2020 年 12 月。用作预测标签时，应在期末收盘后才视作完整可得，并避免以持有期内的发现过滤期初股票池。月报审计中的原因计数可重叠，不能直接相加视作无效月份总数。 [月度有效性审计](09_monthly_return_audit.csv)

## 四、指数收益与无风险利率

`index_ret` 保留课程指数日收益，第二轮已核实和中证 500 价格指数的相邻收盘收益一致。`index_holding_return` 使用同一持有窗口对课程指数日收益连乘，首月因共同的期初边界约定留空。无风险利率列 `riskfree_raw` 保留 {len(index):,} 个交易日原值，有 {index.riskfree.nunique()} 个不同值，范围 {index.riskfree.min():.6f}–{index.riskfree.max():.6f}。可确认逐交易日**记录**，原始利率来源、单位、计息频率、公布时点和年化换算依然无法证实。两张面板标记 `riskfree_status=unverified`，月频表未生成利率。 [第二轮基准和利率核验](07_followup_data_requirements.md#指数收益与无风险利率)

## 五、考试任务可用性

| 考试任务 | 已有数据可支持 | 正式使用所需补证 |
| --- | --- | --- |
| 传统量化选股 | 从有效月份构造可对齐的收盘持有期收益与基准，检查候选行情覆盖 | 官方逐月有效成分及历史变更、退市和离开股票池后的行情、开盘可执行价或收盘下单信息、停牌和涨跌停状态、费用与已核实利率 |
| 个股机器学习 | 明确未来标签的统一收益定义、可观测时间及无效原因 | 官方期初股票池及独立持有期行情，防止按未来有行情筛样，分开定义次日开盘执行下的标签与交易成本 |
| 指数机器学习 | 可用已核验价格基准做数据准备 | 指数投资需要实际可交易载体和费用，次日开盘执行需要相应执行行情 |

## 六、复现

在 `期中考试` 目录执行 `python3 -B code/02_build_research_dataset.py`。脚本使用前两轮脚本及 `output/06_return_consistency.csv` 中五条外部核验结果，无网络依赖。原始 TAR 运行前后哈希为 `{digest}`，收益核验 CSV 哈希为 `{evidence_digest}`。检查覆盖原始键、证据键、指数日期对齐、日收益完整性、月度复利有效性与异常行保留。简称编码异常行以转义显示并附原字节十六进制。Python {platform.python_version()}，pandas {pd.__version__}，NumPy {np.__version__}。

[日频面板](../processed/daily_panel.csv) · [月频面板](../processed/monthly_panel.csv) · [月度审计](09_monthly_return_audit.csv) · [处理脚本](../code/02_build_research_dataset.py)
"""


def build(root, archive, audit_path):
    digest = first.sha256(archive)
    evidence_digest = first.sha256(audit_path)
    assert digest == ARCHIVE_HASH, "原始数据版本变化，需要重新核对证据"
    with TemporaryDirectory(prefix="zz500-research-") as work:
        directory = Path(work)
        first.unpack(archive, directory)
        stock, _, stock_dates, stock_codes = first.read_csv(directory / first.STOCK)
        index, _, index_dates, index_codes = first.read_csv(directory / first.INDEX)
    assert stock_dates == stock_codes == index_dates == index_codes == 0
    assert not stock.duplicated(KEY).any() and index.trddt.is_unique
    assert set(stock.trddt) == set(index.trddt)
    index = index.sort_values("trddt", ignore_index=True)
    days = pd.Index(index.trddt)
    evidence, etf = stock_pool_evidence(days)
    breaks = price_break_evidence(audit_path, stock, days)
    daily = build_daily(stock, index, breaks, evidence, etf)
    monthly, audit = build_monthly(daily, index)
    report = processing_report(daily, monthly, audit, index, breaks, digest, evidence_digest)
    assert first.sha256(archive) == digest and first.sha256(audit_path) == evidence_digest
    paths = ["processed/daily_panel.csv", "processed/monthly_panel.csv",
             "output/08_data_processing_report.md", "output/09_monthly_return_audit.csv"]
    root.mkdir(parents=True, exist_ok=True)
    for path in paths:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        assert not target.is_symlink(), target
        if target.exists():
            assert not (target.samefile(archive) or target.samefile(audit_path)), target
    with TemporaryDirectory(prefix=".research-output-", dir=root) as work:
        staging = Path(work)
        daily.to_csv(staging / "daily_panel.csv", index=False, encoding="utf-8-sig")
        monthly.to_csv(staging / "monthly_panel.csv", index=False, encoding="utf-8-sig")
        (staging / "08_data_processing_report.md").write_text(report, encoding="utf-8")
        audit.to_csv(staging / "09_monthly_return_audit.csv", index=False, encoding="utf-8-sig")
        for path in paths:
            os.replace(staging / Path(path).name, root / path)
    valid = monthly[monthly.return_valid]
    logging.info("日频行 %s，股票月 %s，有效股票 %s，有效股票月 %s，原始 SHA-256 %s",
                 len(daily), len(monthly), valid.stkcd.nunique(), len(valid), digest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--root", type=Path, default=root, help="处理结果写入目录")
    parser.add_argument("--archive", type=Path, default=root / "data.tar")
    parser.add_argument("--return-audit", type=Path, default=root / "output/06_return_consistency.csv")
    args = parser.parse_args()
    if not __debug__:
        parser.error("请使用启用断言的 Python 运行")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build(args.root.resolve(), args.archive.resolve(strict=True), args.return_audit.resolve(strict=True))


if __name__ == "__main__":
    main()
