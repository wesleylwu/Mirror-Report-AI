"use client";

import { useMemo, useCallback } from "react";
import { FaFileExcel, FaSpinner } from "react-icons/fa";
import {
  MatchedTemplate,
  ExtractedData,
  BorderSpec,
  CellSpec,
  HeaderRowSpec,
  ColumnSpec,
} from "../types/template";
import { fuzzyGet, formatItemCode } from "../utils/template";

const normalizeRow = (row: any, colNames: string[]): Record<string, string> => {
  if (!row) return {};
  if (!Array.isArray(row)) {
    return row as Record<string, string>;
  }
  const result: Record<string, string> = {};
  const seen: Record<string, number> = {};
  for (let i = 0; i < colNames.length; i++) {
    const cn = colNames[i] || "";
    const cnt = seen[cn] || 0;
    seen[cn] = cnt + 1;
    const key = cnt === 0 ? cn : (cn ? `${cn}_${cnt + 1}` : `_${cnt + 1}`);
    result[key] = row[i] !== undefined ? String(row[i]) : "";
  }
  return result;
};

interface TemplateViewerProps {
  matchedTemplate: MatchedTemplate;
  extractedData: ExtractedData;
  onExtractedDataChange?: (newData: ExtractedData) => void;
  isRegeneratingExcel?: boolean;
  onDownloadExcel?: () => void;
  xlsxBlob?: Blob | null;
  xlsxName?: string;
}

const TemplateViewer = ({
  matchedTemplate,
  extractedData,
  onExtractedDataChange,
  isRegeneratingExcel = false,
  onDownloadExcel,
  xlsxBlob,
  xlsxName,
}: TemplateViewerProps) => {
  const colWidths = useMemo(() => {
    const spec = matchedTemplate.column_widths || {};
    const colNames = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
    const widths: number[] = [];
    for (let i = 0; i < 24; i++) {
      const colName = colNames[i];
      widths.push(spec[colName] ?? 8.43);
    }
    const total = widths.reduce((sum, w) => sum + w, 0);
    return { widths, total };
  }, [matchedTemplate]);

  const getCellWidthPercent = useCallback(
    (startCol: number, endCol: number) => {
      let sum = 0;
      for (let i = startCol - 1; i < endCol; i++) {
        sum += colWidths.widths[i] ?? 8.43;
      }
      return (sum / colWidths.total) * 100;
    },
    [colWidths],
  );

  const getBorderStyle = useCallback((b: BorderSpec | null | undefined) => {
    if (!b) return {};
    const style: Record<string, string> = {};
    const mapSide = (side: string | null | undefined) => {
      if (!side || side === "none") return "none";
      if (side === "thin") return "1px solid #111827";
      if (side === "medium") return "2px solid #111827";
      if (side === "double") return "3px double #111827";
      return "1px solid #111827";
    };
    style.borderTop = mapSide(b.top);
    style.borderBottom = mapSide(b.bottom);
    style.borderLeft = mapSide(b.left);
    style.borderRight = mapSide(b.right);
    return style;
  }, []);

  const triggerDownload = useCallback((blob: Blob, name: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;

    const isIOS =
      typeof window !== "undefined" &&
      (/iPad|iPhone|iPod/.test(navigator.userAgent) ||
        (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1));
    if (isIOS) {
      a.target = "_blank";
    }

    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    setTimeout(() => {
      URL.revokeObjectURL(url);
    }, 10000);
  }, []);

  const handleDownload = useCallback(() => {
    if (onDownloadExcel) {
      onDownloadExcel();
    } else if (xlsxBlob) {
      triggerDownload(xlsxBlob, xlsxName || "export.xlsx");
    }
  }, [onDownloadExcel, xlsxBlob, xlsxName, triggerDownload]);

  const handleHeaderChange = useCallback(
    (key: string, value: string) => {
      let newData;
      if (key === "title" || key === "section_header") {
        newData = {
          ...extractedData,
          [key]: value,
        };
      } else {
        newData = {
          ...extractedData,
          header: {
            ...extractedData.header,
            [key]: value,
          },
        };
      }
      if (onExtractedDataChange) {
        onExtractedDataChange(newData);
      }
    },
    [extractedData, onExtractedDataChange],
  );

  const getHeaderCellValue = useCallback(
    (cell: CellSpec) => {
      if (cell.fixed) {
        return cell.value || "";
      }
      const key = cell.key || "";
      if (key === "title" || key === "section_header") {
        return extractedData[key] || "";
      }
      if (cell.title_part) {
        const title = extractedData.title || "";
        const splitTitle = (t: string) => {
          t = t.trim();
          let left = "";
          let right = "";
          let center = t;

          const m1 = /^(\d{4}年\d{1,2}月)\s+(.*)$/.exec(center);
          if (m1) {
            left = m1[1];
            center = m1[2];
          }
          const m2 = /^(.*?)\s+(\d{4}\/\d{1,2}\/\d{1,2}.*)$/.exec(center);
          if (m2) {
            center = m2[1];
            right = m2[2];
          }
          return { left, center: center.trim(), right: right.trim() };
        };
        const parts = splitTitle(title);
        return parts[cell.title_part as "left" | "center" | "right"] || "";
      }
      if (cell.concat_keys) {
        const parts = cell.concat_keys.map((k) =>
          fuzzyGet(extractedData.header, k),
        );
        return parts.filter(Boolean).join(" ");
      }
      if (cell.value_part) {
        if (cell.value_part === "tail" && extractedData.header?.[`${key}_sub`] !== undefined) {
          return extractedData.header[`${key}_sub`];
        }
        const raw = fuzzyGet(extractedData.header, key);
        const tokens = raw.trim().split(/[ \u3000]+/);
        if (cell.value_part === "tail") {
          return tokens.length > 1 ? tokens[tokens.length - 1] : "";
        } else {
          return tokens.length > 1
            ? tokens.slice(0, -1).join(" ")
            : tokens[0] || "";
        }
      }
      let value = fuzzyGet(extractedData.header, key);
      if (cell.label_prefix && value) {
        value = `${key} ${value}`;
      }
      return value;
    },
    [extractedData],
  );

  const handleRowChange = useCallback(
    (rIndex: number, key: string, value: string, colIndex?: number) => {
      const rows = [...(extractedData.table?.rows || [])];
      if (rows[rIndex]) {
        if (Array.isArray(rows[rIndex])) {
          const rowArr = [...(rows[rIndex] as any)];
          if (colIndex !== undefined) {
            rowArr[colIndex] = value;
          }
          rows[rIndex] = rowArr as any;
        } else {
          rows[rIndex] = {
            ...(rows[rIndex] as Record<string, string>),
            [key]: value,
          };
        }
      }
      const newData = {
        ...extractedData,
        table: {
          ...extractedData.table,
          rows,
        },
      };
      if (onExtractedDataChange) {
        onExtractedDataChange(newData);
      }
    },
    [extractedData, onExtractedDataChange],
  );

  return (
    <div className="flex w-full flex-col gap-4">
      <div className="border-mirror-light-blue max-h-[70vh] w-full overflow-auto rounded-2xl border bg-slate-100 p-4 shadow-inner print:max-h-none print:border-none print:bg-white print:p-0 print:shadow-none">
        <div
          className="bg-mirror-white print-a4-page relative mx-auto flex aspect-210/297 w-full max-w-4xl flex-col border border-gray-300 p-6 text-xs shadow-md select-none print:border-none print:p-0 print:shadow-none"
          style={{ minWidth: "600px" }}
        >
          <div className="relative flex w-full flex-col">
            {matchedTemplate.header?.map(
              (rowSpec: HeaderRowSpec, rowIndex: number) => (
                <div
                  key={`h-${rowIndex}`}
                  className="flex w-full"
                  style={{ height: `${rowSpec.height || 25}px` }}
                >
                  {rowSpec.cells.map((cell: CellSpec, cellIndex: number) => {
                    const val = getHeaderCellValue(cell);
                    const widthPercent = getCellWidthPercent(
                      cell.col,
                      cell.end_col,
                    );
                    const borderStyle = getBorderStyle(cell.border);
                    const isEditable = !cell.fixed && cell.key && !!onExtractedDataChange;

                    return (
                      <div
                        key={cellIndex}
                        className="flex overflow-hidden p-1"
                        style={{
                          width: `${widthPercent}%`,
                          justifyContent:
                            cell.align?.h === "center"
                              ? "center"
                              : cell.align?.h === "right"
                                ? "flex-end"
                                : "flex-start",
                          alignItems:
                            cell.align?.v === "center"
                              ? "center"
                              : cell.align?.v === "bottom"
                                ? "flex-end"
                                : "flex-start",
                          fontWeight: cell.font?.bold ? "bold" : "normal",
                          fontSize: `${cell.font?.size ? cell.font.size * 0.8 : 8}px`,
                          whiteSpace: cell.align?.wrap ? "normal" : "nowrap",
                          textDecoration: cell.font?.underline ? "underline" : "none",
                          boxSizing: "border-box",
                          ...borderStyle,
                        }}
                      >
                        {isEditable ? (
                          <span
                            contentEditable={true}
                            suppressContentEditableWarning={true}
                            onBlur={(e) =>
                              handleHeaderChange(
                                cell.key!,
                                e.currentTarget.textContent || "",
                              )
                            }
                            className="hover:border-mirror-cyan/40 focus:border-mirror-cyan focus:bg-mirror-cyan/5 max-w-full cursor-text truncate rounded border border-dashed border-transparent px-0.5 leading-tight transition-colors outline-none"
                          >
                            {val}
                          </span>
                        ) : (
                          <span className="max-w-full truncate leading-tight">
                            {val}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              ),
            )}

            {matchedTemplate.col_headers && (
              <div
                className="flex w-full"
                style={{
                  height: `${(matchedTemplate.col_headers.row_heights || []).reduce((a: number, b: number) => a + b, 0) || 30}px`,
                }}
              >
                {matchedTemplate.col_headers.cells.map(
                  (cell: CellSpec, cellIndex: number) => {
                    const widthPercent = getCellWidthPercent(
                      cell.col,
                      cell.end_col,
                    );
                    const borderStyle = getBorderStyle(cell.border);
                    return (
                      <div
                        key={`ch-${cellIndex}`}
                        className="flex overflow-hidden bg-slate-50 p-1"
                        style={{
                          width: `${widthPercent}%`,
                          justifyContent:
                            cell.align?.h === "center"
                              ? "center"
                              : cell.align?.h === "right"
                                ? "flex-end"
                                : "flex-start",
                          alignItems:
                            cell.align?.v === "center"
                              ? "center"
                              : cell.align?.v === "bottom"
                                ? "flex-end"
                                : "flex-start",
                          fontSize: `${cell.font?.size ? cell.font.size * 0.8 : 8}px`,
                          textDecoration: cell.font?.underline ? "underline" : "none",
                          boxSizing: "border-box",
                          ...borderStyle,
                        }}
                      >
                        <span className="max-w-full truncate leading-tight font-bold">
                          {cell.value}
                        </span>
                      </div>
                    );
                  },
                )}
              </div>
            )}

            {matchedTemplate.data_rows && (
              <div className="flex w-full flex-col">
                {(() => {
                  const dr = matchedTemplate.data_rows;
                  const colSpecs = dr.columns || [];
                  const tableData = extractedData.table || {};
                  const colNames = tableData.columns || [];
                  const rawRows = tableData.rows || [];
                  const rows = rawRows
                    .map((r) => normalizeRow(r, colNames))
                    .filter(
                      (r) =>
                        !(
                          "_full_width" in r &&
                          typeof r._full_width === "string" &&
                          r._full_width.replace(/\s+/g, "") === "備考"
                        ),
                    );
                  const maxRows = Math.max(dr.count || 0, rows.length);
                  return Array.from({ length: maxRows }).map((_, rowIndex) => {
                    const rowData = rows[rowIndex] || {};
                    const isFirst = rowIndex === 0;

                    // Positional value resolution for columns based on tableData.columns
                    const colNames = tableData.columns || [];
                    const seen: Record<string, number> = {};
                    const posValues: string[] = [];
                    for (const colName of colNames) {
                      const cnt = seen[colName] || 0;
                      seen[colName] = cnt + 1;
                      if (cnt === 0) {
                        posValues.push(rowData[colName] ?? "");
                      } else {
                        const dedupKey = colName ? `${colName}_${cnt + 1}` : `_${cnt + 1}`;
                        posValues.push(rowData[dedupKey] ?? "");
                      }
                    }

                    if ("_full_width" in rowData) {
                      return (
                        <div
                          key={`dr-${rowIndex}`}
                          className="flex w-full"
                          style={{ height: `${dr.row_height || 25}px` }}
                        >
                          <div
                            contentEditable={true}
                            suppressContentEditableWarning={true}
                            onBlur={(e) =>
                              handleRowChange(
                                rowIndex,
                                "_full_width",
                                e.currentTarget.textContent || "",
                              )
                            }
                            className="hover:border-mirror-cyan/40 focus:border-mirror-cyan focus:bg-mirror-cyan/5 bg-mirror-light-blue/30 flex w-full cursor-text items-center justify-center border border-dashed border-transparent p-1 text-center text-[9px] font-bold transition-colors outline-none"
                            style={{
                              boxSizing: "border-box",
                              ...getBorderStyle(colSpecs[0]?.border),
                            }}
                          >
                            {rowData["_full_width"]}
                          </div>
                        </div>
                      );
                    }

                    return (
                      <div
                        key={`dr-${rowIndex}`}
                        className="flex w-full"
                        style={{ height: `${dr.row_height || 25}px` }}
                      >
                        {colSpecs.map(
                          (colSpec: ColumnSpec, colIndex: number) => {
                            let rawVal = "";
                            if (colSpec.col_index !== undefined && posValues[colSpec.col_index] !== undefined && posValues[colSpec.col_index] !== "") {
                              rawVal = posValues[colSpec.col_index];
                            } else {
                              rawVal = fuzzyGet(rowData, colSpec.key || "");
                            }
                            let val = rawVal;
                            if (colSpec.format === "item_code") {
                              val = formatItemCode(
                                rawVal,
                                colSpec.format_options,
                              );
                            }
                            const widthPercent = getCellWidthPercent(
                              colSpec.col,
                              colSpec.end_col,
                            );
                            const borderSpec = isFirst
                              ? colSpec.first_row_border || colSpec.border
                              : colSpec.border;
                            const borderStyle = getBorderStyle(borderSpec);

                            const editKey = colSpec.col_index !== undefined && colNames[colSpec.col_index] !== undefined
                              ? (() => {
                                  const name = colNames[colSpec.col_index];
                                  const idxOfCol = colNames.slice(0, colSpec.col_index + 1).filter(n => n === name).length;
                                  return idxOfCol > 1 ? `${name}_${idxOfCol}` : name;
                                })()
                              : colSpec.key;
                            const isEditable = !!editKey && !!onExtractedDataChange;

                            return (
                              <div
                                key={colIndex}
                                className="flex overflow-hidden p-1"
                                style={{
                                  width: `${widthPercent}%`,
                                  justifyContent:
                                    colSpec.align?.h === "center"
                                      ? "center"
                                      : colSpec.align?.h === "right"
                                        ? "flex-end"
                                        : "flex-start",
                                  alignItems:
                                    colSpec.align?.v === "center"
                                      ? "center"
                                      : colSpec.align?.v === "bottom"
                                        ? "flex-end"
                                        : "flex-start",
                                  fontSize: `${colSpec.font?.size ? colSpec.font.size * 0.8 : 8}px`,
                                  fontWeight: colSpec.font?.bold
                                    ? "bold"
                                    : "normal",
                                  whiteSpace: colSpec.align?.wrap
                                    ? "pre-wrap"
                                    : "nowrap",
                                  textDecoration: colSpec.font?.underline ? "underline" : "none",
                                  boxSizing: "border-box",
                                  ...borderStyle,
                                }}
                              >
                                {isEditable ? (
                                  <span
                                    contentEditable={true}
                                    suppressContentEditableWarning={true}
                                    onBlur={(e) =>
                                      handleRowChange(
                                        rowIndex,
                                        editKey!,
                                        e.currentTarget.textContent || "",
                                        colSpec.col_index,
                                      )
                                    }
                                    className="hover:border-mirror-cyan/40 focus:border-mirror-cyan focus:bg-mirror-cyan/5 max-w-full cursor-text truncate rounded border border-dashed border-transparent px-0.5 leading-tight transition-colors outline-none"
                                  >
                                    {val}
                                  </span>
                                ) : (
                                  <span className="max-w-full truncate leading-tight">
                                    {val}
                                  </span>
                                )}
                              </div>
                            );
                          },
                        )}
                      </div>
                    );
                  });
                })()}
              </div>
            )}

            {matchedTemplate.footer && (
              <div
                className="flex w-full"
                style={{ height: `${matchedTemplate.footer.height || 35}px` }}
              >
                {matchedTemplate.footer.cells.map(
                  (cell: CellSpec, cellIndex: number) => {
                    const widthPercent = getCellWidthPercent(
                      cell.col,
                      cell.end_col,
                    );
                    const borderStyle = getBorderStyle(cell.border);
                    return (
                      <div
                        key={`f-${cellIndex}`}
                        className="flex bg-slate-50 p-1"
                        style={{
                          width: `${widthPercent}%`,
                          justifyContent:
                            cell.align?.h === "center"
                              ? "center"
                              : cell.align?.h === "right"
                                ? "flex-end"
                                : "flex-start",
                          alignItems:
                            cell.align?.v === "center"
                              ? "center"
                              : cell.align?.v === "bottom"
                                ? "flex-end"
                                : "flex-start",
                          fontSize: `${cell.font?.size ? cell.font.size * 0.8 : 8}px`,
                          fontWeight: cell.font?.bold ? "bold" : "normal",
                          textDecoration: cell.font?.underline ? "underline" : "none",
                          boxSizing: "border-box",
                          ...borderStyle,
                        }}
                      >
                        {cell.value}
                      </div>
                    );
                  },
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="mt-2 flex w-full justify-center gap-4 print:hidden">
        <button
          onClick={handleDownload}
          disabled={isRegeneratingExcel}
          className="bg-mirror-cyan hover:bg-mirror-dark-blue text-mirror-white flex cursor-pointer items-center justify-center gap-2 rounded-lg px-5 py-2.5 text-sm font-bold shadow-sm transition-colors duration-200 disabled:opacity-60"
        >
          {isRegeneratingExcel ? (
            <FaSpinner className="h-5 w-5 animate-spin" />
          ) : (
            <FaFileExcel className="h-5 w-5" />
          )}
          Excel
        </button>
        <button
          onClick={() => window.print()}
          className="bg-mirror-dark-blue hover:bg-mirror-cyan text-mirror-white flex cursor-pointer items-center justify-center gap-2 rounded-lg px-5 py-2.5 text-sm font-bold shadow-sm transition-colors duration-200"
        >
          Print
        </button>
      </div>
    </div>
  );
};

export default TemplateViewer;
