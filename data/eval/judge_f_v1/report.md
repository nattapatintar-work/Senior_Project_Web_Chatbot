# SEASONING_WEIGHT pairwise judge: report

- mode: **REAL**; judge model: `claude-sonnet-5` (UNVERIFIED id)
- runs per pair: 3; candidate weights [0.0, 0.15, 0.5] vs reference 0.3
- calls recorded: 124; status counts: {'ok': 123, 'parse_error': 1}; identical pairs skipped (never judged): 6
- tokens used (from the stored usage fields): input 240694, output 33986
- parameter adaptations during the run: ['temperature switched off after an HTTP 400']

## Judge reliability (negative controls)

The real top-3 beat an unrelated query's top-3 in 16 of 16 valid control calls (accuracy 1.000; ties 0, foreign list won 0). Trust threshold: 0.875 (a definition we chose).

The judge passes the control check (this does not make it a measure of user satisfaction).

## Win rate of each candidate weight versus 0.3

Positions are un-swapped before counting. Win = 1, tie = 0.5, loss = 0, over judged calls with a valid answer. Identical top-3 pairs are not judged and are not in the win rate.

| candidate weight | judged pairs | identical pairs | valid calls | wins | ties | losses | win rate vs 0.3 |
|---|---|---|---|---|---|---|---|
| 0.0 | 8 | 0 | 48 | 7 | 0 | 41 | 0.146 |
| 0.15 | 5 | 3 | 30 | 9 | 0 | 21 | 0.300 |
| 0.5 | 5 | 3 | 29 | 9 | 11 | 9 | 0.500 |
| all candidates | | | 107 | 25 | 11 | 71 | 0.285 |

## Bias and consistency

- position bias, share of answers "A": comparisons 0.486 (107 calls), controls 0.500 (16 calls), all 0.488. Values far from 0.5 suggest the judge favors a position.
- order consistency (same pair and run, A/B swapped, same list preferred): 0.755 over 53 pairs
- self-consistency across runs (all 3 runs agree in a (pair, order) cell): 0.857 over 35 complete cells (of 36 cells)

## Per query

| query | 0.0: top-3 vs 0.3 / judge | 0.15: top-3 vs 0.3 / judge | 0.5: top-3 vs 0.3 / judge |
|---|---|---|---|
| F1 | different / 0W/0T/6L of 6 valid calls | identical / not judged (identical) | reordered / 0W/5T/1L of 6 valid calls |
| F2 | different / 0W/0T/6L of 6 valid calls | different / 0W/0T/6L of 6 valid calls | different / 3W/0T/2L of 5 valid calls |
| F3 | different / 0W/0T/6L of 6 valid calls | identical / not judged (identical) | different / 0W/6T/0L of 6 valid calls |
| F4 | different / 2W/0T/4L of 6 valid calls | reordered / 0W/0T/6L of 6 valid calls | different / 6W/0T/0L of 6 valid calls |
| F5 | different / 0W/0T/6L of 6 valid calls | different / 0W/0T/6L of 6 valid calls | identical / not judged (identical) |
| F6 | different / 1W/0T/5L of 6 valid calls | reordered / 6W/0T/0L of 6 valid calls | different / 0W/0T/6L of 6 valid calls |
| F7 | different / 1W/0T/5L of 6 valid calls | different / 3W/0T/3L of 6 valid calls | identical / not judged (identical) |
| F8 | different / 3W/0T/3L of 6 valid calls | identical / not judged (identical) | identical / not judged (identical) |

## Limitations

- Only 8 queries (group F).
- The F pairs were chosen so that the ranking changes with the seasonings, so the share of changed rankings says nothing about real use.
- The judge measures agreement with the three stated criteria, not user satisfaction.
- There are no human labels to calibrate the judge against.
- The judge is a Claude model and the criteria were written by us.
- The judge model id is UNVERIFIED against the API (claude-sonnet-5 unless JUDGE_MODEL was set).
- Win rates are over a small number of calls and carry no confidence interval.
