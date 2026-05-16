# Copyright 2019 Dirk Thomas
# Licensed under the Apache License, Version 2.0

from xml.etree.ElementTree import ElementTree

from colcon_core.extension_point import get_all_extension_points
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
        self.xunit_extension_installed = "xunit" in get_all_extension_points()["colcon_test_result.test_result"].keys()

    def get_test_results(  # noqa: D102
        self, basepath, *, collect_details, files=None
    ):
        results = set()
        # check all 'TAG' files in a directory named 'Testing'
        for tag_file in basepath.glob('**/Testing/TAG'):
            if not tag_file.is_file():
                continue

            if files is not None:
                files.add(str(tag_file))

            # find the latest Test.xml file
            latest_xml_dir = tag_file.read_text().splitlines()[0]
            latest_xml_path = tag_file.parent / latest_xml_dir / 'Test.xml'
            if not latest_xml_path.exists():
                logger.warning(
                    f"Skipping '{tag_file}': could not find latest XML file "
                    f"'{latest_xml_path}'")
                continue

            # parse the XML file
            tree = ElementTree()
            root = tree.parse(str(latest_xml_path))

            # check if the root tag looks like a CTest file
            if root.tag != 'Site':
                logger.warning(
                    f"Skipping '{latest_xml_path}': the root tag is not "
                    "'Site'")
                continue

            # look for a single 'Testing' child tag
            children = list(root)
            if len(children) != 1:
                logger.warning(
                    f"Skipping '{latest_xml_path}': 'Site' tag is expected to "
                    '"have exactly one child')
                continue
            if children[0].tag != 'Testing':
                logger.warning(
                    f"Skipping '{latest_xml_path}': the child tag is not "
                    "'Testing'")
                continue

            if files is not None:
                files.add(str(latest_xml_path))

            # collect information from all 'Test' tags
            result = Result(str(latest_xml_path))
            for child in children[0]:
                if child.tag != 'Test':
                    continue

                try:
                    status = child.attrib['Status']
                except KeyError:
                    logger.warning(
                        f"Skipping '{latest_xml_path}': a 'test' tag lacks a "
                        "'Status' attribute")
                    break

                name = child.findtext('Name')

                # Skip tests which are labeled as gtest if the "xunit" extension is also installed.
                # Gtest generates an xunit file containing all individual test cases, so don't add +1 for the ctest summary here.
                if self.xunit_extension_installed:
                    labels = child.find("Labels") or []
                    if ("gtest" in [l.text for l in labels]):
                        logger.debug(f"Skipping '{name}' in '{latest_xml_path}': gtest has own result file.")
                        continue

                result.test_count += 1

                if status == 'failed':
                    result.failure_count += 1
                elif status == 'notrun':
                    result.skipped_count += 1
                elif status != 'passed':
                    result.error_count += 1

                if collect_details and status == 'failed':
                    lines = [name]
                    lines.extend(
                        _get_messages(
                            'failure message',
                            child.findtext('Results/Measurement/Value')))
                    result.details.append('\n'.join(lines))
            else:
                if result.test_count > 0:
                    results.add(result)
        return results


def _get_messages(label, message):
    lines = []
    if message:
        lines.append('<<< ' + label)
        for line in message.strip('\n\r').splitlines():
            lines.append('  ' + line)
        lines.append('>>>')
    return lines
