# coding: utf-8

from __future__ import print_function
from __future__ import absolute_import

import os.path
import hashlib
import sys
from base64 import urlsafe_b64encode

from jsonrpc2_zeromq import RPCNotifierClient

from . import Publisher, DEFAULT_CACHE_CONTROL

PACKAGE_SEND_CHUNK_SIZE = 250000


class TansitPublisher(Publisher):

    package_type = "debian"
    config_name = "tansit"

    def _after_init(self):
        try:
            endpoint = self.config['endpoint']
        except KeyError:
            raise Exception("Tansit must be configured with an endpoint")

        # FIXME: Set timeout per-request when that lands in jsonrpc2_zeromq
        self._client = RPCNotifierClient(endpoint, timeout=120*1000)
        # Need to set a low HWM so sending package data
        # doesn't overload server
        self._client.socket.set_hwm(10)

    def list(self, repo, codename, component, arch):
        return self._client.long_list(bucket=repo['bucket'], codename=codename,
                                      component=component, arch=arch)

    def copy(self, repo, packager, from_codename, from_component,
             to_codename, to_component, versions):
        print(self._client.copy(
            package=packager.name, to_codename=to_codename,
            to_component=to_component, codename=from_codename,
            component=from_component, versions=versions,
            cache_control=DEFAULT_CACHE_CONTROL, preserve_versions=True,
            bucket=repo['bucket'], arch=packager.arch))

    def upload(self, repo, packager, codename, component):
        first_chunk = True
        package_hash = hashlib.sha256()
        package_filename = os.path.basename(packager.path)

        print("Uploading {}".format(package_filename), end="")
        with open(packager.path, 'r') as f:
            while True:
                chunk = f.read(PACKAGE_SEND_CHUNK_SIZE)
                if not chunk:
                    print(".")
                    break
                package_hash.update(chunk)
                self._client.send_package_data(file_name=package_filename,
                                               data=urlsafe_b64encode(chunk),
                                               new_file=first_chunk)
                print(".", end="")
                sys.stdout.flush()
                first_chunk = False

        print(self._client.upload(
            file_name=package_filename,
            file_sha256_hash=package_hash.hexdigest(), bucket=repo['bucket'],
            codename=codename, component=component,
            cache_control=DEFAULT_CACHE_CONTROL, preserve_versions=True))
