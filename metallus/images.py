# coding: utf-8

from __future__ import print_function
import subprocess
import docker

from .utils import new_docker_client
from docker.errors import APIError


def get_repository_name(project, stage):
    return '.'.join([project.name, project.current_job.name, stage]).lower()

def get_tag_with_hash(tag, hash):
    return "{}-{}".format(tag, hash)
            
class Image(object):
    def __init__(self, repository, tag):
        self.repository = repository
        self.tag = tag 
        self.client = new_docker_client()
        self.old_versions = []
        self._fetch_docker_image()

    @property
    def id(self):
        return self.docker_image['Id']

    @property
    def repo_tag(self):
        if self.tag:
            return "{}:{}".format(self.repository, self.tag)
        else:
            return self.repository
        
    def create_image(self, dockerfile):
        for i in self.old_versions: 
            image_id = i['Id']
            try:
                self.client.remove_image(image_id)
            except APIError as e:
                print("couldn't delete docker image {}".format(image_id))
        try:
            if not self.docker_image:
                print("creating image {0}".format(self.repo_tag))
                subprocess.check_call(
                    ['docker', 'build', '--rm', '-t', self.repo_tag, '.'],
                    cwd=dockerfile.path_dir)
                self._fetch_docker_image()
        except Exception as e:
            print("failed creating image {0}".format(self.repo_tag))
            raise e

    def exists(self):
        return bool(self.docker_image)

    def remove(self):
        self.client.remove_image(self.docker_image['Id'])

    def _fetch_docker_image(self):
        images = self.client.images(name=self.repository)
        self.docker_image = next(
        (i for i in images
         if self.repo_tag in i['RepoTags']),
        None)
        if not self.docker_image:
            self.old_versions = images


class ImageDoesNotExistError(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return repr("Image '{0}' not found".format(self.name))
