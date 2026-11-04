from http.server import BaseHTTPRequestHandler
import json
import os
import sys
from urllib.parse import parse_qs, urlsplit

# Ensure root directory is in sys.path to import server logic
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import server


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        params = parse_qs(url.query, keep_blank_values=True)
        if set(params) != {'region', 'date'} or any(len(v) != 1 for v in params.values()):
            self.send_response(400)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Chọn đúng miền và ngày cần dò.'}, ensure_ascii=False).encode('utf-8'))
            return
        try:
            result = server.get_results(params['region'][0], params['date'][0])
        except ValueError as e:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}, ensure_ascii=False).encode('utf-8'))
        except Exception:
            self.send_response(502)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Chưa lấy được kết quả từ nguồn. Thử cập nhật lại sau.'}, ensure_ascii=False).encode('utf-8'))
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))

