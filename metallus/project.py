# coding: utf-8

from __future__ import absolute_import
import re
import os
import pkg_resources
from os import path, makedirs
import urlparse

from .source import Git
from .images import Image
from .utils import sha256
from .jobs import Job
from .containers.container import CONTAINER_TEMP


GIT_URL_PATTERN = re.compile(
    r"\Agit(\+(?P<proto>\w+))?://(?P<rest>.+)\Z")
GITHUB_PATTERN = re.compile(
    r"\Agit@github.com:(?P<user>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?\Z")
SCRIPTS_DIR = os.path.abspath(pkg_resources.resource_filename(
    __name__, 'scripts'))


def _format_docker_volume(src, dest):
    return '{}:{}'.format(src, dest)


class JobNotFoundError(Exception):
    pass


class Project(object):

    def __init__(self, scm_path, home, branch, job_name):
        self.name, scm_path, scm_cls = self._parse_scm_path(scm_path)
        self.branch = branch
        self.path = path.join(home, 'projects', self.name)
        self.source = scm_cls(scm_path, self.path, branch, job_name)
        self.shared = path.join(self.path, 'shared')
        self.packages = path.join(self.path, 'packages')
        self.image_id = sha256(self.source.path)
        self.notifications = self.source.settings.get('notifications', {})

        if not path.isdir(self.shared):
            makedirs(self.shared)
        if not path.isdir(self.packages):
            makedirs(self.packages)

        # setup job objects
        self.jobs = []
        for job in self.source.settings['jobs']:
            self.jobs.append(Job(job, self.source.settings['jobs'][job]))
        jobs = [j for j in self.jobs if j.name == job_name]
        try:
            self.current_job = jobs[0]
        except IndexError:
            raise JobNotFoundError(job_name)

        self.skip_all = self.source.skip_all
        self.skip_tests = self.source.skip_tests or self.current_job.skip_tests
        self.num_commits = self.source.num_commits

        self.branch_codenames = (self.source.settings.
                                 get('packages', {}).
                                 get('branch_codenames', {}))
        self.docker_volumes = map(lambda a: _format_docker_volume(*a),
                                  [(SCRIPTS_DIR, '/scripts'),
                                   (self.source.path, CONTAINER_TEMP)])

    def _parse_scm_path(self, scm_path):
        m = GIT_URL_PATTERN.match(scm_path)
        if m:
            pth, proto = m.group('rest', 'proto')
            if proto:
                pth = "{}://{}".format(proto, pth)
            return re.sub(r"\.git\Z", "", path.basename(pth)), pth, Git
        m = GITHUB_PATTERN.match(scm_path)
        if m:
            return m.group('repo'), scm_path, Git
        raise NotImplementedError('Unrecognised SCM path: {}'.format(scm_path))

    def commit_container(self, container, stage):
        return container.commit(
            repository=self.image_name(stage),
            tag=self.source.hash,
        )

    def image_for_stage(self, stage):
        return Image(*self.image_args(stage))

    def image_name(self, stage):
        return '.'.join([self.name, self.current_job.name, stage]).lower()

    def image_args(self, stage):
        return (self.image_name(stage), self.source.current_branch)

    def tag_success(self):
        return self.source.tag_success()
