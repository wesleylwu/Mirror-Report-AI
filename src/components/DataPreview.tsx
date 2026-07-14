"use client";

import { useCallback } from "react";
import { FaFileExcel, FaSpinner } from "react-icons/fa";
import {
  ExtractedData,
  HeaderRow,
  TableRow,
  TaggedRow,
  TaggedRowStyle,
} from "../types/template";

interface DataPreviewProps {
  extractedData: ExtractedData;
  htmlContent?: string;
  onExtractedDataChange?: (newData: ExtractedData) => void;
  isRegeneratingExcel?: boolean;
  onDownloadExcel?: () => void;
  xlsxBlob?: Blob | null;
  xlsxName?: string;
}

const isFullWidthRow = (row: TableRow): row is { _full_width: string } =>
  !Array.isArray(row) &&
  typeof row === "object" &&
  row !== null &&
  "_full_width" in row;

const isTaggedRow = (row: TableRow): row is TaggedRow =>
  !Array.isArray(row) &&
  typeof row === "object" &&
  row !== null &&
  "_tag" in row;

const NAMED_FILLS: Record<string, string> = {
  none: "transparent",
  light_gray: "#EDEDED",
  light_blue: "#D9E1F2",
  light_yellow: "#FFF2CC",
  light_green: "#E2EFDA",
  light_orange: "#FCE4D6",
};

interface ResolvedTagStyle {
  background: string;
  fontWeight: "bold" | "normal";
  textAlign: "left" | "center" | "right";
}

function buildTagStyleMap(rows: TableRow[]): Record<string, ResolvedTagStyle> {
  const map: Record<string, ResolvedTagStyle> = {};
  for (const row of rows) {
    if (isTaggedRow(row) && row._style && !(row._tag in map)) {
      const s: TaggedRowStyle = row._style;
      map[row._tag] = {
        background: NAMED_FILLS[s.fill ?? "none"] ?? "transparent",
        fontWeight: s.bold ? "bold" : "normal",
        textAlign: s.align ?? "left",
      };
    }
  }
  return map;
}

const DEFAULT_TAG_STYLE: ResolvedTagStyle = {
  background: "#EDEDED",
  fontWeight: "bold",
  textAlign: "left",
};

const DataPreview = ({
  extractedData,
  htmlContent,
  onExtractedDataChange,
  isRegeneratingExcel = false,
  onDownloadExcel,
  xlsxBlob,
  xlsxName,
}: DataPreviewProps) => {
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

  const handleTitleChange = useCallback(
    (value: string) => {
      onExtractedDataChange?.({ ...extractedData, title: value });
    },
    [extractedData, onExtractedDataChange],
  );

  const handleSectionChange = useCallback(
    (value: string) => {
      onExtractedDataChange?.({ ...extractedData, section_header: value });
    },
    [extractedData, onExtractedDataChange],
  );

  const handleHeaderCellChange = useCallback(
    (rowIndex: number, cellIndex: number, value: string) => {
      const header = (extractedData.header || []).map(
        (row: HeaderRow, ri: number) =>
          ri === rowIndex
            ? row.map((cell, ci) =>
                ci === cellIndex ? { ...cell, value } : cell,
              )
            : row,
      );
      onExtractedDataChange?.({ ...extractedData, header });
    },
    [extractedData, onExtractedDataChange],
  );

  const handleCellChange = useCallback(
    (rowIndex: number, colIndex: number, value: string) => {
      const rows = (extractedData.table?.rows || []).map((row, ri) => {
        if (ri !== rowIndex || isFullWidthRow(row)) return row;
        if (isTaggedRow(row)) {
          const values = [...row.values];
          values[colIndex] = value;
          return { ...row, values };
        }
        const copy = [...row];
        copy[colIndex] = value;
        return copy;
      });
      onExtractedDataChange?.({
        ...extractedData,
        table: { ...extractedData.table, rows },
      });
    },
    [extractedData, onExtractedDataChange],
  );

  const handleFullWidthChange = useCallback(
    (rowIndex: number, value: string) => {
      const rows = (extractedData.table?.rows || []).map((row, ri) =>
        ri === rowIndex ? { _full_width: value } : row,
      );
      onExtractedDataChange?.({
        ...extractedData,
        table: { ...extractedData.table, rows },
      });
    },
    [extractedData, onExtractedDataChange],
  );

  const handleHtmlCellBlur = useCallback(
    (e: React.FocusEvent<HTMLDivElement>) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "TD") {
        const rowStr = target.getAttribute("data-row");
        const colStr = target.getAttribute("data-col");
        if (rowStr && colStr) {
          const r = parseInt(rowStr, 10);
          const c = parseInt(colStr, 10);
          const val = target.textContent || "";

          // Update the data array in extractedData
          const dataList = extractedData.data || [];
          const exists = dataList.some((item) => item.r === r && item.c === c);
          let newDataList;
          if (exists) {
            newDataList = dataList.map((item) =>
              item.r === r && item.c === c ? { ...item, v: val } : item,
            );
          } else {
            newDataList = [...dataList, { r, c, v: val }];
          }

          // Also update the HTML string using DOMParser to keep it in sync
          let newHtml = htmlContent || "";
          if (typeof window !== "undefined" && htmlContent) {
            try {
              const parser = new DOMParser();
              const doc = parser.parseFromString(htmlContent, "text/html");
              const cell = doc.querySelector(
                `td[data-row="${r}"][data-col="${c}"]`,
              );
              if (cell) {
                cell.textContent = val;
                newHtml = doc.body.innerHTML;
              }
            } catch (err) {
              console.error("Failed to parse/update HTML content", err);
            }
          }

          onExtractedDataChange?.({
            ...extractedData,
            data: newDataList,
            html: newHtml,
          });
        }
      }
    },
    [extractedData, htmlContent, onExtractedDataChange],
  );

  const headerRows = extractedData.header || [];
  const columns = extractedData.table?.columns || [];
  const rows = extractedData.table?.rows || [];
  const isEditable = !!onExtractedDataChange;
  const tagStyleMap = buildTagStyleMap(rows);

  return (
    <div className="flex w-full flex-col gap-4">
      <div className="border-mirror-light-blue max-h-[70vh] w-full overflow-auto rounded-2xl border bg-slate-100 p-4 shadow-inner print:max-h-none print:border-none print:bg-white print:p-0 print:shadow-none">
        {htmlContent ? (
          <div
            className="bg-mirror-white relative mx-auto w-full max-w-4xl overflow-auto border border-gray-300 p-4 shadow-md print:border-none print:p-0 print:shadow-none"
            dangerouslySetInnerHTML={{ __html: htmlContent }}
            onBlur={handleHtmlCellBlur}
          />
        ) : (
          <div
            className="bg-mirror-white print-a4-page relative mx-auto flex w-full max-w-4xl flex-col gap-3 border border-gray-300 p-6 text-xs shadow-md select-none print:border-none print:p-0 print:shadow-none"
            style={{ minWidth: "600px" }}
          >
            {(extractedData.title || isEditable) && (
              <span
                contentEditable={isEditable}
                suppressContentEditableWarning={true}
                onBlur={(e) =>
                  handleTitleChange(e.currentTarget.textContent || "")
                }
                className="hover:border-mirror-cyan/40 focus:border-mirror-cyan focus:bg-mirror-cyan/5 cursor-text rounded border border-dashed border-transparent px-1 py-0.5 text-center text-base font-bold outline-none"
              >
                {extractedData.title}
              </span>
            )}

            {(extractedData.section_header || isEditable) && (
              <span
                contentEditable={isEditable}
                suppressContentEditableWarning={true}
                onBlur={(e) =>
                  handleSectionChange(e.currentTarget.textContent || "")
                }
                className="hover:border-mirror-cyan/40 focus:border-mirror-cyan focus:bg-mirror-cyan/5 cursor-text rounded border border-dashed border-transparent px-1 py-0.5 text-center text-sm font-bold outline-none"
              >
                {extractedData.section_header}
              </span>
            )}

            {headerRows.length > 0 && (
              <div className="flex flex-col gap-1 border-b border-gray-200 pb-3">
                {headerRows.map((row: HeaderRow, rowIndex: number) => (
                  <div
                    key={`h-${rowIndex}`}
                    className="flex flex-wrap gap-x-4 gap-y-1"
                  >
                    {row.map((cell, cellIndex) => {
                      if (!cell.label && !cell.value) return null;
                      return (
                        <div
                          key={cellIndex}
                          className="flex items-baseline gap-1"
                        >
                          {cell.label && (
                            <span className="text-mirror-gray shrink-0 font-semibold">
                              {cell.label}
                            </span>
                          )}
                          <span
                            contentEditable={isEditable}
                            suppressContentEditableWarning={true}
                            onBlur={(e) =>
                              handleHeaderCellChange(
                                rowIndex,
                                cellIndex,
                                e.currentTarget.textContent || "",
                              )
                            }
                            className="hover:border-mirror-cyan/40 focus:border-mirror-cyan focus:bg-mirror-cyan/5 min-w-[1em] cursor-text rounded border border-dashed border-transparent px-0.5 outline-none"
                          >
                            {cell.value}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            )}

            {columns.length > 0 && (
              <table className="w-full table-auto border-collapse text-xs">
                <thead>
                  <tr>
                    {columns.map((col, colIndex) => (
                      <th
                        key={colIndex}
                        className="border border-gray-400 bg-slate-50 px-1.5 py-1 text-center font-bold"
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, rowIndex) =>
                    isFullWidthRow(row) ? (
                      <tr key={`r-${rowIndex}`}>
                        <td
                          colSpan={columns.length}
                          contentEditable={isEditable}
                          suppressContentEditableWarning={true}
                          onBlur={(e) =>
                            handleFullWidthChange(
                              rowIndex,
                              e.currentTarget.textContent || "",
                            )
                          }
                          className="hover:border-mirror-cyan/40 focus:border-mirror-cyan focus:bg-mirror-cyan/5 bg-mirror-light-blue/20 cursor-text border border-gray-400 px-1.5 py-1 text-center font-semibold outline-none"
                        >
                          {row._full_width}
                        </td>
                      </tr>
                    ) : isTaggedRow(row) ? (
                      (() => {
                        const ts = tagStyleMap[row._tag] ?? DEFAULT_TAG_STYLE;
                        return (
                          <tr
                            key={`r-${rowIndex}`}
                            style={{ backgroundColor: ts.background }}
                          >
                            {columns.map((_, colIndex) => (
                              <td
                                key={colIndex}
                                contentEditable={isEditable}
                                suppressContentEditableWarning={true}
                                onBlur={(e) =>
                                  handleCellChange(
                                    rowIndex,
                                    colIndex,
                                    e.currentTarget.textContent || "",
                                  )
                                }
                                style={{
                                  fontWeight: ts.fontWeight,
                                  textAlign: ts.textAlign,
                                }}
                                className="hover:border-mirror-cyan/40 focus:border-mirror-cyan focus:bg-mirror-cyan/5 cursor-text border border-gray-400 px-1.5 py-1 outline-none"
                              >
                                {row.values[colIndex] ?? ""}
                              </td>
                            ))}
                          </tr>
                        );
                      })()
                    ) : (
                      <tr key={`r-${rowIndex}`}>
                        {columns.map((_, colIndex) => (
                          <td
                            key={colIndex}
                            contentEditable={isEditable}
                            suppressContentEditableWarning={true}
                            onBlur={(e) =>
                              handleCellChange(
                                rowIndex,
                                colIndex,
                                e.currentTarget.textContent || "",
                              )
                            }
                            className="hover:border-mirror-cyan/40 focus:border-mirror-cyan focus:bg-mirror-cyan/5 cursor-text border border-gray-400 px-1.5 py-1 outline-none"
                          >
                            {row[colIndex] ?? ""}
                          </td>
                        ))}
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            )}
          </div>
        )}
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

export default DataPreview;
