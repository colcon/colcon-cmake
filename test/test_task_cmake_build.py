# Copyright 2019 Rover Robotics
# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import asyncio
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

from colcon_cmake.task.cmake.build import CmakeBuildTask
from colcon_core.event_handler.console_direct import ConsoleDirectEventHandler
from colcon_core.package_descriptor import PackageDescriptor
from colcon_core.subprocess import new_event_loop
from colcon_core.task import TaskContext
import pytest


@pytest.fixture(autouse=True)
def monkey_patch_put_event_into_queue(monkeypatch):
    event_handler = ConsoleDirectEventHandler()
    monkeypatch.setattr(
        TaskContext,
        'put_event_into_queue',
        lambda self, event: event_handler((event, 'cmake')),
    )


def _test_build_package(
    tmp_path, *, cmake_args=None, cmake_clean_cache=False,
    cmake_clean_first=False, cmake_force_configure=None,
    cmake_target=None, cmake_target_skip_unavailable=None,
):
    event_loop = new_event_loop()
    asyncio.set_event_loop(event_loop)

    try:
        package = PackageDescriptor(tmp_path / 'src')
        package.name = 'test-package'
        package.type = 'cmake'

        context = TaskContext(
            pkg=package,
            args=SimpleNamespace(
                path=str(tmp_path / 'src'),
                build_base=str(tmp_path / 'build'),
                install_base=str(tmp_path / 'install'),
                cmake_args=cmake_args,
                cmake_clean_cache=cmake_clean_cache,
                cmake_clean_first=cmake_clean_first,
                cmake_force_configure=cmake_force_configure,
                cmake_target=cmake_target,
                cmake_target_skip_unavailable=cmake_target_skip_unavailable,
            ),
            dependencies={}
        )

        task = CmakeBuildTask()
        task.set_context(context=context)

        package.path.mkdir(exist_ok=True)
        (package.path / 'CMakeLists.txt').write_text(
            'cmake_minimum_required(VERSION 3.5)\n'
            'project(test-package NONE)\n'
            'file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/out-file"\n'
            '     CONTENT "Hello, World!")\n'
            'install(FILES "${CMAKE_CURRENT_BINARY_DIR}/out-file"\n'
            '        DESTINATION "share")\n'
            'add_custom_target(custom-target\n'
            '                  ${CMAKE_COMMAND} -E echo "Hello, World!")\n'
        )

        src_base = Path(task.context.args.path)

        source_files_before = set(src_base.rglob('*'))
        rc = event_loop.run_until_complete(task.build())
        assert not rc
        source_files_after = set(src_base.rglob('*'))
        assert source_files_before == source_files_after

        install_base = Path(task.context.args.install_base)
        assert (cmake_target is None) == \
            (install_base / 'share' / 'out-file').is_file()
    finally:
        event_loop.close()


@pytest.mark.parametrize(
    'cmake_target',
    [None, 'custom-target'])
@pytest.mark.skipif(
    not shutil.which('cmake'),
    reason='CMake must be installed to run this test')
@pytest.mark.skipif(
    os.name == 'nt' and 'VisualStudioVersion' not in os.environ,
    reason='Must be run from a developer command prompt')
def test_build_package(tmpdir, cmake_target):
    tmp_path = Path(tmpdir)
    _test_build_package(tmp_path, cmake_target=cmake_target)
