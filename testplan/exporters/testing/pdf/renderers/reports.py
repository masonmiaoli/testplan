"""PDF Renderer classes for test report objects"""
import logging

from reportlab.lib import colors

from testplan.common.exporters.pdf import RowStyle
from testplan.common.utils.registry import Registry
from testplan.common.utils.strings import format_description, wrap
from testplan.testing.multitest.base import Categories
from testplan.report.testing import (
    Status, TestReport, TestGroupReport, TestCaseReport
)
from testplan.testing import tagging
from . import constants as const
from .base import format_duration, RowData, BaseRowRenderer, MetadataMixin


class ReportRendererRegistry(Registry):

    def __getitem__(self, item):
        """Try to get renderers for TestGroupReports by category first"""
        if isinstance(item, TestGroupReport):
            try:
                return self.data[(type(item), item.category)]
            except KeyError:
                pass
        return super(ReportRendererRegistry, self).__getitem__(item)


registry = ReportRendererRegistry()


def format_status(report_status):
    """
    For readability purposes, both failed and
    erroneous tests will be displayed as failed.
    """
    if report_status in (Status.FAILED, Status.ERROR):
        return Status.FAILED.title()
    return report_status.title()


@registry.bind(TestReport)
class TestReportRenderer(BaseRowRenderer, MetadataMixin):
    """Renders the rows for the root node: ``report.testing.TestReport``."""

    always_display = True  # Root element always get displayed

    # Need to make this configurable for OS version
    datetime_fmt = '%Y-%m-%d %H:%M:%S %Z'
    metadata_labels = (
        ('user', 'User'),
        ('project', 'Project'),
        ('git_url', 'Git URL'),
        ('git_commit', 'Git commit'),
        # These two will be set via `get_tag_pdf_ctx`
        ('report_tags_all', 'Report tags (all)'),
        ('report_tags_any', 'Report tags (any)'),
    )

    def get_metadata_context(self, source):
        """
          Enriched meta context with test counts, run times etc.
        """
        ctx = super(TestReportRenderer, self).get_metadata_context(source)

        counts = source.counts

        ctx.update([
            ('Total run', counts.failed + counts.passed + counts.error),
            ('Passed', counts.passed),
            ('Failed', counts.failed + counts.error),
            ('Style (Passing / Failing)', '{} / {}'.format(
                self.style.passing.label,
                self.style.failing.label
            )),
        ])

        if 'run' in source.timer:
            run_interval = source.timer['run']
            ctx.update([
                ('Start time', run_interval.start.strftime(self.datetime_fmt)),
                ('End time', run_interval.end.strftime(self.datetime_fmt)),
                ('Elapsed', format_duration(run_interval.elapsed)),
            ])
        return ctx

    def get_row_data(self, source, depth, row_idx):
        """Render Testplan header & metadata"""
        row_data = RowData(
            start=row_idx,
            content=[source.name, '', '', format_status(source.status)],
            style=[
                RowStyle(
                    bottom_padding=const.TITLE_PADDING,
                    font=(const.FONT_BOLD, const.FONT_SIZE_LARGE),
                    left_padding=0,
                ),
                RowStyle(
                    text_color=colors.green if source.passed else colors.red,
                    start_column=3,
                )
            ]
        )

        # Metadata
        row_data.append(
            content=[
                [key, value, '', '']
                for key, value in self.get_metadata_context(source).items()
            ],
            style=[
                RowStyle(
                    bottom_padding=0,
                    left_padding=0,
                    top_padding=0,
                    valign='TOP',
                ),
                RowStyle(
                    font=(const.FONT_BOLD, const.FONT_SIZE_SMALL),
                    start_column=0,
                    end_column=0,
                ),
                RowStyle(
                    font=(const.FONT, const.FONT_SIZE_SMALL),
                    start_column=1,
                    end_column=1,
                )
            ]
        )

        return row_data


@registry.bind(TestGroupReport)
class TestRowRenderer(BaseRowRenderer, MetadataMixin):
    """Common logic for rendering test report objects."""

    def get_row_data(self, source, depth, row_idx):
        """
        Display test name/description, passed status & logs (if enabled).
        """
        row_data = self.get_header(source, depth, row_idx)

        if source.description:
            row_data += self.get_description(
                description=source.description,
                depth=depth,
                row_idx=row_data.end)

        # Display logs that are higher than ERROR level
        logs = [log for log in source.logs if log['levelno'] >= logging.ERROR]
        if logs:
            row_data += self.get_logs(
                logs=source.logs, depth=depth + 1, row_idx=row_data.end)

        return row_data

    def get_header_linestyle(self):
        """Styling for the line below test header."""
        return 1, colors.lightgrey

    def get_header(self, source, depth, row_idx):
        """
        Assuming we have 4 columns per row, render the header in the format:

        [<TEST_NAME> - <NATIVE TAGS>][][][<TEST_STATUS>]
        """
        passed = source.passed
        font_size = const.FONT_SIZE if depth == 0 else const.FONT_SIZE_SMALL
        font = const.FONT_BOLD if (depth == 0) or not passed else const.FONT

        styles = [
            RowStyle(
                font=(font, font_size),
                line_above=self.get_header_linestyle(),
            ),
            RowStyle(
                left_padding=const.INDENT * depth,
                end_column=0,
            ),
            RowStyle(
                text_color=colors.green if passed else colors.red,
                start_column=const.LAST_COLUMN_IDX,
            )
        ]

        if not source.passed:
            styles.append(RowStyle(background=colors.whitesmoke))

        header_text = source.name

        if source.tags:
            header_text += ' (Tags: {})'.format(tagging.tag_label(source.tags))

        return RowData(
            start=row_idx,
            content=[header_text, '', '', format_status(source.status)],
            style=styles
        )

    def get_description(self, description, depth, row_idx):
        """
        Description for a test object,
        this will generally be docstring text.
        """
        return RowData(
            start=row_idx,
            content=format_description(description),
            style=RowStyle(
                font=(const.FONT_ITALIC, const.FONT_SIZE_SMALL),
                left_padding=const.INDENT * depth,
                text_color=colors.grey
            )
        )

    def get_logs(self, logs, depth, row_idx):
        """Logs created by the `report.logger` object."""
        font_size = const.FONT_SIZE_SMALL
        width = const.WRAP_LIMITS[font_size]

        return RowData(
            start=row_idx,
            content=[
                [wrap(log['message'], width=width), '', '', '']
                for log in logs
            ],
            style=RowStyle(
                font=(const.FONT, font_size),
                left_padding=const.INDENT * depth,
                text_color=colors.gray,
            )
        )

    def get_style(self, source):
        if source.passed:
            return self.style.passing
        return self.style.failing

    def should_display(self, source):
        """
        Filter out passing rows if `failing_tests` is `True`.
        """
        style = self.get_style(source)
        if source.category == Categories.SUITE:
            return style.display_suite
        elif source.category == Categories.PARAMETRIZATION:
            return style.display_testcase
        return style.display_multitest


@registry.bind(TestCaseReport)
class TestCaseRowBuilder(TestRowRenderer):
    """
    Row builder for TestCaseReport, this mainly corresponds
    to a testcase method / function.
    """

    def get_header_linestyle(self):
        """
        Testcase line separators are a little bit
        thinner, as there are many testcases per test run.
        """
        return 0.5, colors.lightgrey

    def should_display(self, source):
        return self.get_style(source).display_testcase


@registry.bind((TestGroupReport, Categories.MULTITEST))
class MultiTestRowBuilder(TestRowRenderer):
    """Multitests get special treatment with extra formatting & summary."""

    def get_header_linestyle(self):
        """
        More distinctive line separator for Multitests,
        as they are high level test containers.
        """
        return 1, colors.black

    def get_header(self, source, depth, row_idx):
        """Display short summary & run times along with pass/fail status."""
        row_data = RowData(
            start=row_idx,
            content=const.EMPTY_ROW,
            style=RowStyle(line_below=(1, colors.black))
        )

        row_data += super(
            MultiTestRowBuilder, self).get_header(source, depth, row_data.end)

        if source.passed:
            summary = 'All tests passed'
        else:
            summary = '{} tests failed' .format(
                source.counts.failed + source.counts.error)

        if 'run' in source.timer:
            summary += ', total run time: {}.'.format(
                format_duration(source.timer['run'].elapsed))

        row_data.append(
            content=[summary, '', '', ''],
            style=[
                RowStyle(
                    font=(const.FONT, const.FONT_SIZE_SMALL),
                    left_padding=const.INDENT * depth,
                    end_column=0
                ),
                RowStyle(
                    bottom_padding=0,
                    top_padding=0,
                    valign='TOP'
                )
            ]
        )

        return row_data