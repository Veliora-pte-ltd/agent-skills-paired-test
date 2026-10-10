# Subscription follow-up: release tasks

## Claude Pro subscription (cost = Claude Code estimate)

| Model | Condition | Passed | Pass rate (95% Wilson) | Mean cost US$ | Wall median s |
|---|---|---|---|---|---|
| claude-opus-5-5 | none | 6/24 | 25% (12-45%) | 0.1751 | 22.4 |
| claude-opus-5-5 | compact | 24/24 | 100% (86-100%) | 0.1311 | 12.7 |

## Main experiment, API (cost = published prices)

| Model | Condition | Passed | Pass rate (95% Wilson) | Mean cost US$ | Wall median s |
|---|---|---|---|---|---|
| claude-haiku-5-5 | none | 5/30 | 17% (7-34%) | 0.0051 | 20.8 |
| claude-haiku-5-5 | compact | 29/30 | 97% (83-99%) | 0.0030 | 10.2 |
| claude-opus-5-5 | none | 3/11 | 27% (10-57%) | 0.1118 | 34.5 |
| claude-opus-5-5 | compact | 12/12 | 100% (76-100%) | 0.0795 | 21.5 |
| claude-sonnet-5-5 | none | 10/30 | 33% (19-51%) | 0.0431 | 14.6 |
| claude-sonnet-5-5 | compact | 30/30 | 100% (89-100%) | 0.0365 | 10.0 |

- claude-opus-5-5: compact vs none, mean per-task difference +75 points (95% bootstrap +42 to +100), tasks better 5/6, p_perm 0.060; cost estimate total $7.35

Aborted runs: 1; events: []
