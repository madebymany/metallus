# coding: utf-8

from os import path


class Job:

    def __init__(self, name, values):
        self.name = name
        self.start_in = values.get('start_in', '')
        self.apt_keys = values.get('apt_keys', [])
        self.apt_repos = values.get('apt_repos', [])
        self.images = values.get('images', [])
        self.base = values.get('base', None)
        self.persist = values.get('persist', [])
        self.environment = values.get('environment', {})
        self.build_depends = values.get('build_depends', [])
        self.build_depends_target = values.get('build_depends_target', None)
        self.packages = values.get('packages', [])
        self.skip_tests = values.get('skip_tests', False)
        self.tests = values.get('tests', [])
        if 'builder' not in values:
            raise JobPropertyNoneException(
                "you must provide the 'builder' property "
                "in your metallus file")
        self.build_type = values.get('builder', None)
        self._load_dockerfile()

    def _load_dockerfile(self):
        path_values = []
        if self.start_in is not None:
            path_values.append(self.start_in)
        path_values = path_values + ['metallus', 'build', self.name]
        dockerfile_path = path.join(*path_values)
        self.dockerfile = None
        if path.isfile(dockerfile_path):
            with open(dockerfile_path, 'r') as f:
                self.docker_file = f.read()


class JobPropertyNoneException(Exception):
    pass
