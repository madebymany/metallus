## Metallus 
![Metallus](https://s3-eu-west-1.amazonaws.com/metallus/metallus_72.jpg)


## What is it?

A build and Debian packaging tool.

* build projects inside Docker containers.
* package GitHub projects into debs.
* manage Debian repositories

Metallus is responsible for pulling from a Git repository to the local machine, checking out the requested branch, determining if it should be built or not, building and then packaging and uploading the defined packages. Each repository has a configuration file, `metallus.yml`, which lists possibly many "jobs". These are essentially different projects, different apps. Sets of packages that need to be built together. One job is built at a time by specifying it on the command line when Metallus is started. Each job has many packages that will be made. Each package can be interested in a subset of files within the repository (or the job's root, if it has one) so that packages are only built if something in them has changed. Here is an example:


```yaml
# Global configuration for packages
packages:
  # This maps Git branches to the APT codenames they should be uploaded to
  branch_codenames:
    master: unstable
    production: stable

jobs:
  app1:
    # The name of the script to be run in the build container
    builder: "make"
    # The base docker image, pulled straight through to the Dockerfile
    base: "ubuntu:12.04"
    # An array of layers required in the Dockerfile to build the job. These
    # are stored in metallus/metallus.yaml in this repository.
    # Dockerfile.
    build_depends:
      - "elasticsearch-runit=0.90.13-4"
    # Gives the root of the job in the source repository. For repositories with
    # multiple apps.
    start_in: app1
    # Gives absolute build container directories to persist between builds.
    # As the container is rebuilt every build so as to give a blank slate,
    # these are rsynced out of the container and back again.
    persist:
      - '${SOURCE_ROOT}/${START_IN}/.bundle'
      - '${SOURCE_ROOT}/${START_IN}/vendor/bundle'
      - '${SOURCE_ROOT}/${START_IN}/vendor/assets/components'
      - '${SOURCE_ROOT}/${START_IN}/node_modules'
    # This gives a list of APT components that Metallus will look in for
    # packages that have already been built for the current commit ID. If one
    # is found, it will be copied within the APT repository rather than
    # being rebuilt.
    promote_through:
      - unstable
      - stable
    # An array of hashes of packages to be built
    packages:
        # We only support Debian packages at the moment.
      - type: debian
        # The package name
        name: app1
        # Its dependency list. Can include version specifiers.
        depends:
          - "libmysqlclient-dev"
          - "zlib1g"
          - "zlib1g-dev"
        # From the built container, the packager runs `make` with the given
        # target to move the built files into place on the container.
        target: install
        # Specifies which files (relative to the job's "start_in" value, unless
        # prefixed with a slash '/', in which case relative to the repository
        # root) that, when changed, should trigger a new version of the package
        # to be built. If suffixed by a slash '/', a prefix match on a given
        # path will be made – otherwise a glob match using `fnmatch`. Includes
        # all files under the job's "start_in" by default, but this can be
        # overridden by giving a "root" value underneath the "files" hash.
        files:
          include:
            - /shared/
          exclude:
            - roger/
            - services/
        # The APT repositories this package should be uploaded to. These names
        # match up with the repositories given in the `metallus.yaml` in this
        # repository.
        repos:
          - apps
      - type: debian
        name: app1-web
        # If `false` is given for the target, don't run `make` to copy files
        # into place. This is useful for packages that only have dependencies
        # and pre/post install scripts.
        target: false
        # Usually the packager uses the files that changed between the build
        # image and the `make` target above being run. This stops that.
        copy_diff: false
        depends: 
          - "app1"
          - "nginx-passenger"
        repos:
          - app1
        files:
          # An example of overriding the "root" of files to be interested in
          # for this package.
          root: services/nginx/
```

Also available to the developer are "commit message commands":

* Adding `[ci skip tests]` to a commit message summary will make Metallus pass an environment variable of `SKIP_TESTS=1` to the build process. The Makefile can then use this to skip over automated testing.
* Adding `[ci skip]` to a commit message summary will make Metallus ignore the commit entirely: it neither builds nor packages if this is the only commit that has been pulled.

Note that skipped commits can still be built if commits without a skip command are pulled at the same time.

## Installation

Mostly automated.

* Start with Ubuntu 14.04 LTS "trusty".
* Check out this repository on the system and chdir to the repository root.
* Run `sudo ./dependencies`. Have a look through the script. It installs docker, fpm, and our custom version of deb-s3.
* You'll need to generate a GPG public/private key pair to sign packages with. The key ID is then given in the `repos` in the server's `/etc/metallus/metallus.yml`
* Configure AWS access IDs and secret access keys for all the repos too.

## Running on Mac

You will need to install boot2docker : [https://github.com/boot2docker/osx-installer/releases](https://github.com/boot2docker/osx-installer/releases)

Once installed you will need to start the boot2docker VM, through the CLI tool.

    boot2docker init && boot2docker start

You'll also need to set the global environment variables for your shell, run the following command

    eval $(boot2docker shellinit)

You'll need to install the latest version of deb-s3, to push changes up to a debian repo.

    curl -SsLO https://github.com/madebymany/deb-s3/releases/download/0.7.0-mxm1/deb-s3-0.7.0.gem
	sudo gem install -f deb-s3-0.7.0.gem

If you have an existing GPG key to sign the package list files, then you'll need to import it into your GPG vault using.
	
	gpg --allow-secret-key-import --import {your private key file}

Now you can either develop or install metallus, it will default to using your home directories private key combination when cloning git repositories so make sure you have the correct access to the git repo you want to build.

AWS credentials are best provided through the following shell environment exports.

	export AWS_ACCESS_KEY_ID="your access id"
	export AWS_SECRET_ACCESS_KEY="your access key"
	
This is what deb-s3 will use to connect to the AWS API to upload debian packages

There is also a dependency on zeromq and pyzmq.

This is a little harder to get working.

first install zeromq on your system, we use brew for this.

    brew install zeromq

As of writing this the current release is 4.0.5_2

Once installed you'll need to setup the pyzmq lib to point to the brew location.

download the pyzmq python package (not the source from git) from.

[https://pypi.python.org/packages/source/p/pyzmq/pyzmq-14.5.0.tar.gz](https://pypi.python.org/packages/source/p/pyzmq/pyzmq-14.5.0.tar.gz)

and untar it, compile it with the path to the zeromq library, and then install it into your virtualenv
	 
	curl -SsLO https://pypi.python.org/packages/source/p/pyzmq/pyzmq-14.5.0.tar.gz
    tar -xzf pyzmq-14.5.0.tar.gz
    cd pyzmq-14.5.0
    python setup.py configure --zmq=/usr/local/Cellar/zeromq/4.0.5_2
    python setup.py install
    cd ..
    deactivate
    activate
    rm -rf pyzmq-14.5.0*

## Currently Windows is not supported

## Development

Using Vagrant, a should be brought up with the same `dependencies` script and Just Work. 

[logo]: https://raw.githubusercontent.com/madebymany/metallus/master/site/images/metallus.jpg?token=AAJQq-6lKGsT-nrD0Gh_PMjjPHU5agdxks5UWhlqwA%3D%3D
