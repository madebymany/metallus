# coding: utf-8

from __future__ import print_function
from __future__ import absolute_import

from contextlib import contextmanager
import os
from os import path
import fcntl
import re
import subprocess

from . import Publisher, DEFAULT_CACHE_CONTROL
from .. import config
from ..utils import s3_host

DEB_S3_LOCK = "deb-s3.lock"


def deb_s3_args(subcommand, *args, **kwargs):
    kwargs = dict((k.replace('_', '-'), v) for (k, v) in kwargs.items())
    if 'repo' in kwargs:
        repo = kwargs.pop('repo')
        kwargs['bucket'] = repo['bucket']
        kwargs['endpoint'] = s3_host(repo.get('region'))
        kwargs['sign'] = repo['gpg_id']
    return ['deb-s3', subcommand] + list(args) + \
        [("--{}".format(k) if v is True else "--{}={}".format(k, v))
         for (k, v) in kwargs.items()]


@contextmanager
def deb_s3_lock():
    fn = path.join(os.path.expanduser(config.current().home), DEB_S3_LOCK)
    with open(fn, 'w') as lock:
        print("Trying to acquire deb-s3 lock...")
        fcntl.lockf(lock, fcntl.LOCK_EX)
        try:
            print("Lock aquired.")
            yield
        finally:
            print("Releasing deb-s3 lock")
            fcntl.lockf(lock, fcntl.LOCK_UN)


class LocalDebS3Publisher(Publisher):
    package_type = "debian"
    config_name = "local-deb-s3"

    MANIFEST_LINE_PATTERN = re.compile(r"^(\S+?): (\S.*)$",
                                       re.MULTILINE | re.UNICODE)

    def list(self, repo, codename, component, arch):
        # No need for deb-s3 lock, as it's read-only
        raw = subprocess.check_output(
            deb_s3_args('list', repo=repo, long=True,
                        codename=codename, component=component, arch=arch))
        return [dict(LocalDebS3Publisher.MANIFEST_LINE_PATTERN.findall(p))
                for p in raw.split("\n\n")]

    def copy(self, repo, packager, from_codename, from_component,
             to_codename, to_component, versions):
        versions = ' '.join(versions)
        with deb_s3_lock():
            return subprocess.check_call(deb_s3_args(
                'copy', packager.name, to_codename, to_component, repo=repo,
                preserve_versions=True, versions=versions,
                arch=packager.arch, codename=from_codename,
                component=from_component, cache_control=DEFAULT_CACHE_CONTROL))

    def upload(self, repo, packager, codename, component):
        with deb_s3_lock():
            return subprocess.check_call(
                deb_s3_args('upload', packager.path, preserve_versions=True,
                            repo=repo, codename=codename, component=component,
                            cache_control=DEFAULT_CACHE_CONTROL))
