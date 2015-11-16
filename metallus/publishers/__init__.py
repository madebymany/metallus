# coding: utf-8

"""
Publishing a package makes it available to be installed somewhere.

Currently, publishing is tied to Debian packages because the idea of a
'codename' is written into it quite deeply. Another job will be to make this
more generic if we want to support Docker images and stuff. This and
packages.py is also particularly badly-factored at the moment. Really the
publisher should deal with promotion and hide all that, but that is also
another job.

Classes register themselves, and are automatically imported if they're in this
package. See local_deb_s3.py.
"""

from __future__ import print_function
from __future__ import absolute_import

import collections
import sys

DEFAULT_CACHE_CONTROL = "max-age=0"

publishers_for_types = collections.defaultdict(dict)


class PublisherNotFoundError(Exception):
    pass


def get_publisher(config, pkg_type):
    if pkg_type not in publishers_for_types:
        raise PublisherNotFoundError("No publishers found for {} packages".
                                     format(pkg_type))
    type_config = config[pkg_type]
    if isinstance(type_config, basestring):
        publisher_type = type_config
        opts = {}
    else:
        if len(type_config) != 1:
            raise PublisherNotFoundError(
                "Only one publisher should be configured "
                "for {} packages".format(pkg_type))
        publisher_type = type_config.keys()[0]
        opts = type_config[publisher_type]
        opts = opts if isinstance(opts, collections.Mapping) else {}

    try:
        return publishers_for_types[pkg_type][publisher_type](**opts)
    except KeyError:
        raise PublisherNotFoundError("Publisher not defined for {} packages "
                                     "and {} publisher".
                                     format(pkg_type, publisher_type)), \
            None, sys.exc_info()[2]


class PublisherMeta(type):
    def __new__(cls, name, bases, d):
        out = super(PublisherMeta, cls).__new__(cls, name, bases, d)
        if name != 'Publisher':
            package_type, config_name = \
                d.get('package_type'), d.get('config_name')
            if not package_type:
                raise Exception("No package_type set for " + repr(out))
            if not config_name:
                raise Exception("No config_name set for " + repr(out))
            publishers_for_types[package_type][config_name] = out
        return out


class Publisher(object):
    __metaclass__ = PublisherMeta

    def __init__(self, **config):
        self.config = config
        self._after_init()

    def _after_init(self):
        pass


# Allow all other modules in this package to register with the above
import pkgutil
import importlib
for (module_loader, name, ispkg) in pkgutil.iter_modules(__path__):
    importlib.import_module('.'.join([__name__, name]))
