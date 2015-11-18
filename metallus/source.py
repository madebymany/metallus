# coding: utf-8

from os import path
import re
from fnmatch import fnmatch
import urlparse

import git

from . import utils


CI_SKIP_PATTERN = re.compile(r"(?<!\\)\[ci skip\]", re.IGNORECASE)
CI_SKIP_TESTS_PATTERN = re.compile(r"(?<!\\)\[ci skip([-_\s]tests)?\]",
                                   re.IGNORECASE)
MAX_COMMIT_LOG = 50


def _changed_paths(diffs):
    def gen():
        for d in diffs:
            if d.a_blob:
                yield d.a_blob.path
            if d.b_blob:
                yield d.b_blob.path
    return set(gen())


def _path_is_prefix(prefix, p):
    if prefix.endswith('/'):
        return p.startswith(prefix)
    else:
        return fnmatch(p, prefix)


class Git(object):

    EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    LAST_BUILD_TAG_FORMAT = "metallus.{branch}.last-successful-build"

    def __init__(self, url, fn, branch, job):
        self._path = path.join(fn, "src", branch, job)
        self.url = url
        self._repo = None
        self._changed_paths = None

        self.job = job
        self._settings = None
        self.checkout(branch)

    @property
    def path(self):
        return self._path

    @property
    def hash(self):
        return self._repo.head.commit.hexsha

    @property
    def settings(self):
        if not self.current_branch:
            raise Exception("you must set the current_branch property "
                            "of the object: this can be done with the "
                            "checkout function")
        if self._settings is None:
            self._settings = utils.deserialise(path.join(self.path,
                                                         "metallus.yml"))
        return self._settings

    def path_has_changes(self, root, include=None, exclude=None):
        if not root.endswith('/'):
            root += '/'

        if self._changed_paths is True:
            return True
        elif self._changed_paths:
            if 'metallus.yml' in self._changed_paths:
                return True
            return any((_path_is_prefix(root, p) or
                        any(_path_is_prefix(q, p) for q in include or [])) and
                       all(not _path_is_prefix(r, p) for r in exclude or [])
                       for p in self._changed_paths)
        else:
            return False

    @property
    def last_build_tag_name(self):
        return Git.LAST_BUILD_TAG_FORMAT.format(branch=self.current_branch)

    def checkout(self, branch):
        self.skip_all = False
        self.skip_tests = False
        self.num_commits = 0
        self.current_branch = branch

        if path.isdir(path.join(self.path, ".git")):
            self._repo = git.Repo(self.path)
            self._changed_paths = None
        else:
            self._repo = git.Repo.clone_from(self.url, self.path + "/",
                                             recursive=True)
            self._changed_paths = True  # "everything"
        repo = self._repo

        repo.remotes.origin.fetch()

        repo.head.reset(index=True, working_tree=True)
        new_ref = getattr(repo.branches, branch, None)
        if new_ref:
            new_ref.checkout()
        else:
            getattr(repo.remotes.origin.refs, branch).checkout(b=branch)
        repo.head.reset(index=True, working_tree=True,
                        commit=getattr(repo.remotes.origin.refs,
                                       branch))
        repo.submodule_update(recursive=True, init=True, force_remove=True,
                              force_reset=True)

        last_build_tag = getattr(repo.tags, self.last_build_tag_name, None)
        last_successful_commit = (last_build_tag.commit if last_build_tag
                                  else Git.EMPTY_TREE_HASH)

        self._changed_paths = _changed_paths(
            repo.head.commit.diff(last_successful_commit))
        commits = list(self._iter_commits_until(last_successful_commit))
        self.num_commits = len(commits)
        self.commits = commits
        self.skip_all = all(CI_SKIP_PATTERN.search(c.summary)
                            for c in commits)
        self.skip_tests = all(CI_SKIP_TESTS_PATTERN.search(c.summary)
                              for c in commits)
        if len(self.commits) > 0:
            self.author = self.commits[0].author
        else:
            self.author = ""

    def log_commits(self):
        r = list(self.commits)
        l = len(r)
        if l > MAX_COMMIT_LOG:
            return (r[0:MAX_COMMIT_LOG], True)
        return (r, False)

    def format_commits(self):
        def mklink(c):
            github_base_url = self.settings.get('github_base_url')
            if github_base_url is not None and \
                    not github_base_url.endswith("/"):
                github_base_url += "/"
            return u"<{}|{}>".format(
                unicode(urlparse.urljoin(github_base_url,
                                         "/".join(["commit", c.hexsha]))),
                unicode(c.summary))

        commits, truncated = self.log_commits()

        msg = u"\n".join(u"• {} ({})".
                         format(mklink(c), c.author.name)
                         for c in commits)
        if truncated:
            msg += u"\ntruncated....."
        return msg

    def tag_success(self):
        self._repo.create_tag(self.last_build_tag_name, force=True)

    def _iter_commits_until(self, until_commit):
        for c in self._repo.iter_commits():
            if c == until_commit:
                break
            yield c
