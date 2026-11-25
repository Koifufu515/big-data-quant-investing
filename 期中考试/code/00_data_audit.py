#!/usr/bin/env python3
"""只读审计期中考试数据。依赖 Python 3.10+、pandas、NumPy。"""

import argparse
import csv
import hashlib
import logging
import platform
import shlex
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd


STOCK = "zz500_component_20241231.csv"
INDEX = "index_zz500.csv"
PAPER_STOCK = "zz500_component_20230531"
START, SPLIT, END = "2016-02-01", "2021-01-01", "2024-12-31"
SCHEMAS = {
    STOCK: ("stkcd", "trddt", "close_adj", "volume", "amount", "name", "ret"),
    INDEX: ("stkcd", "trddt", "volume", "amount", "ret", "riskfree"),
}
TEXT = {"stkcd", "trddt", "name"}
FIELDS = {
    "stkcd": ("证券标识，保留前导零", "结构已核验", "六位数字字符串，指数表仅一个代码"),
    "trddt": ("交易日标识", "结构已核验", "ISO 日期，逐日和指数表比对"),
    "name": ("证券简称", "含义有样例支持", "简称样例与股票代码组合，历史更名生效日期待确认"),
    "close_adj": ("疑似复权收盘价", "复权方式待确认", "与个股 ret 作相邻交易日价格变化一致性检验，前后复权、锚点及公司行动口径待确认"),
    "volume": ("疑似成交量", "单位待确认", "非负值且与 amount 零值同步，股或手及指数汇总口径待确认"),
    "amount": ("疑似成交额", "单位待确认", "非负值且与 volume 零值同步，币种及缩放倍数待确认"),
    "ret": ("日收益率候选", "口径待确认", "试卷确认数据用途，个股表以价格变化作交叉检验，指数价格/全收益及分红口径待确认"),
    "riskfree": ("无风险利率序列", "用途试卷确认，计量待确认", "逐交易日记录，量级与日小数相容，代理资产、原始频率、日计数和换算方式未证实"),
}


def sha256(path):
    with path.open("rb") as handle:
        digest = hashlib.sha256()
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def unpack(archive, root):
    with tarfile.open(archive, "r:*") as tar:
        members = tar.getmembers()
        names = [entry.name for entry in members]
        assert len(names) == len(set(names)), "归档成员重名"
        assert set(names) == set(SCHEMAS), f"归档版本或结构变化，须更新审计映射：{names}"
        inventory = []
        for member in members:
            assert member.isfile() and Path(member.name).name == member.name, member.name
            path = root / member.name
            with tar.extractfile(member) as source, path.open("xb") as target:
                shutil.copyfileobj(source, target)
            assert path.stat().st_size == member.size, member.name
            inventory.append((member.name, member.size, sha256(path)))
            logging.info("解压 %s (%d bytes) SHA-256=%s", member.name, member.size, inventory[-1][2])
    return inventory


def read_csv(path):
    encoding = "gb18030" if path.name == STOCK else "utf-8"
    raw_blanks = dict.fromkeys(SCHEMAS[path.name], 0)
    count = 0
    with path.open(encoding=encoding, errors="surrogateescape", newline="") as handle:
        rows = csv.reader(handle, strict=True)
        header = tuple(next(rows))
        assert header == SCHEMAS[path.name], header
        for count, row in enumerate(rows, 1):
            assert len(row) == len(header), (path.name, count, len(row))
            for field, value in zip(header, row):
                if value == "":
                    raw_blanks[field] += 1
    frame = pd.read_csv(path, encoding=encoding, encoding_errors="surrogateescape",
                        dtype={field: object for field in header if field in TEXT},
                        keep_default_na=False, na_values=[""], float_precision="round_trip")
    assert count == len(frame) and tuple(frame.columns) == header, path.name
    assert frame.isna().sum().to_dict() == raw_blanks, path.name
    for field in set(frame) - TEXT:
        assert pd.api.types.is_numeric_dtype(frame[field]), (path.name, field)
    parsed = pd.to_datetime(frame.trddt, format="%Y-%m-%d", errors="coerce")
    date_errors = int((parsed.isna() | parsed.dt.strftime("%Y-%m-%d").ne(frame.trddt)).sum())
    code_errors = int((~frame.stkcd.str.fullmatch(r"[0-9]{6}", na=False)).sum())
    return frame, encoding, date_errors, code_errors


def write_csv(path, rows):
    assert rows
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def period_table(frame):
    periods = {"全部": frame, "开发期": frame[frame.trddt.between(START, SPLIT, inclusive="left")],
               "样本外": frame[frame.trddt.between(SPLIT, END)]}
    assert sum(len(periods[p]) for p in ("开发期", "样本外")) == len(frame)
    assert set(periods["开发期"].trddt).isdisjoint(periods["样本外"].trddt)
    return periods


def describe_fields(asset, periods, encoding):
    frame = periods["全部"]
    dictionary, missing = [], []
    for field, series in frame.items():
        meaning, status, evidence = FIELDS[field]
        valid = series.dropna()
        comparable = field != "name" and len(valid) > 0
        dictionary.append(dict(
            文件=asset, 字段=field, 含义=meaning, 确认状态=status, 证据与待确认=evidence,
            审计读入类型=str(series.dtype), 建议逻辑类型=(
                "日期" if field == "trddt" else "字符串" if field in TEXT else "数值"),
            文件编码=encoding, 非缺失不同值=valid.nunique(),
            最小值=valid.min() if comparable else "", 最大值=valid.max() if comparable else "",
        ))
        for period, data in periods.items():
            blank = int(data[field].isna().sum())
            escaped = int(data[field].str.contains(r"[\udc80-\udcff]", na=False).sum()) if field in TEXT else 0
            missing.append(dict(文件=asset, 区间=period, 字段=field, 总行数=len(data), 缺失数=blank,
                                缺失比例=blank / len(data), 编码异常非空行数=escaped))
    return dictionary, missing


def audit(archive, output, work_parent, argv):
    original_hash = sha256(archive)
    logging.info("环境 Python=%s pandas=%s NumPy=%s OS=%s", platform.python_version(),
                 pd.__version__, np.__version__, platform.platform())
    logging.info("命令 %s", shlex.join(argv))
    logging.info("原 tar %s | %d bytes | SHA-256=%s", archive, archive.stat().st_size, original_hash)
    quality, dictionary, missing, coverage, annual = [], [], [], [], []

    def check(asset, item, value, expected=None, detail="", level="记录"):
        if expected is not None:
            level = "通过" if value == expected else "异常"
        quality.append(dict(文件=asset, 检查项=item, 实测=value, 预期="" if expected is None else expected,
                            状态=level, 说明=detail))
        logging.info("%s | %s | %s | %s", asset, item, value, level)

    with tempfile.TemporaryDirectory(prefix="zz500-audit-", dir=work_parent) as extracted:
        logging.info("独立解压目录 %s", extracted)
        inventory = unpack(archive, Path(extracted))
        check("data.tar", "试卷所列个股文件名存在", any(Path(x[0]).stem == PAPER_STOCK for x in inventory),
              True, "实际个股文件为 " + STOCK)
        frames = {}
        for asset, _, _ in inventory:
            frame, encoding, dates_bad, codes_bad = read_csv(Path(extracted) / asset)
            frames[asset] = frame
            check(asset, "缺失或非法日期", dates_bad, 0)
            check(asset, "缺失或非法证券标识", codes_bad, 0)
            assert dates_bad == codes_bad == 0, "无法可靠建立交易日与代码键"
            check(asset, "至少有一个空字段的行数", int(frame.isna().any(axis=1).sum()),
                  detail=f"占全文件 {frame.isna().any(axis=1).mean():.6%}")
            check(asset, "全部空单元格", int(frame.isna().sum().sum()),
                  detail=f"占全文件单元格 {frame.isna().to_numpy().mean():.6%}")
            periods = period_table(frame)
            glossary, blanks = describe_fields(asset, periods, encoding)
            dictionary.extend(glossary)
            missing.extend(blanks)
            for label, data in periods.items():
                coverage.append((asset, label, len(data), data.shape[1], data.trddt.min(),
                                 data.trddt.max(), data.trddt.nunique(), data.stkcd.nunique()))
            for year, data in frame.groupby(frame.trddt.str[:4]):
                annual.append((asset, year, len(data), data.trddt.nunique(), data.stkcd.nunique()))
            for name, columns in [("完全相同的额外记录", None), ("股票代码与日期重复额外记录", ["stkcd", "trddt"])]:
                check(asset, name, int(frame.duplicated(columns).sum()), 0, "每组保留一条的计数口径")
                check(asset, name.replace("额外", "涉及的全部"), int(frame.duplicated(columns, keep=False).sum()), 0)
            for field in frame.select_dtypes(include="number"):
                data = frame[field].dropna()
                check(asset, f"{field} 非有限值", int((~np.isfinite(data)).sum()), 0)
            check(asset, "周末日期数", int(pd.to_datetime(frame.trddt.unique()).dayofweek.isin([5, 6]).sum()), 0)
            check(asset, "成交量负值", int(frame.volume.lt(0).sum()), 0)
            check(asset, "成交额负值", int(frame.amount.lt(0).sum()), 0)
            check(asset, "收益率小于等于 -100%", int(frame.ret.le(-1).sum()), 0)

    stock, index = frames[STOCK], frames[INDEX]
    days = pd.Index(sorted(index.trddt.unique()))
    stock_days = pd.Index(sorted(stock.trddt.unique()))
    for left, right, label in [(stock_days, days, "个股有记录而指数没有"), (days, stock_days, "指数有记录而个股全市场没有")]:
        diff = left.difference(right)
        check("联合", f"{label}的日期数", len(diff), 0, ", ".join(diff[:10]))
    index_dups = int(index.duplicated("trddt").sum())
    check(INDEX, "重复日期的额外行数", index_dups, 0)
    check(INDEX, "每个日期正好一行", index.trddt.nunique() == len(index), True)
    assert index_dups == 0, "指数日期必须唯一，才能验证多对一连接"
    joined = stock[["trddt"]].merge(index[["trddt", "ret", "riskfree"]], on="trddt",
                                    how="left", validate="many_to_one", indicator=True)
    assert len(joined) == len(stock)
    assert int(joined["_merge"].ne("both").sum()) == int((~stock.trddt.isin(days)).sum())
    check("联合", "未匹配指数的个股行数", int(joined["_merge"].ne("both").sum()), 0)
    check(INDEX, "检验窗口起止日期", f"{days.min()} 至 {days.max()}", f"{START} 至 {END}")
    check(INDEX, "指数代码", ", ".join(sorted(index.stkcd.unique())), "000905")
    check(INDEX, "指数点位或开盘价字段", False, level="待确认", detail="表内无价格，不能用点位反证 ret 或验证开盘收益")
    rate = index.sort_values("trddt").riskfree
    check(INDEX, "无风险利率不同取值数", rate.nunique())
    check(INDEX, "相邻记录利率变化次数", int(rate.diff().dropna().ne(0).sum()))
    check(INDEX, "零成交量行", int(index.volume.eq(0).sum()), 0)
    check(INDEX, "零成交额行", int(index.amount.eq(0).sum()), 0)
    check(INDEX, "无风险利率非正值", int(rate.le(0).sum()), 0)
    check(INDEX, "无风险利率来源和换算口径", "无元数据", level="待确认")

    sets = stock.groupby("trddt").stkcd.agg(frozenset)
    sizes = sets.map(len)
    check(STOCK, "不同日度出现代码集合数", sets.nunique())
    check(STOCK, "每日可见股票数范围", f"{sizes.min()}–{sizes.max()}")
    check(STOCK, "每日可见代码少于 500 的日期数", int(sizes.lt(500).sum()), detail="不据此认定成分缺失")
    set_changes = sets.ne(sets.shift())
    check(STOCK, "日度集合变化次数", int(set_changes.sum()) - 1)
    check(STOCK, "官方成分及生效区间可核验", False, level="阻碍", detail="逐日出现的代码随时间变化，含义待提供方确认")
    snapshots = []
    for day in dict.fromkeys([stock_days[0], "2023-05-31", stock_days[-1]]):
        if day in sets.index:
            snapshots.append((day, len(sets[day]), len(sets[day] & sets.iloc[-1])))
    memberships = []
    previous = frozenset()
    for day, observed in sets[set_changes].items():
        memberships.append((day, len(observed), len(observed - previous), len(previous - observed)))
        previous = observed

    stock = stock.sort_values(["stkcd", "trddt"])
    positions = stock.trddt.map(pd.Series(range(len(days)), index=days))
    gaps = positions.groupby(stock.stkcd).diff() - 1
    prior = stock.groupby("stkcd").close_adj.shift()
    errors = (stock.close_adj / prior - 1 - stock.ret).abs()
    adjacent = gaps.eq(0) & errors.notna()
    mismatched = errors.gt(0.0001)
    assert int(adjacent.sum() + (gaps.gt(0) & errors.notna()).sum()) <= int(errors.notna().sum())
    check(STOCK, "跨越至少一条指数日期的相邻个股记录对", int(gaps.gt(0).sum()),
          detail=f"按股票累计跳过 {int(gaps[gaps.gt(0)].sum())} 个指数日，最大 {int(gaps.max())} 日")
    check(STOCK, "相邻指数日可比的价变与收益率对数", int(adjacent.sum()))
    check(STOCK, "相邻指数日价变与 ret 偏离超过 1 基点", int((adjacent & mismatched).sum()), 0)
    check(STOCK, "跨缺口价变与 ret 偏离超过 1 基点", int((gaps.gt(0) & mismatched).sum()),
          detail="跨期价格变化与单日收益不可直接等同")
    examples = []
    for row_id in errors[adjacent & mismatched].nlargest(10).index:
        row = stock.loc[row_id]
        examples.append((row.stkcd, row.trddt, f"{row.close_adj / prior[row_id] - 1:.8f}",
                         f"{row.ret:.8f}", f"{errors[row_id]:.8f}"))
    zeros = stock.volume.eq(0)
    check(STOCK, "零成交量行", int(zeros.sum()), detail=f"{stock.loc[zeros, 'stkcd'].nunique()} 只股票，{stock.loc[zeros, 'trddt'].nunique()} 日期")
    check(STOCK, "零成交额行", int(stock.amount.eq(0).sum()))
    check(STOCK, "零成交量与零成交额标记不一致", int(zeros.ne(stock.amount.eq(0)).sum()), 0)
    check(STOCK, "成交量与成交额缺失标记不一致", int(stock.volume.isna().ne(stock.amount.isna()).sum()), 0)
    check(STOCK, "零成交量且收益非零或缺失", int((zeros & stock.ret.ne(0)).sum()), 0)
    check(STOCK, "零成交量且相邻指数日收盘价变化", int((zeros & gaps.eq(0) & stock.close_adj.ne(prior)).sum()), 0)
    check(STOCK, "非正收盘价", int(stock.close_adj.le(0).sum()), 0)
    check(STOCK, "收益率绝对值超过 0.20", int(stock.ret.abs().gt(0.20).sum()),
          detail="筛查阈值，不作为认定涨跌停违规或错误的依据")
    name_issues = stock.name.str.contains(r"[\udc80-\udcff]", na=False)
    check(STOCK, "简称编码异常行", int(name_issues.sum()), 0,
          "原字节保留在分析内存，涉及代码 " + ", ".join(stock.loc[name_issues, "stkcd"].unique()))
    ret_missing = [(row.stkcd, row.trddt) for row in stock[stock.ret.isna()].itertuples()]
    check(STOCK, "收益率空白行", len(ret_missing), 0, ", ".join(" ".join(x) for x in ret_missing))
    for item, detail in [
        ("复权和公司行动", "无原价、复权因子及调整锚点"),
        ("停牌、涨跌停与可成交性", "只有零成交等代理线索，无官方状态字段"),
        ("市值、换手率、行业", "无对应字段，成交量额仅作流动性候选"),
        ("财务披露时点", "无财务报表或首次披露及修订时间"),
        ("月末与次日成交价", "观测日可分离，无个股开盘价或可执行报价"),
    ]:
        check(STOCK, item, "需补证", detail=detail, level="待确认")

    month_ends = pd.Series(days).groupby(days.str[:7]).last()
    successors = pd.Series(days, index=days).shift(-1)
    month_rows = [(label, date, successors[date] if pd.notna(successors[date]) else "区间外")
                  for label, date in month_ends.items()]
    check("联合", "观测月份数", len(month_rows))
    check("联合", "月末在样本内有下一指数日的月份数", sum(row[2] != "区间外" for row in month_rows))
    check("联合", "开发期至样本外的月末执行边界",
          " → ".join(next(row[1:] for row in month_rows if row[0] == "2020-12")))
    assert sha256(archive) == original_hash, "原压缩包哈希发生变化"
    check("data.tar", "运行前后 SHA-256 一致", True, True, original_hash)
    write_csv(output / "01_data_dictionary.csv", dictionary)
    write_csv(output / "02_missing_audit.csv", missing)
    write_csv(output / "03_data_quality.csv", quality)
    report = make_report(inventory, coverage, annual, dictionary, missing, quality, snapshots,
                         memberships, examples, month_rows, sizes, original_hash, archive, argv)
    (output / "00_data_audit.md").write_text(report, encoding="utf-8")
    logging.info("交付生成，共 %d 字段、%d 缺失统计、%d 质量检查", len(dictionary), len(missing), len(quality))


def table(headers, rows):
    def line(row):
        return "| " + " | ".join(str(value).replace("|", "&#124;") for value in row) + " |"

    return "\n".join([line(headers), line(["---"] * len(headers)), *(line(row) for row in rows)])


def make_report(inventory, coverage, annual, dictionary, missing, quality, snapshots,
                memberships, examples, months, sizes, digest, archive, argv):
    metrics = {(row["文件"], row["检查项"]): row["实测"] for row in quality}
    checks = {(row["文件"], row["检查项"]): row for row in quality}
    fields = {(row["文件"], row["字段"]): row for row in dictionary}
    stock_total = next(row[2] for row in coverage if row[:2] == (STOCK, "全部"))
    rate = fields[INDEX, "riskfree"]
    roles = {STOCK: "个股日面板，含行情、收益与简称", INDEX: "指数日基准、量额和无风险利率"}
    asset_rows = [(name, "CSV", f"{size:,}", roles[name], f"`{checksum}`")
                  for name, size, checksum in inventory]
    missing_rows = [(row["文件"], row["区间"], row["字段"], f'{row["缺失数"]:,}',
                     f'{row["缺失比例"]:.6%}', row["编码异常非空行数"])
                    for row in missing if row["缺失数"] or row["编码异常非空行数"]]
    summary = table(("文件", "区间", "行数", "列数", "首日", "末日", "日期数", "代码数"),
                    [(row[0], row[1], f"{row[2]:,}", *row[3:]) for row in coverage])
    field_table = table(("文件", "字段", "读入类型", "含义及确认状态", "最小", "最大", "不同值"),
                        [(r["文件"], r["字段"], r["审计读入类型"], r["含义"] + "（" + r["确认状态"] + "）",
                          r["最小值"], r["最大值"], r["非缺失不同值"]) for r in dictionary])

    return f"""# 厦门大学《大数据与量化投资》2026 年期中考试 A 卷数据审计

## 审计结论

| 问题 | 结论 |
| --- | --- |
| 数据是否完整 | 归档内两份 CSV 都可读取，两表覆盖试卷要求的起止日期且日集合一致。试卷所列个股文件名与归档不同。个股面板存在缺口、空值和文本字节异常，对正式回测所需数据的完整性尚无法确认。 |
| 传统量化策略 | 现有行情能支持描述性研究和原型开发。考试规定按当时有效成分股选股，正式执行还需补齐成分资格、价格与交易状态证据。 |
| 机器学习策略 | 现有行情和指数序列能支持探索性原型。若采用指数级预测，成分资格问题对预测输入的影响较小，交易工具、执行价格和收益口径仍需落实。个股级预测还受历史股票池、跨日缺口及标签可观测性的限制。 |
| 正式回测阻碍 | 逐日成分资格未经证实，缺少可执行行情和交易状态，复权与基准收益口径待核验。无风险利率计量未确认，直接用于 Sharpe 比率可能造成频率或单位错配。 |
| 需要补充 | 官方历史成分及调整公告和生效日，交易所日历，逐日未复权开收盘价和复权因子，公司行动、停复牌、涨跌停、退市及交易状态，指数官方点位和收益口径，无风险利率来源与计算说明。采用基本面、行业、市值或换手率数据时，另需对应的历史可用版本及时间戳。 |

## 一、资料与归档盘点

依据《大数据与量化投资2026期中考试试卷A.pdf》第 1–2 页及同目录 `data.tar`。试卷要求覆盖 2016-02-01 至 2024-12-31，每月使用月末已知信息形成决策，可在月末收盘或下一交易日开盘执行。传统题每次从当时有效的成分股中选 30–50 只，禁止做空及杠杆。2016–2020 年用于开发，2021–2024 年用于最终样本外评价。机器学习部分要求标签与实际交易时点对齐，训练时标签完全可见，并处理标签窗口重叠。

试卷称个股数据为 `{PAPER_STOCK}`。归档根目录只有下列两个普通文件，无 20230531 命名成员、独立名单、数据字典或供应商说明。以实际归档版本审计，建议向出题方核实文件名版本和面板构造规则。

归档为 TAR，共 {archive.stat().st_size:,} 字节。运行前后 SHA-256 一致，为 `{digest}`。解压使用独立临时目录，结束后清理。

{table(("成员", "格式", "字节数", "用途", "SHA-256"), asset_rows)}

## 二、结构与缺失

{summary}

两份数据均为交易日频。指数 `stkcd=000905` 对应一个指数标识。个股是证券日面板。CSV 不自带类型，上表分期使用自然日期边界切分。以下字段含义结合试卷、字段值与交叉检验，供应商单位和定义以字典中的待确认说明为准。

{field_table}

全行完全重复或代码–交易日重复，按每组除第一条的额外行计数，个股分别为 {metrics[STOCK, "完全相同的额外记录"]} 和 {metrics[STOCK, "股票代码与日期重复额外记录"]}，指数分别为 {metrics[INDEX, "完全相同的额外记录"]} 和 {metrics[INDEX, "股票代码与日期重复额外记录"]}。两表键字段均通过格式校验。股票代码和交易日可以共同标识一条个股记录。

缺失以原 CSV 空字段计数，分母为对应文件与区间的总行数。简称异常按不可严格解码的非空行另计。下表列出有观测问题的字段，其余零值明细见缺失表。个股有 **{sum(r["缺失数"] for r in missing if r["文件"] == STOCK and r["区间"] == "全部"):,} 个空单元格**，涉及 {metrics[STOCK, "至少有一个空字段的行数"]:,} 行，占个股记录 {checks[STOCK, "至少有一个空字段的行数"]["说明"].removeprefix("占全文件 ")}。指数每列空值数均为 {max(r["缺失数"] for r in missing if r["文件"] == INDEX)}。

{table(("文件", "区间", "字段", "缺失数", "缺失比例", "编码异常非空行数"), missing_rows)}

个股表大部分文本与 GB18030 相容，简称存在 {metrics[STOCK, "简称编码异常行"]} 条异常行。读取时用 `surrogateescape` 保留异常字节，异常简称不参与业务解释。指数表可按 UTF-8 读取。收益率缺失定位为 `{checks[STOCK, "收益率空白行"]["说明"]}`。

<details>
<summary>按年覆盖与代码数量</summary>

{table(("文件", "年份", "记录数", "日期数", "代码数"), annual)}

</details>

## 三、中证 500 个股面板

### 历史成分资格

观察到 **{metrics[STOCK, "不同日度出现代码集合数"]} 套不同日度代码集合**，日度集合变化 {metrics[STOCK, "日度集合变化次数"]} 次，每日出现 {sizes.min()}–{sizes.max()} 只股票，{sizes.lt(500).sum():,} 天少于 500 只。2023-05-31 与期末的可见名单也有实质差异。全期 {fields[STOCK, "stkcd"]["非缺失不同值"]:,} 个代码和分段变化的日度集合表明，数据包含跨时点变化的观察池，已有证据排除了全期仅围绕一份固定 500 股名单的解释。是否真实逐日采用当时有效成分，仍需核实。文件没有成分标记、权重、纳入及剔除生效日，行情行是否出现可能受构造规则或数据覆盖影响。

{table(("交易日", "可见股票数", "与最后一日交集"), snapshots)}

若后续把 2023-05-31、2024-12-31 或其他事后快照固定回填全期，将引入潜在幸存者偏差和前视选样。使用全期代码并集作为历史股票池也会暴露未来纳入信息。当前逐日出现集合可作为候选，与官方有效名单核对前，无法认证无幸存者偏差。

<details>
<summary>观测代码集合变化日期</summary>

首行表示初始集合，相邻行的增减是观测变化。

{table(("日期", "可见股票数", "新增可见", "退出可见"), memberships)}

</details>

### 交易状态、价格与收益

- 零成交量 **{metrics[STOCK, "零成交量行"]:,} 行**，占个股行 {metrics[STOCK, "零成交量行"] / stock_total:.4%}，涉及 {checks[STOCK, "零成交量行"]["说明"]}。零量与零额完全同步，这些记录上的收益均为零。有相邻指数日个股记录可比时，价格也无变化。该模式与停牌或无交易时沿用旧价相符，仍需正式停复牌与成交状态判断。另有成对空白的量额记录，空值应与零值分别识别。
- 价格为非正的记录 {metrics[STOCK, "非正收盘价"]} 条，成交量及成交额负值分别为 {metrics[STOCK, "成交量负值"]}、{metrics[STOCK, "成交额负值"]} 条。收益率绝对值超过 20% 的记录 {metrics[STOCK, "收益率绝对值超过 0.20"]} 条。20% 仅为筛查阈值，制度、上市阶段和公司行动需结合原始行情判读。最高 `close_adj` 为 {fields[STOCK, "close_adj"]["最大值"]}，可能受调整尺度影响，不能直接当作可执行价格或认定为录入错误。
- `close_adj` 与 `ret` 在 {metrics[STOCK, "相邻指数日可比的价变与收益率对数"]:,} 个可比相邻指数日记录对中，只有 {metrics[STOCK, "相邻指数日价变与 ret 偏离超过 1 基点"]} 对的绝对偏差超过 0.0001。该结果支持 `ret` 为日小数收益率、`close_adj` 与经调整的历史价格序列相容。具体复权方式、是否含分红和调整因子可用时点待确认。
- 同股相邻记录间有 {metrics[STOCK, "跨越至少一条指数日期的相邻个股记录对"]} 处跨越指数交易日缺口，{checks[STOCK, "跨越至少一条指数日期的相邻个股记录对"]["说明"]}。该计数不含各股票首末记录之外的日期，也不能据此区分退出股票池、停牌和行情漏采。跨缺口时有 {metrics[STOCK, "跨缺口价变与 ret 偏离超过 1 基点"]} 对超过上述阈值，跨期价格变化不能直接替代日收益。
- 价格、收益、量额和简称有研究用途。表内没有市值、换手率、行业、流通股份、原始开收盘价或公司行动字段。

{table(("代码", "日期", "相邻价变", "ret", "绝对偏差"), examples)}

## 四、指数与对齐

- 指数表有 **{metrics[INDEX, "检验窗口起止日期"]}** 的 {next(r[6] for r in coverage if r[:2] == (INDEX, "全部")):,} 个观测交易日，重复日期 {metrics[INDEX, "重复日期的额外行数"]} 个，缺失日期字段 {metrics[INDEX, "缺失或非法日期"]} 行。指数与个股日期集合双向差集均为 0，按日期多对一左连接验证后，未匹配指数的个股行数为 {metrics["联合", "未匹配指数的个股行数"]}。双方若同时缺日，内部比对无法发现，完整的交易所日历尚未独立核验。
- 指数表含 `ret`，范围 {fields[INDEX, "ret"]["最小值"]} 至 {fields[INDEX, "ret"]["最大值"]}，若按小数收益率读取，与日收益量级相容。缺少指数开盘、收盘点位和价格／全收益定义，无法直接交叉验算日收益或开盘到开盘收益。
- `riskfree` 逐交易日记录，取值 {rate["最小值"]:.6f} 至 {rate["最大值"]:.6f}，有 {metrics[INDEX, "无风险利率不同取值数"]} 个不同值，相邻记录变化 {metrics[INDEX, "相邻记录利率变化次数"]} 次。若其单位为日小数，则对应 {rate["最小值"]:.4%}–{rate["最大值"]:.4%} 每日，量级支持这一候选口径。原代理资产、报价可得时间、原频率、简单或复利、交易日或自然日计数和年化转换均待确认。

## 五、信息边界与执行时间

- **切分可行。** 以 `trddt < 2021-01-01` 划入开发期，其余在考试窗口内的日期划入样本外。两期互斥并覆盖全部行。开发期 2016 年从 2 月 1 日起，首个观察月缺少前置历史，滚动窗口的可用起点取决于所需历史长度。
- **月末信号与执行。** 从指数观测日取每月最后一个交易日候选，再查下一指数日。样本内有 {len(months)} 个观测月，其中 {sum(r[2] != "区间外" for r in months)} 个有下一观测交易日。2020 年 12 月末至下一执行日为 **{metrics["联合", "开发期至样本外的月末执行边界"]}**。2024-12 末后的执行日、成交价及收益越出材料窗口。若使用月末完整收盘价、全天量额等收盘后才可确认的数据，不能假定能以同一收盘价成交。月末收盘执行需可证明信号在委托截止前已知，次日开盘执行则需开盘行情并核对实际可交易性。指数和个股日历对齐无法凭空提供开盘价。
- **财务信息。** 两表均无财务字段，也无报告期、实际公告日或修订版本，无法检查具体错位实例。若补充财务数据，应以首次可获得的披露时间和当时可见版本合并。报告期末回填、披露当日收盘后发布却用于同日成交，以及用修订值覆盖历史快照，均可能泄漏。
- **未来数据与机器学习。** 原数据没有显式标签或因子，不能验证采集版本是否保留历史当时可见的信息。历史成员、复权锚点、全样本标准化、未来收益标签都需核对时间边界。训练或更新时，标签的结束与可观测时间应早于当时的信息截止点。开发末尾持有期穿过 2021 边界的训练标签需移出开发训练，训练与验证窗口的标签重叠需清除，样本外表现不能反向用于调参。
- **最低补数依据。** 优先补成分进出日期及生效规则、带开盘价的实际可交易行情和状态、复权因子与事件、官方基准和日历、无风险利率口径。若要分析行业归因或扩展到基本面，再取得历史行业分类、市值／流通股本和含披露时间的财务记录。指数级策略还需明确可交易载体及其行情、费用和可用起始时间。

<details>
<summary>月末信号候选与下一交易日候选</summary>

{table(("月份", "观测月末", "下一指数观测日"), months)}

</details>

## 六、复现与运行记录

- Python {platform.python_version()}，pandas {pd.__version__}，NumPy {np.__version__}，{platform.platform()}。
- 实际命令 `{shlex.join(argv)}`。
- 数据字典见 [01_data_dictionary.csv](01_data_dictionary.csv)，缺失见 [02_missing_audit.csv](02_missing_audit.csv)，质量检查见 [03_data_quality.csv](03_data_quality.csv)，过程与结果见 [运行日志](00_data_audit.log)。
- 断言覆盖归档成员与字节大小、CSV 结构与空值计数、键格式、阶段切分、指数日期唯一、连接行数及原包哈希。零成交、收益偏差、版本差异等以审计结果记录。请用普通 Python 模式运行，以启用断言。
- 仅进行数据结构与一致性检查。相邻价变检验用于核对既有收益字段，未构造投资因子、预测标签或策略，也未增删或填补原始记录。
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True, help="原 data.tar 路径")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "output")
    parser.add_argument("--work-dir", type=Path, help="临时解压目录的父目录，默认使用系统临时目录")
    args = parser.parse_args()
    if not __debug__:
        parser.error("请关闭 Python 优化以启用审计断言")
    archive = args.archive.resolve(strict=True)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for filename in ("00_data_audit.log", "00_data_audit.md", "01_data_dictionary.csv",
                     "02_missing_audit.csv", "03_data_quality.csv"):
        target = output / filename
        if target.is_symlink() or (target.exists() and target.samefile(archive)):
            parser.error(f"输出目标为符号链接或与原档案相同：{target}")
    # 上海时间与考试所在时区一致。
    logging.Formatter.converter = staticmethod(
        lambda t: datetime.fromtimestamp(t, timezone(timedelta(hours=8))).timetuple()
    )
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s +08:00 %(levelname)s %(message)s",
        handlers=[logging.FileHandler(output / "00_data_audit.log", mode="w", encoding="utf-8"),
                  logging.StreamHandler()],
    )
    try:
        audit(archive, output, args.work_dir, [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])
    except Exception:
        logging.exception("审计未完成")
        raise


if __name__ == "__main__":
    main()
