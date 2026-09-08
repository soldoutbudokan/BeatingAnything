import hashlib
import json
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from beating.tennis_source import (Collector, parse_daily_results, parse_fixtures,
                                   parse_match_detail, parse_quote_time,
                                   select_sample, _write_once)


def daily_html(first=('7', '6'), second=('6<sup>12</sup>', '4'), status='', identifier='123', tournament='Test challenger'):
    def scores(values):
        return ''.join(f'<td class="score">{v}</td>' for v in values)
    return f'''<div id="center"><ul><li class="set"><span class="tab">22. 03. 2022</span></li><li class="set"><a href="/results/?type=atp-single">ATP singles</a></li></ul>
    <table class="result"><tbody><tr class="head flags"><td class="t-name">{tournament}</td></tr>
    <tr id="r1"><td class="time">12:00</td><td class="t-name"><a href="/player/alpha/">A</a></td>
    <td class="result">2</td>{scores(first)}<td title="{status}"></td><td><a href="/match-detail/?id={identifier}">info</a></td></tr>
    <tr id="r1b"><td class="t-name"><a href="/player/beta-a1b2/">B</a></td><td class="result">0</td>{scores(second)}</tr>
    </tbody></table></div>'''


def cell(side, opening='1.90', final='1.91', opened='20.03. 10:00', changed='21.03. 11:00', active=True, history=True):
    deactivated = '' if active else ' deactivated'
    tooltip = ''
    if history:
        change = '' if changed is None else f'<tr><td>{changed}</td><td class="bold">{final}</td></tr>'
        tooltip = f'<div class="odds-change-div"><table>{change}<tr><td class="title">Opening odds</td></tr><tr><td>{opened}</td><td class="bold">{opening}</td></tr></table></div>'
    return f'<td class="k{side}{deactivated}"><div class="odds-in">{final}{tooltip}</div></td>'


def detail_html(totals=None, moneyline=None, line='21.5', start='22.03.2022, 12:00'):
    totals = totals or (cell(1), cell(2))
    moneyline = moneyline or (cell(1), cell(2))
    return f'''<meta property="og:url" content="https://www.tennisexplorer.com/match-detail/?id=123">
    <div id="center"><div class="box boxBasic lGray"><span class="upper">{start.split(',')[0]}</span>,{start.split(',')[1]}, Test challenger</div>
    <table class="result gDetail noMgB"><thead><tr><th class="plName"><a href="/player/alpha">A</a></th><td class="gScore">2:0</td><th class="plName"><a href="/player/beta-a1b2">B</a></th></tr></thead>
    <tbody><tr><td>Current ranking 1</td></tr></tbody></table>
    <div id="oddsMenu-1-data"><table class="result"><tbody><tr><td><span class="t">Pinnacle</span></td>{''.join(moneyline)}</tr></tbody></table></div>
    <div id="oddsMenu-2-data"><table class="result odds-ou"><tbody><tr><td><span class="t">Pinnacle</span></td><td class="value">{line}</td>{''.join(totals)}</tr></tbody></table></div></div>'''


class TennisSourceTests(unittest.TestCase):
    def test_superscripts_are_not_extra_games(self):
        parsed = parse_daily_results(daily_html(), '2022-03-22')
        self.assertEqual(parsed['errors'], [])
        record = parsed['records'][0]
        self.assertEqual(record['sets'], [[7, 6], [6, 4]])
        self.assertTrue(record['completed'])
        self.assertEqual(record['player2'], 'beta-a1b2')

    def test_retirement_keeps_completed_sets_but_not_complete_match(self):
        record = parse_daily_results(daily_html(status='Retired'), '2022-03-22')['records'][0]
        self.assertFalse(record['completed'])
        self.assertEqual(record['sets'], [[7, 6], [6, 4]])

    def test_nonconventional_match_tiebreak_remains_ungraded(self):
        record = parse_daily_results(daily_html(('6', '4', '10'), ('4', '6', '8')), '2022-03-22')['records'][0]
        self.assertFalse(record['completed'])
        self.assertEqual(record['sets'][-1], [10, 8])

    def test_missing_cell_does_not_become_zero(self):
        parsed = parse_daily_results(daily_html(('7', '6'), ('6', '')), '2022-03-22')
        self.assertFalse(parsed['records'][0]['completed'])
        self.assertTrue(parsed['errors'])
        self.assertEqual(parsed['records'][0]['sets'], [[7, 6]])

    def test_missing_opponent_row_does_not_steal_next_match_player(self):
        raw = daily_html().replace('<tr id="r1b">', '<tr id="r1b"><td><a href="/match-detail/?id=124">info</a></td>')
        fixtures = parse_fixtures(raw, '2022-03-22')
        self.assertEqual(fixtures[0]['identity_error'], 'opponent_row_is_another_match')
        self.assertEqual(parse_daily_results(raw, '2022-03-22')['records'], [])

    def test_wrong_date_and_page_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'date_not_verified'):
            parse_daily_results(daily_html(), '2022-03-23')
        with self.assertRaises(ValueError):
            parse_fixtures('<html>Access denied</html>', '2022-03-22')
        with self.assertRaisesRegex(ValueError, 'atp_singles_filter_not_verified'):
            parse_fixtures(daily_html().replace('type=atp-single', 'type=all'), '2022-03-22')

    def test_sample_uses_only_ids_and_weekday(self):
        fixtures = [{'event_id': f'te:{i}', 'match_id': str(i), 'date': '2022-03-22',
                     'source_url': f'https://www.tennisexplorer.com/match-detail/?id={i}',
                     'challenger': True, 'result': i % 2} for i in range(30)]
        expected = sorted(range(30), key=lambda i: hashlib.sha256(f'N2-v1|{i}'.encode()).hexdigest())[:12]
        self.assertEqual([int(f['match_id']) for f in select_sample(fixtures, '2022-03-22')], expected)
        self.assertEqual(select_sample(fixtures, '2022-03-23'), [])
        self.assertNotIn('result', select_sample(fixtures, '2022-03-22')[0])

    def test_changed_prices_and_literal_times(self):
        result = parse_match_detail(detail_html(), '123')
        self.assertTrue(result['entry_valid_n2'])
        self.assertTrue(result['closing_valid'])
        self.assertEqual(result['totals_21_5']['side1']['opening_at'], '2022-03-20T09:00:00+00:00')
        self.assertNotIn('ranking', json.dumps(result).lower())

    def test_deactivated_close_never_removes_valid_entry(self):
        result = parse_match_detail(detail_html(totals=(cell(1, active=False), cell(2))), '123')
        self.assertTrue(result['entry_valid_n3'])
        self.assertFalse(result['closing_valid'])
        self.assertIn('deactivated_final', result['closing_errors'])

    def test_missing_history_is_not_an_unchanged_opening(self):
        result = parse_match_detail(detail_html(totals=(cell(1, history=False), cell(2))), '123')
        self.assertFalse(result['entry_valid_n3'])
        self.assertIsNone(result['totals_21_5']['side1']['opening_at'])

    def test_explicit_unchanged_opening_can_supply_last_change(self):
        result = parse_match_detail(detail_html(totals=(cell(1, final='1.90', changed=None), cell(2))), '123')
        self.assertTrue(result['closing_valid'])
        self.assertTrue(result['totals_21_5']['side1']['unchanged_opening'])

    def test_n2_requires_all_four_openings_but_n3_only_totals(self):
        result = parse_match_detail(detail_html(moneyline=(cell(1, opened='19.03. 10:00'), cell(2, opened='19.03. 10:00'))), '123')
        self.assertFalse(result['entry_valid_n2'])
        self.assertTrue(result['entry_valid_n3'])

    def test_after_start_quote_and_alternate_line_fail(self):
        result = parse_match_detail(detail_html(totals=(cell(1, opened='22.03. 13:00'), cell(2, opened='22.03. 13:00'))), '123')
        self.assertFalse(result['entry_valid_n3'])
        self.assertIn('opening_not_prestart', result['entry_errors_n3'])
        result = parse_match_detail(detail_html(line='22.5'), '123')
        self.assertFalse(result['entry_valid_n3'])
        self.assertFalse(result['totals_21_5']['present'])

    def test_malformed_duplicate_market_cannot_be_silently_skipped(self):
        raw = detail_html()
        position = raw.index('<div id="oddsMenu-2-data">')
        duplicate = '<tr><td><span class="t">Pinnacle</span></td><td class="value">21.5</td>' + cell(1) + '</tr>'
        raw = raw[:position] + raw[position:].replace('</tbody>', duplicate + '</tbody>', 1)
        result = parse_match_detail(raw, '123')
        self.assertFalse(result['entry_valid_n3'])
        self.assertEqual(result['totals_21_5']['reason'], 'duplicate_market')

    def test_year_rollover_and_dst_fail_closed(self):
        self.assertEqual(parse_quote_time('31.12. 23:50', datetime(2022, 1, 1, 12)), '2021-12-31T22:50:00+00:00')
        for value, start in [('27.03. 02:30', datetime(2022, 3, 27, 12)), ('30.10. 02:30', datetime(2022, 10, 30, 12))]:
            with self.assertRaisesRegex(ValueError, 'ambiguous_or_nonexistent'):
                parse_quote_time(value, start)

    def test_mismatched_detail_identity_fails(self):
        with self.assertRaisesRegex(ValueError, 'event_id_mismatch'):
            parse_match_detail(detail_html(), '456')
        with self.assertRaisesRegex(ValueError, 'event_id_unverified'):
            parse_match_detail(detail_html().replace('property="og:url"', 'property="other"'), '123')

    def test_sample_pin_precedes_score_parse_and_is_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            collector = Collector(directory)
            real = parse_daily_results
            def inspect(raw, day):
                self.assertTrue((Path(directory) / 'sample' / f'{day}.json').exists())
                return real(raw, day)
            with patch.object(collector, 'fetch', return_value=daily_html().encode()), patch('beating.tennis_source.parse_daily_results', side_effect=inspect):
                self.assertEqual(collector.collect_day('2022-03-22')['status'], 'parsed')
            path = Path(directory) / 'sample' / '2022-03-22.json'
            with self.assertRaisesRegex(ValueError, 'immutable_file_conflict'):
                _write_once(path, {'matches': []})

    def test_download_cache_and_failures_are_audited(self):
        class Response:
            status = 200
            headers = {'Content-Type': 'text/html'}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return b'<html>source</html>'
        with tempfile.TemporaryDirectory() as directory:
            collector = Collector(directory, max_attempts=1)
            with patch('beating.tennis_source.urlopen', return_value=Response()) as request:
                self.assertEqual(collector.fetch('daily/test.html', 'https://www.tennisexplorer.com/test'), b'<html>source</html>')
                collector.fetch('daily/test.html', 'https://www.tennisexplorer.com/test')
                self.assertEqual(request.call_count, 1)
            with patch('beating.tennis_source.urlopen', side_effect=HTTPError('url', 429, 'rate limit', {}, None)), patch.object(collector, '_pace'):
                with self.assertRaisesRegex(RuntimeError, 'rate_limit'):
                    collector.fetch('daily/fail.html', 'https://www.tennisexplorer.com/fail')
            ledger = [json.loads(line) for line in (Path(directory) / 'acquisition.jsonl').read_text().splitlines()]
            self.assertEqual([r['status'] for r in ledger], ['downloaded', 'cache_hit', 'failed'])


if __name__ == '__main__':
    unittest.main()
