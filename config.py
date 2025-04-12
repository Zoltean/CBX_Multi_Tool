# -*- coding: utf-8 -*-
import os

VPS_API_URL = "http://185.253.219.57:5000/api/versions"
VPS_VERSION_URL = "http://185.253.219.57:5000/api/tool_version"
VPS_LOGS_URL = "http://185.253.219.57:5000/api/logs"
VPS_CONFIG_URL = "http://185.253.219.57:5000/api/config"
DRIVES = ["C:", "D:", "E:", "F:"]
PROGRAM_VERSION = "0.0.5_beta"
PROGRAM_TITLE = f"CBX Multi Tool {PROGRAM_VERSION}"

os.system(f"title {PROGRAM_TITLE}")