# Copyright 2016-2018 Dirk Thomas
# Licensed under the Apache License, Version 2.0

import os
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
