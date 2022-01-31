import os
import os.path
import threading

import pytest

try:
    # python2
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
    from SimpleHTTPServer import SimpleHTTPRequestHandler
except:
    # python3
    from http.server import (BaseHTTPRequestHandler, HTTPServer,
                             SimpleHTTPRequestHandler)

class HTTPReplayHandler(SimpleHTTPRequestHandler):
    " Serves pages saved alongside with headers. See `curl --http1.1 -is http://...` "

    directory = os.path.join(os.path.dirname(__file__), './samples/')

    __init__ = BaseHTTPRequestHandler.__init__

    def do_GET(self):
        path = self.translate_path(self.path)

        if os.path.isdir(path):
            f = self.list_directory(path)

        else:
            f = open(path, 'rb')

        try:
            self.copyfile(f, self.wfile)

        finally:
            f.close()

class MuteHTTPServer(HTTPServer):
    def handle_error(self, request, client_address):
        # mute errors
        pass

def make_server(port=8888):
    print('Serving http://localhost:%s/' % port)
    return MuteHTTPServer(('', port), RequestHandlerClass=HTTPReplayHandler)

@pytest.fixture
def replay_server():
    httpd = make_server()
    thread = threading.Thread(target=httpd.serve_forever)
    thread.start()

    yield

    httpd.shutdown()
    thread.join()

if __name__ == '__main__':
    httpd = make_server()
    httpd.serve_forever()
