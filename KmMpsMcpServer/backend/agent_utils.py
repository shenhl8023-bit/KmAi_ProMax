# -*- coding: utf-8 -*-
from __future__ import print_function

import json

def _json_bytes(data):
    return json.dumps(data, ensure_ascii=False).encode("utf-8")
