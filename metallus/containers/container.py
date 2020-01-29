# coding: utf-8

from __future__ import print_function

from distutils import dir_util
import errno
import os
import os.path
import shutil
import tarfile
import threading
import time

from ..images import Image, get_repository_name
from ..utils import new_docker_client

CONTAINER_BASE_DIR = '/.metallus'
CONTAINER_HOME = '{}/build'.format(CONTAINER_BASE_DIR)
CONTAINER_TEMP = '{}/tmp'.format(CONTAINER_BASE_DIR)
CONTAINER_SOURCE = '{}/src'.format(CONTAINER_HOME)

COPY_THREADS = 10


class Container(object):

    def __init__(self, image, cmd, env=None, volumes=None,
                 tty=False, detached=False, folders=None,
                 user='root'):

        self.client = new_docker_client()
        self.image = image
        self.volumes = volumes
        self.mounts = [x.split(':')[1] for x in volumes]
        self.bindings = dict(map(lambda s: s.split(':'), self.volumes))
        self.tty = tty
        self.user = user
        self.cmd = " ".join(cmd)
        self.env = env
        self.folders = folders
        self.docker_default_directories = \
            ['dev', '.metallus', '.wh..wh.aufs', '.wh..wh.plnk',
             '.wh..wh.orph', 'tmp']
        self.directory = None
        self.status = None

    def start(self):
        self.container = self.client.create_container(self.image.id,
                                                      user=self.user,
                                                      command=self.cmd,
                                                      environment=self.env,
                                                      volumes=self.mounts,
                                                      host_config=create_host_config(privileged=True, binds=self.bindings))
        self.container_id = self.container['Id']

        self.client.start(self.container)

        for line in self.client.logs(self.container, stdout=True, stderr=True,
                                     stream=True):
            print(line.strip())

        self.stop()
        self.status = int(
            self.client.inspect_container(self.container)['State']['ExitCode'])

        root_dir = next(v for k, v in self.client.info()['DriverStatus']
                        if k == "Root Dir")
        self.directory = os.path.join(root_dir, 'diff', self.container_id)

    def stop(self):
        self.client.stop(self.container_id)
        self.client.kill(self.container_id)

    def remove(self):
        self.client.remove_container(self.container_id, force=True)

    def copy_diff(self, dest):
        if self._has_aufs_diff:
            self._copy_from_aufs(dest)
        else:
            self._copy_from_docker_api(dest)

    def _copy_from_docker_api(self, dest):
        print("Copying package data from container through Docker...")

        def copy_thread(files):
            for f in files:
                self._copy_file_from_docker_api(f, dest)

        time_started = time.time()
        threads = []
        diff = list(self.diff())
        if len(diff) >= (COPY_THREADS * 5):
            n = max(1, len(diff) // COPY_THREADS)
            for i in xrange(0, len(diff), n):
                t = threading.Thread(
                    target=copy_thread, args=(diff[i:i+n],))
                t.start()
                threads.append(t)
            for t in threads:
                t.join()
        else:
            copy_thread(diff)

        print("Time taken: {}s".format(time.time() - time_started))

    def _copy_from_aufs(self, dest):
        print("Copying package data from container through AUFS...")

        dir_util.copy_tree(self.directory, dest, preserve_symlinks=True)
        for d in self.docker_default_directories:
            path = os.path.join(dest, d)
            if os.path.exists(path):
                os.chmod(path, 0777)
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)

    def _copy_file_from_docker_api(self, src, dest):
        if not os.path.isabs(src):
            raise Exception("src must be an absolute path")

        path = os.path.normpath(dest + src)
        dest_dir = os.path.dirname(path)
        try:
            os.makedirs(dest_dir)
        except OSError as e:
            if not e.errno == errno.EEXIST:
                raise

        with self.client.copy(self.container_id, src) as src_f, \
                tarfile.open(fileobj=src_f, mode='r|') as tar:
            tar.extractall(dest_dir)

        if os.path.exists(path):
            os.chmod(path, 0o777)

    def diff(self):
        prev = ''
        for p in reversed(map(lambda y: y['Path'],
                              filter(lambda x: x['Kind'] != 2,
                              self.client.diff(self.container_id)))):
            if not prev.startswith(p + '/') and \
               p not in self.docker_default_directories:
                yield p
            prev = p

    def commit(self, project, stage):
        repository = get_repository_name(project, 'build')
        tag = project.source.current_branch
        self.client.commit(self.container_id, repository=repository,
                           tag=tag)
        return Image(repository, tag)

    @property
    def success(self):
        return self.status == 0

    @property
    def _has_aufs_diff(self):
        return self.directory and os.path.isdir(self.directory)
