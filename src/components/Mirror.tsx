"use client";

import { useState, useEffect, useCallback } from "react";
import { FaSpinner, FaExclamationCircle } from "react-icons/fa";
import { ExtractedData } from "../types/template";
import DocumentUploader from "./DocumentUploader";
import DocumentPreview from "./DocumentPreview";
import DataPreview from "./DataPreview";

interface MirrorProps {
  uploadedFiles: File[];
  onClear: () => void;
  onFilesSelect: (files: File[]) => void;
}

interface PageResult {
  extractedData: ExtractedData;
  htmlContent?: string;
  filename?: string;
}

type ConvertStatus = "idle" | "loading" | "done" | "error";

const LOADING_STEPS = [
  "Uploading manufacturing document to secure server...",
  "Correcting document rotation & perspective (deskewing)...",
  "Connecting to Document Analysis API...",
  "Analyzing report layout and reading text characters...",
  "Structuring extracted fields into rows and columns...",
  "Building custom sheets and styling Excel borders...",
  "Finalizing Excel spreadsheet binary generation...",
];

const compressImage = async (file: File): Promise<File> => {
  if (!file.type.startsWith("image/")) {
    return file;
  }
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        const MAX_WIDTH = 2000;
        const MAX_HEIGHT = 2000;
        let width = img.width;
        let height = img.height;

        if (width > height) {
          if (width > MAX_WIDTH) {
            height = Math.round((height * MAX_WIDTH) / width);
            width = MAX_WIDTH;
          }
        } else {
          if (height > MAX_HEIGHT) {
            width = Math.round((width * MAX_HEIGHT) / height);
            height = MAX_HEIGHT;
          }
        }

        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          resolve(file);
          return;
        }

        ctx.drawImage(img, 0, 0, width, height);
        canvas.toBlob(
          (blob) => {
            if (blob) {
              const compressed = new File([blob], file.name, {
                type: "image/jpeg",
                lastModified: Date.now(),
              });
              resolve(compressed);
            } else {
              resolve(file);
            }
          },
          "image/jpeg",
          0.85,
        );
      };
      img.onerror = () => resolve(file);
      img.src = e.target?.result as string;
    };
    reader.onerror = () => resolve(file);
    reader.readAsDataURL(file);
  });
};

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
            htmlContent: newData.html || next[activePageIndex].htmlContent,
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
      // Compress image files client-side before sending to respect Vercel's body size limits
      const processedFiles = await Promise.all(
        uploadedFiles.map(async (file) => {
          try {
            return await compressImage(file);
          } catch (e) {
            console.error("Compression failed for", file.name, e);
            return file;
          }
        }),
      );

      const form = new FormData();
      processedFiles.forEach((file) => {
        form.append("file", file);
      });
      const res = await fetch("/api/convert", { method: "POST", body: form });

      if (!res.ok) {
        let errMessage = "Conversion failed";
        try {
          const contentType = res.headers.get("content-type");
          if (contentType && contentType.includes("application/json")) {
            const errorJson = await res.json();
            errMessage = errorJson.error || errMessage;
          } else {
            const text = await res.text();
            if (text.includes("<html") || text.includes("<!DOCTYPE")) {
              if (res.status === 413) {
                errMessage =
                  "Upload payload too large (Vercel has a 4.5MB limit). Try uploading fewer documents.";
              } else if (res.status === 504) {
                errMessage =
                  "Vercel execution timed out. Try uploading fewer documents.";
              } else {
                errMessage = `Server error ${res.status}: ${res.statusText}`;
              }
            } else {
              errMessage = text || `HTTP error ${res.status}`;
            }
          }
        } catch {
          errMessage = `HTTP error ${res.status}`;
        }
        throw new Error(errMessage);
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

        if (extracted.table?.rows) {
          extracted.table = {
            ...extracted.table,
            rows: extracted.table.rows.filter(
              (r) =>
                !(
                  !Array.isArray(r) &&
                  "_full_width" in r &&
                  typeof r._full_width === "string" &&
                  r._full_width.replace(/\s+/g, "") === "備考"
                ),
            ),
          };
        }

        return {
          ...page,
          extractedData: extracted,
          htmlContent: extracted.html || page.htmlContent,
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

    return () => {
      document.title = "Mirror Report AI";
    };
  }, [uploadedFiles]);

  useEffect(() => {
    if (status === "done" && pages[activePageIndex]) {
      const activePage = pages[activePageIndex];
      const name =
        activePage.filename ||
        activePage.extractedData.title ||
        `Page ${activePageIndex + 1}`;
      const lastDot = name.lastIndexOf(".");
      const baseName = lastDot !== -1 ? name.substring(0, lastDot) : name;
      document.title = baseName;
    } else if (uploadedFiles.length > 0) {
      const name = uploadedFiles[0].name;
      const lastDot = name.lastIndexOf(".");
      const baseName = lastDot !== -1 ? name.substring(0, lastDot) : name;
      document.title = baseName;
    } else {
      document.title = "Mirror Report AI";
    }
  }, [uploadedFiles, status, pages, activePageIndex]);

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

          {status === "done" && pages.length > 1 && (
            <div className="border-mirror-light-blue mb-4 flex flex-wrap gap-2 border-b pb-3 print:hidden">
              {pages.map((p, index) => {
                const pageTitle =
                  p.filename || p.extractedData.title || `Page ${index + 1}`;
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
                <div className="bg-mirror-white border-mirror-light-gray relative mx-auto flex aspect-210/297 w-full max-w-4xl animate-pulse flex-col border p-6 shadow-md">
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
              <DataPreview
                extractedData={pages[activePageIndex].extractedData}
                htmlContent={pages[activePageIndex].htmlContent}
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
