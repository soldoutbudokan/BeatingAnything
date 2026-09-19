"""Fixed, chronological first-score models from the September 19 protocol."""
from collections import Counter, defaultdict, deque
import math

POSSESSION_SCORE_RATE = 4941 / 7520
MODELS = ("tip", "tip_role")


def elo_probability(home, away):
    return 1 / (1 + 10 ** ((away - home) / 400))


class FirstBasketState:
    def __init__(self):
        self.ratings = defaultdict(lambda: 1500.0)
        self.jump_appearances = Counter()
        self.team_jumps = defaultdict(lambda: deque(maxlen=10))
        self.starts = defaultdict(lambda: deque(maxlen=50))
        self.player_team = {}
        self.season = None
        self.observed = set()

    def observe(self, event):
        gid = event["game_id"]
        if gid in self.observed:
            raise ValueError("Repeated historical game")
        self.observed.add(gid)
        season = event["season"]
        if self.season is not None and season < self.season:
            raise ValueError("History is out of season order")
        if self.season is not None and season > self.season:
            factor = .75 ** (season - self.season)
            self.ratings = defaultdict(lambda: 1500.0,
                {k: 1500 + factor*(v-1500) for k,v in self.ratings.items()})
        self.season = season
        for player, team, starter in event["roster"]:
            self.player_team[player] = team
            if starter:
                role = None
                if event["valid_role"]:
                    role = (event["possession_team"] == team,
                            event["scorer_team"] == team,
                            event["scorer"] == player)
                self.starts[player].append(role)
        if event["valid_jump"]:
            h, a = event["jumper_home"], event["jumper_away"]
            q = elo_probability(self.ratings[h], self.ratings[a])
            delta = 24 * ((event["possession_team"] == event["home"]) - q)
            self.ratings[h] += delta
            self.ratings[a] -= delta
            self.jump_appearances.update((h, a))
            self.team_jumps[event["home"]].append(h)
            self.team_jumps[event["away"]].append(a)

    def jumper_weights(self, team, players):
        counts = Counter(self.team_jumps.get(team, ()))
        total_prior = sum(self.jump_appearances[p] for p in players)
        prior = {p: self.jump_appearances[p]/total_prior if total_prior else 1/len(players) for p in players}
        values = {p: counts[p] + 2*prior[p] for p in players}
        total = sum(values.values())
        return {p: v/total for p,v in values.items()}

    def forecast(self, home, away, runners):
        if len(runners) != 10 or len({r["player_id"] for r in runners}) != 10:
            raise ValueError("Forecast needs ten distinct player IDs")
        if any(not math.isfinite(r["decimal"]) or r["decimal"] <= 1 for r in runners):
            raise ValueError("Invalid price")
        players = {t: [r["player_id"] for r in runners if self.player_team.get(r["player_id"]) == t]
                   for t in (home, away)}
        if any(len(v) != 5 for v in players.values()):
            raise ValueError("Prior rosters do not establish five candidates per current team")
        weights = {t: self.jumper_weights(t, players[t]) for t in (home, away)}
        q = sum(weights[home][h]*weights[away][a]*elo_probability(self.ratings[h], self.ratings[a])
                for h in players[home] for a in players[away])
        raw = {r["player_id"]: 1/r["decimal"] for r in runners}
        hold = sum(raw.values())
        market = {p:v/hold for p,v in raw.items()}
        team_market = {t:sum(market[p] for p in players[t]) for t in (home, away)}
        shares = {t: {p: market[p]/team_market[t] for p in players[t]} for t in (home, away)}
        role_shares = {}
        for team in (home, away):
            for own_possession in (False, True):
                values = {}
                for p in players[team]:
                    records = [r for r in self.starts.get(p, ()) if r is not None and r[0] == own_possession]
                    n = sum(r[1] for r in records)
                    k = sum(r[2] for r in records)
                    values[p] = (k + 20*shares[team][p])/(n+20)
                total = sum(values.values())
                role_shares[(team, own_possession)] = {p:v/total for p,v in values.items()}
        c = POSSESSION_SCORE_RATE
        team_fair = {home:q*c+(1-q)*(1-c), away:q*(1-c)+(1-q)*c}
        tip = {p:team_fair[t]*shares[t][p] for t in (home, away) for p in players[t]}
        role = {}
        for p in players[home]:
            role[p] = q*c*role_shares[(home, True)][p] + (1-q)*(1-c)*role_shares[(home, False)][p]
        for p in players[away]:
            role[p] = q*(1-c)*role_shares[(away, False)][p] + (1-q)*c*role_shares[(away, True)][p]
        for distribution in (market, tip, role):
            if abs(sum(distribution.values())-1) > 1e-10 or any(v <= 0 or v >= 1 for v in distribution.values()):
                raise ValueError("Invalid probability distribution")
        return {"market":market, "tip":tip, "tip_role":role, "home_possession_probability":q,
                "home_first_score_probability":team_fair[home], "market_home_first_score_probability":team_market[home],
                "jumper_weights":weights, "overround":hold-1,
                "prior_start_counts":{p:len(self.starts.get(p, ())) for p in market}}


def select_bet(runners, probabilities, reserve=False):
    candidates = []
    for r in runners:
        if 1.20 <= r["decimal"] <= 26:
            p = probabilities[r["player_id"]] * (.99 if reserve else 1)
            ev = p*(1+.98*(r["decimal"]-1))-1
            if ev >= .05:
                candidates.append({**r, "probability":p, "expected_return":ev})
    return min(candidates, key=lambda r:(-r["expected_return"], r["player_id"])) if candidates else None
