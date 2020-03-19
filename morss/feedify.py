#!/usr/bin/env python

import os.path

import re
import json

from . import crawler

try:
    basestring
except NameError:
    basestring = str


def pre_worker(url):
    if url.startswith('http://itunes.apple.com/') or url.startswith('https://itunes.apple.com/'):
        match = re.search('/id([0-9]+)(\?.*)?$', url)
        if match:
            iid = match.groups()[0]
            redirect = 'https://itunes.apple.com/lookup?id=%s' % iid

            try:
                con = crawler.custom_handler(basic=True).open(redirect, timeout=4)
                data = con.read()

            except (IOError, HTTPException):
                raise

            return json.loads(data.decode('utf-8', 'replace'))['results'][0]['feedUrl']

    return None
