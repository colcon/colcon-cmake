# Copyright 2016-2018 Dirk Thomas
# Licensed under the Apache License, Version 2.0

import os

from colcon_cmake.task.cmake import CTEST_EXECUTABLE
from colcon_cmake.task.cmake import get_variable_from_cmake_cache
from colcon_core.event.test import TestFailure
from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import satisfies_version
from colcon_core.shell import get_command_environment
from colcon_core.subprocess import check_output
from colcon_core.task import check_call
from colcon_core.task import TaskExtensionPoint

logger = colcon_logger.getChild(__name__)


class CmakeTestTask(TaskExtensionPoint):
    """Test CMake packages."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(TaskExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def add_arguments(self, *, parser):  # noqa: D102
        parser.add_argument(
            '--ctest-args',
            nargs='*', metavar='*', type=str.lstrip,
            help='Pass arguments to CTest projects. '
            'Arguments matching other options must be prefixed by a space,\n'
            'e.g. --ctest-args " --help"')

    async def test(self, *, additional_hooks=None):  # noqa: D102
        pkg = self.context.pkg
        args = self.context.args

        logger.info(
            "Testing CMake package in '{args.path}'".format_map(locals()))

        assert os.path.exists(args.build_base)

        try:
            env = await get_command_environment(
                'test', args.build_base, self.context.dependencies)
        except RuntimeError as e:
            logger.error(str(e))
            return 1

        if CTEST_EXECUTABLE is None:
            raise RuntimeError("Could not find 'ctest' executable")

        # check if CTest has any tests
        output = await check_output(
            [CTEST_EXECUTABLE, '--show-only'],
            cwd=args.build_base,
            env=env)
        for line in output.decode().splitlines():
            if line.startswith('  '):
                break
        else:
            logger.log(
                5, "No ctests found in '{args.path}'".format_map(locals()))
            return

        # CTest arguments
        ctest_args = [
            # choose configuration, required for multi-configuration generators
            '-C', self._get_configuration_from_cmake(args.build_base),
            # generate xml of test summary
            '-D', 'ExperimentalTest', '--no-compress-output',
            # show all test output
            '-V',
            '--force-new-ctest-process',
        ]
        ctest_args += (args.ctest_args or [])

        if args.retest_until_fail:
            count = args.retest_until_fail + 1
            ctest_args += [
                '--repeat-until-fail', str(count),
            ]

        rerun = 0
        while True:
            # invoke CTest
            rc = await check_call(
                self.context,
                [CTEST_EXECUTABLE] + ctest_args,
                cwd=args.build_base, env=env)

            if not rc.returncode:
                return

            # try again if requested
            if args.retest_until_pass > rerun:
                if not rerun:
                    ctest_args += [
                        '--rerun-failed',
                    ]
                rerun += 1
                continue

            # CTest reports failing tests
            if rc.returncode == 8:
                self.context.put_event_into_queue(TestFailure(pkg.name))
                # the return code should still be 0
                return 0
            return rc.returncode

    def _get_configuration_from_cmake(self, build_base):
        # get for CMake build type from the CMake cache
        build_type = get_variable_from_cmake_cache(
            build_base, 'CMAKE_BUILD_TYPE')
        if build_type in ('Debug', 'MinSizeRel', 'RelWithDebInfo'):
            return build_type
        return 'Release'
