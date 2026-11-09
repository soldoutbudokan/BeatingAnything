# FanDuel board against Pinnacle's no-vig line, November 9, 2026

`tools/screen_fanduel_vs_pinnacle.py` prices every FanDuel selection that Pinnacle quotes two-sided at the same line. It reads all FanDuel event-page tabs, maps "X+" ladders to Over X−0.5, and devigs the Pinnacle pair three ways (multiplicative, additive, power). The flag uses the worst of the three, which removes the long-shot goal-scorer rows that multiplicative devig alone would flag at +10% or more.

Two cycles at 19:13–19:15 UTC priced 3,457 FanDuel selections across NFL, NBA, NHL, NCAAF, NCAAB and soccer. Median EV is −5.3%, FanDuel's usual hold. **21 selections clear +2% worst-case EV.** They are listed in [flags.jsonl](flags.jsonl) and below.

| Start (UTC) | Game | Market | FanDuel bet | FD price | Pinnacle same line | Worst-case EV | EV at PointsBet fair |
|---|---|---|---|---:|---|---:|---:|
| 11-10 00:10 | Cleveland Cavaliers @ Charlotte Hornets | nba total Q2 | Over 52.5 | 2.12 (+112) | 1.9524 / 1.885 (limit 500) | +4.0% | — |
| 11-10 00:10 | Cleveland Cavaliers @ Charlotte Hornets | nba total 1H | Over 103.5 | 1.7937 (−126) | 1.6623 / 2.29 (limit 1000) | +3.9% | — |
| 11-10 00:10 | Cleveland Cavaliers @ Charlotte Hornets | nba total Q2 | Over 51.5 | 1.9259 (−108) | 1.7752 / 2.06 (limit 500) | +3.4% | — |
| 11-10 00:10 | Cleveland Cavaliers @ Charlotte Hornets | nba total 1H | Over 104.5 | 1.9091 (−110) | 1.7812 / 2.1 (limit 1000) | +3.3% | -0.7% |
| 11-10 00:10 | Cleveland Cavaliers @ Charlotte Hornets | nba total 1H | Over 105.5 | 2.04 (+104) | 1.9174 / 1.9524 (limit 1000) | +2.9% | — |
| 11-10 00:10 | Cleveland Cavaliers @ Charlotte Hornets | nba total Q2 | Over 53.5 | 2.32 (+132) | 2.14 / 1.7194 (limit 500) | +2.4% | — |
| 11-10 01:00 | Louisiana Tech @ LSU | ncaab spread 1H | Louisiana Tech +17.5 | 1.8929 (−112) | 1.7692 / 2.07 (limit 250) | +2.1% | — |
| 11-10 01:10 | New York Rangers @ Edmonton Oilers | nhl prop | Dylan Garand Over 24.5 saves | 2.0 (+100) | 1.8 / 1.9524 (limit 250) | +4.1% | — |
| 11-10 02:00 | Alabama A&M @ DePaul | ncaab spread | Alabama A&M +24.5 | 1.9091 (−110) | 1.7634 / 2.1 (limit 500) | +3.8% | — |
| 11-10 02:00 | Appalachian State @ Auburn | ncaab spread 1H | Auburn -12.5 | 1.8929 (−112) | 1.7692 / 2.07 (limit 250) | +2.1% | — |
| 11-10 02:10 | San Antonio Spurs @ Phoenix Suns | nba team_total Q1 | San Antonio Spurs Under 30.5 | 2.02 (+102) | 1.8929 / 1.9434 (limit 1000) | +2.3% | — |
| 11-10 02:30 | Eastern Washington @ Oregon State | ncaab spread 1H | Oregon State -9.5 | 1.8929 (−112) | 1.7576 / 2.09 (limit 250) | +2.8% | — |
| 11-10 02:40 | Philadelphia Flyers @ Vancouver Canucks | nhl prop | Jamie Drysdale Over 0.5 assists | 2.76 (+176) | 2.4 / 1.5319 (limit 250) | +4.2% | +8.7% |
| 11-10 02:40 | Philadelphia Flyers @ Vancouver Canucks | nhl prop | Tyson Foerster Over 2.5 shots on goal | 2.82 (+182) | 2.48 / 1.5025 (limit 250) | +2.7% | — |
| 11-10 03:10 | New York Islanders @ San Jose Sharks | nhl prop | Mason Marchment Over 0.5 points | 2.04 (+104) | 1.8 / 1.9434 (limit 250) | +5.9% | — |
| 11-10 03:10 | New Orleans Pelicans @ Golden State Warriors | nba total Q1 | Under 58.5 | 2.3 (+130) | 2.1 / 1.7463 (limit 500) | +3.6% | — |
| 11-10 03:10 | New Orleans Pelicans @ Golden State Warriors | nba total Q1 | Under 59.5 | 2.08 (+108) | 1.9259 / 1.9091 (limit 500) | +3.5% | — |
| 11-10 03:10 | New York Islanders @ San Jose Sharks | nhl prop | Tyler Toffoli Over 0.5 points | 2.32 (+132) | 2.05 / 1.6897 (limit 250) | +3.4% | — |
| 11-10 03:10 | New Orleans Pelicans @ Golden State Warriors | nba total Q1 | Under 60.5 | 1.9091 (−110) | 1.7692 / 2.08 (limit 500) | +3.2% | — |
| 11-14 17:00 | Northwestern @ Ohio State | ncaaf team_total | Northwestern Over 17.5 | 2.18 (+118) | 2.01 / 1.8475 (limit 500) | +4.1% | — |
| 11-14 17:00 | Wake Forest @ SMU | ncaaf team_total | SMU Under 30.5 | 1.9804 (−102) | 1.8475 / 1.9709 (limit 500) | +2.2% | -3.0% |

## What the flags are

- **Period totals priced a point off Pinnacle (11 rows, 3 games).** In Cavaliers–Hornets the two books agree on the game total (214.5–215.5) and the first-quarter total (53), but FanDuel's second-quarter pivot is about 51.3 against Pinnacle's 52.5, and its first-half line is 104.5 at −110 both ways against Pinnacle's 105.5. PointsBet prices Over 104.5 at 1.80, on Pinnacle's side. Pelicans–Warriors first-quarter Unders show the same one-point gap in the other direction. Each book is consistent with itself, so this is a disagreement between period models, not a typo.
- **NHL props (5 rows).** Marchment and Toffoli points, Drysdale assists, Foerster shots, Garand saves. Pinnacle's limit on these is $250, so its price carries less information than on a main line. PointsBet agrees on the one row it quotes (Drysdale).
- **College lines a point off (5 rows).** Alabama A&M +24.5 at −110 where Pinnacle's ladder puts the main spread near 23.5; three first-half spreads; two NCAAF team totals. PointsBet disagrees on the SMU row.

Three minutes after capture FanDuel had already cut the three Warriors Unders (2.30 → 2.26, 2.08 → 2.06, 1.909 → 1.877) and Toffoli (2.32 → 2.26), toward Pinnacle.

## What this does and does not show

It shows 21 FanDuel prices that beat a sharper book's same-line fair price by 2–6% at one instant. It does not show that Pinnacle is right. Its period and prop markets take $250–$1,000, far below its main lines, and one snapshot cannot separate a slow FanDuel number from a soft Pinnacle one.

The test is closing-line value: re-price each flag's entry price against Pinnacle's fair line just before start.

```bash
FD_REGION=nj PB_REGION=au python tools/screen_fanduel_vs_pinnacle.py --leagues nba,nhl,ncaab --no-pointsbet \
    --grade reports/fanduel-pinnacle-screen-2026-11-09/flags.jsonl --grade-max-hours 1 \
    --grade-out reports/fanduel-pinnacle-screen-2026-11-09/clv.jsonl
```

If Pinnacle moves toward FanDuel's entry number, the flag was noise in a thin reference. If the mean entry price still beats the closing fair price over a few hundred flags, the screen is an edge. Results from the first night go in `clv.jsonl`.

## Limits

- Prices are FanDuel New Jersey read from the cloud. The earlier audit found them 99.3% identical to Ontario; confirm each number on the Ontario board before staking.
- Pinnacle and FanDuel were read within the same 90-second cycle, not the same second.
- Same-game rows are correlated: six Cavaliers–Hornets flags are one opinion, not six.
- theScore Bet was not reachable from this cloud session. The October 8 redundant-leg SGP check still needs the Ontario browser session.
- No wager was placed and no schedule installed.
