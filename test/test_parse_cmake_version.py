# Copyright 2016-2018 Dirk Thomas
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
    for test_item in test_items:
        parsed_version = _parse_cmake_version_string(test_item[0])
        expected_ver = test_item[1]
        # print(test_item[0], ':', parsed_version, 'expected:', expected_ver)
        if expected_ver is None:
            # Input string was garbage. Assert parsing failed.
            assert parsed_version is None
        else:
            assert parsed_version._version.release[0] == expected_ver[0]
            assert parsed_version._version.release[1] == expected_ver[1]
            assert parsed_version._version.release[2] == expected_ver[2]


if __name__ == '__main__':
    test_parse_cmake_version()
