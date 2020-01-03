# Copyright 2016-2018 Dirk Thomas
# Licensed under the Apache License, Version 2.0

import os
from pkg_resources import parse_version
import re
import shutil
import subprocess

from colcon_core.environment_variable import EnvironmentVariable
from colcon_core.subprocess import check_output

"""Environment variable to override the CMake executable"""
CMAKE_COMMAND_ENVIRONMENT_VARIABLE = EnvironmentVariable(
    'CMAKE_COMMAND', 'The full path to the CMake executable')
"""Environment variable to override the CTest executable"""
CTEST_COMMAND_ENVIRONMENT_VARIABLE = EnvironmentVariable(
    'CTEST_COMMAND', 'The full path to the CTest executable')


def which_executable(environment_variable, executable_name):
    """
    Determine the path of an executable.

    An environment variable can be used to override the location instead of
    relying on searching the PATH.

    :param str environment_variable: The name of the environment variable
    :param str executable_name: The name of the executable
    :rtype: str
    """
    value = os.getenv(environment_variable)
    if value:
        return value
    return shutil.which(executable_name)


CMAKE_EXECUTABLE = which_executable(
    CMAKE_COMMAND_ENVIRONMENT_VARIABLE.name, 'cmake')
CTEST_EXECUTABLE = which_executable(
    CTEST_COMMAND_ENVIRONMENT_VARIABLE.name, 'ctest')
MSBUILD_EXECUTABLE = shutil.which('msbuild')


async def has_target(path, target):
    """
    Check if the CMake generated build system has a specific target.

    :param str path: The path of the directory contain the generated build
      system
    :param str target: The name of the target
    :rtype: bool
    """
    generator = get_generator(path)
    if 'Unix Makefiles' in generator:
        return target in await get_makefile_targets(path)
    if 'Ninja' in generator:
        return target in get_ninja_targets(path)
    if 'Visual Studio' in generator:
        assert target == 'install'
        install_project_file = get_project_file(path, 'INSTALL')
        return install_project_file is not None
    assert False, \
        "'has_target' not implemented for CMake generator '{generator}'" \
        .format_map(locals())


async def get_makefile_targets(path):
    """
    Get all targets from a `Makefile`.

    :param str path: The path of the directory contain the Makefile
    :returns: The target names
    :rtype: list
    """
    output = await check_output([
        CMAKE_EXECUTABLE, '--build', path, '--target', 'help'], cwd=path)
    lines = output.decode().splitlines()
    prefix = '... '
    return [l[len(prefix):] for l in lines if l.startswith(prefix)]


def get_ninja_targets(path):
    """
    Get all targets from a `build.ninja` file.

    :param str path: The path of the directory contain the Makefile
    :returns: The target names
    :rtype: list
    """
    output = subprocess.check_output([
        CMAKE_EXECUTABLE, '--build', path, '--target', 'help'], cwd=path)
    lines = output.decode().splitlines()
    suffix = ':'
    return [
        l.split(' ')[0][:-len(suffix)]
        for l in lines
        if len(l.split(' ')) == 2 and l.split(' ')[0].endswith(suffix)]


def get_buildfile(cmake_cache):
    """
    Get the buildfile of the used CMake generator.

    :param Path cmake_cache: The path of the directory contain the build system
    :returns: The buildfile
    :rtype: Path
    """
    generator = get_variable_from_cmake_cache(
        str(cmake_cache.parent), 'CMAKE_GENERATOR')
    if generator == 'Ninja':
        return cmake_cache.parent / 'build.ninja'
    return cmake_cache.parent / 'Makefile'


def get_generator(path, cmake_args=None):
    """
    Get CMake generator name.

    Either the CMake generator is specified in the command line arguments or it
    is being read from the `CMakeCache.txt` file.

    :param str path: The path of the directory contain the CMake cache file
    :param list cmake_args: The CMake command line arguments
    :rtype: str
    """
    # check for generator in the command line arguments first
    generator = None
    for i, cmake_arg in enumerate(cmake_args or []):
        if cmake_arg == '-G' and i < len(cmake_args) - 1:
            generator = cmake_args[i + 1]
    if generator is None:
        # get the generator from the CMake cache
        generator = get_variable_from_cmake_cache(
            path, 'CMAKE_GENERATOR')
    return generator


def is_multi_configuration_generator(path, cmake_args=None):
    """
    Check if the used CMake generator is a multi configuration generator.

    :param str path: The path of the directory contain the CMake cache file
    :param list cmake_args: The CMake command line arguments
    :rtype: bool
    """
    known_multi_configuration_generators = (
        'Visual Studio',
        'Xcode',
    )
    generator = get_generator(path, cmake_args)
    for multi in known_multi_configuration_generators:
        if multi in generator:
            return True
    return False


def get_variable_from_cmake_cache(path, var, *, default=None):
    """
    Get a variable value from the CMake cache.

    :param str path: The path of the directory contain the CMake cache file
    :param str var: The name of the variable
    :param default: The default value returned if the variable is not defined
      in the cache
    :rtype: str
    """
    lines = _get_cmake_cache_lines(path)
    if lines is None:
        return default
    line_prefix = '{var}:'.format_map(locals())
    for line in lines:
        if line.startswith(line_prefix):
            try:
                index = line.index('=')
            except ValueError:
                continue
            return line[index + 1:]
    return default


def _get_cmake_cache_lines(path):
    cmake_cache = os.path.join(path, 'CMakeCache.txt')
    if not os.path.exists(cmake_cache):
        return None
    with open(cmake_cache, 'r') as h:
        content = h.read()
    return content.splitlines()


def get_project_file(path, target):
    """
    Get a Visual Studio project file for a specific target.

    :param str path: The path of the directory project files
    :param str target: The name of the target
    :returns: The path of the project file if it exists, otherwise None
    :rtype: str
    """
    project_file = os.path.join(path, target + '.vcxproj')
    if not os.path.isfile(project_file):
        return None
    return project_file


def get_visual_studio_version():
    """
    Get the Visual Studio version.

    :rtype: str
    """
    return os.environ.get('VisualStudioVersion', None)


def _parse_cmake_version():
    """
    Parse the CMake version number by running `cmake --version`.

    The version number is parse from the output of 'cmake --version' and is
    expected in the form 'cmake version #.#.#' where each '#' character
    represents part of the version number. Additional text may follow, however
    only the first line is parsed. Parsing is performed by the pkg_resources
    package and the returned object is a Version object from that package.

    This function blocks on the execution of cmake and should only be used to
    cache the CMake version number. External API users should use
    get_cmake_version()

    :returns: The version as parsed by the pkg_resources package
    :rtype pkg_resources.extern.packaging.version.Version
    """
    try:
        output = subprocess.check_output([CMAKE_EXECUTABLE, '--version'])
        lines = output.decode().splitlines()
        ver_line = lines[0] if lines and len(lines) else None
        if ver_line:
            # Extract just the version part of the string.
            ver_re_str = r'^(?:.*)(\d+\.\d+\..*)'
            ver_match = re.match(ver_re_str, ver_line, re.I)
            if ver_match:
                return parse_version(ver_match.group(1))
        return None
    except subprocess.CalledProcessError:
        return None
    return None


# Global variable for the cached CMake version number.
# When valid, this will be of pkg_resources.extern.packaging.version.Version
# It may also have a boolean value False when the cmake version has failed
# to parse. This saves recurring parse failures.
_cached_cmake_version = None


def get_cmake_version():
    """
    Get the cached CMake version number if available and successfully parsed.

    The result is None when a version number is not available or cannot be
    parsed. This may occur if CMake is not present, is a very old version or is
    a newer version where the version number string output has changed.

    :returns: The version as parsed by the pkg_resources package
    :rtype pkg_resources.extern.packaging.version.Version
    """
    global _cached_cmake_version
    if _cached_cmake_version is None:
        # No value yet. Parse the version number.
        _cached_cmake_version = _parse_cmake_version()
        if not _cached_cmake_version is None:
            # Success.
            return _cached_cmake_version
        # Failed to parse. Set _cached_cmake_version to False to prevent
        # parsing again, but we can still return None as required.
        _cached_cmake_version = False
    # Have cached a previous result. Check if the previous result is a bool
    # type. If so, this implies we've tried and failed to parse the version
    # number and should return None. Otherwise return the cached value as is.
    elif not isinstance(_cached_cmake_version, bool):
        return _cached_cmake_version
    return None
