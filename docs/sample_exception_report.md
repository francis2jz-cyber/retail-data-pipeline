# Pipeline Exception Report

- **Batch:** `20261006T171901_f21050`
- **Generated (UTC):** 2026-10-06 17:19:01
- **Database:** sqlite

## 1. Record counts

| source    |   ingested |   valid |   rejected |   loaded |
|:----------|-----------:|--------:|-----------:|---------:|
| customers |        202 |     192 |         10 |      192 |
| products  |         41 |      37 |          4 |       37 |
| orders    |       1507 |    1485 |         22 |     1485 |
| payments  |       1310 |    1301 |          9 |     1301 |

## 2. Financial control totals

| metric                           |      value |
|:---------------------------------|-----------:|
| expected revenue billable orders | 698,965.08 |
| within settlement window         |   2,377.42 |
| expected revenue due             | 696,587.66 |
| settled payments on valid orders | 696,533.32 |
| settled payments unmatched       |   4,348.53 |
| net difference                   |     -54.34 |

## 3. Data quality: validation errors by rule

A record can break more than one rule, so error counts can exceed rejected record counts.

| source    | rule              | column_name    |   errors |
|:----------|:------------------|:---------------|---------:|
| customers | invalid_email     | email          |        3 |
| customers | not_null          | email          |        3 |
| customers | duplicate_key     | customer_id    |        2 |
| customers | invalid_date      | signup_date    |        1 |
| customers | not_null          | last_name      |        1 |
| orders    | invalid_number    | quantity       |        6 |
| orders    | unknown_reference | customer_id    |        5 |
| orders    | unknown_reference | product_id     |        4 |
| orders    | duplicate_key     | order_id       |        2 |
| orders    | invalid_date      | order_date     |        2 |
| orders    | invalid_value     | status         |        2 |
| orders    | not_null          | order_date     |        1 |
| payments  | invalid_date      | paid_at        |        2 |
| payments  | invalid_number    | amount         |        2 |
| payments  | invalid_value     | currency       |        2 |
| payments  | not_null          | amount         |        2 |
| payments  | duplicate_key     | payment_id     |        1 |
| products  | duplicate_key     | product_id     |        1 |
| products  | invalid_number    | stock_quantity |        1 |
| products  | invalid_number    | unit_price     |        1 |
| products  | not_null          | category       |        1 |

## 4. Reconciliation exceptions by type

| exception_type             | severity   |   count |   total_abs_difference |
|:---------------------------|:-----------|--------:|-----------------------:|
| PRICE_MISMATCH             | low        |      15 |                 271.16 |
| MISSING_PAYMENT            | high       |      12 |               6,042.43 |
| AMOUNT_MISMATCH            | high       |      10 |                 136.05 |
| PAYMENT_FOR_REJECTED_ORDER | medium     |       8 |               3,384.23 |
| ORPHAN_PAYMENT             | high       |       8 |                 964.30 |
| DUPLICATE_PAYMENT          | high       |       6 |               4,539.29 |
| PAYMENT_ON_CANCELLED_ORDER | medium     |       3 |               1,384.69 |

## 5. High-severity exceptions (first 25)

| exception_type    | order_id   | payment_id          |   expected_amount |   actual_amount |   difference | details                                                            |
|:------------------|:-----------|:--------------------|------------------:|----------------:|-------------:|:-------------------------------------------------------------------|
| AMOUNT_MISMATCH   | O00042     | PAY000033           |            144.24 |          159.57 |        15.33 | payment amount differs from order amount                           |
| AMOUNT_MISMATCH   | O00276     | PAY000231           |            452.66 |          467.59 |        14.93 | payment amount differs from order amount                           |
| AMOUNT_MISMATCH   | O00317     | PAY000262           |            620.10 |          637.81 |        17.71 | payment amount differs from order amount                           |
| AMOUNT_MISMATCH   | O00470     | PAY000387           |            240.40 |          249.93 |         9.53 | payment amount differs from order amount                           |
| AMOUNT_MISMATCH   | O00578     | PAY000481           |             75.44 |           54.93 |       -20.51 | payment amount differs from order amount                           |
| AMOUNT_MISMATCH   | O00623     | PAY000523           |            719.96 |          728.15 |         8.19 | payment amount differs from order amount                           |
| AMOUNT_MISMATCH   | O00844     | PAY000719           |          1,072.05 |        1,063.28 |        -8.77 | payment amount differs from order amount                           |
| AMOUNT_MISMATCH   | O00928     | PAY000795           |            154.69 |          173.30 |        18.61 | payment amount differs from order amount                           |
| AMOUNT_MISMATCH   | O01034     | PAY000894           |            577.40 |          593.18 |        15.78 | payment amount differs from order amount                           |
| AMOUNT_MISMATCH   | O01096     | PAY000951           |            289.35 |          282.66 |        -6.69 | payment amount differs from order amount                           |
| DUPLICATE_PAYMENT | O00035     | PAY000026,PAY000027 |          1,048.28 |        2,096.56 |     1,048.28 | 2 successful payments for one order                                |
| DUPLICATE_PAYMENT | O00581     | PAY000484,PAY000485 |          1,756.16 |        3,512.32 |     1,756.16 | 2 successful payments for one order                                |
| DUPLICATE_PAYMENT | O00599     | PAY000501,PAY000502 |            719.96 |        1,439.92 |       719.96 | 2 successful payments for one order                                |
| DUPLICATE_PAYMENT | O00832     | PAY000709,PAY000710 |            275.72 |          551.44 |       275.72 | 2 successful payments for one order                                |
| DUPLICATE_PAYMENT | O01012     | PAY000873,PAY000874 |            445.15 |          890.30 |       445.15 | 2 successful payments for one order                                |
| DUPLICATE_PAYMENT | O01186     | PAY001029,PAY001030 |            294.02 |          588.04 |       294.02 | 2 successful payments for one order                                |
| MISSING_PAYMENT   | O00123     |                     |            458.10 |            0.00 |      -458.10 | shipped order has no successful payment 213 days after the order   |
| MISSING_PAYMENT   | O00281     |                     |             37.72 |            0.00 |       -37.72 | shipped order has no successful payment 169 days after the order   |
| MISSING_PAYMENT   | O00447     |                     |          1,072.05 |            0.00 |    -1,072.05 | shipped order has no successful payment 259 days after the order   |
| MISSING_PAYMENT   | O00511     |                     |            231.48 |            0.00 |      -231.48 | completed order has no successful payment 26 days after the order  |
| MISSING_PAYMENT   | O00558     |                     |            506.48 |            0.00 |      -506.48 | completed order has no successful payment 154 days after the order |
| MISSING_PAYMENT   | O00834     |                     |            144.24 |            0.00 |      -144.24 | completed order has no successful payment 220 days after the order |
| MISSING_PAYMENT   | O00845     |                     |            425.46 |            0.00 |      -425.46 | completed order has no successful payment 266 days after the order |
| MISSING_PAYMENT   | O01008     |                     |          1,310.35 |            0.00 |    -1,310.35 | completed order has no successful payment 218 days after the order |
| MISSING_PAYMENT   | O01059     |                     |            509.67 |            0.00 |      -509.67 | completed order has no successful payment 67 days after the order  |

Full detail: `reconciliation_exceptions_20261006T171901_f21050.csv` and `validation_errors_20261006T171901_f21050.csv`.
