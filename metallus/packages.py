# coding: utf-8

from __future__ import print_function

from datetime import datetime
from os import path
import os
import shutil
import subprocess
import time
import traceback

from .containers.container import Container, CONTAINER_HOME, CONTAINER_TEMP, \
    CONTAINER_SOURCE
from . import publishers

PACKAGES_SCRIPTS_ROOT = "metallus/packages"


class RepoManifest(object):

    def __init__(self, publisher, repo, codename, component, arch):
        self.publisher = publisher
        self.repo = repo
        self.codename = codename
        self.component = component
        self.arch = arch
        self._index_manifest()

    def _list_publisher(self):
        return self.publisher.list(repo=self.repo, codename=self.codename,
                                   component=self.component, arch=self.arch)

    def _index_manifest(self):
        self._package_git_commits_to_version = {}
        for fields in self._list_publisher():
            if 'Git-Commit-Id' in fields:
                self._package_git_commits_to_version[
                    (fields['Package'], fields['Git-Commit-Id'])] = \
                    fields['Version']

    def version_for_package_git_commit(self, package_name, git_commit_id):
        return self._package_git_commits_to_version.get(
            (package_name, git_commit_id))


class PackageManager(object):

    def __init__(self, project, repos, codename, config, package_name=None,
                 override_repo=None):
        self.project = project
        self.config = config
        self.packages = [Packager(self, self.project, p, repos,
                                  config.publishers,
                                  override_repo=override_repo)
                         for p in self.project.current_job.packages
                         if package_name is None or p['name'] == package_name]
        self.repos = repos
        self.repo_manifests = {}
        self.codename = codename
        self.component = 'main'  # TODO: maybe make this configurable?
        self.source_commit_id = project.source.hash

    @property
    def should_package(self):
        return bool(self.codename)

    @property
    def any_need_packaging(self):
        return any(p.needs_packaging for p in self.packages)

    def promote_possible_packages(self):
        # Return remaining ones
        out_packages = set(self.packages)
        for package in self.packages:
            if self.promote(package):
                out_packages.remove(package)
        return out_packages

    def package(self, image, packages=None):
        for package in packages or self.packages:
            self._run_packager(package, image)
        try:
            image.remove()
        except Exception as e:
            print(e)

    def promote(self, packager):
        if all(self._get_package_version(packager, r, self.codename,
                                         self.component)
               for r in packager.repos):
            print("{} package already uploaded for commit {}".format(
                packager.name, self.source_commit_id))
            return True

        # TODO: maybe if the package exists in a proper subset of the repos,
        # download it and upload it to the others? Currently we do a full
        # rebuild if it doesn't exist in all of them.
        from_codenames = packager.codenames_promoting_from(self.codename)
        if not from_codenames:
            print("No codename found to promote from")
            return False

        package_versions = [(cn, v) for cn, v in [
            (cn, self._get_package_version(packager, rn, cn))
            for cn in from_codenames
            for rn in packager.repos
        ] if v]
        if package_versions:
            from_codename, package_version = package_versions[0]
        else:
            print("Existing package not found in repository; building")
            return False
        if not all(v == package_version for _, v in package_versions):
            print("Inconsistent package versions found for commit; rebuilding")
            return False

        print("No need to build, version {version} found. "
              "Copying from {from_codename} to {to_codename}...".
              format(version=package_version, from_codename=from_codename,
                     to_codename=self.codename))

        packager.publisher_copy(
            to_codename=self.component, to_component=self.component,
            versions=[package_version], from_codename=from_codename,
            from_component=self.component)

        return True

    def upload(self, package):
        if not self.codename:
            raise TypeError("Expected codename to be present; not {!r}".
                            format(self.codename))
        package.publisher_upload(self.codename, self.component)
        print('uploaded package')
        print(' name : {}'.format(package.name))
        print(' version : {}'.format(package.version))

    def _run_packager(self, packager, image):
        try:
            if packager.package(image):
                self.upload(packager)
            else:
                print("skipping package build; no changes found")
        finally:
            if os.path.isfile(packager.path):
                os.remove(packager.path)

    def _get_repo_manifest(self, publisher, repo_name, codename, component,
                           arch):
        # defaultdict doesn't cope with tuple keys, for some reason. Says
        # zero arguments have been passed in.
        mkey = (publisher.package_type, repo_name, codename, component, arch)
        if mkey in self.repo_manifests:
            return self.repo_manifests[mkey]
        else:
            print("Getting manifest for {repo_name} {codename}...".
                  format(**locals()))
            m = RepoManifest(publisher, self.repos[repo_name], codename,
                             component, arch)
            self.repo_manifests[mkey] = m
            return m

    def _get_package_version(self, packager, repo_name, codename,
                             component):
        return self._get_repo_manifest(packager.publisher, repo_name,
                                       codename, component, packager.arch). \
            version_for_package_git_commit(packager.name,
                                           self.source_commit_id)


class Packager(object):

    def __init__(self, manager, project, config, repos_config,
                 publisher_config, override_repo=None):
        self.config = config
        self.name = self.config['name']

        try:
            self.type = config['type']
        except KeyError:
            self.type = 'debian'
            print("Warning: defaulting {} package to type '{}'".
                  format(self.name, self.type))

        self.publisher = publishers.get_publisher(publisher_config, self.type)
        self.manager = manager
        self.project = project
        self.start_in = project.current_job.start_in
        self.repos = ([override_repo] if override_repo
                      else self.config['repos'])
        try:
            self.repo_dicts = [repos_config[r] for r in self.repos]
        except KeyError as e:
            raise Exception("Given APT repository {} not found in config".
                            format(e))

        self.config['architecture'] = 'amd64'  # TODO: detect this somehow
        version_epoch = config.get('version_epoch')
        self.version = config.get(
            'version', '{}{}-{}'.format(
                str(version_epoch) + ":" if version_epoch else "",
                datetime.now().strftime('%Y%m%d%H%M%S'),
                self.project.source.hash))
        self.directory = os.path.join(self.project.packages,
                                      self.project.source.current_branch,
                                      self.name)
        self.description = self.config.get('description',
                                           'no description provided')
        self.path = '{}/{}-{}.deb'.format(self.project.packages,
                                          self.config['name'],
                                          self.version)

        self._needs_packaging = None
        files_config = self.config.get('files')
        if files_config:
            self.files_root = \
                self._process_files_path(files_config.get('root'))
            self.files_include = map(self._process_files_path,
                                     files_config.get('include', []))
            self.files_exclude = map(self._process_files_path,
                                     files_config.get('exclude', []))
        else:
            self._needs_packaging = True

    @property
    def needs_packaging(self):
        if self._needs_packaging is None:
            include = self.files_include + \
                [os.path.join(PACKAGES_SCRIPTS_ROOT, self.name) + "/"]
            self._needs_packaging = self.project.source.path_has_changes(
                self.files_root, include=include, exclude=self.files_exclude)
        return self._needs_packaging

    @property
    def arch(self):
        return self.config['architecture']

    def codenames_promoting_from(self, to_codename):
        promote_through = self.config.get('promote_through', [])[:]
        if promote_through:
            try:
                i = promote_through.index(to_codename)
            except ValueError:
                return None
            else:
                del promote_through[i]
                return promote_through

    def package(self, image):
        if not self.needs_packaging:
            return False

        self.clean()
        if self.config.get('copy_diff', True):
            self.copy(image)
        self.debian_scripts()
        self.fpm()
        return True

    def clean(self):
        print("cleaning package directory {}".format(self.directory))
        if os.path.isdir(self.directory):
            shutil.rmtree(self.directory)
        time.sleep(2)
        if not os.path.isdir(self.directory):
            os.makedirs(self.directory)

    def copy(self, image):
        container = self._create_container(image)
        try:
            if container.status > 0:
                raise PackageException(container.status)
            if self.config['target']:
                container.copy_diff(self.directory)
        except Exception:
            print("Removing container before raising:")
            traceback.print_exc()
            raise
        finally:
            container.remove()

    def publisher_copy(self, to_codename, to_component, from_codename,
                       from_component, versions):
        if isinstance(versions, basestring):
            versions = versions.split(' ')
        for r in self.repo_dicts:
            self.publisher.copy(
                repo=r, packager=self, to_codename=to_codename,
                to_component=to_component, from_codename=from_codename,
                from_component=from_component, versions=versions)

    def publisher_upload(self, codename, component):
        for r in self.repo_dicts:
            self.publisher.upload(r, self, codename, component)

    def fpm(self):
        paths = []
        for name in os.listdir(self.directory):
            paths.append(name)
        if len(paths) == 0:
            paths.append(self.directory)
        args = ['fpm'] + \
            list(self.get_dependencies(self.config.get('depends', []))) + \
            list(self.get_conflicts(self.config.get('conflicts', []))) + \
            list(self.get_replaces(self.config.get('replaces', []))) + \
            self.debian_scripts() + \
            list(self.activates()) + \
            list(self.interests()) + \
            ['-C', self.directory,
             '--deb-field', "Git-Commit-Id: {}".
                format(self.project.source.hash),
             '-t', 'deb',
             '-s', 'dir',
             '--architecture', self.arch,
             '-n', self.config['name'],
             '-p', self.path,
             '-v', str(self.version)] + paths
        subprocess.call(args)

    def debian_scripts(self):
        args = []
        scripts = {'postinst': '--post-install',
                   'prerm': '--pre-uninstall',
                   'preinst': '--pre-install',
                   'postrm': '--post-uninstall'}
        for k, v in scripts.iteritems():
            path = os.path.join(self.project.source.path,
                                PACKAGES_SCRIPTS_ROOT, self.name, k)
            if os.path.isfile(path):
                args.append(v)
                args.append(path)
        return args

    def interests(self):
        for interest in self.config.get('interests', []):
            yield '--deb-interest'
            yield interest

    def activates(self):
        for activate in self.config.get('activates', []):
            yield '--deb-activate'
            yield activate

    def get_dependencies(self, dependencies):
        for d in dependencies:
            yield '-d'
            yield d

    def get_conflicts(self, conflicts):
        for d in conflicts:
            yield '--conflicts'
            yield d

    def get_replaces(self, replaces):
        for d in replaces:
            yield '--replaces'
            yield d

    def _process_files_path(self, p):
        if p is None:
            return self.start_in
        elif p.startswith('/'):
            return p[1:]
        else:
            return path.join(self.start_in, p)

    def _create_container(self, image):
        c = Container(image,
                      ['/bin/bash /scripts/make-install'],
                      env={'HOME': CONTAINER_HOME,
                           'TARGET': self.config['target'],
                           'SOURCE_ROOT': CONTAINER_SOURCE,
                           'TEMP_ROOT': CONTAINER_TEMP,
                           'START_IN': self.project.current_job.start_in},
                      volumes=self.project.docker_volumes)
        c.start()
        return c


class PackageException(Exception):
    def __init__(self, status):
        self.status = status

    def __str__(self):
        return repr(self.status)
