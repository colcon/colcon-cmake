# Copyright 2020 Dirk Thomas
# Licensed under the Apache License, Version 2.0

from pathlib import Path

from colcon_core.event.job import JobEnded
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
        self._compile_commands = {}
        self._delayed_packages = set()

    def __call__(self, event):  # noqa: D102
        data = event[0]

        if isinstance(data, JobQueued) or isinstance(data, JobUnselected):
            # delay loading json for all packages
            self._delayed_packages.add(data.identifier)

        if isinstance(data, JobEnded):
            # parse json when a job ended
            self._add_compile_commands(data.identifier)
            self._delayed_packages.discard(data.identifier)

        elif isinstance(data, EventReactorShutdown):
            # load json for previously delayed packages
            for package_name in self._delayed_packages:
                self._add_compile_commands(package_name)

            # keep deterministic order independent of aborted/selected packages
            all_compile_commands = []
            for k in sorted(self._compile_commands.keys()):
                all_compile_commands += self._compile_commands[k]

            json_path = self._get_path()
            if all_compile_commands:
                data = yaml.dump(all_compile_commands, default_flow_style=True)

                with json_path.open('w') as h:
                    h.write(data)
            elif json_path.exists():
                json_path.unlink()

    def _add_compile_commands(self, package_name):
        json_path = self._get_path(package_name)
        if not json_path.exists():
            return
        try:
            compile_commands = yaml.safe_load(json_path.read_bytes())
        except Exception as e:
            logger.warning(
                "Failed to parse '%s': %s" % (json_path.absolute(), e))
            return
        if not isinstance(compile_commands, list):
            logger.warning(
                "Data in '%s' is expected to be a list" % json_path.absolute())
            return
        if compile_commands:
            self._compile_commands[package_name] = compile_commands

    def _get_path(self, package_name=None):
        path = Path(self.context.args.build_base)
        if package_name is not None:
            path /= package_name
        path /= CompileCommandsEventHandler.FILENAME
        return path

        self._file_handle = path.open(mode='w')
        return True
