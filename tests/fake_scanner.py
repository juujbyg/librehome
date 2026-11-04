# SPDX-License-Identifier: GPL-2.0-or-later
"""A small eSCL (AirPrint) scanner simulator."""
import http.server
import threading

CAPABILITIES = b"""<?xml version="1.0" encoding="UTF-8"?>
<scan:ScannerCapabilities xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
  xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
<scan:Platen><scan:PlatenInputCaps>
<scan:MaxWidth>2550</scan:MaxWidth><scan:MaxHeight>3508</scan:MaxHeight>
<scan:SettingProfiles><scan:SettingProfile>
<scan:ColorModes><scan:ColorMode>RGB24</scan:ColorMode><scan:ColorMode>Grayscale8</scan:ColorMode></scan:ColorModes>
<scan:DocumentFormats><pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat></scan:DocumentFormats>
<scan:SupportedResolutions><scan:DiscreteResolutions>
<scan:DiscreteResolution><scan:XResolution>150</scan:XResolution><scan:YResolution>150</scan:YResolution></scan:DiscreteResolution>
<scan:DiscreteResolution><scan:XResolution>300</scan:XResolution><scan:YResolution>300</scan:YResolution></scan:DiscreteResolution>
</scan:DiscreteResolutions></scan:SupportedResolutions>
</scan:SettingProfile></scan:SettingProfiles>
</scan:PlatenInputCaps></scan:Platen>
</scan:ScannerCapabilities>"""
JPEG = b"\xff\xd8\xff\xe0fake-jpeg\xff\xd9"


def serve():
    state = {"settings": [], "pages": {}, "busy": 1}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _reply(self, code, body=b"", headers=None):
            self.send_response(code)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/eSCL/ScannerCapabilities":
                return self._reply(200, CAPABILITIES)
            job = self.path.rsplit("/NextDocument", 1)[0]
            if self.path.endswith("/NextDocument") and state["pages"].get(job):
                state["pages"][job] -= 1
                return self._reply(200, JPEG)
            self._reply(404)

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            if state["busy"]:  # the first request finds the scanner warming up
                state["busy"] -= 1
                return self._reply(503)
            job = "/eSCL/ScanJobs/%d" % (len(state["settings"]) + 1)
            state["settings"].append(body)
            state["pages"][job] = 1
            self._reply(201, headers={"Location": f"http://127.0.0.1:{self.server.server_address[1]}{job}"})

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, state
