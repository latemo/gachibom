from http.server import BaseHTTPRequestHandler

from src.vercel_api import handle_health, handle_options, method_not_allowed


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        handle_health(self)

    def do_OPTIONS(self):
        handle_options(self)

    def do_POST(self):
        method_not_allowed(self)
