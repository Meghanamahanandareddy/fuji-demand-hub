from datetime import date

import pytest
from openpyxl import load_workbook

from app import reporting

END = date(2026, 10, 31)


def test_week_is_seven_days_ending_on_the_given_day():
    assert reporting.week_start(END) == date(2026, 10, 25)


@pytest.mark.parametrize("code", ["railway", "hotels", "park"])
def test_both_report_files_are_created(code, tmp_path):
    pdf, xlsx = reporting.generate(code, END, tmp_path)
    assert pdf.read_bytes()[:4] == b"%PDF"
    wb = load_workbook(xlsx)
    assert "Summary" in wb.sheetnames
    assert "Daily" in wb.sheetnames
    assert wb["Daily"].max_row == 8  # header plus seven days


def test_report_with_no_data_is_refused(tmp_path):
    with pytest.raises(ValueError):
        reporting.generate("railway", date(2020, 1, 1), tmp_path)