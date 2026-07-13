"""Unit tests for the pure chart-rendering helpers."""

from pytest_tqdm.chart import dot_rows, sparkline_rows


def test_sparkline_full_column_is_solid():
    assert sparkline_rows([10], height=1, peak=10) == ["█"]


def test_sparkline_zero_is_blank():
    assert sparkline_rows([0], height=1, peak=10) == [" "]


def test_sparkline_half_fills_bottom_row_only():
    top, bottom = sparkline_rows([5], height=2, peak=10)
    assert top == " "
    assert bottom == "█"


def test_sparkline_scales_across_columns():
    (row,) = sparkline_rows([10, 5, 0], height=1, peak=10)
    assert row == "█▄ "


def test_sparkline_no_peak_is_all_blank():
    assert sparkline_rows([3, 7], height=2, peak=0) == ["  ", "  "]


def test_dot_rows_places_higher_dot_for_more_failures():
    # counts: 0 -> none, 1 -> bottom, 2 -> top (height 2)
    top, bottom = dot_rows([0, 1, 2], height=2)
    assert top == "  ●"
    assert bottom == " ● "


def test_dot_rows_caps_at_height():
    top, bottom = dot_rows([99], height=2)
    assert top == "●"
    assert bottom == " "
