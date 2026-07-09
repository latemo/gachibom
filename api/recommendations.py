from http.server import BaseHTTPRequestHandler

from src.vercel_api import handle_options, handle_recommendations, method_not_allowed


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        handle_recommendations(self)

    def do_OPTIONS(self):
        handle_options(self)

    def do_GET(self):
        method_not_allowed(self)
