# Copyright 2020 Kazys Stepanas
# Licensed under the Apache License, Version 2.0

from colcon_cmake.task.cmake import _parse_cmake_version_string


def test_parse_cmake_version():
    # Build version prefix string closely matching what cmake version outputs.
    base_prefix = 'cmake version '

    # Expected results list. Each element is a tuple containing the following:
    # - Version string to parse.
    # - Numeric version tuple to compare against (major, minor, patch).
    # The second item is None where the parse string should not parse.
    test_items = [
        (base_prefix + '3.0.0', (3, 0, 0)),
        (base_prefix + '3.0.0-dirty', (3, 0, 0)),
        (base_prefix + '3.0.0-rc1', (3, 0, 0)),
        (base_prefix + 'cmake version 3.0.0-rc1-dirty', (3, 0, 0)),
        (base_prefix + 'this.is.garbage', None),
        (base_prefix + '3.15.1', (3, 15, 1)),
        ('3.15.1', (3, 15, 1)),
        (base_prefix + '101.202.303-xxx', (101, 202, 303)),
        ('101.202.303-xxx', (101, 202, 303)),
        ('prefix 1 number 101.202.303-xxx', (101, 202, 303)),
        ('not the right format', None)
    ]

    # Iterate the strings and parse.
    for version_string, expected_version in test_items:
        parsed_version = _parse_cmake_version_string(version_string)
        if expected_version is None:
            # Input string was garbage. Assert parsing failed.
            assert parsed_version is None
        else:
            assert parsed_version._version.release[0:3] == expected_version


if __name__ == '__main__':
    test_parse_cmake_version()
