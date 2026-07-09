from http.server import BaseHTTPRequestHandler

from src.vercel_api import handle_help_chat, handle_options, method_not_allowed


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        handle_help_chat(self)

    def do_OPTIONS(self):
        handle_options(self)

    def do_GET(self):
        method_not_allowed(self)
