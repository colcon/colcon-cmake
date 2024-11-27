# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import time
from types import SimpleNamespace

from colcon_cmake.event_handler.compile_commands \
    import CompileCommandsEventHandler
from colcon_cmake.task.cmake import CMAKE_EXECUTABLE
from colcon_core.command import CommandContext
from colcon_core.event.command import Command
from colcon_core.event.job import JobQueued
from colcon_core.event.timer import TimerEvent
from colcon_core.event_reactor import EventReactorShutdown


def test_compile_commands_simple(tmp_path):
    extension = CompileCommandsEventHandler()
    extension.context = CommandContext(
        command_name='colcon',
        args=SimpleNamespace(build_base=str(tmp_path)))

    event = JobQueued('job_name')
    extension((event, None))

    event = JobQueued('another_job_name')
    extension((event, None))

    # CMake invocation
    event = Command([CMAKE_EXECUTABLE, 'foo'], cwd=str(tmp_path))
    extension((event, None))
    (tmp_path / 'job_name').mkdir()
    (tmp_path / 'job_name' / extension.FILENAME).write_text('["foo"]')
    (tmp_path / 'another_job_name').mkdir()
    (tmp_path / 'another_job_name' / extension.FILENAME).write_text('["bar"]')

    # Fin
    event = EventReactorShutdown()
    extension((event, None))

    assert (tmp_path / extension.FILENAME).is_file()


def test_compile_commands_skip(tmp_path):
    extension = CompileCommandsEventHandler()
    extension.context = CommandContext(
        command_name='colcon',
        args=SimpleNamespace(build_base=str(tmp_path)))

    # Unrelated event
    event = TimerEvent()
    extension((event, None))

    # Non-CMake invocation
    event = Command(['not-cmake', 'foo'], cwd=str(tmp_path))
    extension((event, None))

    # Fin
    event = EventReactorShutdown()
    extension((event, None))

    # No CMake invocations, so nothing to do
    assert not any(tmp_path.iterdir())

    # CMake invocation
    event = Command([CMAKE_EXECUTABLE, 'foo'], cwd=str(tmp_path))
    extension((event, None))

    # Fin
    event = EventReactorShutdown()
    extension((event, None))

    # No package-level output, so nothing to do
    assert not any(tmp_path.iterdir())


def test_compile_commands_cleanup(tmp_path):
    extension = CompileCommandsEventHandler()
    extension.context = CommandContext(
        command_name='colcon',
        args=SimpleNamespace(build_base=str(tmp_path)))

    # Simulate previous run
    (tmp_path / extension.FILENAME).write_text('["foo"]')

    # CMake invocation
    event = Command([CMAKE_EXECUTABLE, 'foo'], cwd=str(tmp_path))
    extension((event, None))

    # Fin
    event = EventReactorShutdown()
    extension((event, None))

    # The previous invocation's output should have been removed
    assert not any(tmp_path.iterdir())


def test_compile_commands_rerun(tmp_path):
    extension = CompileCommandsEventHandler()
    extension.context = CommandContext(
        command_name='colcon',
        args=SimpleNamespace(build_base=str(tmp_path)))

    # Simulate previous run 0.1s ago
    (tmp_path / extension.FILENAME).write_text('["foo"]')
    time.sleep(0.1)

    event = JobQueued('job_name')
    extension((event, None))

    # CMake invocation
    event = Command([CMAKE_EXECUTABLE, 'foo'], cwd=str(tmp_path))
    extension((event, None))
    (tmp_path / 'job_name').mkdir()
    (tmp_path / 'job_name' / extension.FILENAME).write_text('["foo"]')

    # Fin
    event = EventReactorShutdown()
    extension((event, None))

    assert (tmp_path / extension.FILENAME).is_file()

    # Simulate another run which doesn't touch any job-level output

    # Fin
    event = EventReactorShutdown()
    extension((event, None))

    assert (tmp_path / extension.FILENAME).is_file()


def test_compile_commands_bad_data(tmp_path):
    extension = CompileCommandsEventHandler()
    extension.context = CommandContext(
        command_name='colcon',
        args=SimpleNamespace(build_base=str(tmp_path)))

    event = JobQueued('job_name')
    extension((event, None))

    # CMake invocation
    event = Command([CMAKE_EXECUTABLE, 'foo'], cwd=str(tmp_path))
    extension((event, None))
    (tmp_path / 'job_name').mkdir()
    (tmp_path / 'job_name' / extension.FILENAME).write_text('')

    # Fin
    event = EventReactorShutdown()
    extension((event, None))

    assert (tmp_path / extension.FILENAME).is_file()
