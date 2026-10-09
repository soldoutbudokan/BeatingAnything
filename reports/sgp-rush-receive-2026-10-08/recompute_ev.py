"""Recompute and validate the sanitized public EV data; Python standard library only."""
import json
import math
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CELLS = ('OO', 'OU', 'UO', 'UU')

def calculate(prices):
    with localcontext() as ctx:
        ctx.prec = 60
        q = []
        for c in CELLS:
            a = Decimal(prices[c])
            d = 1 + a / 100 if a > 0 else 1 + 100 / -a
            q.append(1 / d)
        lo, hi = Decimal(0), Decimal(50)
        for _ in range(200):
            k = (lo + hi) / 2
            if sum(ctx.power(x, k) for x in q) > 1:
                lo = k
            else:
                hi = k
        power = [ctx.power(x, (lo + hi) / 2) for x in q]
        additive = [x - (sum(q) - 1) / 4 for x in q]
        return {'power': list(map(float, power)), 'additive': list(map(float, additive)) if all(0 <= x <= 1 for x in additive) else None}

def main():
    data = json.loads((ROOT / 'prices-and-ev.json').read_text())
    refs = {r['id']: r for r in data['references']}
    models = {r['id']: calculate(r['prices']) for r in refs.values() if all(r['prices'].get(c) is not None for c in CELLS)}
    groups = {g['id']: g for g in data['instances']}
    checks = 0
    for v in data['variants']:
        ref = refs.get(v.get('reference_id'))
        group = groups[v['instance_id']]
        for method in ('power', 'additive'):
            observed = v['ev_' + method]
            if not ref or v['american'] is None or v['relation'] == 'incomparable' or ref['id'] not in models:
                assert observed is None
                continue
            probs = models[ref['id']][method]
            if probs is None:
                assert observed is None
                continue
            assert abs(sum(probs) - 1) < 1e-12
            a = v['american']
            d = 1 + a / 100 if a > 0 else 1 + 100 / -a
            assert abs(d * probs[1] - 1 - observed) < 1e-12
            checks += 1
        if ref and group.get('required_receiving_minimum'):
            assert v['relation'] == 'subset'
            assert math.floor(ref['sum_line']) + 1 >= group['sum_minimum']
            assert math.ceil(ref['rush_line']) - 1 <= math.ceil(group['rush_line']) - 1
            assert math.floor(ref['sum_line']) + 1 - (math.ceil(ref['rush_line']) - 1) >= group['required_receiving_minimum']
    assert sum(g['in_census'] for g in groups.values()) == 24
    assert all(g['base_american'] is not None for g in groups.values() if g['in_census'])
    edge = next(g for g in groups.values() if g.get('required_receiving_minimum') == 40)
    assert edge['ev_power'] > 0 and edge['ev_additive'] > 0
    print(json.dumps({'status': 'passed', 'constructions': len(groups), 'observations': len(data['variants']), 'partitions': len(models), 'ev_checks': checks, 'McCaffrey_power_lower_bound': edge['ev_power'], 'McCaffrey_additive_lower_bound': edge['ev_additive']}, indent=2))

if __name__ == '__main__':
    main()
