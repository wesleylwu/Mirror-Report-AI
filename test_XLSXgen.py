from XLSXgen import json_to_xlsx

COMMON_KWARGS = dict(
    footer="備考",
    column_alignments={
        "原単位": "right",
        "分量": "right",
        "称量者": "center",
        "原料ロット": "center",
        "確認者": "center",
    },
    column_vertical_alignments={
        "原単位": "center",
    },
    column_number_formats={
        "原単位": "0.0000",
    },
)

json_to_xlsx(
    "test_output/chouhyou.json",
    "test_output/chouhyou.xlsx",
    blank_rows=14,
    column_widths={
        "成分名": 45,
        "原単位": 10,
        "分量": 12,
        "称量者": 10,
        "原料ロット": 14,
        "確認者": 10,
    },
    **COMMON_KWARGS,
)
print("Generated test_output/chouhyou.xlsx")

json_to_xlsx(
    "test_output/seizou_shijisho.json",
    "test_output/seizou_shijisho.xlsx",
    blank_rows=18,
    column_widths={
        "成分名": 50,
        "原単位": 10,
        "分量": 12,
        "称量者": 10,
        "原料ロット": 14,
        "確認者": 10,
    },
    **COMMON_KWARGS,
)
print("Generated test_output/seizou_shijisho.xlsx")

json_to_xlsx(
    "test_output/kijun_kyakusaki_abc.json",
    "test_output/kijun_kyakusaki_abc.xlsx",
    column_width=16,
    column_widths={
        "順位": 6,
        "基準客先名": 30,
    },
    column_alignments={
        "順位": "center",
        "基準客先名": "left",
        "営業部": "right",
        "他営業所": "right",
        "本部売上額": "right",
        "累計売上額": "right",
        "売上原価": "right",
        "営業粗利率": "right",
    },
    column_number_formats={
        "営業部": "#,##0",
        "他営業所": "#,##0",
        "本部売上額": "#,##0",
        "累計売上額": "#,##0",
        "売上原価": "#,##0",
        "営業粗利率": '0.0"%"',
    },
)
print("Generated test_output/kijun_kyakusaki_abc.xlsx")

json_to_xlsx(
    "test_output/kahetsu_kijun_uriage.json",
    "test_output/kahetsu_kijun_uriage.xlsx",
    column_width=12,
    column_widths={"部門名": 8, "基準客": 8, "基準客名": 32},
    column_alignments={
        "部門名": "center",
        "基準客": "center",
        "基準客名": "left",
        "営業粗利額": "right",
        "営業粗利率": "right",
        "目標粗利達成率": "right",
        "純売上金額": "right",
        "目標純売上達成率": "right",
        "目標在庫金額": "right",
        "在庫金額": "right",
        "目標売上額": "right",
    },
    column_number_formats={
        "営業粗利額": "#,##0",
        "営業粗利率": '0.0"%"',
        "目標粗利達成率": '0.0"%"',
        "純売上金額": "#,##0",
        "目標純売上達成率": '0.0"%"',
        "目標在庫金額": "#,##0",
        "在庫金額": "#,##0",
        "目標売上額": "#,##0",
    },
    # The "1課計" (department total) row gets a light gray fill, matching the
    # paper's visual distinction between individual customer rows and the
    # department subtotal at the bottom. The one row with a negative
    # adjustment (関合担当その他, -1,900) gets red text, matching how the
    # source paper prints that figure in red ink.
    row_fills={39: "D9D9D9"},
    row_font_colors={38: "FF0000"},
)
print("Generated test_output/kahetsu_kijun_uriage.xlsx")

_MONTH_COLUMNS = [
    "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月", "1月", "2月", "3月",
    "上半期合計", "下半期合計", "年間合計",
]
json_to_xlsx(
    "test_output/tsukibetsu_uriage.json",
    "test_output/tsukibetsu_uriage.xlsx",
    column_width=12,
    column_widths={"区分": 10},
    column_alignments={"区分": "center", **{m: "right" for m in _MONTH_COLUMNS}},
    # All four rows are currency by default; row 3 (粗利率, the growth-rate
    # row) overrides to a percentage format instead, since the metric type
    # here varies by row, not by column.
    column_number_formats={m: "#,##0" for m in _MONTH_COLUMNS},
    row_number_formats={3: '0.0"%"'},
    # The three summary columns get a light gray fill, matching how the
    # paper visually sets totals apart from the per-month figures.
    column_fills={"上半期合計": "D9D9D9", "下半期合計": "D9D9D9", "年間合計": "D9D9D9"},
)
print("Generated test_output/tsukibetsu_uriage.xlsx")

json_to_xlsx(
    "test_output/kijun_kyakusaki_simple.json",
    "test_output/kijun_kyakusaki_simple.xlsx",
    column_width=14,
    column_widths={"基準客": 16},
    # Leaf names here are "当月"/"累計" (shared across every metric group),
    # so the alignment/format overrides apply uniformly across all of them.
    column_alignments={"基準客": "left", "当月": "right", "累計": "right"},
    column_number_formats={"当月": "#,##0", "累計": "#,##0"},
)
print("Generated test_output/kijun_kyakusaki_simple.xlsx")
