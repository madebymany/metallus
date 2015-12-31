# coding: utf-8

from __future__ import print_function
import argparse
import sys
import os
from os import path

from .builders import Builder, BuildException
from .dockerfile import get_dockerfile
from .config import Config
from .project import Project
from .images import Image, get_tag_with_hash, get_repository_name
from .packages import PackageManager
from .notifications import NotificationManager
from os.path import expanduser


def run():
    Command()()


class HumanError(Exception):
    pass


class Command(object):

    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-v', '--verbosity', type=int,
                            help="increase output verbosity")
        parser.add_argument('command')

        required, extra = parser.parse_known_args()

        self.command = required.command
        self.config = Config()

        self.notifier = NotificationManager(
            self.config.notifications)
        self.home = expanduser(self.config.defaults["home"])
        if not path.isdir(self.home):
            os.makedirs(self.home)
        os.chdir(self.home)

        self.args = extra

    def __call__(self):
        self.method_for_command(self.command)(self.args)

    def method_for_command(self, command):
        def command_not_found(_):
            raise Exception("{0} command not found".format(command))
        return {
            "build": self.build,
            "dist": self.dist,
        }.get(command, command_not_found)

    def _gen_notification_context(self):
        context = self.project.notifications
        context["project"] = self.project.name
        context["author"] = self.project.source.author
        context["branch"] = self.project.source.current_branch
        context["changelog"] = self.project.source.format_commits()
        context["job"] = self.project.current_job.name
        return context

    def _set_project_from_args(self, args):
        self.project = Project(args.git_url, self.home, args.branch, args.job)
        if args.skip_tests:
            self.project.skip_tests = True

    def _set_package_manager_from_args(self, args):
        self.package_manager = PackageManager(
            self.project, self.config.repos, args.codename,
            self.config, args.package, override_repo=args.repo)

    def parse_build_args(self, args):
        parser = argparse.ArgumentParser()
        parser.add_argument("git_url")
        parser.add_argument("job")
        parser.add_argument("branch")
        parser.add_argument("-p", type=bool, default=False)
        parser.add_argument("--skip-tests", action='store_true')
        args = parser.parse_args(args)
        self._set_project_from_args(args)
        return args

    def parse_package_args(self, args):
        parser = argparse.ArgumentParser()
        parser.add_argument("git_url")
        parser.add_argument("job")
        parser.add_argument("branch")
        parser.add_argument("--codename", help="e.g. unstable, stable")
        parser.add_argument("--or-just-build", action='store_true')
        parser.add_argument("--skip-tests", action='store_true')
        parser.add_argument("--package", help="e.g. my-package-name",
                            default=None)
        parser.add_argument("--repo", help="override APT repository "
                            "to upload to", default=None)
        args = parser.parse_args(args)
        self._set_project_from_args(args)
        if not args.codename:
            args.codename = self.project.branch_codenames.get(args.branch)
        self._set_package_manager_from_args(args)
        return args

    def build(self, args):
        args = self.parse_build_args(args)
        return self._build(args)

    def _build(self, args):
        if self.project.current_job.dockerfile is not None:
            raise NotImplementedError("build the dockerfile")
        dockerfile = get_dockerfile(self.project)
        tag = get_tag_with_hash(self.project.source.current_branch, dockerfile.hash())
        repository = get_repository_name(self.project, "build-deps")
        image = Image(repository, tag)
        image.create_image(dockerfile)

        builder = Builder(self.config.defaults, image,
                          self.project.current_job,
                          self.project.current_job.build_type, self.project)
        try:
            builder.build()
            #self.notifier.run_hook("build-success",
            #                       self._gen_notification_context())
            return builder
        except BuildException as ex:
            builder.remove()
            #self.notifier.run_hook("build-failure",
            #                       self._gen_notification_context())
            self.die("failed to build project {}; "
                     "build exited with '{}'".format(self.project.name,
                                                     ex.status))

    def _package(self, *args, **kwargs):
        self.package_manager.package(*args, **kwargs)

    def dist(self, args):
        args = self.parse_package_args(args)
        try:
            if self.project.skip_all:
                if self.project.num_commits == 0:
                    print("No new commits")
                print("Skipping everything.")
                return

            if self.package_manager.should_package:
                print("Promoting packages if possible...")
                unpromoted_packages = \
                    self.package_manager.promote_possible_packages()
                if unpromoted_packages:
                    if self.package_manager.any_need_packaging:
                        print("Some package(s) couldn't be promoted, " +
                              "build required")
                        with self._build(args) as image:
                            print("Packaging and uploading remaining packages")
                            self._package(image, unpromoted_packages)
                    else:
                        print("No packaging required; all done")
            elif args.or_just_build:
                print("No APT codename configured for the '{}' branch; " +
                      "just building".format(args.branch))
                self._build(args).remove()
            else:
                raise HumanError(
                    "no configuration found to package '{}' branch".format(
                        args.branch))

        except HumanError as e:
            self.die(e.message)
        else:
            self.project.tag_success()

    def die(self, msg):
        print("fatal: " + msg)
        sys.exit(1)
