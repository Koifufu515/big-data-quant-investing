#!/usr/bin/env python3
"""验收第三轮研究面板，并按月末信号日对齐下一期收盘到收盘收益。"""

import argparse
import csv
import importlib
import io
import math
import os
import platform
import sys
import tarfile
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
third = importlib.import_module("02_build_research_dataset")
first = third.first

THIRD_COMMIT = "bdfc177d261a10d7d4afe75be6718421810ef0c3"
THIRD_URL = f"https://github.com/Koifufu515/big-data-quant-investing/commit/{THIRD_COMMIT}"
DAILY = "processed/daily_panel.csv"
MONTHLY = "processed/monthly_panel.csv"
KEY = ["stkcd", "trddt"]
STOCK_NUMERIC = ["close_adj", "ret", "volume", "amount"]
MEMBER = {third.MEMBER_QUOTE: "confirmed_member", third.MEMBER_ABSENT: "confirmed_member",
          third.NONMEMBER: "confirmed_nonmember", third.UNKNOWN: "unknown"}
TRACKED = (
    "data.tar", "code/00_data_audit.py", "code/01_followup_audit.py", "code/02_build_research_dataset.py",
    "output/00_data_audit.md", "output/01_data_dictionary.csv", "output/02_missing_audit.csv",
    "output/03_data_quality.csv", "output/04_constituent_reconciliation.md",
    "output/05_constituent_reconciliation.csv", "output/06_return_consistency.csv",
    "output/07_followup_data_requirements.md", "output/08_data_processing_report.md",
    "output/09_monthly_return_audit.csv", DAILY, MONTHLY,
)


def read_csv(path, **kwargs):
    return pd.read_csv(path, encoding="utf-8-sig", dtype={"stkcd": str},
                       float_precision="round_trip", low_memory=False, **kwargs)


def check_lfs(local, pointer, downloaded, digest):
    if pointer is None:
        return None
    assert local.resolve() != downloaded.resolve() and not local.samefile(downloaded)
    expected = ["version https://git-lfs.github.com/spec/v1", f"oid sha256:{digest}",
                f"size {local.stat().st_size}"]
    assert pointer.read_text(encoding="ascii").splitlines() == expected, "远端指针与本地面板不一致"
    assert downloaded.stat().st_size == local.stat().st_size, "LFS 实体大小不一致"
    assert first.sha256(downloaded) == digest, "LFS 实体 SHA-256 不一致"
    return local.stat().st_size


def source_data(archive):
    with tarfile.open(archive, "r:*") as tar:
        assert set(tar.getnames()) == {first.STOCK, first.INDEX}
        with io.TextIOWrapper(tar.extractfile(first.INDEX), encoding="utf-8", newline="") as handle:
            records = list(csv.DictReader(handle))
        market = {row["trddt"]: (float(row["ret"]), float(row["riskfree"])) for row in records}
        assert len(market) == len(records) == 2167
        with tar.extractfile(first.STOCK) as handle:
            original = pd.read_csv(handle, encoding="gb18030", encoding_errors="surrogateescape",
                                  dtype={"stkcd": str}, float_precision="round_trip",
                                  keep_default_na=False, na_values=[""], usecols=[*KEY, *STOCK_NUMERIC])
    assert not original.duplicated(KEY).any() and set(original.trddt) == set(market)
    return original, market


def check_daily(root, original, market):
    columns = [*KEY, *STOCK_NUMERIC, "stock_row_present", "membership_status",
               "membership_evidence", "membership_claim", "membership_event_date",
               "etf_index_holding", "ret_input_valid", "quote_state", "close_adj_break",
               "index_ret", "riskfree_raw", "riskfree_status"]
    daily = read_csv(root / DAILY, usecols=columns)
    assert not daily.duplicated(KEY).any()
    present = daily.stock_row_present
    expected = original.sort_values(["trddt", "stkcd"], ignore_index=True)
    actual = daily.loc[present, expected.columns].reset_index(drop=True)
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)
    assert daily.loc[~present, STOCK_NUMERIC].isna().to_numpy().all()
    assert daily.ret_input_valid.eq(present & np.isfinite(daily.ret) & daily.ret.ge(-1)).all()
    joined_index = daily[["trddt", "index_ret", "riskfree_raw"]].drop_duplicates()
    assert {r.trddt: (r.index_ret, r.riskfree_raw) for r in joined_index.itertuples(index=False)} == market
    assert daily.riskfree_status.eq("unverified").all()

    zero = present & daily.volume.eq(0) & daily.amount.eq(0)
    no_amount = present & (daily.volume.isna() | daily.amount.isna())
    missing_ret = present & daily.ret.isna()
    assert zero.eq(daily.quote_state.eq("zero_volume_and_amount")).all()
    assert no_amount.eq(daily.quote_state.eq("volume_or_amount_missing")).all()
    assert (~present).eq(daily.quote_state.eq("no_row")).all()

    days = pd.Index(sorted(market))
    expected_evidence, expected_etf = third.stock_pool_evidence(days)
    actual_evidence = daily.loc[daily.membership_evidence.notna(), expected_evidence.columns]
    pd.testing.assert_frame_equal(actual_evidence.sort_values(KEY, ignore_index=True),
                                 expected_evidence.sort_values(KEY, ignore_index=True))
    etf = daily.loc[daily.etf_index_holding.eq("yes"), KEY].sort_values(KEY, ignore_index=True)
    pd.testing.assert_frame_equal(etf, expected_etf[KEY].sort_values(KEY, ignore_index=True))
    official = daily.membership_evidence.isin(["official_delta", "szse_delisted"])
    member = official & daily.membership_claim.eq("in")
    nonmember = official & daily.membership_claim.eq("out")
    assert daily.membership_status.eq(third.MEMBER_QUOTE).equals(member & present)
    assert daily.membership_status.eq(third.MEMBER_ABSENT).equals(member & ~present)
    assert daily.membership_status.eq(third.NONMEMBER).equals(nonmember)
    assert daily.membership_status.eq(third.UNKNOWN).equals(~(member | nonmember))

    stock = original.sort_values(KEY)
    positions = stock.trddt.map(pd.Series(range(len(days)), index=days))
    prior_close = stock.groupby("stkcd").close_adj.shift()
    adjacent = positions.groupby(stock.stkcd).diff().eq(1)
    deviations = (stock.close_adj / prior_close - 1 - stock.ret).abs()
    breaks = {tuple(row) for row in stock.loc[adjacent & deviations.gt(.0001), KEY].to_numpy()}
    assert breaks == {tuple(row) for row in daily.loc[daily.close_adj_break, KEY].to_numpy()}
    result = dict(rows=len(daily), stock_rows=len(original), zero_volume=int(zero.sum()),
                  incomplete_quote=int(no_amount.sum()), missing_ret=int(missing_ret.sum()),
                  breaks=len(breaks), break_keys=breaks)
    return daily, result


def check_monthly(root, daily, original, market, checks):
    month_days = defaultdict(list)
    for day in sorted(market):
        month_days[day[:7]].append(day)
    end_dates = {month: days[-1] for month, days in month_days.items()}
    months = list(month_days)
    anchors = {month: end_dates[previous] for previous, month in zip(months, months[1:])}

    monthly = read_csv(root / MONTHLY)
    codes = sorted(daily.stkcd.unique())
    target_grid = pd.MultiIndex.from_product([codes, months], names=["stkcd", "month"])
    monthly = monthly.set_index(["stkcd", "month"], verify_integrity=True).sort_index()
    pd.testing.assert_index_equal(monthly.index, target_grid)
    stock = original.sort_values(KEY).assign(month=lambda rows: rows.trddt.str[:7])
    values = stock.groupby(["stkcd", "month"], sort=False).ret.agg(list).to_dict()
    known_dates = set(end_dates.values())
    endpoints = daily.loc[daily.trddt.isin(known_dates)].set_index(KEY)
    candidates = {tuple(key) for key in endpoints.loc[endpoints.stock_row_present].index}
    zero_per_month = daily.loc[daily.quote_state.eq("zero_volume_and_amount")].groupby(
        [daily.stkcd, daily.trddt.str[:7]]).size().to_dict()
    empty_quote_per_month = daily.loc[daily.quote_state.eq("volume_or_amount_missing")].groupby(
        [daily.stkcd, daily.trddt.str[:7]]).size().to_dict()
    break_per_month = defaultdict(int)
    for code, day in checks["break_keys"]:
        break_per_month[code, day[:7]] += 1
    benchmark = {month: math.prod(1 + market[day][0] for day in days) - 1
                 for month, days in month_days.items() if month in anchors}

    for (code, month), row in zip(monthly.index, monthly.itertuples(index=False)):
        days = month_days[month]
        anchor = anchors.get(month)
        returns = values.get((code, month), [])
        valid_values = [v for v in returns if math.isfinite(v) and v >= -1]
        anchor_ok = (code, anchor) in candidates
        end_ok = (code, days[-1]) in candidates
        has_missing = sum(math.isnan(v) for v in returns)
        has_invalid = len(returns) - len(valid_values) - has_missing
        valid = anchor_ok and len(valid_values) == len(days)
        assert row.first_date == days[0] and row.end_date == days[-1]
        assert row.start_anchor_date == anchor if anchor else pd.isna(row.start_anchor_date)
        assert row.anchor_row_present == anchor_ok and row.end_row_present == end_ok
        assert row.expected_sessions == len(days) and row.stock_sessions == len(returns)
        assert row.missing_stock_sessions == len(days) - len(returns)
        assert row.valid_ret_sessions == len(valid_values)
        assert row.missing_ret_on_rows == has_missing and row.invalid_ret_on_rows == has_invalid
        reasons = []
        for condition, reason in [(not anchor, "no_anchor_in_archive"),
                                  (anchor is not None and not anchor_ok, "missing_anchor_stock_row"),
                                  (not returns, "no_stock_rows_in_month"),
                                  (0 < len(returns) < len(days), "missing_stock_sessions"),
                                  (has_missing > 0, "missing_ret_on_rows"),
                                  (has_invalid > 0, "invalid_ret_on_rows")]:
            if condition:
                reasons.append(reason)
        assert ("|".join(reasons) if reasons else "") == (
            "" if pd.isna(row.return_invalid_reason) else row.return_invalid_reason)
        assert row.return_valid == valid and pd.notna(row.holding_return) == valid
        assert row.zero_quote_sessions == zero_per_month.get((code, month), 0)
        assert row.missing_quote_fields_sessions == empty_quote_per_month.get((code, month), 0)
        assert row.price_break_sessions == break_per_month[code, month]
        if valid:
            assert math.isclose(row.holding_return, math.prod(1 + v for v in returns) - 1, abs_tol=1e-12)
        if month in benchmark:
            assert math.isclose(row.index_holding_return, benchmark[month], abs_tol=1e-12)
        else:
            assert pd.isna(row.index_holding_return)
        assert row.window_period == ("development" if days[0] < first.SPLIT else "out_of_sample")

    # 当第三轮月末状态为未知时，也与原日面板的证据状态逐行核对。
    indexed = monthly.reset_index()
    for col, prefix in [("start_anchor_date", "anchor"), ("end_date", "end")]:
        endpoint_keys = pd.MultiIndex.from_frame(indexed[["stkcd", col]])
        status = endpoints.membership_status.reindex(endpoint_keys).fillna(third.UNKNOWN)
        assert indexed[f"{prefix}_membership_status"].tolist() == status.tolist()
        etf = endpoints.etf_index_holding.reindex(endpoint_keys).fillna("")
        assert indexed[f"{prefix}_etf_index_holding"].fillna("").tolist() == etf.tolist()

    audit = read_csv(root / "output/09_monthly_return_audit.csv").set_index("month")
    group = indexed.groupby("month")
    pd.testing.assert_series_equal(audit.valid_stock_months, group.return_valid.sum(),
                                   check_names=False)
    assert audit.stock_months.eq(len(codes)).all()
    assert audit.invalid_stock_months.eq(audit.stock_months - audit.valid_stock_months).all()
    return indexed


def align_signals(monthly):
    signal = monthly[["stkcd", "month", "end_date", "window_period", "end_row_present",
                      "end_membership_status", "end_etf_index_holding"]].rename(columns={
        "month": "signal_month", "end_date": "signal_date", "window_period": "signal_period",
        "end_row_present": "signal_stock_row_present", "end_membership_status": "signal_membership_status",
        "end_etf_index_holding": "signal_etf_index_holding",
    })
    signal["return_month"] = (pd.PeriodIndex(signal.signal_month, freq="M") + 1).astype(str)
    labels = monthly[["stkcd", "month", "window_period", "start_anchor_date", "first_date", "end_date",
                     "expected_sessions", "stock_sessions", "holding_return", "return_valid",
                     "return_invalid_reason", "index_holding_return"]].rename(columns={
        "month": "return_month", "window_period": "return_period", "first_date": "next_session_date",
        "end_date": "return_end_date", "holding_return": "monthly_close_to_close_return",
        "return_valid": "return_chain_complete", "index_holding_return": "index_monthly_close_to_close_return",
    })
    result = signal.merge(labels, on=["stkcd", "return_month"], how="left", validate="one_to_one", indicator=True)
    missing_window = result.pop("_merge").eq("left_only")
    result["return_window_in_archive"] = ~missing_window
    result["return_period"] = result.return_period.fillna("outside_sample")
    for col in ["stock_sessions", "expected_sessions"]:
        result[col] = result[col].astype("Int64")
    result["return_chain_complete"] = result.return_chain_complete.eq(True)
    result.loc[missing_window, "return_invalid_reason"] = "next_month_outside_archive"
    result["label_observable_after_close_date"] = result.return_end_date.where(result.return_chain_complete)
    result["signal_membership_confirmation"] = result.signal_membership_status.map(MEMBER)
    result["trade_execution_status"] = "unconfirmed"
    assert len(result) == len(monthly) and not result.duplicated(["stkcd", "signal_month"]).any()
    assert result.signal_membership_confirmation.notna().all()
    assert result.return_month.eq((pd.PeriodIndex(result.signal_month, freq="M") + 1).astype(str)).all()
    assert result.loc[~missing_window, "signal_date"].eq(result.loc[~missing_window, "start_anchor_date"]).all()
    assert result.loc[~missing_window, "signal_date"].lt(result.loc[~missing_window, "next_session_date"]).all()
    assert result.loc[~missing_window, "next_session_date"].le(result.loc[~missing_window, "return_end_date"]).all()
    assert result.monthly_close_to_close_return.notna().equals(result.return_chain_complete)
    assert result.return_invalid_reason.notna().equals(~result.return_chain_complete)
    assert result.label_observable_after_close_date.notna().equals(result.return_chain_complete)
    assert result.loc[missing_window, "signal_month"].eq("2024-12").all()
    assert result.loc[missing_window, "return_month"].eq("2025-01").all()
    assert not result.return_chain_complete[missing_window].any()
    assert result.return_chain_complete.sum() == monthly.return_valid.sum()
    columns = ["stkcd", "signal_month", "signal_date", "signal_period",
               "signal_stock_row_present", "signal_membership_status", "signal_membership_confirmation",
               "signal_etf_index_holding", "return_month", "return_period", "return_window_in_archive",
               "next_session_date", "return_end_date", "label_observable_after_close_date",
               "expected_sessions", "stock_sessions", "monthly_close_to_close_return",
               "index_monthly_close_to_close_return", "return_chain_complete",
               "return_invalid_reason", "trade_execution_status"]
    return result[columns].sort_values(["signal_month", "stkcd"], ignore_index=True)


def validation_report(aligned, monthly, checks, lfs_size, hashes):
    coverage = aligned.groupby("signal_month").agg(
        signal_date=("signal_date", "first"), return_month=("return_month", "first"),
        unknown_eligibility=("signal_membership_confirmation", lambda x: x.eq("unknown").sum()),
        confirmed_member=("signal_membership_confirmation", lambda x: x.eq("confirmed_member").sum()),
        confirmed_nonmember=("signal_membership_confirmation", lambda x: x.eq("confirmed_nonmember").sum()),
        complete_returns=("return_chain_complete", "sum"),
    )
    all_unknown = coverage[coverage.confirmed_member.eq(0) & coverage.confirmed_nonmember.eq(0)]
    partial = coverage.drop(all_unknown.index)
    mutually_distinct = int(aligned.trade_execution_status.eq("unconfirmed").sum())
    valid = aligned[aligned.return_chain_complete]
    return_range = monthly.groupby("window_period").agg(
        first_month=("month", "min"), last_month=("month", "max"), months=("month", "nunique"),
        complete=("return_valid", "sum"),
    )
    development = return_range.loc["development"]
    test = return_range.loc["out_of_sample"]
    boundary = aligned[aligned.signal_month.eq("2020-12")]
    b = boundary.iloc[0]
    csv_coverage = first.table(("信号月", "月末信号日", "收益月", "资格未知", "确认成分",
                                "确认非成分", "收益链完整"),
                               [(m, row.signal_date, row.return_month, row.unknown_eligibility,
                                 row.confirmed_member, row.confirmed_nonmember, row.complete_returns)
                                for m, row in coverage.iterrows()])
    breaks = first.table(("代码", "交易日"), sorted(checks["break_keys"]))
    if lfs_size is not None:
        lfs_status = (
            f"已从 GitHub 的 Git LFS 端点完整拉取 {lfs_size:,} 字节，并读取第三轮提交内的原始指针。"
            f"下载实体、本地日频面板及远端指针的 SHA-256 均为 `{hashes[DAILY]}`。"
        )
    else:
        lfs_status = "本次离线运行未提供远端指针和完整拉取副本，未重验 Git LFS 下载。"
    return f"""# 第四轮 · 研究数据最终验收与时间对齐

## 验收结论

第三轮日频和月频面板通过数值与边界核对。原月度列 `holding_return` 是**月度收盘到收盘收益**，在本轮对齐表中以 `monthly_close_to_close_return` 明确命名。{len(aligned):,} 个信号股票月保留 {len(valid):,} 个收益链完整的研究标签，涉及 {valid.stkcd.nunique():,} 只股票。历史成分资格和交易可执行性各有独立的状态和证据要求。现有资料支持收益及标签准备，仍缺正式选股回测所需的月末成分名册和可执行报价。

## 收益定义与三个独立状态

| 字段 | 定义 |
| --- | --- |
| `monthly_close_to_close_return` | 从信号日收盘到下月最后一个交易日收盘的持有期研究收益。沿用课程日 `ret` 连乘 `∏(1 + ret[t]) − 1`，连乘区间从下月第一交易日开始，含下月最后交易日。 |
| `return_chain_complete` | 信号日有原始个股行作为期初收盘锚点，随后每个目标交易日都有原行情和有效日 `ret`。无标签的行保留原因，收益留空。 |
| `signal_membership_confirmation` | 月末当日历史资格，取 `confirmed_member`、`confirmed_nonmember` 或 `unknown`。原日面板四种状态保存在 `signal_membership_status`，ETF 截面证据单列。 |
| `trade_execution_status` | 交易可执行性。全部 {mutually_distinct:,} 行为 `unconfirmed`。材料缺次日开盘报价和逐股可执行状态。 |

对完整收益链，逐行用原 TAR 的日收益独立复算，并与月频数值核对。相同窗口的指数收益也以课程指数 `ret` 连乘。无风险利率继续保留日面板原值及未核实状态，月度标签不使用利率。

## 历史成分资格覆盖

保留第三轮已核实的官方调样和退市证据，ETF 截面仍保留独立旁证。现有证据中，{len(all_unknown)} 个月的月末资格全部未知，另外 {len(partial)} 个月（{partial.index.min()} 至 {partial.index.max()}）仅能确认 000540 为非成分，其余代码仍为未知。所有月末目前均没有可直接确认的成分股记录。第三轮 `confirmed_member_at_anchor_and_return_valid=0` 反映已证实记录的覆盖范围，无法据此判定未知股票的资格。

<details>
<summary>逐月资格证据和完整收益覆盖</summary>

{csv_coverage}

</details>

## 信号、标签与执行时间

- 月末观察日只使用当时已可知的信息形成下一期信号。`signal_month` 和 `return_month` 始终相隔一个自然月。表内的目标窗口、收益和可见时间属于事后标签信息，只用于事后核对与监督目标。
- 样本内最早的信号日为 2016-02-29，对应 2016 年 3 月标签。首个持有月 2016 年 2 月缺档内上月末锚点。最终信号日 2024-12-31 对应 2025 年 1 月，下一期超出档案，所有股票行保留并标为 `next_month_outside_archive`。
- 开发期按目标持有月为 {development.first_month} 至 {development.last_month}，{development.months} 个观测月、{development.complete:,} 个有效原月度标签。样本外为 {test.first_month} 至 {test.last_month}，{test.months} 个月、{test.complete:,} 个有效标签。边界例为 **{b.signal_date} 信号 → {b.next_session_date} 下一交易日 → {b.return_end_date} 标签期末**，信号月在开发期，目标月份及其完整标签归样本外。开发期训练应按标签窗口的可观测截止约束处理该边界。
- `label_observable_after_close_date` 只为完整标签填写，对应期末收盘之后。月末收盘到收盘收益包含从月末收盘到下一交易日开盘的价格变化。次日开盘买入会从开盘成交价开始计量，现有收益无法替代该执行口径。次日交易日期仅作为候选，表内没有生成次日开盘收益。

## 原始异常与 Git LFS 验收

| 复核项目 | 结果 |
| --- | --- |
| 日频数值 | 原始行情 {checks["stock_rows"]:,} 行的键、`ret`、`close_adj`、量额逐行一致，衍生日频行共 {checks["rows"]:,}。 |
| 缺失收益 | 原始行内 `ret` 缺失 {checks["missing_ret"]} 条，保留缺失。月频无效收益继续为空并保留原因。 |
| 零成交与量额缺失 | 零量零额 {checks["zero_volume"]:,} 行，量额字段缺失 {checks["incomplete_quote"]:,} 行，均单独标记。 |
| 价格异常 | 由原档独立复算的 {checks["breaks"]} 条相邻日价格异常与日频标记、月频计数相符。 |
| Git LFS | {lfs_status} |

{breaks}

## 复现与交付

在桌面 `期中考试` 下运行 `python3 -B code/03_validate_research_dataset.py`。运行默认验证本地数据。在线拉取第三轮提交中的实际 Git LFS 文件和原始指针后，另加 `--lfs-pointer 指针文件 --lfs-copy 下载副本` 可重验两者。Python {platform.python_version()}、pandas {pd.__version__}。原始 TAR 的 SHA-256 为 `{hashes["data.tar"]}`，第三轮月频文件 SHA-256 为 `{hashes[MONTHLY]}`。原始数据、旧报告、旧脚本及原面板在运行前后逐项核对哈希。

[信号收益对齐表](11_signal_return_alignment.csv) · [第三轮处理报告](08_data_processing_report.md) · [第三轮 GitHub 提交与 LFS 指针出处]({THIRD_URL}) · [验收脚本](../code/03_validate_research_dataset.py)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    project = Path(__file__).resolve().parents[1]
    parser.add_argument("--project-dir", type=Path, default=project, help="第三轮的完整期中考试目录")
    parser.add_argument("--output-dir", type=Path, help="输出目录，默认是期中考试/output")
    parser.add_argument("--lfs-pointer", type=Path, help="第三轮提交中的原始 Git LFS 指针")
    parser.add_argument("--lfs-copy", type=Path, help="从 GitHub LFS 取得的日频面板副本")
    args = parser.parse_args()
    if not __debug__:
        parser.error("请使用启用断言的 Python")
    if (args.lfs_pointer is None) != (args.lfs_copy is None):
        parser.error("--lfs-pointer 与 --lfs-copy 必须同时提供")
    root = args.project_dir.resolve(strict=True)
    output = args.output_dir.resolve() if args.output_dir else root / "output"
    inputs = [root / name for name in TRACKED]
    if (root / "output/00_data_audit.log").is_file():
        inputs.append(root / "output/00_data_audit.log")
    hashes = {str(path.relative_to(root)): first.sha256(path) for path in inputs}
    assert hashes["data.tar"] == third.ARCHIVE_HASH, "原始归档版本变化"
    lfs_size = check_lfs(root / DAILY, args.lfs_pointer, args.lfs_copy, hashes[DAILY])
    original, market = source_data(root / "data.tar")
    daily, checks = check_daily(root, original, market)
    monthly = check_monthly(root, daily, original, market, checks)
    aligned = align_signals(monthly)
    report = validation_report(aligned, monthly, checks, lfs_size, hashes)
    assert all(first.sha256(path) == hashes[str(path.relative_to(root))] for path in inputs)
    output.mkdir(parents=True, exist_ok=True)
    names = ("10_final_data_validation.md", "11_signal_return_alignment.csv")
    with TemporaryDirectory(prefix=".validation-", dir=output) as temp:
        work = Path(temp)
        (work / names[0]).write_text(report, encoding="utf-8")
        aligned.to_csv(work / names[1], index=False, encoding="utf-8-sig")
        for name in names:
            assert not (output / name).is_symlink()
        for name in names:
            os.replace(work / name, output / name)
    print(f"已验收 {len(aligned):,} 个信号股票月，{aligned.return_chain_complete.sum():,} 个完整收益标签；"
          f" Git LFS {'核验通过' if lfs_size is not None else '离线未重查'}。")


if __name__ == "__main__":
    main()
