# coding: utf-8

from __future__ import absolute_import
from . import utils
from .defaults import CONFIG_PATHS, HOME
from os.path import expanduser
import threading

_thread_local = threading.local()


def current(*args, **kwargs):
    out = getattr(_thread_local, 'config', None)
    if not out:
        out = Config(*args, **kwargs)
    return out


class Config(object):

    @property
    def defaults(self):
        return self._config.get("defaults", {})

    @property
    def home(self):
        return self.defaults.get('home', HOME)

    @property
    def environment(self):
        return self._config["environment"]

    @property
    def source(self):
        return self._config["source"]

    @property
    def images(self):
        return self._config["images"]

    @property
    def repos(self):
        return self._config["repos"]

    @property
    def publishers(self):
        return self._config.get('publishers', {'debian': 'local-deb-s3'})

    @property
    def notifications(self):
        return self._config.get("notifications", {})

    def __init__(self):
        self._load_config()
        if not hasattr(self, '_config'):
            raise IOError("Couldn't find a suitable metallus config file")

    def _load_config(self):
        for path in CONFIG_PATHS:
            try:
                self._config = utils.deserialise(expanduser(path))
            except IOError:
                continue

    def get_repo(self, name):
        config = self.repos[name]
        config["name"] = name
        return config

    def get_image(self, name):
        config = self.images[name]
        config["name"] = name
        return config
