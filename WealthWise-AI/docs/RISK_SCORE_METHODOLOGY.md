# WealthWise AI risk indicator methodology

## Purpose

The portfolio risk indicator is an explainable product heuristic. It is not a regulated rating, validated investment-risk model, probability of loss, investment recommendation, or suitability assessment.

## Score range and aggregation

Each scored dimension is bounded from 0 to 100. A higher value means greater pressure against the configured rule or weaker source-data quality. The overall score is the unweighted arithmetic mean of dimensions that have sufficient inputs. Unavailable dimensions are excluded and shown as unavailable; they are never silently treated as zero.

The API returns the scoring version, each dimension's inputs, the rule text, coverage, aggregation method and limitations.

## Dimension rules

- Concentration: calculate utilization of the configured single-holding and top-three limits. Use the higher utilization ratio. Score 50 at the configured limit and 100 at or above twice the limit, with a 0–100 clamp.
- Equity allocation: when a maximum equity percentage is explicitly configured, score 50 at that limit and 100 at or above twice the limit, with a 0–100 clamp. Without a configured limit, do not score this dimension.
- Reported liquidity: score the proportional shortfall below the configured minimum. Score zero at or above the minimum and 100 at zero reported liquid allocation.
- Data quality: subtract the mean of document completeness and historical coverage percentages from 100.
- Sector concentration: only when an explicit maximum sector percentage is configured, score 50 at that limit and 100 at or above twice the limit. Grouped identified sector values are divided by total portfolio value; missing sector values reduce the reported coverage.
- Issuer exposure: show identified issuer coverage and largest identified issuer, but do not score it until issuer identifiers, taxonomy and thresholds are validated.
- Historical volatility: expose the maximum available per-observation volatility as context, but do not include it in the aggregate. Observation intervals are not guaranteed to be uniform, and the metric is not annualized; comparing it directly to a portfolio-wide threshold would be misleading.

## Known exclusions

The indicator does not automatically score sector concentration unless a sector limit is explicitly configured. Issuer exposure is informational only. Instrument overlap, duration, credit quality, market beta, currency exposure, cash-flow-adjusted returns, and liquidity-at-sale are not scored; these require reliable underlying data and separately documented rules.

## Interpretation and governance

- Thresholds are configurable product assumptions, not universal standards.
- User profile thresholds affect the inputs and therefore can change the result.
- Missing evidence reduces scoring coverage; it must not be interpreted as low risk.
- Historical NAV performance does not predict future performance.
- Thresholds and score rules require domain validation, back-testing and compliance review before use in a customer-facing regulated investment context.
