# Independent review of the tennis scoring kernel

Reviewed 2026-09-08. No scoring defect was found in `beating/tennis_kernel.py`. The independent check simulated 200,000 synthetic matches and agreed with the exact kernel on the four prespecified parameter pairs. This validates the implemented scoring assumptions; it supplies no historical betting result or evidence of market edge.

## Rules and mathematical inspection

The modeled contract is best-of-three singles, advantage games, and a seven-point, win-by-two tiebreak at 6-6 in every set. Standard games alternate service. The first tiebreak server serves one point, then service changes in blocks of two points. That first tiebreak server receives in the next set. These are the relevant standard-game, tiebreak and service-order provisions in ITF Rules 5–7 and 14. The source also describes alternative formats, which this kernel does not model. [Official 2026 Rules of Tennis](https://www.itftennis.com/media/7221/2026-rules-of-tennis-english.pdf)

Code inspection confirmed the following:

- For service-point probability `p` and `q = 1-p`, the advantage-game formula correctly adds the three ways to win before deuce, `p^4 * (1 + 4q + 10q^2)`, to the probability of reaching deuce, `20p^3q^3`, multiplied by its win probability, `p^2 / (p^2 + q^2)`. The production inverse uses a bracketed root on `[0,1]` and returns the exact endpoint for hold probabilities zero and one.
- The tiebreak dynamic program accounts for every terminal score before 6-6. At 6-6 and later ties, each next pair of points contains one serve from each player. A player-one two-point sweep has probability `p1*(1-p2)` and a player-two sweep `(1-p1)*p2`; splitting returns to a tie. Their ratio gives the infinite-tail absorption probability. This requires constant independent service-point probabilities. Degenerate nonabsorbing cases are rejected.
- The set law absorbs ordinary set wins at six or seven games, sends precisely the 6-6 state to a tiebreak, and records that tiebreak as the thirteenth game. At 6-6, the next server is the set's initial server, because twelve ordinary service games have elapsed.
- The match state retains both sets won and the next server. An even-length set preserves the initial server for the next set; an odd-length set switches it. Consequently a 7-6 set switches the next-set server, as required. The production code averages the initial server only once and carries subsequent service order through its state transitions.
- Winner-specific convolutions terminate when either player wins two sets. The total-game distribution therefore has support from 12 through 39. The cheap match-probability path aggregates the same set transitions by parity; it does not introduce an independent fresh initial-server draw between sets.

These arguments were checked against the implementation and its existing deterministic tests. They describe mathematical correctness under the stated assumptions, not the validity of the latent hold-rate estimation from score history.

## Independent synthetic experiment

The reusable [validation script](../tools/validate_tennis_kernel.py) uses a separate scoring implementation. It obtains service-point probabilities by solving an 18-state absorbing Markov system with Gaussian elimination, then bisecting the desired game hold rate. It does not use the production closed-form game probability or its root solver to generate simulations.

Every ordinary game is simulated point by point until a player has at least four points and a two-point lead. Every tiebreak is likewise simulated point by point, including scores beyond 6-6, with literal one-then-two service turns. Each match randomizes its first server once, carries ordinary service order, and explicitly makes the first tiebreak server receive in the next set. No game, set, match or total-game outcome is sampled from a production-kernel probability.

Before execution, the design fixed four hold-rate pairs `(0.50,0.50)`, `(0.72,0.86)`, `(0.96,0.60)`, `(0.995,0.995)`; 50,000 matches per pair; seeds `20260908` through `20260911`; and a diagnostic limit of five Monte Carlo standard errors. This covers equal players, unequal players, strongly unequal players and near-universal holds. No case or seed was selected from its result. All comparisons are retained in the [machine-readable report](../reports/tennis-kernel-independent-check.json), including full simulated and exact total-game distributions.

The official artifact was regenerated under the repository's verified Python 3.12 environment after an initial check under Python 3.14. The report records Python, NumPy and SciPy versions, interpreter path, and both source-file hashes. Repeating for a changed numerical environment was the reason for the rerun; the cases, seeds, sample size and diagnostic threshold were unchanged.

| Hold probabilities | Player-one match probability, exact / simulated | Over 21.5 probability, exact / simulated | Mean games, exact / simulated | Largest absolute standardized difference across four metrics |
| --- | --- | --- | --- | --- |
| 0.50 / 0.50 | 0.500000 / 0.501140 | 0.614780 / 0.618160 | 24.155273 / 24.189280 | 1.553 |
| 0.72 / 0.86 | 0.167140 / 0.165280 | 0.553654 / 0.557060 | 23.689505 / 23.733660 | 1.685 |
| 0.96 / 0.60 | 0.996934 / 0.996880 | 0.130939 / 0.132960 | 18.232031 / 18.249620 | 1.340 |
| 0.995 / 0.995 | 0.500000 / 0.503980 | 0.998373 / 0.998480 | 32.064227 / 32.108320 | 1.780 |

The fourth compared metric is first-set tiebreak probability, corresponding to the kernel's `set_tiebreak_p`; it is not the probability of any tiebreak during a match. Every one of the 16 comparisons is within 1.780 standard errors of the exact prediction. The report provides both the standard error under the exact model and the empirical simulation standard error. These quantify Monte Carlo noise, not uncertainty in a real player's hold probability.

The run simulated 29,976,191 points. It checked 273,053 transitions into another set, including 97,035 following a tiebreak, without a service-order assertion failure. The largest difference between independent and production service-point inversions was below `7e-15`. Production kernel code was not changed for this audit.

## Reproduction and limits

```sh
/tmp/beating-venv312/bin/python tools/validate_tennis_kernel.py
```

The fixed simulation completed well within five minutes. A failed diagnostic exits nonzero and still writes every result; it must be investigated rather than resolved by changing the seed. Hashes tie the saved result to the checked kernel and validation script.

Finite simulation cannot prove all parameter cases or detect every sufficiently small implementation error. The analytical inspection and existing deterministic tests provide complementary evidence, especially for server carryover. This audit does not validate player-data chronology, historical format classification, retirements or bookmaker settlement, the inversion from Elo/tiebreak history to hold rates, or the constant-probability assumption. Those require their own data checks and out-of-sample evidence.
