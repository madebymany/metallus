# coding: utf-8

import StringIO
import hashlib
import re
import glob
import json
import os
import sys
from urlparse import urlparse
from os import path
import shutil

from .utils import s3_deb_uri
from . import defaults

DEP_MAKEFILE_PATH = "/tmp/metallus/build_deps/"  # trailing slash is needed
MAKEFILE_NAME = "Makefile"


def get_dockerfile(project):
    if project.current_job.build_depends_target:
        return MakeDockerFile(project)
    else:
        return AptDockerFile(project,
                       project.current_job.apt_repos,
                       project.current_job.apt_keys)

class DockerFile(object):
    
    def __init__(self, project):
        self.project = project
        self.path_dir = path.join(defaults.HOME, project.path, 'image')

        if not path.isdir(self.path_dir):
            os.makedirs(self.path_dir)
        self.path = path.join(self.path_dir, 'Dockerfile')
        self.contents = StringIO.StringIO()
        self.commands = []

        self._create_manifest()
        if not path.isfile(self.path):
            self.write()

    def _create_manifest(self):
        self._add_base_image()
        self._add_environment()
        self.process_commands()

    def _add_base_image(self):
        self._write_line("FROM {0}\n".format(self.project.current_job.base))

    def _add_environment(self):
        self._write_line("ENV DEBIAN_FRONTEND noninteractive")

    def _run_commands(self, config):
        if config is not None:
            for command in config:
                self._add_command(command)

    def _copy_file(self, from_path, to_path):
        self._write_line("COPY {}".format(json.dumps([from_path, to_path])))

    def _flush_commands(self):
        if self.commands:
            self._write_line("RUN {}".format(" && ".join(self.commands)))
            self.commands = []
            
    def _add_command(self, cmd):
        self.commands.append(cmd)

    def file_exists(self):
        return path.isfile(self.path)

    def changed(self):
        if not path.isfile(self.path):
            return True

        old = hashlib.sha256(self.contents.getvalue()).digest()
        with open(self.path, "r") as f:
            current = hashlib.sha256(f.read()).digest()
        return old != current

    def write(self):
        if self.changed():
            with open(self.path, "w") as f:
                f.write(self.contents.getvalue())
            return True
        else:
            return False

    def _write_line(self, l):
        self.contents.write(l.strip() + "\n")


class AptDockerFile(DockerFile):

    def __init__(self, project, repos, keys):
        if repos is None:
            self.repos = []
        if keys is None:
            self.keys = []
        self.repos = repos
        self.keys = keys
        self._repo_hashes = []
        super(AptDockerFile, self).__init__(project)

    def process_commands(self):
        self._add_apt_keys(self.keys)
        self._add_apt_repos(self.repos)

        job = self.project.current_job
        self._install_packages(job.build_depends)
        self._flush_commands()

    def _add_apt_keys(self, keys):
        for key in self.keys:
            self._add_command("curl '{0}' | apt-key add -".format(key))

    def _add_apt_repos(self, config):
        if config is not None:
            for repo in config:
                if "s3://" in repo:
                    s3_url = s3_deb_uri(repo["architectures"],
                                        repo["access_id"],
                                        repo["secret_key"],
                                        repo["bucket"],
                                        repo["distribution"],
                                        repo["components"],
                                        repo["region"])
                    if s3_url not in self._repo_hashes:
                        self._add_command(
                            "echo '{0}' | "
                            "tee -a /etc/apt/sources.list.d/{1}.{2}.list".
                            format(s3_url, defaults.S3_HOST, repo["bucket"]))
                        self._repo_hashes.append(s3_url)
                elif "ppa:" in repo:
                    self._add_command("add-apt-repository -y \"{0}\"".
                                      format(repo))
                else:
                    self._add_command(
                        "echo '{0}' | "
                        "tee -a /etc/apt/sources.list.d/{1}.list".
                        format(repo, self._apt_repository_filename(repo)))

    def _apt_repository_filename(self, repo):
        found = False
        filename = []
        for v in repo.split(" "):
            url = urlparse(v)
            if found is True:
                filename.append(v)
            if url.netloc is not "":
                found = True
                filename.append(url.netloc)
        return "-".join(filename)

    def _add_repositories(self, config):
        if config is not None:
            for repo in config:
                if repo.get("type", "") == "s3":
                    s3_url = s3_deb_uri(repo["architectures"],
                                        repo["access_id"],
                                        repo["secret_key"],
                                        repo["bucket"],
                                        repo["distribution"],
                                        repo["components"],
                                        repo["region"])
                    if s3_url not in self._repo_hashes:
                        self._add_command(
                            "echo '{0}' | "
                            "tee -a /etc/apt/sources.list.d/{1}.{2}.list".
                            format(s3_url, defaults.S3_HOST, repo["bucket"]))
                        self._repo_hashes.append(s3_url)
                else:
                    url = repo["url"]
                    if "ppa:" in url:
                        self._add_command("add-apt-repository -y \"{0}\"".
                                          format(repo["url"]))
                    else:
                        self._add_command("echo 'deb {0} {1} {2}' | tee /etc/apt/sources.list.d/{3}.list".
                            format(url, repo["distribution"],
                            repo["components"], urlparse(url).netloc))

                if "key" in repo.iterkeys():
                    self._add_command(
                        "apt-key adv --keyserver keys.gnupg.net "
                        "--recv-keys {}".format(repo["key"]))


    def _install_packages(self, config):
        if config is not None:
            packages = []
            for software in config:
                if type(software) is dict:
                    if "selections" in software:
                        for s in software["selections"]:
                            self._add_command(
                                "echo '{0} {1}' | debconf-set-selections".
                                format(software["name"], s))
                    packages.append(software['name'])
                else:
                    packages.append(software)
            if packages:
                self._add_apt_update()
                self._add_command(
                    "apt-get install -qy {}".
                    format(' '.join("'{}'".format(p) for p in packages)))

    def _add_apt_update(self):
        self._add_command("apt-get update -qq")


class MakeDockerFile(DockerFile):

    def __init__(self, project):
        self.paths = []
        super(MakeDockerFile, self).__init__(project)

    def expand_make_file(self, prefix, path):
        with open(os.path.join(prefix, path), "r") as f:
            p = re.compile('^include\s+([\*\.\/\S]+)')
            for l in f:
                m = p.match(l)
                if m is not None:
                    g = m.group(1)
                    all_make_files = glob.glob(os.path.join(prefix, g))

                    for mp in all_make_files:
                        d = os.path.dirname(mp)
                        d = d.split(prefix)[1].strip("/")
                        if d not in self.paths:
                            self.paths.append(d)
                        self.expand_make_file(prefix, mp)

    def process_commands(self):
        job = self.project.current_job

        tmp_path = os.path.join(self.path_dir, "src")
        if os.path.exists(tmp_path):
            shutil.rmtree(tmp_path, True)

        shutil.copytree(self.project.source.path, tmp_path)
        prefix = os.path.join(tmp_path, job.start_in)
        self.expand_make_file(prefix, "Makefile")
        for v in self.paths:
            self._copy_file(path.join("src", v), path.join(DEP_MAKEFILE_PATH, v))

        self._copy_file(path.join("src", job.start_in, "Makefile"),
                        DEP_MAKEFILE_PATH)

        self._add_command("cd '{}' && make '{}'".
                          format(DEP_MAKEFILE_PATH,
                                 job.build_depends_target))
        self._flush_commands()
