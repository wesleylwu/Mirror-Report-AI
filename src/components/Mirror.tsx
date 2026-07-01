"use client";

import { useState, useEffect, useCallback } from "react";
import { FaSpinner, FaExclamationCircle } from "react-icons/fa";
import { ExtractedData, MatchedTemplate } from "../types/template";
import DocumentUploader from "./DocumentUploader";
import DocumentPreview from "./DocumentPreview";
import TemplateViewer from "./TemplateViewer";

interface MirrorProps {
  uploadedFiles: File[];
  onClear: () => void;
  onFilesSelect: (files: File[]) => void;
}

interface PageResult {
  extractedData: ExtractedData;
  template: MatchedTemplate;
}

type ConvertStatus = "idle" | "loading" | "done" | "error";

const LOADING_STEPS = [
  "Uploading manufacturing document to secure server...",
  "Correcting document rotation & perspective (deskewing)...",
  "Connecting to Anthropic Claude 3.5 Haiku Vision API...",
  "Analyzing report layout and reading text characters...",
  "Fuzzy-matching OCR results against layout schemas...",
  "Building custom sheets and styling Excel borders...",
  "Finalizing Excel spreadsheet binary generation...",
];

const Mirror = ({ uploadedFiles, onClear, onFilesSelect }: MirrorProps) => {
  const [status, setStatus] = useState<ConvertStatus>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [xlsxBlob, setXlsxBlob] = useState<Blob | null>(null);
  const [xlsxName, setXlsxName] = useState("");

  const [pages, setPages] = useState<PageResult[]>([]);
  const [activePageIndex, setActivePageIndex] = useState(0);

  const [isRegenerating, setIsRegenerating] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);

  useEffect(() => {
    if (status !== "loading") {
      setLoadingStep(0);
      return;
    }
    const interval = setInterval(() => {
      setLoadingStep((prev) =>
        prev < LOADING_STEPS.length - 1 ? prev + 1 : prev,
      );
    }, 3000);
    return () => clearInterval(interval);
  }, [status]);

  const handleExtractedDataChange = useCallback(
    (newData: ExtractedData) => {
      setPages((prev) => {
        const next = [...prev];
        if (next[activePageIndex]) {
          next[activePageIndex] = {
            ...next[activePageIndex],
            extractedData: newData,
          };
        }
        return next;
      });
      setIsDirty(true);
    },
    [activePageIndex],
  );

  const handleDownloadExcel = useCallback(async () => {
    if (pages.length === 0 || isRegenerating) return;

    // Optimize: if document has not been edited, download cached blob immediately
    if (!isDirty && xlsxBlob) {
      const url = URL.createObjectURL(xlsxBlob);
      const a = document.createElement("a");
      a.href = url;
      a.download = xlsxName || "export.xlsx";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      return;
    }

    setIsRegenerating(true);
    try {
      const res = await fetch("/api/convert", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          extractedData: {
            pages: pages.map((p) => p.extractedData),
          },
        }),
      });
      if (!res.ok) throw new Error("Excel regeneration failed");
      const result = await res.json();
      const binaryString = window.atob(result.xlsx);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const blob = new Blob([bytes], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
      setXlsxBlob(blob);
      setIsDirty(false);

      // Trigger standard browser download
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = xlsxName || "export.xlsx";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (err) {
      console.error("Excel download error:", err);
    } finally {
      setIsRegenerating(false);
    }
  }, [pages, isRegenerating, xlsxName, isDirty, xlsxBlob]);

  const handleGenerate = useCallback(async () => {
    if (uploadedFiles.length === 0) return;
    setStatus("loading");
    setErrorMsg(null);
    setXlsxBlob(null);
    setIsDirty(false);
    setPages([]);
    setActivePageIndex(0);

    try {
      const form = new FormData();
      uploadedFiles.forEach((file) => {
        form.append("file", file);
      });
      const res = await fetch("/api/convert", { method: "POST", body: form });

      if (!res.ok) {
        const { error } = await res.json();
        throw new Error(error || "Conversion failed");
      }

      const result = await res.json();
      const binaryString = window.atob(result.xlsx);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const blob = new Blob([bytes], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });

      const rawPages = result.pages || [];
      const cleanedPages = rawPages.map((page: PageResult) => {
        const extracted = { ...page.extractedData };

        // 1. Filter out duplicate full-width 備考 row from OCR data
        if (extracted.table?.rows) {
          extracted.table.rows = extracted.table.rows.filter(
            (r: Record<string, unknown>) =>
              !(
                "_full_width" in r &&
                typeof r._full_width === "string" &&
                r._full_width.replace(/\s+/g, "") === "備考"
              ),
          );
        }

        // 1.5 Clean up customer codes for 基準客先ABC template
        const title = (extracted.title || "").trim();
        const normTitle = title.replace(/[Ａ-Ｚａ-ｚ０-９]/g, (s) =>
          String.fromCharCode(s.charCodeAt(0) - 0xfee0),
        );
        if (normTitle.startsWith("基準客先ABC") && extracted.table?.rows) {
          const mapping: Record<string, string> = {
            "＝39": "ﾘ39",
            "＝42": "ﾆ42",
            Ａ21: "ｸ21",
            Ａ29: "ｷ29",
            Ａ31: "ｶ31",
            Ｂ50: "ﾋ50",
            Ｅ03: "ｴ03",
            Ｅ10: "ｱ10",
            Ｅ15: "ﾓ15",
            Ｅ30: "ｺ30",
            Ｅ60: "ｴ60",
            Ｅ70: "ｴ70",
            Ｆ20: "ｷ20",
            Ｇ48: "ｺ48",
            Ｊ03: "ｼ03",
            Ｊ11: "ｼ11",
            Ｊ12: "ｼ12",
            Ｊ13: "ｼ13",
            Ｊ17: "ｿ17",
            Ｊ20: "ｼ20",
            Ｊ22: "ｼ22",
            Ｊ50: "ｼ50",
            Ｊ58: "ｼ58",
            Ｊ72: "ｼ72",
            Ｊ90: "ｾ90",
            Ｊ92: "ｼ92",
            Ｊ99: "ｼ99",
            Ｋ70: "ｷ70",
            Ｋ91: "ｷ91",
            Ｋ92: "ｷ92",
            Ｋ93: "ｷ93",
            Ｔ01: "701",
            Ｔ13: "713",
            Ｔ23: "723",
            Ｔ30: "ﾅ30",
            Ｔ35: "735",
            Ｔ40: "740",
            Ｔ78: "ﾄ78",
            Ｔ80: "ﾗ80",
            Ｙ01: "ｸ01",
            Ｙ04: "ｸ04",
            Ｙ50: "ﾀ50",
            Ｚ15: "ｽ15",
            Ｄ60: "ﾄ60",
            Ｄ70: "ﾄ70",
            Ｙ60: "ｹ60",
          };
          extracted.table.rows = extracted.table.rows.map((r: unknown) => {
            if (Array.isArray(r) && r.length > 1) {
              const code = r[1];
              if (typeof code === "string" && mapping[code]) {
                const newRow = [...r];
                newRow[1] = mapping[code];
                return newRow;
              }
            } else if (r && typeof r === "object") {
              const obj = r as Record<string, unknown>;
              const code = (obj["基準客先名"] || obj[1]) as string | undefined;
              if (typeof code === "string" && mapping[code]) {
                return { ...obj, 基準客先名: mapping[code] };
              }
            }
            return r;
          }) as Record<string, string>[];
        }

        // 2. Extract main and sub from 手配No.
        if (extracted.header) {
          if (extracted.header["店番"] === "S50") {
            extracted.header["店番"] = "シ50";
          }
          const rawNo = extracted.header["手配No."] || "";
          if (typeof rawNo === "string" && rawNo.includes("　")) {
            const parts = rawNo.split("　");
            extracted.header["手配No."] = parts[0];
            extracted.header["手配No._sub"] = parts[1] || "1";
          } else if (typeof rawNo === "string" && rawNo.includes(" ")) {
            const parts = rawNo.split(" ");
            extracted.header["手配No."] = parts[0];
            extracted.header["手配No._sub"] = parts[1] || "1";
          } else {
            extracted.header["手配No._sub"] = "1";
          }
        }

        return {
          ...page,
          extractedData: extracted,
        };
      });

      setXlsxBlob(blob);
      setXlsxName(result.filename);
      setPages(cleanedPages);
      setStatus("done");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Unknown error");
      setStatus("error");
    }
  }, [uploadedFiles]);

  useEffect(() => {
    setStatus("idle");
    setXlsxBlob(null);
    setIsDirty(false);
    setPages([]);
    setActivePageIndex(0);
    setErrorMsg(null);
  }, [uploadedFiles]);

  return (
    <div className="mx-auto w-full max-w-[90vw] grow px-6 py-8 md:px-12 print:m-0 print:w-full print:max-w-none print:p-0">
      <div className="relative grid grid-cols-1 gap-8 md:grid-cols-2 md:gap-16 print:m-0 print:block print:w-full print:p-0">
        <div className="border-mirror-light-blue flex flex-col pr-8 md:border-r md:pr-16 print:hidden">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-mirror-dark-blue text-xl font-bold tracking-wide uppercase md:text-2xl">
              document source
            </p>
            {uploadedFiles.length > 0 && (
              <p className="bg-mirror-green/20 text-mirror-dark-blue rounded-full px-3 py-1 text-xs font-semibold">
                Loaded
              </p>
            )}
          </div>
          <div className="mb-4">
            <p className="text-mirror-gray text-sm font-semibold">
              Scanning Status:{" "}
            </p>
            <p className="text-mirror-dark-blue text-sm font-normal">
              {uploadedFiles.length > 0
                ? `${uploadedFiles.length} File(s) Ready for Processing`
                : "Waiting for file upload..."}
            </p>
          </div>

          {uploadedFiles.length === 0 ? (
            <DocumentUploader onFilesSelect={onFilesSelect} />
          ) : (
            <div className="flex flex-col gap-4">
              <DocumentPreview
                uploadedFiles={uploadedFiles}
                onClear={onClear}
              />
              {(status === "idle" || status === "error") && (
                <button
                  onClick={handleGenerate}
                  className="bg-mirror-cyan hover:bg-mirror-dark-blue text-mirror-white inline-flex cursor-pointer items-center justify-center self-center rounded-lg px-5 py-2.5 text-sm font-bold shadow-sm transition-all duration-200 focus:outline-none active:scale-95"
                >
                  Generate Template
                </button>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-col md:pl-4 print:w-full print:p-0">
          <div className="mb-2 flex items-center justify-between print:hidden">
            <p className="text-mirror-dark-blue text-xl font-bold tracking-wide uppercase md:text-2xl">
              generated template
            </p>
          </div>
          <div className="mb-4 print:hidden">
            <p className="text-mirror-gray text-sm font-semibold">
              Generating Status:{" "}
            </p>
            <p className="text-mirror-dark-blue text-sm font-normal">
              {status === "idle" && "Waiting for generation..."}
              {status === "loading" && "Processing document..."}
              {status === "done" && `Template ready (${pages.length} pages)`}
              {status === "error" && "Generation failed"}
            </p>
          </div>

          {/* Page Switching Tabs */}
          {status === "done" && pages.length > 1 && (
            <div className="border-mirror-light-blue mb-4 flex flex-wrap gap-2 border-b pb-3 print:hidden">
              {pages.map((p, index) => {
                const pageTitle = p.extractedData.title || `Page ${index + 1}`;
                return (
                  <button
                    key={index}
                    onClick={() => setActivePageIndex(index)}
                    className={`cursor-pointer rounded-xl px-4 py-2 text-xs font-bold transition-all duration-200 ${
                      activePageIndex === index
                        ? "bg-mirror-cyan text-mirror-white shadow-mirror-cyan/15 shadow-md"
                        : "bg-mirror-light-blue/50 text-mirror-dark-blue hover:bg-mirror-cyan/15"
                    }`}
                  >
                    {pageTitle}
                  </button>
                );
              })}
            </div>
          )}

          {status === "loading" ? (
            <div className="flex w-full flex-col gap-6">
              <div className="bg-mirror-light-blue border-mirror-light-blue flex flex-col gap-3 rounded-2xl border p-6">
                <div className="flex items-center justify-between">
                  <span className="text-mirror-dark-blue flex items-center gap-2 text-sm font-bold">
                    <FaSpinner className="text-mirror-cyan h-4 w-4 animate-spin" />
                    {LOADING_STEPS[loadingStep]}
                  </span>
                  <span className="text-mirror-gray text-xs font-semibold">
                    Step {loadingStep + 1} of {LOADING_STEPS.length}
                  </span>
                </div>
                <div className="bg-mirror-light-gray h-2 w-full overflow-hidden rounded-full">
                  <div
                    className="bg-mirror-cyan h-full transition-all duration-500 ease-out"
                    style={{
                      width: `${((loadingStep + 1) / LOADING_STEPS.length) * 100}%`,
                    }}
                  />
                </div>
              </div>

              <div className="border-mirror-light-blue bg-mirror-light-blue max-h-[70vh] w-full overflow-hidden rounded-2xl border p-4 shadow-inner">
                <div className="bg-mirror-white border-mirror-light-gray relative mx-auto flex aspect-[210/297] w-full max-w-4xl animate-pulse flex-col border p-6 shadow-md">
                  <div className="bg-mirror-light-gray/60 mx-auto mb-6 h-6 w-48 rounded" />

                  <div className="mb-6 grid grid-cols-4 gap-4">
                    <div className="bg-mirror-light-gray/60 h-4 rounded" />
                    <div className="bg-mirror-light-gray/40 h-4 w-3/4 rounded" />
                    <div className="bg-mirror-light-gray/40 h-4 w-5/6 rounded" />
                    <div className="bg-mirror-light-gray/60 h-4 rounded" />
                    <div className="bg-mirror-light-gray/60 h-4 w-2/3 rounded" />
                    <div className="bg-mirror-light-gray/60 h-4 rounded" />
                    <div className="bg-mirror-light-gray/40 h-4 w-1/2 rounded" />
                    <div className="bg-mirror-light-gray/40 h-4 w-3/4 rounded" />
                  </div>

                  <div className="border-mirror-light-gray mb-3 grid grid-cols-6 gap-2 border-y py-3">
                    <div className="bg-mirror-gray/30 h-5 rounded" />
                    <div className="bg-mirror-gray/30 h-5 rounded" />
                    <div className="bg-mirror-gray/30 h-5 rounded" />
                    <div className="bg-mirror-gray/30 h-5 rounded" />
                    <div className="bg-mirror-gray/30 h-5 rounded" />
                    <div className="bg-mirror-gray/30 h-5 rounded" />
                  </div>

                  <div className="flex flex-col gap-3">
                    {Array.from({ length: 8 }).map((_, i) => (
                      <div
                        key={i}
                        className="border-mirror-light-blue grid grid-cols-6 gap-2 border-b pb-2"
                      >
                        <div className="bg-mirror-light-gray/40 h-4 w-2/3 rounded" />
                        <div className="bg-mirror-light-gray/40 h-4 w-5/6 rounded" />
                        <div className="bg-mirror-light-gray/40 h-4 w-1/2 rounded" />
                        <div className="bg-mirror-light-gray/40 h-4 w-3/4 rounded" />
                        <div className="bg-mirror-light-gray/40 h-4 rounded" />
                        <div className="bg-mirror-light-gray/40 h-4 w-2/3 rounded" />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ) : status !== "done" ? (
            <div className="bg-mirror-light-blue border-mirror-light-blue flex min-h-[55vh] flex-col items-center justify-center gap-6 rounded-2xl border p-8">
              {status === "idle" && (
                <p className="text-mirror-gray text-sm font-medium">
                  No template generated yet
                </p>
              )}

              {status === "error" && (
                <div className="flex flex-col items-center gap-4">
                  <FaExclamationCircle className="h-12 w-12 text-red-500" />
                  <p className="text-mirror-dark-blue text-sm font-semibold">
                    Generation failed
                  </p>
                  {errorMsg && (
                    <p className="text-mirror-gray max-w-[25vw] text-center text-xs">
                      {errorMsg}
                    </p>
                  )}
                </div>
              )}
            </div>
          ) : (
            pages[activePageIndex] && (
              <TemplateViewer
                matchedTemplate={pages[activePageIndex].template}
                extractedData={pages[activePageIndex].extractedData}
                onExtractedDataChange={handleExtractedDataChange}
                isRegeneratingExcel={isRegenerating}
                onDownloadExcel={handleDownloadExcel}
              />
            )
          )}
        </div>
      </div>
    </div>
  );
};

export default Mirror;
