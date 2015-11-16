# coding: utf-8

from __future__ import print_function
from __future__ import absolute_import
from .containers.build import BuildContainer


class Builder(object):
    def __init__(self, config, image, job, builder, project):
        self.job = job
        self.builder = builder
        self.image = image
        self.project = project
        self.ssh_dir = config.get('ssh_dir', None)
        self.container = None
        self.result_image = None

    def remove(self):
        if self.container:
            self.container.remove()
            self.container = None

    def build(self):
        container = BuildContainer(self.project, self.image, self.builder,
                                   self.ssh_dir)
        self.container = container

        print('Building...')
        container.start()
        if container.success:
            self.result_image = container.commit(self.project)
        else:
            raise BuildException(container.status)

    def __enter__(self):
        return self.result_image

    def __exit__(self, *args):
        self.remove()


class BuildException(Exception):
    def __init__(self, status):
        self.status = status

    def __str__(self):
        return repr(self.status)
