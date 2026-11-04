from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import URLError
import xml.etree.ElementTree as ET

import server

FIXTURE = json.loads((Path(__file__).parent / 'tests/fixtures/lottery.json').read_text(encoding='utf-8'))


def feed(region, draws=None, day='04/11/2026'):
    rss = ET.Element('rss')
    channel = ET.SubElement(rss, 'channel')
    item = ET.SubElement(channel, 'item')
    ET.SubElement(item, 'title').text = 'KẾT QUẢ NGÀY ' + day
    ET.SubElement(item, 'pubDate').text = day
    sections = []
    for draw in draws if draws is not None else FIXTURE[region]:
        prefix = '[' + draw['station'] + ']' if region == 'central' else ''
        parts = [(('DB6' if region == 'central' else 'DB') if key == 'DB' else 'G.' + key)
                 + ': ' + ' - '.join(numbers) for key, numbers in draw['prizes'].items()]
        sections.append(prefix + '\n'.join(parts))
    ET.SubElement(item, 'description').text = '\n'.join(sections)
    return ET.tostring(rss, encoding='utf-8', xml_declaration=True)


class FeedTests(unittest.TestCase):
    def test_parse_both_regions_and_keep_leading_zeroes(self):
        for region in ['north', 'central']:
            result = server.parse_feed(feed(region), region)
            self.assertEqual(result['2026-11-04']['draws'], FIXTURE[region])
        self.assertEqual(server.parse_feed(feed('north'), 'north')['2026-11-04']['draws'][0]['prizes']['1'], ['03675'])

    def test_partial_wrong_width_extra_and_repeated_prize_never_complete(self):
        for mutate in ['missing', 'width', 'placeholder', 'extra']:
            draws = deepcopy(FIXTURE['north'])
            if mutate == 'missing':
                del draws[0]['prizes']['7']
            elif mutate == 'width':
                draws[0]['prizes']['7'][0] = '079'
            elif mutate == 'placeholder':
                draws[0]['prizes']['DB'][0] = '.....'
            else:
                draws[0]['prizes']['7'].append('46')
            parsed = server.parse_feed(feed('north', draws), 'north')
            self.assertFalse(parsed['2026-11-04']['draws'][0]['complete'], mutate)
        prizes, complete = server.parse_prizes('DB: 53046\nDB: 53046', 'north')
        self.assertFalse(complete)

    def test_mismatched_date_and_unsafe_xml_rejected(self):
        payload = feed('north').replace(b'<pubDate>04/11/2026', b'<pubDate>03/11/2026')
        with self.assertRaises(ValueError):
            server.parse_feed(payload, 'north')
        for payload in [b'<!DOCTYPE rss><rss/>', b'<!ENTITY a "x"><rss/>', b'x' * (server.MAX_FEED_BYTES + 1)]:
            with self.assertRaises(ValueError):
                server.parse_feed(payload, 'north')

    def test_request_date_never_falls_back_to_yesterday(self):
        days = server.parse_feed(feed('north'), 'north')
        with patch.object(server, 'load_feed', return_value=(days, '2026-11-04T12:00:00Z')):
            self.assertEqual(server.get_results('north', '2026-11-04')['status'], 'complete')
            waiting = server.get_results('north', '2026-11-05', now=datetime(2026, 11, 5, 19, tzinfo=server.VIETNAM))
            self.assertEqual(waiting['status'], 'pending')
            self.assertEqual(waiting['draws'], [])
            self.assertEqual(server.get_results('north', '2026-10-01')['status'], 'unavailable')

    def test_all_central_stations_must_exist_before_region_is_complete(self):
        days = server.parse_feed(feed('central', FIXTURE['central'][:1]), 'central')
        with patch.object(server, 'load_feed', return_value=(days, '2026-11-04T12:00:00Z')):
            self.assertEqual(server.get_results('central', '2026-11-04')['status'], 'pending')
        days = server.parse_feed(feed('central'), 'central')
        with patch.object(server, 'load_feed', return_value=(days, '2026-11-04T12:00:00Z')):
            self.assertEqual(server.get_results('central', '2026-11-04')['status'], 'complete')

    def test_invalid_queries_and_future_date(self):
        for region, day in [('south', '2026-11-04'), ('north', '04/11/2026'), ('north', '2026-02-30'),
                            ('north', 'https://example.com'), ('north', (datetime.now(server.VIETNAM).date() + timedelta(days=1)).isoformat())]:
            with self.assertRaises(ValueError):
                server.get_results(region, day)

    def test_today_is_locked_before_opening_even_if_source_has_full_results(self):
        for region, hour in [('central', 17), ('north', 18)]:
            days = server.parse_feed(feed(region), region)
            with patch.object(server, 'load_feed', return_value=(days, '2026-11-04T12:00:00Z')) as source:
                locked = server.get_results(region, '2026-11-04', now=datetime(2026, 11, 4, hour, 14, 59, tzinfo=server.VIETNAM))
                self.assertEqual(locked['status'], 'locked')
                self.assertEqual(locked['draws'], [])
                self.assertIsNone(locked['fetchedAt'])
                self.assertEqual(locked['latestSelectableDate'], '2026-11-03')
                source.assert_not_called()
                for second in [0, 1]:
                    opened = server.get_results(region, '2026-11-04', now=datetime(2026, 11, 4, hour, 15, second, tzinfo=server.VIETNAM))
                    self.assertEqual(opened['status'], 'complete')
                    self.assertEqual(opened['latestSelectableDate'], '2026-11-04')
                    self.assertTrue(opened['draws'])

    def test_old_dates_remain_available_before_todays_opening(self):
        days = server.parse_feed(feed('north'), 'north')
        with patch.object(server, 'load_feed', return_value=(days, '2026-11-04T12:00:00Z')) as source:
            result = server.get_results('north', '2026-11-04', now=datetime(2026, 11, 5, 0, 0, tzinfo=server.VIETNAM))
            self.assertEqual(result['status'], 'complete')
            source.assert_called_once()

    def test_opening_uses_vietnam_timezone_not_request_timezone(self):
        from datetime import timezone
        with patch.object(server, 'load_feed') as source:
            result = server.get_results('north', '2026-11-04', now=datetime(2026, 11, 4, 11, 14, 59, tzinfo=timezone.utc))
            self.assertEqual(result['status'], 'locked')
            self.assertEqual(result['opensAt'], '2026-11-04T18:15:00+07:00')
            source.assert_not_called()

    def test_cache_prevents_repeated_fetches_and_failure_does_not_serve_stale(self):
        server._cache.clear()
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = feed('north')
        with patch.object(server, 'urlopen', return_value=response) as fetch:
            first = server.load_feed('north')
            second = server.load_feed('north')
            self.assertEqual(first, second)
            self.assertEqual(fetch.call_count, 1)
        _, days, fetched = server._cache['north']
        server._cache['north'] = (-1000000, days, fetched)
        with patch.object(server, 'urlopen', side_effect=URLError('offline')):
            with self.assertRaises(URLError):
                server.load_feed('north')
        server._cache.clear()


if __name__ == '__main__':
    unittest.main()
