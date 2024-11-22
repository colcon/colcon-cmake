# Copyright 2016-2018 Dirk Thomas
# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from colcon_cmake.environment.cmake_module_path \
    import CmakeModulePathEnvironment


def test_cmake_module_path():
    extension = CmakeModulePathEnvironment()

    with TemporaryDirectory(prefix='test_colcon_') as prefix_path:
        prefix_path = Path(prefix_path)
        with patch(
            'colcon_cmake.environment.cmake_module_path.'
            'create_environment_hook',
            return_value=['/some/hook', '/other/hook']
        ):
            # No CMake configs exist
            hooks = extension.create_environment_hooks(prefix_path, 'pkg_name')
            assert len(hooks) == 0

            pkg_share_path = prefix_path / 'share' / 'pkg_name'

            # Unrelated file
            unrelated_file = pkg_share_path / 'cmake' / 'README.md'
            unrelated_file.parent.mkdir(parents=True, exist_ok=True)
            unrelated_file.touch()
            hooks = extension.create_environment_hooks(prefix_path, 'pkg_name')
            assert len(hooks) == 0

            # FindPkgName.cmake exists
            cmake_module = pkg_share_path / 'cmake' / 'FindPkgName.cmake'
            cmake_module.parent.mkdir(parents=True, exist_ok=True)
            cmake_module.touch()
            hooks = extension.create_environment_hooks(prefix_path, 'pkg_name')
            assert len(hooks) == 2
