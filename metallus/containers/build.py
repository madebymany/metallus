# coding: utf-8

from .container import Container, CONTAINER_BASE_DIR
import os
import pkg_resources
from metallus.utils import sha256
from os.path import expanduser

CONTAINER_SCRIPTS_DIR = "/scripts"


class BuildContainer(Container):
    def __init__(self, project, image, builder, ssh_dir):
        self.user = 'root'
        self.project = project
        self.image = image
        self.start_in = self.project.current_job.start_in
        self.persisted_volumes = []
        self.volumes = []
        self.ssh_dir = ssh_dir

        # Container paths
        self.home = '{}/build'.format(CONTAINER_BASE_DIR)
        self.source = '{}/src'.format(self.home)
        self.config = '{}/config'.format(self.home)
        self.tmp = '{}/tmp'.format(CONTAINER_BASE_DIR)
        self.shared = '{}/shared'.format(CONTAINER_BASE_DIR)

        self.builder = builder

        self._set_scripts_dir()
        self._set_volumes()

        self._set_cmds()
        env = {'METALLUS_HOME': self.home, 'SOURCE_ROOT': self.source,
               'TEMP_ROOT': self.tmp, 'START_IN': self.start_in}
        if self.project.skip_tests:
            env['SKIP_TESTS'] = "true"
        if len(self.project.current_job.tests) > 0:
            env['TESTS'] = " ".join(self.project.tests)

        # TODO worry about the order of overrides here, branch env vars should
        # override job env vars

        job_env = self.project.current_job.environment
        for key, value in job_env.iteritems():
            if key == "branches":
                if self.project.branch in job_env[key].keys():
                    for key, value in \
                            job_env[key][self.project.branch].iteritems():
                        env[key] = value
            else:
                env[key] = value

        super(BuildContainer, self).__init__(
            self.image, ['/bin/bash -c "{}"'.format('; '.join(self.cmds))],
            env=env, volumes=self.volumes)

    def container_script(self, script):
        return os.path.join(CONTAINER_SCRIPTS_DIR, script)

    def commit(self, project):
        return super(BuildContainer, self).commit(project, 'build')

    def _set_cmds(self):
        self.cmds = ['set -e']

        self.cmds.append(
            'mkdir -p "{}" "{}" "{}"'.format(self.home, self.source, self.tmp))
        self.cmds.append(
            'source "{}"'.format(self.container_script('persist')))
        self.cmds.append('sync "{}/" "{}"'.format(self.tmp, self.source))

        # Copy persisted folders in before build
        for hash, folder, path, host_path in self.persisted_volumes:
            self.cmds.append('sync "{0}/" "{1}"'.format(host_path, folder))

        # run builder
        self.cmds.append(
            '/bin/bash < "{}"'.format(self.container_script(self.builder)))

        # Sync persisted folders back to host
        for hash, folder, path, host_path in self.persisted_volumes:
            self.cmds.append('sync "{0}/" "{1}"'.format(folder, host_path))

    def _set_volumes(self):
        self._create_persistent_volumes()
        self.volumes.append(
            self._get_volume(self.scripts_dir, CONTAINER_SCRIPTS_DIR))
        self.volumes.append(
            self._get_volume(self.project.source.path, self.tmp))
        if self.ssh_dir is None:
            self.volumes.append(self._get_volume('/root/.ssh'))
        else:
            self.volumes.append(
                self._get_volume(expanduser(self.ssh_dir), '/root/.ssh'))

    def _create_persistent_volumes(self):
        for folder in self.project.current_job.persist:
            hash = sha256(folder)
            path = os.path.join(self.project.shared,
                                self.project.source.current_branch,
                                self.project.current_job.name,
                                hash)
            if not os.path.isdir(path):
                os.makedirs(path)
            host_path = os.path.join(self.shared, hash)
            t = hash, folder, path, host_path
            self.persisted_volumes.append(t)
            self.volumes.append(self._get_volume(path, host_path))

    def _get_volume(self, src, dest=None):
        if dest is None:
            dest = src
        return '{0}:{1}'.format(src, dest)

    def _set_scripts_dir(self):
        self.scripts_dir = os.path.abspath(
            pkg_resources.resource_filename('metallus', 'scripts'))
        if not os.path.exists(os.path.join(self.scripts_dir, self.builder)):
            raise Exception(
                'builder {0} does not exists'.format(self.builder))
