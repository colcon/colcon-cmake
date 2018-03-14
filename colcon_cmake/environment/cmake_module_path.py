# Copyright 2016-2018 Dirk Thomas
# Licensed under the Apache License, Version 2.0

import os

from colcon_core.environment import EnvironmentExtensionPoint
from colcon_core.environment import logger
from colcon_core.plugin_system import satisfies_version
from colcon_core.shell import create_environment_hook


class CmakeModulePathEnvironment(EnvironmentExtensionPoint):
    """Extend the `CMAKE_PREFIX_PATH` variable to find CMake modules."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            EnvironmentExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def create_environment_hooks(self, prefix_path, pkg_name):  # noqa: D102
        hooks = []

        logger.log(1, "checking '%s' for CMake module files" % prefix_path)
        for dirpath, _, filenames in os.walk(str(prefix_path)):
            for filename in filenames:
                if filename.startswith('Find') and filename.endswith('.cmake'):
                    hooks += create_environment_hook(
                        'cmake_module_path', prefix_path / dirpath,
                        pkg_name, 'CMAKE_MODULE_PATH', '', mode='prepend')
                    break

        return hooks
