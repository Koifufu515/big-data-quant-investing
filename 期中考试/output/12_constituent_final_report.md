# T5 · 历史成分股核验

2016-02 至 2024-12 共 **107 个候选月末股票池，每月 500 个不同代码**。其中 **104 个月为 B 级研究截面**，其余 **3 个月为 C 级候选**。正式研究筛选依据是 `pool_status=research_supported`。B 级由供应商或多源重建支持，指数公司完整逐日名册仍有缺口。C 级月份及其无法证实的成分资格留有显式标记。

| 月份 | 结果 | 证据边界 |
| --- | --- | --- |
| 2021-09 | 499 只供应商证据，601868 暂列候选 | 9 月 28 日上市，9 月末 BaoStock 无该股，10 月 8 日查询首次见其作为唯一新增。该区间内的正式调入日尚未获得 000905 专属公告 |
| 2021-12 | 500 只，B 级重建 | 完整 ETF 指数投资持仓相对 11 月 BaoStock 恰好 50 进、50 出，逐码等于次年 1 月 BaoStock |
| 2022-12 | 500 只，B 级重建 | 年末 ETF 对 11 月 BaoStock 恰好 50 进、50 出，公告公开示例 603606 与 688063 均属调入，逐码等于次年 3 月 BaoStock |
| 2023-01 | 500 只候选，C 级 | 2022 年末与 2023 年 3 月截面相同，期间临时调整与当月有效名单待证实 |
| 2023-02 | 500 只候选，C 级 | 2022 年末与 2023 年 3 月截面相同，期间临时调整与当月有效名单待证实 |

601868 的上市日、接口可见日和正式指数生效日分别看待。上交所吸收合并附件没有 000905 条目。新浪 000905 关联记录列调入日为 09-28，公开整理档列 09-29，两者的生效日口径及完整性未核实。2023 年 1–2 月定向检索公开调样公告未取得能还原该区间全部临时调整的证据，年末名单仅作为候选。2021 年 12 月和 2022 年 12 月的交易日起点分别为 12 月 13 日和 12 月 12 日。官方公告确认调样日及数量，逐码变更来自前截面与完整 ETF 持仓的差集，另用后续 BaoStock 完整截面交叉验证。 [601868 上市公告](https://www.sse.com.cn/disclosure/announcement/listing/ipo/c/c_20210927_83094980.shtml) · [吸收合并公告](https://www.sse.com.cn/market/sseindex/diclosure/c/c_20210830_5570656.shtml) · [新浪关联记录](https://vip.stock.finance.sina.com.cn/corp/go.php/vCI_CorpXiangGuan/stockid/601868.phtml) · [公开整理档](https://github.com/unliftedq/index-constitution/blob/b724386d375f281fa693032772221f0d2e2a144f/history/csi500.csv) · [2021-12 调样公告转述](https://www.cnfin.com/kx/detail/20211126/3467213_1.html) · [2022-12 调样公告转述](https://www.cnfin.com/gs-lb/detail/20221125/3752600_1.html) · [2021 ETF 年报](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2022-03-31/510500_20220331_1_3qPQoPDA.pdf) · [2022 ETF 年报](https://pdf.dfcfw.com/pdf/H2_AN202303311584743601_1.pdf)

完整 53,500 行保留证券代码、证据等级、来源及获取日期。2021-09 仅 601868 的个别资格为 `unknown`，整个截面仍为 C；2023 年两个月的个股资格均为 `unknown`。这些月份纳入报价查缺，收益覆盖报告单列。 [逐月名单](../processed/monthly_constituents.csv)
