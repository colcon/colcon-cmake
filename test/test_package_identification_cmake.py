# Copyright 2016-2018 Dirk Thomas
# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from tempfile import TemporaryDirectory

from colcon_cmake.package_identification.cmake \
    import CmakePackageIdentification
from colcon_core.package_descriptor import PackageDescriptor


def test_identify():
    extension = CmakePackageIdentification()

    with TemporaryDirectory(prefix='test_colcon_') as basepath:
        desc = PackageDescriptor(basepath)
        desc.type = 'other'
        assert extension.identify(desc) is None
        assert desc.name is None

        desc.type = None
        assert extension.identify(desc) is None
        assert desc.name is None
        assert desc.type is None

        basepath = Path(basepath)
        (basepath / 'CMakeLists.txt').write_text('')
        assert extension.identify(desc) is None
        assert desc.name == basepath.name
        assert desc.type == 'cmake'

        desc = PackageDescriptor(basepath)
        (basepath / 'CMakeLists.txt').write_text(
            'cmake_minimum_required(VERSION 3.10)\n'
            'project(Project NONE)\n')
        assert extension.identify(desc) is None
        assert desc.name == 'Project'
        assert desc.type == 'cmake'

        desc = PackageDescriptor(basepath)
        (basepath / 'CMakeLists.txt').write_text(
            'cmake_minimum_required(VERSION 3.10)\n'
            'project(Project NONE)\n'
            'catkin_workspace()\n')
        assert extension.identify(desc) is None
        assert desc.name is None
        assert desc.type is None

        desc = PackageDescriptor(basepath)
        (basepath / 'CMakeLists.txt').write_text(
            'cmake_minimum_required(VERSION 3.10)\n'
            'project(pkg-name NONE)\n')
        assert extension.identify(desc) is None
        assert desc.name == 'pkg-name'
        assert desc.type == 'cmake'
        assert set(desc.dependencies.keys()) == {'build', 'run'}
        assert not desc.dependencies['build']
        assert not desc.dependencies['run']
        assert extension.identify(desc) is None
        assert desc.name == 'pkg-name'
        assert desc.type == 'cmake'

        desc = PackageDescriptor(basepath)
        (basepath / 'CMakeLists.txt').write_text(
            'cmake_minimum_required(VERSION 3.10)\n'
            'project(other-name NONE)\n'
            'find_package(PkgConfig REQUIRED)\n'
            'pkg_check_modules(DEP_NAME REQUIRED dep-name>=1.1)\n'
            'add_subdirectory(src)\n')
        (basepath / 'src').mkdir(parents=True, exist_ok=True)
        (basepath / 'src' / 'CMakeLists.txt').write_text(
            'find_package(dep-name2 REQUIRED)\n')
        (basepath / 'src' / 'README.txt').write_text(
            'find_package(other-dep-name REQUIRED)\n')
        assert extension.identify(desc) is None
        assert desc.name == 'other-name'
        assert desc.type == 'cmake'
        assert set(desc.dependencies.keys()) == {'build', 'run'}
        assert desc.dependencies['build'] == {
            'dep-name', 'dep-name2', 'PkgConfig',
        }
        assert desc.dependencies['run'] == {
            'dep-name', 'dep-name2', 'PkgConfig',
        }
