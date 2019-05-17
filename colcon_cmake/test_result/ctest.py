# Copyright 2019 Dirk Thomas
# Licensed under the Apache License, Version 2.0

from xml.etree.ElementTree import ElementTree

from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import satisfies_version
from colcon_test_result.test_result import Result
from colcon_test_result.test_result import TestResultExtensionPoint

logger = colcon_logger.getChild(__name__)


class CtestTestResult(TestResultExtensionPoint):
    """
    Collect the CTest results generated when testing a set of CMake packages.

    It checks each direct subdirectory of the passed build base for a
    'Testing/TAG' file.
    The first line in that file contains the directory name of the latest
    'Test.xml' result file relative to the 'Testing' directory.
    """

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            TestResultExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def get_test_results(self, basepath, *, collect_details):  # noqa: D102
        results = set()
        # check all 'TAG' files in a directory named 'Testing'
        for tag_file in basepath.glob('**/Testing/TAG'):
            if not tag_file.is_file():
                continue

            # find the latest Test.xml file
            latest_xml_dir = tag_file.read_text().splitlines()[0]
            latest_xml_path = tag_file.parent / latest_xml_dir / 'Test.xml'
            if not latest_xml_path.exists():
                logger.warn(
                    "Skipping '{tag_file}': could not find latest XML file "
                    "'{latest_xml_path}'".format_map(locals()))
                continue

            # parse the XML file
            tree = ElementTree()
            root = tree.parse(str(latest_xml_path))

            # check if the root tag looks like a CTest file
            if root.tag != 'Site':
                logger.warn(
                    "Skipping '{latest_xml_path}': the root tag is not 'Site'"
                    .format_map(locals()))
                continue

            # look for a single 'Testing' child tag
            children = root.getchildren()
            if len(children) != 1:
                logger.warn(
                    "Skipping '{latest_xml_path}': 'Site' tag is expected to "
                    '"have exactly one child'.format_map(locals()))
                continue
            if children[0].tag != 'Testing':
                logger.warn(
                    "Skipping '{latest_xml_path}': the child tag is not "
                    "'Testing'".format_map(locals()))
                continue

            # collect information from all 'Test' tags
            result = Result(str(latest_xml_path))
            for child in children[0]:
                if child.tag != 'Test':
                    continue

                result.test_count += 1

                try:
                    status = child.attrib['Status']
                except KeyError:
                    logger.warn(
                        "Skipping '{latest_xml_path}': a 'test' tag lacks a "
                        "'Status' attribute".format_map(locals()))
                    break

                if status == 'failed':
                    result.failure_count += 1
                elif status == 'notrun':
                    result.skipped_count += 1
                elif status != 'passed':
                    result.error_count += 1
            else:
                results.add(result)
        return results
