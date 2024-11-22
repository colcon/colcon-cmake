# Copyright 2016-2018 Dirk Thomas
# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from colcon_cmake.environment.cmake_prefix_path \
    import CmakePrefixPathEnvironment


def test_cmake_prefix_path():
    extension = CmakePrefixPathEnvironment()

    with TemporaryDirectory(prefix='test_colcon_') as prefix_path:
        prefix_path = Path(prefix_path)
        with patch(
            'colcon_cmake.environment.cmake_prefix_path'
            '.create_environment_hook',
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

            # PkgNameConfig.cmake exists
            cmake_config = pkg_share_path / 'cmake' / 'PkgNameConfig.cmake'
            cmake_config.parent.mkdir(parents=True, exist_ok=True)
            cmake_config.touch()
            hooks = extension.create_environment_hooks(prefix_path, 'pkg_name')
            assert len(hooks) == 2
            cmake_config.unlink()

            # pkg_name-config.cmake exists
            cmake_config = pkg_share_path / 'cmake' / 'pkg_name-config.cmake'
            cmake_config.parent.mkdir(parents=True, exist_ok=True)
            cmake_config.touch()
            hooks = extension.create_environment_hooks(prefix_path, 'pkg_name')
            assert len(hooks) == 2
            cmake_config.unlink()
