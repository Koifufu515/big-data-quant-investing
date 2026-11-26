# 中证 500 历史成分免费获取与对账

## 覆盖结论

使用 BaoStock 免费 `query_zz500_stocks(date=...)`，查验 2016 年 1 月至 2024 年 12 月的全部月末及调样窗口，共 348 个请求日期。2018-11 至 2024-12 的 74 个目标月均实际查询。接口历史覆盖早于 2018-11。最早实测的 2016-01-04 完整起点有 500 只且无重复，返回版本为 2016-01-04。课程数据从 2016-02-01 开始，在该日完整起始名单有 500 个代码，课程有 478 个，缺 22 个且仅课程有 0 个。两个起点的完整代码均收入名单表。这两个起始截面来自直接公开查询，官方完整起始名册仍未取得。 [BaoStock 免费接口](https://www.baostock.com/mainContent?file=pythonAPI.md)

| 时期 | 月数 | BaoStock 唯一代码 500 | 选用名单或候选达到 500 | BaoStock 或证据重建可用 | ETF 旁证 | unknown |
| --- | --- | --- | --- | --- | --- | --- |
| 2016-01 至 2018-10 | 34 | 34 | 34 | 34 | 0 | 0 |
| 2018-11 至 2024-12 | 74 | 73 | 73 | 69 | 2 | 3 |
| 全期 | 108 | 107 | 107 | 103 | 2 | 3 |

BaoStock 的 `updateDate` 是接口提供的名单更新日期，与调样实际生效日分列。仅返回 500 只不保证时点正确。2021-06 的原响应仍停在端午休市日 06-14 的旧名单，使用生效日前的完整 BaoStock 截面应用公开转载的 50 进、50 出代码，结果与 7 月接口截面一致，作为 B 级重建。7 月用于事后交叉核对。 [上交所 2021-06 调整日期](https://www.sse.com.cn/market/sseindex/diclosure/c/c_20210528_5476672.shtml) · [逐码转载附件](https://www.lcaj.net/jingji/080530688.html)

2021-12, 2022-12 各有 500 只 ETF 指数投资持仓作为旁证，官方资格仍标 `unknown`。其余 `unknown` 月份为 2021-09, 2023-01, 2023-02，保留候选名单和原始差异。2021-09 BaoStock 只有 499 只，课程独有的 601868 当月已上市，但不能单凭课程补齐。2022-12 调样后，接口到 2023-02 仍返回 2022-08-01 的版本。ETF 年末名单的有效日不能自动外推到翌年两个月。 [中国能建上市公告](https://www.sse.com.cn/disclosure/announcement/listing/ipo/c/c_20210927_83094980.shtml) · [2021 年 ETF 完整年报](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2022-03-31/510500_20220331_1_3qPQoPDA.pdf) · [2022 年 ETF 完整年报](https://pdf.dfcfw.com/pdf/H2_AN202303311584743601_1.pdf)

## 早期调样与独立核对

以实际返回的完整截面为起始证据。对每个早期调样，从生效日前一交易日的完整截面减去 BaoStock 显示的调出代码、加入调入代码，分别检查数量、通知生效日和已公开的示例代码。5 个早期事件通过上述核验。保留全部代码的变更来源为 BaoStock，公告只有数量及示例时，其他代码及两次调样之间的临时变更证据仍有限。2017-12-29 的 BaoStock 截面与上交所披露的南方中证 500 ETF 年报中 500 只指数投资持仓逐码完全一致，可独立验证一个早期完整截面。 [2016 年 6 月公告](https://www.sse.com.cn/market/sseindex/diclosure/c/c_20160530_4121664.shtml) · [2017 年 6 月公告](https://www.sse.com.cn/market/sseindex/diclosure/c/c_20170531_4318582.shtml) · [2017 年 ETF 完整年报](https://www.sse.com.cn/disclosure/fund/announcement/c/2018-03-28/510500_2017_n.pdf)

2019-01-18 中国外运上市替换外运发展有中证指数公司公告，BaoStock 在后续查询日才反映变更。2023-06、2023-12 和 2024-12 的完整调整附件用于逐码核对，2024-06 的转载仅提供调入代码。临时和规则日期匹配并列记录，七个交易日的观察窗内首次出现变化仅表示供应商可见，不作为实际生效日。以下覆盖 18 次规则定期调样及另外 13 个课程集合变化日，全期其他临时事件仍需逐份公告补证。 [调样规则](https://www.sse.com.cn/market/sseindex/calculation/c/10765000/files/fa4fc087fde8418d8f86265d511446bd.pdf) · [中国外运换股公告](https://www.sse.com.cn/market/sseindex/diclosure/c/c_20181217_4694178.shtml)

<details>
<summary>逐次调样检查</summary>

| 应核对日 | 证据 | 首个可见变更日 | 当日调入 | 当日调出 | 日期结果 |
| --- | --- | --- | --- | --- | --- |
| 2016-06-13 | A_official_examples_only | 2016-06-13 | 50 | 50 | same_day_vendor_change |
| 2016-12-12 | A_official_examples_only | 2016-12-12 | 50 | 50 | same_day_vendor_change |
| 2017-01-18 | U_unverified | 2017-01-23 | 0 | 0 | nonregular_observed_change_not_officially_verified |
| 2017-02-14 | U_unverified | 2017-02-20 | 0 | 0 | nonregular_observed_change_not_officially_verified |
| 2017-06-12 | A_official_examples_only | 2017-06-12 | 50 | 50 | same_day_vendor_change |
| 2017-07-03 | U_unverified | — | 0 | 0 | nonregular_observed_change_not_officially_verified |
| 2017-12-11 | A_official_examples_only | 2017-12-11 | 50 | 50 | same_day_vendor_change |
| 2018-06-11 | A_official_examples_only | 2018-06-11 | 50 | 50 | same_day_vendor_change |
| 2018-12-17 | B_notice_or_schedule_date_only | 2018-12-17 | 50 | 50 | same_day_vendor_change |
| 2019-01-18 | A_official_merger | 2019-01-21 | 0 | 0 | official_event_vendor_delayed |
| 2019-06-17 | B_notice_or_schedule_date_only | 2019-06-17 | 50 | 50 | same_day_vendor_change |
| 2019-12-16 | B_notice_or_schedule_date_only | 2019-12-16 | 50 | 50 | same_day_vendor_change |
| 2020-01-02 | U_unverified | — | 0 | 0 | nonregular_observed_change_not_officially_verified |
| 2020-06-15 | B_notice_or_schedule_date_only | 2020-06-15 | 50 | 50 | same_day_vendor_change |
| 2020-08-17 | U_unverified | 2020-08-17 | 1 | 1 | nonregular_observed_change_not_officially_verified |
| 2020-12-01 | U_unverified | — | 0 | 0 | nonregular_observed_change_not_officially_verified |
| 2020-12-14 | B_notice_or_schedule_date_only | 2020-12-14 | 50 | 50 | same_day_vendor_change |
| 2021-01-04 | U_unverified | — | 0 | 0 | nonregular_observed_change_not_officially_verified |
| 2021-03-15 | U_unverified | 2021-03-15 | 2 | 2 | nonregular_observed_change_not_officially_verified |
| 2021-06-15 | B_reproduced_full_delta | — | 0 | 0 | no_vendor_change_in_checked_window |
| 2021-09-06 | U_unverified | 2021-09-13 | 0 | 0 | nonregular_observed_change_not_officially_verified |
| 2021-09-13 | U_unverified | 2021-09-13 | 1 | 2 | nonregular_observed_change_not_officially_verified |
| 2021-09-28 | U_unverified | 2021-10-08 | 0 | 0 | nonregular_observed_change_not_officially_verified |
| 2021-12-13 | B_notice_or_schedule_date_only | — | 0 | 0 | no_vendor_change_in_checked_window |
| 2022-01-04 | U_unverified | — | 0 | 0 | nonregular_observed_change_not_officially_verified |
| 2022-06-13 | B_notice_or_schedule_date_only | 2022-06-13 | 50 | 50 | same_day_vendor_change |
| 2022-12-12 | B_notice_or_schedule_date_only | — | 0 | 0 | no_vendor_change_in_checked_window |
| 2023-06-12 | A_official_full_delta | 2023-06-12 | 50 | 50 | same_day_vendor_change |
| 2023-12-11 | A_official_full_delta | 2023-12-11 | 50 | 50 | same_day_vendor_change |
| 2024-06-17 | B_reproduced_incoming_only | 2024-06-17 | 50 | 50 | same_day_vendor_change |
| 2024-12-16 | A_official_full_delta | 2024-12-16 | 50 | 50 | same_day_vendor_change |

</details>

## 与课程月末行情的差异

在 102 个有课程日且可作为 B 级研究截面的月份中，累计 1,118 个名单内代码月缺课程行情，累计 0 个已见于课程却不在名单内的代码月。按两个集合的双向差集统计，不能据此认定停牌或采集问题。unknown 和 ETF 旁证月的数值仅供比对。2016-01 的查询日超出课程窗口，差异留空。每月及每次变动的证券代码和来源链接见审计表。月末间集合差异保留为观测结果，确切生效日须查对应变更公告。

| 月份 | 查询日 | BaoStock 数 | 选用/候选数 | 状态 | 课程数 | 仅名单有 | 仅课程有 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2016-01 | 2016-01-29 | 500 | 500 | vendor_snapshot |  |  |  |
| 2016-02 | 2016-02-29 | 500 | 500 | vendor_snapshot | 478 | 22 | 0 |
| 2016-03 | 2016-03-31 | 500 | 500 | vendor_snapshot | 478 | 22 | 0 |
| 2016-04 | 2016-04-29 | 500 | 500 | vendor_snapshot | 478 | 22 | 0 |
| 2016-05 | 2016-05-31 | 500 | 500 | vendor_snapshot | 478 | 22 | 0 |
| 2016-06 | 2016-06-30 | 500 | 500 | vendor_snapshot | 480 | 20 | 0 |
| 2016-07 | 2016-07-29 | 500 | 500 | vendor_snapshot | 480 | 20 | 0 |
| 2016-08 | 2016-08-31 | 500 | 500 | vendor_snapshot | 480 | 20 | 0 |
| 2016-09 | 2016-09-30 | 500 | 500 | vendor_snapshot | 480 | 20 | 0 |
| 2016-10 | 2016-10-31 | 500 | 500 | vendor_snapshot | 480 | 20 | 0 |
| 2016-11 | 2016-11-30 | 500 | 500 | vendor_snapshot | 480 | 20 | 0 |
| 2016-12 | 2016-12-30 | 500 | 500 | vendor_snapshot | 475 | 25 | 0 |
| 2017-01 | 2017-01-26 | 500 | 500 | vendor_snapshot | 476 | 24 | 0 |
| 2017-02 | 2017-02-28 | 500 | 500 | vendor_snapshot | 476 | 24 | 0 |
| 2017-03 | 2017-03-31 | 500 | 500 | vendor_snapshot | 476 | 24 | 0 |
| 2017-04 | 2017-04-28 | 500 | 500 | vendor_snapshot | 476 | 24 | 0 |
| 2017-05 | 2017-05-31 | 500 | 500 | vendor_snapshot | 476 | 24 | 0 |
| 2017-06 | 2017-06-30 | 500 | 500 | vendor_snapshot | 475 | 25 | 0 |
| 2017-07 | 2017-07-31 | 500 | 500 | vendor_snapshot | 473 | 27 | 0 |
| 2017-08 | 2017-08-31 | 500 | 500 | vendor_snapshot | 473 | 27 | 0 |
| 2017-09 | 2017-09-29 | 500 | 500 | vendor_snapshot | 473 | 27 | 0 |
| 2017-10 | 2017-10-31 | 500 | 500 | vendor_snapshot | 473 | 27 | 0 |
| 2017-11 | 2017-11-30 | 500 | 500 | vendor_snapshot | 473 | 27 | 0 |
| 2017-12 | 2017-12-29 | 500 | 500 | vendor_snapshot | 471 | 29 | 0 |
| 2018-01 | 2018-01-31 | 500 | 500 | vendor_snapshot | 471 | 29 | 0 |
| 2018-02 | 2018-02-28 | 500 | 500 | vendor_snapshot | 471 | 29 | 0 |
| 2018-03 | 2018-03-30 | 500 | 500 | vendor_snapshot | 471 | 29 | 0 |
| 2018-04 | 2018-04-27 | 500 | 500 | vendor_snapshot | 471 | 29 | 0 |
| 2018-05 | 2018-05-31 | 500 | 500 | vendor_snapshot | 471 | 29 | 0 |
| 2018-06 | 2018-06-29 | 500 | 500 | vendor_snapshot | 472 | 28 | 0 |
| 2018-07 | 2018-07-31 | 500 | 500 | vendor_snapshot | 472 | 28 | 0 |
| 2018-08 | 2018-08-31 | 500 | 500 | vendor_snapshot | 472 | 28 | 0 |
| 2018-09 | 2018-09-28 | 500 | 500 | vendor_snapshot | 472 | 28 | 0 |
| 2018-10 | 2018-10-31 | 500 | 500 | vendor_snapshot | 472 | 28 | 0 |
| 2018-11 | 2018-11-30 | 500 | 500 | vendor_snapshot | 472 | 28 | 0 |
| 2018-12 | 2018-12-28 | 500 | 500 | vendor_snapshot | 476 | 24 | 0 |
| 2019-01 | 2019-01-31 | 500 | 500 | vendor_snapshot | 477 | 23 | 0 |
| 2019-02 | 2019-02-28 | 500 | 500 | vendor_snapshot | 477 | 23 | 0 |
| 2019-03 | 2019-03-29 | 500 | 500 | vendor_snapshot | 477 | 23 | 0 |
| 2019-04 | 2019-04-30 | 500 | 500 | vendor_snapshot | 477 | 23 | 0 |
| 2019-05 | 2019-05-31 | 500 | 500 | vendor_snapshot | 477 | 23 | 0 |
| 2019-06 | 2019-06-28 | 500 | 500 | vendor_snapshot | 489 | 11 | 0 |
| 2019-07 | 2019-07-31 | 500 | 500 | vendor_snapshot | 489 | 11 | 0 |
| 2019-08 | 2019-08-30 | 500 | 500 | vendor_snapshot | 489 | 11 | 0 |
| 2019-09 | 2019-09-30 | 500 | 500 | vendor_snapshot | 489 | 11 | 0 |
| 2019-10 | 2019-10-31 | 500 | 500 | vendor_snapshot | 489 | 11 | 0 |
| 2019-11 | 2019-11-29 | 500 | 500 | vendor_snapshot | 489 | 11 | 0 |
| 2019-12 | 2019-12-31 | 500 | 500 | vendor_snapshot | 492 | 8 | 0 |
| 2020-01 | 2020-01-23 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2020-02 | 2020-02-28 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2020-03 | 2020-03-31 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2020-04 | 2020-04-30 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2020-05 | 2020-05-29 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2020-06 | 2020-06-30 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2020-07 | 2020-07-31 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2020-08 | 2020-08-31 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2020-09 | 2020-09-30 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2020-10 | 2020-10-30 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2020-11 | 2020-11-30 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2020-12 | 2020-12-31 | 500 | 500 | vendor_snapshot | 487 | 13 | 0 |
| 2021-01 | 2021-01-29 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2021-02 | 2021-02-26 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2021-03 | 2021-03-31 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2021-04 | 2021-04-30 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2021-05 | 2021-05-31 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2021-06 | 2021-06-30 | 500 | 500 | reconstructed_snapshot | 500 | 0 | 0 |
| 2021-07 | 2021-07-30 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2021-08 | 2021-08-31 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2021-09 | 2021-09-30 | 499 | 499 | unknown | 500 | 0 | 1 |
| 2021-10 | 2021-10-29 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2021-11 | 2021-11-30 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2021-12 | 2021-12-31 | 500 | 500 | etf_proxy | 500 | 0 | 0 |
| 2022-01 | 2022-01-28 | 500 | 500 | vendor_snapshot | 497 | 3 | 0 |
| 2022-02 | 2022-02-28 | 500 | 500 | vendor_snapshot | 497 | 3 | 0 |
| 2022-03 | 2022-03-31 | 500 | 500 | vendor_snapshot | 497 | 3 | 0 |
| 2022-04 | 2022-04-29 | 500 | 500 | vendor_snapshot | 497 | 3 | 0 |
| 2022-05 | 2022-05-31 | 500 | 500 | vendor_snapshot | 497 | 3 | 0 |
| 2022-06 | 2022-06-30 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2022-07 | 2022-07-29 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2022-08 | 2022-08-31 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2022-09 | 2022-09-30 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2022-10 | 2022-10-31 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2022-11 | 2022-11-30 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2022-12 | 2022-12-30 | 500 | 500 | etf_proxy | 499 | 1 | 0 |
| 2023-01 | 2023-01-31 | 500 | 500 | unknown | 499 | 51 | 50 |
| 2023-02 | 2023-02-28 | 500 | 500 | unknown | 499 | 51 | 50 |
| 2023-03 | 2023-03-31 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2023-04 | 2023-04-28 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2023-05 | 2023-05-31 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2023-06 | 2023-06-30 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2023-07 | 2023-07-31 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2023-08 | 2023-08-31 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2023-09 | 2023-09-28 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2023-10 | 2023-10-31 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2023-11 | 2023-11-30 | 500 | 500 | vendor_snapshot | 500 | 0 | 0 |
| 2023-12 | 2023-12-29 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2024-01 | 2024-01-31 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2024-02 | 2024-02-29 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2024-03 | 2024-03-29 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2024-04 | 2024-04-30 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2024-05 | 2024-05-31 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2024-06 | 2024-06-28 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2024-07 | 2024-07-31 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2024-08 | 2024-08-30 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2024-09 | 2024-09-30 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2024-10 | 2024-10-31 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2024-11 | 2024-11-29 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |
| 2024-12 | 2024-12-31 | 500 | 500 | vendor_snapshot | 499 | 1 | 0 |

## 字段、证据等级与复现

- A 级用于官方逐码附件、公告示例及公司换股事件。B 级表示结构完整且未发现当月冲突的 BaoStock 截面，含官方日期或独立 ETF 交叉验证，以及分别标明的公开名单重建。C 级是基金真实持仓旁证，不能单独确认指数资格。U 级表示冲突或数量、日期检查未通过。所有月份均保留供应商实际响应行数、去重数、重复数及日期版本。
- 名单表 `snapshot_status` 区分 BaoStock、调整重建、ETF 旁证和未知。C/U 的 `constituent_status` 为 `unknown`，需要研究样本时以审计表 `research_snapshot_usable` 筛出经本轮核验的供应商口径。B 级按供应商口径具备研究可用性，未获得指数公司全期逐日认证。代码保留六位，`security_name` 是供应商展示名，可能跨期更名，名称不参与匹配。
- 原始归档 SHA-256 为 `2bac5bed1488cb181b7b29757f02199d6d2d4f91171847817fdd1214d222e0ea`。在期中考试目录运行 `python3 -B code/fetch_constituents.py`，需要安装免费包 `baostock` 与 `pandas`。可用 `--cache /路径/bao.json` 保留接口原始响应，再加 `--offline` 重放。官方和基金名单证据固定在本脚本及第二轮核验脚本中。临时原始响应仅在验证时使用，正文数据与审计表包含逐条获取日期及来源。

[历史名单](historical_constituents.csv) · [月度与事件审计](constituent_source_audit.csv) · [获取脚本](../code/fetch_constituents.py)
