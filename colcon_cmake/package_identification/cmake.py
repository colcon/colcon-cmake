# Copyright 2016-2018 Dirk Thomas
# Licensed under the Apache License, Version 2.0

import os
from pathlib import Path
import re
import sys

from colcon_core.package_identification \
    import PackageIdentificationExtensionPoint
from colcon_core.plugin_system import satisfies_version


class CmakePackageIdentification(PackageIdentificationExtensionPoint):
    """Identify CMake packages with `CMakeLists.txt` files."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            PackageIdentificationExtensionPoint.EXTENSION_POINT_VERSION,
            '^1.0')

    def identify(self, metadata):  # noqa: D102
        if metadata.type is not None and metadata.type != 'cmake':
            return

        cmakelists_txt = metadata.path / 'CMakeLists.txt'
        if not cmakelists_txt.is_file():
            return

        data = extract_data(cmakelists_txt)
        if not data['name'] and not metadata.name:
            raise RuntimeError(
                "Failed to extract project name from '%s'" % cmakelists_txt)

        metadata.type = 'cmake'
        if metadata.name is None:
            metadata.name = data['name']
        metadata.dependencies['build'] |= data['depends']
        metadata.dependencies['run'] |= data['depends']


def extract_data(cmakelists_txt):
    """
    Extract the project name and dependencies from a CMakeLists.txt file.

    :param Path cmakelists_txt: The path of the CMakeLists.txt file
    :rtype: dict
    """
    content = extract_content(cmakelists_txt)

    data = {}
    data['name'] = extract_project_name(content)
    # fall back to use the directory name
    if data['name'] is None:
        data['name'] = cmakelists_txt.parent.name

    # extract dependencies from all CMake files in the project directory
    depends_content = content + extract_content(
        cmakelists_txt.parent, exclude=[cmakelists_txt])

    depends = extract_dependencies(depends_content)
    # exclude self references
    data['depends'] = depends - {data['name']}

    return data


def extract_content(basepath, exclude=None):
    """
    Get all non-comment lines from CMake files under the given basepath.

    All `CMakeLists.txt` files as well as files ending with `.cmake` are used.
    Directories starting with a dot (`.`) are being skipped.

    :param Path basepath: The path to recursively crawl
    :param list exclude: The paths to exclude
    :rtype: str
    """
    if basepath.is_file():
        content = basepath.read_text(errors='replace')
    elif basepath.is_dir():
        content = ''
        for dirpath, dirnames, filenames in os.walk(str(basepath)):
            # skip subdirectories starting with a dot
            dirnames[:] = filter(lambda d: not d.startswith('.'), dirnames)
            dirnames.sort()

            for name in sorted(filenames):
                if name != 'CMakeLists.txt' and not name.endswith('.cmake'):
                    continue

                path = Path(dirpath) / name
                if path in (exclude or []):
                    continue

                content += path.read_text(errors='replace') + '\n'
    else:
        return ''
    return _remove_cmake_comments(content)


def _remove_cmake_comments(content):
    lines = content.splitlines()
    for index, line in enumerate(lines):
        lines[index] = _remove_cmake_comments_from_line(line)
    return '\n'.join(lines)


def _remove_cmake_comments_from_line(line):
    # match comments starting with #
    # which are not within a string enclosed in double quotes
    pattern = (
        # strings
        '("[^"]*")'
        '|'
        # comments
        '(#.*)'
        '|'
        # other
        '([^#"]*)'
    )

    modline = ''
    for matches in re.findall(pattern, line):
        modline += matches[0] + matches[2]
    return modline


def extract_project_name(content):
    """
    Extract the CMake project name from the CMake code.

    The `project()` call must be on a single line and the first argument must
    be a literal string for this function to be able to extract the name.

    :param str content: The CMake source code
    :returns: The project name, otherwise None
    :rtype: str
    """
    # extract project name
    match = re.search(
        # case insensitive function name
        _get_case_insensitive_pattern('project') +
        # optional white space
        r'\s*'
        # open parenthesis
        r'\('
        # optional white space
        r'\s*'
        # optional "opening" quote
        '("?)'
        # project name
        '([a-zA-Z0-9_-]+)'
        # optional "closing" quote (only if an "opening" quote was used)
        r'\1'
        # optional language
        r'(\s+[^\)]*)?'
        # close parenthesis
        r'\)',
        content)
    if not match:
        return None
    return match.group(2)


def extract_dependencies(content):
    """
    Extract the dependencies from the CMake code.

    The `find_package()` and `pkg_check_modules` calls must be on a single line
    and the first argument must be a literal string for this function to be
    able to extract the dependency name.

    :param str content: The CMake source code
    :returns: The dependencies name
    :rtype: list
    """
    return \
        extract_find_package_calls(content) | \
        _extract_pkg_config_calls(content)


def extract_find_package_calls(content, *, function_name='find_package'):
    """
    Extract `find_package()`-like calls from the CMake code.

    The function call must be on a single line and the first argument must be
    a literal string for this function to be able to extract it.

    :param str content: The CMake source code
    :returns: The first arguments of the functions (in the case of
      `find_package()` these are the package names)
    :rtype: set
    """
    matches = re.findall(
        # case insensitive function name
        _get_case_insensitive_pattern(function_name) +
        # optional white space
        r'\s*'
        # open parenthesis
        r'\('
        # optional white space
        r'\s*'
        # optional "opening" quote
        '("?)'
        # package name
        '([a-zA-Z0-9_-]+)'
        # optional "closing" quote (only if an "opening" quote was used)
        r'\1'
        # white space
        r'(\s+'
        # optional arguments
        r'[^\)]*)?'
        # close parenthesis
        r'\)',
        content)
    return {m[1] for m in matches}


def _extract_pkg_config_calls(content):
    pattern1 = _get_case_insensitive_pattern('pkg_check_modules')
    pattern2 = _get_case_insensitive_pattern('pkg_search_module')
    function_names_pattern = '(?:{pattern1}|{pattern2})'.format_map(locals())
    matches = re.findall(
        # case insensitive function names
        function_names_pattern +
        # optional white space
        r'\s*'
        # open parenthesis
        r'\('
        # optional white space
        r'\s*'
        # optional "opening" quote
        '("?)'
        # prefix
        '[a-zA-Z0-9_]+'
        # optional "closing" quote (only if an "opening" quote was used)
        r'\1'
        # optional options prefixed by white space
        r'(?:\s+(?:REQUIRED|QUIET|NO_CMAKE_PATH|NO_CMAKE_ENVIRONMENT_PATH))*'
        # package names prefixed by white space with opt. trailing white space
        '([^)]+)'
        # close parenthesis
        r'\)',
        content)
    names = set()
    for modules in [m[1].strip() for m in matches]:
        # split multiple modules
        for module in modules.split():
            # remove optional version suffix
            for char in ('>', '=', '<'):
                if char in module:
                    module = module[:module.index(char)]
            names.add(module)
    return names


def _get_case_insensitive_pattern(value):
    # non-capturing case insensitive pattern for a string literal
    if sys.version_info[:2] < (3, 6):
        # match each character separately with arbitrary case
        pattern = ''
        for char in value:
            if char.lower() != char.upper():
                pattern += '[' + char.lower() + char.upper() + ']'
            else:
                pattern += char
        return pattern
    return '(?i:{value})'.format_map(locals())
