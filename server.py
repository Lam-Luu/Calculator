"""Local So Tinh server. Public draw results only; bet messages stay in the browser."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
VIETNAM = timezone(timedelta(hours=7))
SOURCES = {
    'north': 'https://xosodaiphat.com/ket-qua-xo-so-mien-bac-xsmb.rss',
    'central': 'https://xosodaiphat.com/ket-qua-xo-so-mien-trung-xsmt.rss',
}
# Prize -> (number count, digit width). Preserve leading zeroes as strings.
SHAPES = {
    'north': {'DB': (1, 5), '1': (1, 5), '2': (2, 5), '3': (6, 5),
              '4': (4, 4), '5': (6, 4), '6': (3, 3), '7': (4, 2)},
    'central': {'DB': (1, 6), '1': (1, 5), '2': (1, 5), '3': (2, 5),
                '4': (7, 5), '5': (1, 4), '6': (3, 4), '7': (1, 3), '8': (1, 2)},
}
MAX_FEED_BYTES = 512_000
CACHE_TTL = 60
DRAW_TIMES = {'central': (17, 15), 'north': (18, 15)}
# Monday first, matching the stations named in the provider's weekly feed.
CENTRAL_STATIONS = (
    ('Phú Yên', 'Huế'), ('Đắk Lắk', 'Quảng Nam'), ('Đà Nẵng', 'Khánh Hòa'),
    ('Bình Định', 'Quảng Trị', 'Quảng Bình'), ('Gia Lai', 'Ninh Thuận'),
    ('Đà Nẵng', 'Quảng Ngãi', 'Đắk Nông'), ('Khánh Hòa', 'Kon Tum', 'Huế'),
)
_cache: dict = {}
_locks = {region: threading.Lock() for region in SOURCES}


def parse_prizes(text: str, region: str) -> tuple[dict, bool]:
    matches = list(re.finditer(r'(?:\bG\.\s*([1-8])|\bDB(?:6)?)\s*:', text))
    prizes = {}
    valid = True
    for index, match in enumerate(matches):
        key = match.group(1) or 'DB'
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw = text[match.end():end].strip()
        numbers = re.split(r'\s*-\s*|\s+', raw) if raw else []
        shape = SHAPES[region].get(key)
        if key in prizes or not shape:
            valid = False
        if not shape or len(numbers) != shape[0] or any(
            not re.fullmatch(r'[0-9]{' + str(shape[1]) + '}', number) for number in numbers
        ):
            valid = False
        prizes[key] = [number for number in numbers if re.fullmatch(r'[0-9]+', number)]
    return prizes, valid and set(prizes) == set(SHAPES[region])


def parse_feed(payload: bytes, region: str) -> dict:
    if region not in SOURCES:
        raise ValueError('Miền không hợp lệ.')
    if len(payload) > MAX_FEED_BYTES or b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():
        raise ValueError('Nguồn kết quả không hợp lệ.')
    channel = ET.fromstring(payload).find('channel')
    if channel is None:
        raise ValueError('Không đọc được nguồn kết quả.')
    days = {}
    for item in channel.findall('item'):
        raw_date = (item.findtext('pubDate') or '').strip()
        try:
            day = datetime.strptime(raw_date, '%d/%m/%Y').date().isoformat()
        except ValueError:
            continue
        title = item.findtext('title') or ''
        title_date = re.search(r'\b\d{2}/\d{2}/\d{4}\b', title)
        if not title_date or title_date.group() != raw_date or day in days:
            raise ValueError('Ngày kết quả từ nguồn không khớp hoặc bị trùng.')
        text = item.findtext('description') or ''
        if region == 'north':
            sections = [('Miền Bắc', text)]
        else:
            stations = list(re.finditer(r'\[([^\[\]]+)\]', text))
            sections = [(m.group(1).strip(), text[m.end():stations[i + 1].start() if i + 1 < len(stations) else len(text)])
                        for i, m in enumerate(stations)]
        draws = []
        for station, section in sections:
            if not station or station in [draw['station'] for draw in draws]:
                raise ValueError('Danh sách đài không hợp lệ.')
            prizes, complete = parse_prizes(section, region)
            draws.append({'station': station, 'prizes': prizes, 'complete': complete})
        # Use an application-owned URL, never an untrusted feed link.
        kind = 'xsmb' if region == 'north' else 'xsmt'
        source_url = f'https://xosodaiphat.com/{kind}-{date.fromisoformat(day):%d-%m-%Y}.html'
        days[day] = {'draws': draws, 'sourceUrl': source_url}
    if not days:
        raise ValueError('Nguồn chưa cung cấp kết quả đọc được.')
    return days


def load_feed(region: str) -> tuple[dict, str]:
    with _locks[region]:
        cached = _cache.get(region)
        if cached and time.monotonic() - cached[0] < CACHE_TTL:
            return cached[1], cached[2]
        request = Request(SOURCES[region], headers={'User-Agent': 'SoTinh/1.0 (public results reader)',
                                                   'Accept': 'application/rss+xml, text/xml'})
        with urlopen(request, timeout=15) as response:
            payload = response.read(MAX_FEED_BYTES + 1)
        days = parse_feed(payload, region)
        fetched_at = datetime.now(timezone.utc).isoformat()
        _cache[region] = (time.monotonic(), days, fetched_at)
        return days, fetched_at


def get_results(region: str, day: str, *, now: datetime | None = None) -> dict:
    if region not in SOURCES:
        raise ValueError('Chỉ hỗ trợ miền Trung và miền Bắc.')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
        raise ValueError('Ngày phải có dạng YYYY-MM-DD.')
    selected_date = date.fromisoformat(day)
    current_time = (now or datetime.now(VIETNAM)).astimezone(VIETNAM)
    today = current_time.date()
    opens_at = current_time.replace(hour=DRAW_TIMES[region][0], minute=DRAW_TIMES[region][1], second=0, microsecond=0)
    latest_date = today if current_time >= opens_at else today - timedelta(days=1)
    if selected_date > today:
        raise ValueError('Không thể lấy kết quả cho ngày tương lai.')
    expected = list(CENTRAL_STATIONS[selected_date.weekday()]) if region == 'central' else ['Miền Bắc']
    window = {'today': today.isoformat(), 'opensAt': opens_at.isoformat(),
              'latestSelectableDate': latest_date.isoformat(), 'serverTime': current_time.isoformat()}
    if selected_date == today and current_time < opens_at:
        # Never even read cached/upstream results before the configured opening time.
        return {'region': region, 'date': day, 'status': 'locked', 'draws': [],
                'expectedStations': expected, 'availableDates': [], 'fetchedAt': None,
                'source': 'Xổ Số Đại Phát', 'sourceUrl': SOURCES[region], **window}
    days, fetched_at = load_feed(region)
    selected = days.get(day)
    draws = selected['draws'] if selected else []
    if draws:
        status = 'complete' if all(draw['complete'] for draw in draws) and set(expected) == {d['station'] for d in draws} else 'pending'
    elif day < min(days):
        status = 'unavailable'
    else:
        status = 'pending'
    return {'region': region, 'date': day, 'status': status, 'draws': draws,
            'expectedStations': expected,
            'availableDates': sorted(days, reverse=True), 'fetchedAt': fetched_at,
            'source': 'Xổ Số Đại Phát', 'sourceUrl': selected['sourceUrl'] if selected else SOURCES[region], **window}


class Handler(BaseHTTPRequestHandler):
    def send_body(self, status: int, content: bytes, content_type: str):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, status: int, data: dict):
        self.send_body(status, json.dumps(data, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == '/api/results':
            params = parse_qs(url.query, keep_blank_values=True)
            if set(params) != {'region', 'date'} or any(len(v) != 1 for v in params.values()):
                self.send_json(400, {'error': 'Chọn đúng miền và ngày cần dò.'})
                return
            try:
                result = get_results(params['region'][0], params['date'][0])
            except ValueError:
                self.send_json(400, {'error': 'Miền, ngày hoặc dữ liệu nguồn không hợp lệ. Vui lòng kiểm tra lại.'})
            except Exception:
                self.send_json(502, {'error': 'Chưa lấy được kết quả từ nguồn. Thử cập nhật lại sau.'})
            else:
                self.send_json(200, result)
        elif url.path in ('/', '/index.html', '/dist/index.html'):
            self.send_body(200, (ROOT / 'dist' / 'index.html').read_bytes(), 'text/html; charset=utf-8')
        elif url.path == '/favicon.ico':
            self.send_body(204, b'', 'image/x-icon')
        else:
            self.send_json(404, {'error': 'Không tìm thấy đường dẫn.'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5173)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'So Tinh: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
