# coding: utf-8

import copy
import yaml
from os import path
import hashlib

import docker.utils

from . import defaults


def new_docker_client():
    kwargs = docker.utils.kwargs_from_env()
    if len(kwargs.keys()) == 0:
        kwargs['base_url'] = "unix:///var/run/docker.sock"
    else:
        kwargs['tls'].assert_hostname = False
    kwargs['version'] = "1.21"
    return docker.APIClient(timeout=120, **kwargs)


def s3_host(region):
    if region and region != "us-east-1":
        return defaults.REGION_S3_HOST.format(region)
    else:
        return defaults.S3_HOST


def s3_deb_uri(arch, access_id, secret_key, bucket, distribution,
               components, region=None):
    values = copy.deepcopy(locals())
    values['s3_host'] = s3_host(region)
    return "deb [arch={arch}] " \
        "s3://{access_id}:[{secret_key}]@{s3_host}/{bucket} " \
        "{distribution} {components}".format(**values)


def deserialise(fn):
    if not path.isfile(fn):
        raise IOError("the provided metallus config file does not exist: {0}".
                      format(fn))
    with file(fn) as stream:
        return yaml.load(stream)


def sha256(val):
    m = hashlib.sha256()
    m.update(val)
    return m.hexdigest()


def merge(a, b):
    '''recursively merges dict's. not just simple a['key'] = b['key'], if
    both a and bhave a key who's value is a dict then dict_merge is called
    on both values and the result stored in the returned dictionary.'''
    if not isinstance(b, dict):
        return b
    result = copy.deepcopy(a)
    for k, v in b.iteritems():
        if k in result and isinstance(result[k], dict):
                result[k] = merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result
