# Copyright 2016-2018 Dirk Thomas
# Licensed under the Apache License, Version 2.0

import ast
from contextlib import suppress
import os
from pathlib import Path
import re

from colcon_cmake.task.cmake import CMAKE_EXECUTABLE
from colcon_cmake.task.cmake import get_buildfile
from colcon_cmake.task.cmake import get_cmake_version
from colcon_cmake.task.cmake import get_generator
from colcon_cmake.task.cmake import get_variable_from_cmake_cache
from colcon_cmake.task.cmake import get_visual_studio_version
from colcon_cmake.task.cmake import has_target
from colcon_cmake.task.cmake import is_jobs_based_generator
from colcon_cmake.task.cmake import is_multi_configuration_generator
from colcon_core.environment import create_environment_scripts
from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import satisfies_version
from colcon_core.shell import get_command_environment
from colcon_core.task import run
from colcon_core.task import TaskExtensionPoint
from pkg_resources import parse_version

logger = colcon_logger.getChild(__name__)


class CmakeBuildTask(TaskExtensionPoint):
    """Build CMake packages."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(TaskExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def add_arguments(self, *, parser):  # noqa: D102
        parser.add_argument(
            '--cmake-args',
            nargs='*', metavar='*', type=str.lstrip,
            help='Pass arguments to CMake projects. '
            'Arguments matching other options must be prefixed by a space,\n'
            'e.g. --cmake-args " --help" (stdout might not be shown by '
            'default, e.g. add `--event-handlers console_cohesion+`)')
        parser.add_argument(
            '--cmake-target',
            help='Build a specific target instead of the default target')
        parser.add_argument(
            '--cmake-target-skip-unavailable',
            action='store_true',
            help="Skip building packages which don't have the target passed "
                 'to --cmake-target')
        parser.add_argument(
            '--cmake-clean-cache',
            action='store_true',
            help='Remove CMake cache before the build (implicitly forcing '
                 'CMake configure step)')
        parser.add_argument(
            '--cmake-clean-first',
            action='store_true',
            help="Build target 'clean' first, then build (to only clean use "
                 "'--cmake-target clean')")
        parser.add_argument(
            '--cmake-force-configure',
            action='store_true',
            help='Force CMake configure step')
        parser.add_argument(
            '--cmake-jobs',
            type=int,
            help='Number of jobs to use for supported generators (e.g., Ninja '
            'Makefiles). Negative values subtract from the maximum '
            'available, so --jobs=-1 uses all bar 1 available threads.')

    async def build(  # noqa: D102
        self, *, additional_hooks=None, skip_hook_creation=False,
        environment_callback=None, additional_targets=None
    ):
        pkg = self.context.pkg
        args = self.context.args

        logger.info(
            "Building CMake package in '{args.path}'".format_map(locals()))

        try:
            env = await get_command_environment(
                'build', args.build_base, self.context.dependencies)
        except RuntimeError as e:
            logger.error(str(e))
            return 1

        if environment_callback is not None:
            environment_callback(env)

        rc = await self._reconfigure(args, env)
        if rc:
            return rc

        # ensure that CMake cache contains the project name
        project_name = get_variable_from_cmake_cache(
            args.build_base, 'CMAKE_PROJECT_NAME')
        if project_name is None:
            # if not the CMake code hasn't called project() and can't be built
            logger.warning(
                "Could not build CMake package '{pkg.name}' because the "
                "CMake cache has no 'CMAKE_PROJECT_NAME' variable"
                .format_map(locals())
            )
            return

        rc = await self._build(
            args, env, additional_targets=additional_targets)
        if rc:
            return rc

        # skip install step if a specific target was requested
        if not args.cmake_target:
            if await has_target(args.build_base, 'install'):
                completed = await self._install(args, env)
                if completed.returncode:
                    return completed.returncode
            else:
                logger.warning(
                    "Could not run installation step for package '{pkg.name}' "
                    "because it has no 'install' target".format_map(locals()))

        if not skip_hook_creation:
            create_environment_scripts(
                pkg, args, additional_hooks=additional_hooks)

    async def _reconfigure(self, args, env):
        self.progress('cmake')

        cmake_cache = Path(args.build_base) / 'CMakeCache.txt'
        run_configure = args.cmake_force_configure
        if args.cmake_clean_cache and cmake_cache.exists():
            cmake_cache.unlink()
        if not run_configure:
            run_configure = not cmake_cache.exists()
        if not run_configure:
            buildfile = get_buildfile(cmake_cache)
            run_configure = not buildfile.exists()

        # check CMake args from last run to decide on need to reconfigure
        if not run_configure:
            last_cmake_args = self._get_last_cmake_args(args.build_base)
            run_configure = (args.cmake_args or []) != (last_cmake_args or [])
        self._store_cmake_args(args.build_base, args.cmake_args)

        if not run_configure:
            return

        # invoke CMake / reconfigure target
        cmake_args = [args.path]
        cmake_args += (args.cmake_args or [])
        cmake_args += ['-DCMAKE_INSTALL_PREFIX=' + args.install_base]
        generator = get_generator(args.build_base, args.cmake_args)
        if os.name == 'nt' and generator is None:
            vsv = get_visual_studio_version()
            if vsv is None:
                raise RuntimeError(
                    'VisualStudioVersion is not set, '
                    'please run within a Visual Studio Command Prompt.')
            supported_vsv = {
                '16.0': 'Visual Studio 16 2019',
                '15.0': 'Visual Studio 15 2017',
                '14.0': 'Visual Studio 14 2015',
            }
            if vsv not in supported_vsv:
                raise RuntimeError(
                    "Unknown / unsupported VS version '{vsv}'"
                    .format_map(locals()))
            cmake_args += ['-G', supported_vsv[vsv]]
            # choose 'x64' on VS 14 and 15 if not specified explicitly
            # since otherwise 'Win32' is the default for those
            # newer versions default to the host architecture
            if '-A' not in cmake_args and vsv in ('14.0', '15.0'):
                cmake_args += ['-A', 'x64']
        if CMAKE_EXECUTABLE is None:
            raise RuntimeError("Could not find 'cmake' executable")
        os.makedirs(args.build_base, exist_ok=True)
        completed = await run(
            self.context,
            [CMAKE_EXECUTABLE] + cmake_args,
            cwd=args.build_base, env=env)
        # in the case CMake fails with an error code make sure to delete the
        # buildfile if it exists to avoid not running reconfigure next time
        if completed.returncode:
            buildfile = get_buildfile(cmake_cache)
            if buildfile.exists():
                buildfile.unlink()
        return completed.returncode

    def _get_last_cmake_args(self, build_base):
        path = self._get_last_cmake_args_path(build_base)
        if not path.exists():
            return None
        with path.open('r') as h:
            content = h.read()
        try:
            return ast.literal_eval(content)
        except SyntaxError as e:  # noqa: F841
            logger.error(
                "Failed to parse previous --cmake-args from '{path}': {e}"
                .format_map(locals())
            )
            return None

    def _store_cmake_args(self, build_base, cmake_args):
        path = self._get_last_cmake_args_path(build_base)
        with path.open('w') as h:
            h.write(str(cmake_args))

    def _get_last_cmake_args_path(self, build_base):
        return Path(build_base) / 'cmake_args.last'

    async def _build(self, args, env, *, additional_targets=None):
        self.progress('build')

        # invoke build step
        if CMAKE_EXECUTABLE is None:
            raise RuntimeError("Could not find 'cmake' executable")

        targets = []
        if args.cmake_target:
            targets.append(args.cmake_target)
        else:
            targets.append('')
            if additional_targets:
                targets += additional_targets

        jobs_base_generator = is_jobs_based_generator(
            args.build_base, args.cmake_args)
        multi_configuration_generator = is_multi_configuration_generator(
            args.build_base, args.cmake_args)
        if multi_configuration_generator:
            generator = get_generator(args.build_base)
            if 'Visual Studio' in generator:
                env = self._get_msbuild_environment(args, env)

        for i, target in enumerate(targets):
            cmd = [CMAKE_EXECUTABLE, '--build', args.build_base]
            if target:
                if args.cmake_target_skip_unavailable:
                    if not await has_target(args.build_base, target):
                        continue
                self.progress("build target '{target}'".format_map(locals()))
                cmd += ['--target', target]
            if i == 0 and args.cmake_clean_first:
                cmd += ['--clean-first']
            if multi_configuration_generator:
                cmd += ['--config', self._get_configuration(args)]
            if jobs_base_generator:
                job_args = self._get_jobs_arguments(args, env)
                if job_args:
                    cmd += ['--'] + job_args
            completed = await run(
                self.context, cmd, cwd=args.build_base, env=env)
            if completed.returncode:
                return completed.returncode

    def _get_configuration(self, args):
        # check for CMake build type in the command line arguments
        arg_prefix = '-DCMAKE_BUILD_TYPE='
        build_type = None
        for cmake_arg in (args.cmake_args or []):
            if cmake_arg.startswith(arg_prefix):
                build_type = cmake_arg[len(arg_prefix):]
        if build_type is None:
            # get the CMake build type from the CMake cache
            build_type = get_variable_from_cmake_cache(
                args.build_base, 'CMAKE_BUILD_TYPE')
        if build_type in ('Debug', 'MinSizeRel', 'RelWithDebInfo'):
            return build_type
        return 'Release'

    def _get_msbuild_environment(self, args, env):
        generator = get_generator(args.build_base)
        if 'Visual Studio' in generator:
            if 'CL' in env:
                cl_split = env['CL'].split(' ')
                # check that /MP* isn't set already
                if any(x.startswith('/MP') for x in cl_split):
                    # otherwise avoid overriding existing parameters
                    return env
            else:
                cl_split = []
            # build with multiple processes using the number of processors
            cl_split.append('/MP')
            env = dict(env)
            env['CL'] = ' '.join(cl_split)
        return env

    def _get_jobs_arguments(self, args, env):
        """
        Get the make arguments to limit the number of simultaneously run jobs.

        The arguments are chosen based on the `cpu_count`, e.g. -j4 -l4.

        This only handles jobs based generators, see `is_jobs_based_generator()`.

        :param dict env: a dictionary with environment variables
        :returns: list of make arguments
        :rtype: list of strings
        """
        generator = get_generator(args.build_base)
        if 'Makefiles' in generator and args.cmake_jobs is None:
            # check MAKEFLAGS for -j/--jobs/-l/--load-average arguments
            # Note: Ninja does not support environment variables.
            makeflags = env.get('MAKEFLAGS', '')
            regex = (
                r'(?:^|\s)'
                r'(-?(?:j|l)(?:\s*[0-9]+|\s|$))'
                r'|'
                r'(?:^|\s)'
                r'((?:--)?(?:jobs|load-average)(?:(?:=|\s+)[0-9]+|(?:\s|$)))'
            )
            matches = re.findall(regex, makeflags) or []
            matches = [m[0] or m[1] for m in matches]
            if matches:
                # do not extend make arguments, let MAKEFLAGS set things
                return []
        # Use command line specified jobs if positive.
        jobs = 0
        if args.cmake_jobs is not None:
            jobs = args.cmake_jobs
        # If positive, use jobs as is, even if it's more than available.
        # Excessive jobs specified is a user error.
        if jobs <= 0:
            # Base off the number of CPU cores if jobs arg non-positive.
            cores = os.cpu_count()
            with suppress(AttributeError):
                # consider restricted set of CPUs if applicable
                cores = min(cores, len(os.sched_getaffinity(0)))
            if cores is None:
                # the number of cores can't be determined
                return []
            # Finalize jobs as as CPU count deducting the limit specified.
            jobs = max(cores + jobs, 1)
        return [
            '-j{jobs}'.format_map(locals()),
            '-l{jobs}'.format_map(locals()),
        ]

    async def _install(self, args, env):
        self.progress('install')

        if CMAKE_EXECUTABLE is None:
            raise RuntimeError("Could not find 'cmake' executable")
        cmd = [CMAKE_EXECUTABLE]
        cmake_ver = get_cmake_version()
        allow_job_args = is_jobs_based_generator(
            args.build_base, args.cmake_args)
        if cmake_ver and cmake_ver >= parse_version('3.15.0'):
            # CMake 3.15+ supports invoking `cmake --install`
            cmd += ['--install', args.build_base]
            # Job args not compatible with --install directive
            allow_job_args = False
        else:
            # fallback to the install target which implicitly runs a build
            if not cmake_ver:
                logger.warning(
                    'Unable to determine CMake version, building the install'
                    "target instead of invoking 'cmake --install'")
            cmd += ['--build', args.build_base, '--target', 'install']

        multi_configuration_generator = is_multi_configuration_generator(
            args.build_base, args.cmake_args)
        if multi_configuration_generator:
            cmd += ['--config', self._get_configuration(args)]
        if allow_job_args:
            job_args = self._get_jobs_arguments(args, env)
            if job_args:
                cmd += ['--'] + job_args
        return await run(
            self.context, cmd, cwd=args.build_base, env=env)
