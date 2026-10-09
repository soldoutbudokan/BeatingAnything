# McCaffrey: repeated +483 to +854 with a redundant leg

On October 8, 2026, theScore Bet quoted the following Christian McCaffrey SGP for SF at Seattle on October 11:

| Construction | Offered odds | Power EV lower bound | Additive EV lower bound |
|---|---:|---:|---:|
| 90+ rushing + receiving yards, under 54.5 rushing yards, 40+ receiving yards | +483 | −31.08% | −35.14% |
| Same three legs plus over 34.5 receiving yards | **+854** | **+12.77%** | **+6.13%** |

The extra over-34.5 receiving leg cannot change the winning event: 40+ receiving already implies it. The observed sequence was **+854, +483, +854, +483, +854**. The latest full repeat was recorded at 18:55–18:57 ET, around and after the refreshed FanDuel partition. The payout multiplier increased by 63.64%.

This is a three-leg base event with a fourth redundant leg. The 40+ receiving condition is **not** redundant in the two-leg 90+ combined / under-54.5 rushing event. It remains part of the base throughout this comparison.

## Why the FanDuel comparison is a lower bound

FanDuel's target was combined over 91.5 and rushing under 51.5. Integer final totals imply:

- Combined yards are at least 92, exceeding Score's 90+ requirement.
- Rushing yards are at most 51, satisfying Score's under-54.5 requirement.
- Receiving yards are at least 92 − 51 = 41, satisfying Score's 40+ receiving requirement and the redundant over-34.5 leg.

Every FanDuel target winner is therefore a Score target winner, under common yardage definitions and normal completed-game settlement. The FanDuel target probability gives a conservative probability bound for the entire Score SGP; no independence assumption is used.

## Reference and calculation

FanDuel's complete partition, refreshed 18:54–18:55 ET, was:

| Combined 91.5 / rushing 51.5 | American odds |
|---|---:|
| Over / over | +127 |
| Over / under (target) | +515 |
| Under / over | +550 |
| Under / under | +123 |

Let q be reciprocal decimal odds. Power chooses k such that the four q^k probabilities sum to one. Additive subtracts one quarter of the partition overround from each q. The target probabilities are 11.82086534% under power and 11.12498991% under additive.

At +854, decimal odds are 9.54. EV = 9.54 × probability − 1, producing the lower bounds above. Break-even offered prices using those probability bounds are +745.96 power and +798.88 additive. These are model-dependent bounds from observed quotes, not proof that either devig model equals the true probability or that the quote remains available.

## Reproduce

The sanitized numerical inputs and timestamped observations are in [prices-and-ev.json](prices-and-ev.json). Run `python3 recompute_ev.py` to independently reproduce both devig methods and verify the set-inclusion bound.
