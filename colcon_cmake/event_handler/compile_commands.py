# Copyright 2020 Dirk Thomas
# Licensed under the Apache License, Version 2.0

import os
from pathlib import Path

from colcon_core.event.job import JobQueued
from colcon_core.event.job import JobUnselected
from colcon_core.event_handler import EventHandlerExtensionPoint
from colcon_core.event_reactor import EventReactorShutdown
from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import satisfies_version
import yaml

logger = colcon_logger.getChild(__name__)


class CompileCommandsEventHandler(EventHandlerExtensionPoint):
    """
    Generate a `compile_commands.json` file for the whole workspace.

    The file is created in the build directory and aggregates the data from all
    packages.
    """

    FILENAME = 'compile_commands.json'

    # the priority should be lower than e.g. the status and summary extensions
    # in order to show those as soon as possible
    PRIORITY = 40

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            EventHandlerExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        self._package_names = set()

    def __call__(self, event):  # noqa: D102
        data = event[0]

        if isinstance(data, JobQueued) or isinstance(data, JobUnselected):
            # delay loading json for all packages
            self._package_names.add(data.identifier)

        elif isinstance(data, EventReactorShutdown):
            # if no package has a json file there is no need for a
            # workspace-level json file
            package_level_json_paths = self._get_package_level_json_paths()
            workspace_level_json_path = self._get_path()
            if not package_level_json_paths:
                if workspace_level_json_path.exists():
                    workspace_level_json_path.unlink()
                return

            # if the workspace-level json file is newer than all package-level
            # json files it doesn't need to be regenerated
            try:
                workspace_level_mtime = os.path.getmtime(
                    str(workspace_level_json_path))
            except Exception:
                pass
            else:
                for json_path in sorted(package_level_json_paths):
                    try:
                        mtime = os.path.getmtime(str(json_path))
                    except Exception:
                        continue
                    if mtime > workspace_level_mtime:
                        break
                else:
                    return

            # collect all package-level json data
            all_compile_commands = []
            # keep deterministic order independent of aborted/selected packages
            for json_path in sorted(package_level_json_paths):
                compile_commands = self._get_compile_commands(json_path)
                if compile_commands is not None:
                    all_compile_commands += compile_commands

            # generate workspace-level json file or remove if empty
            if all_compile_commands:
                data = yaml.dump(all_compile_commands, default_flow_style=True)
                with workspace_level_json_path.open('w') as h:
                    h.write(data)
            elif workspace_level_json_path.exists():
                workspace_level_json_path.unlink()

    def _get_package_level_json_paths(self):
        json_paths = set()
        for package_name in self._package_names:
            json_path = self._get_path(package_name)
            if json_path.exists():
                json_paths.add(json_path)
        return json_paths

    def _get_compile_commands(self, json_path):
        try:
            compile_commands = yaml.safe_load(json_path.read_bytes())
        except Exception as e:
            logger.warning(
                "Failed to parse '%s': %s" % (json_path.absolute(), e))
            return None
        if not isinstance(compile_commands, list):
            logger.warning(
                "Data in '%s' is expected to be a list" % json_path.absolute())
            return None
        return compile_commands

    def _get_path(self, package_name=None):
        path = Path(self.context.args.build_base)
        if package_name is not None:
            path /= package_name
        path /= CompileCommandsEventHandler.FILENAME
        return path

        self._file_handle = path.open(mode='w')
        return True
