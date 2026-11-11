# Method (synthetic example)

This page is rendered by `Sheets.loadMarkdown()` from a plain `method.md` file. The models will ship their own; this one exists to exercise the renderer. Jump to [the simulator](#2-game-simulator) or [the ratings table](#ratings-at-a-glance).

## 1. Player ratings

Each player gets a **bottom-up rating** built from ball-level (or possession-level) outcomes, shrunk towards a role prior:

1. Count outcomes per player, per phase.
2. Fit a hierarchical model with *partial pooling*:
   - players with few balls are pulled toward their role mean;
   - venue and opposition effects are estimated jointly.
3. Convert to runs (or points) above replacement.

> Ratings are point estimates with an uncertainty column (`Uncert`). Treat differences smaller than one standard error as noise.

### Ratings at a glance

| Tier | Value range | Players | Share of minutes |
|:-----|------------:|--------:|-----------------:|
| Elite | +3.0 and up | 41 | 12.4% |
| Starter | +0.5 to +3.0 | 388 | 51.0% |
| Rotation | −1.0 to +0.5 | 1,120 | 31.9% |
| Fringe | below −1.0 | 1,451 | 4.7% |

## 2. Game simulator

The simulator plays each game ball by ball. For every delivery it draws an outcome from the batter-vs-bowler matchup probabilities, adjusted for phase and venue:

```text
p(outcome | batter, bowler, phase, venue)
  = softmax(β_bat + β_bowl + β_phase + β_venue)
```

Totals, wickets and player lines come from the simulated games directly, so every market is priced from the same joint distribution. Fair odds strip the bookmaker margin with a proportional de-vig; see `Sheets.odds.devig`.

### Known limitations

- Weather is not modelled; rain-shortened games are excluded from training.
- Lineups are taken as announced. Late changes are __not__ reflected until the next build.
- Sources: ball-by-ball data from public archives; see the [repository](https://github.com/) for details.

---

*Last reviewed with the synthetic demo build.*
