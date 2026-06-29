"use client";

import { useState, useEffect, useCallback } from "react";
import { FaSpinner, FaExclamationCircle } from "react-icons/fa";
import { ExtractedDataPage, MatchedTemplate } from "../types/template";
import DocumentUploader from "./DocumentUploader";
import DocumentPreview from "./DocumentPreview";
import TemplateViewer from "./TemplateViewer";

interface MirrorProps {
  uploadedFiles: File[];
  onClear: () => void;
  onFilesSelect: (files: File[]) => void;
}

type ConvertStatus = "idle" | "loading" | "done" | "error";

interface PageResult {
  extractedData: ExtractedDataPage;
  template: MatchedTemplate;
}

const Mirror = ({ uploadedFiles, onClear, onFilesSelect }: MirrorProps) => {
  const [status, setStatus] = useState<ConvertStatus>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [xlsxBlob, setXlsxBlob] = useState<Blob | null>(null);
  const [xlsxName, setXlsxName] = useState("");
  const [pages, setPages] = useState<PageResult[]>([]);
  const [activePageIndex, setActivePageIndex] = useState(0);

  // Editing state trackers
  const [isDirty, setIsDirty] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);

  const handleGenerate = useCallback(async () => {
    if (uploadedFiles.length === 0) return;
    setStatus("loading");
    setErrorMsg(null);
    setXlsxBlob(null);
    setPages([]);
    setActivePageIndex(0);
    setIsDirty(false);

    try {
      const form = new FormData();
      for (const file of uploadedFiles) {
        form.append("file", file);
      }
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

      setXlsxBlob(blob);
      setXlsxName(result.filename);
      setPages(result.pages || []);
      setStatus("done");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Unknown error");
      setStatus("error");
    }
  }, [uploadedFiles]);

  useEffect(() => {
    setStatus("idle");
    setXlsxBlob(null);
    setPages([]);
    setActivePageIndex(0);
    setErrorMsg(null);
    setIsDirty(false);
  }, [uploadedFiles]);

  const handlePageDataChange = useCallback(
    (index: number, newPageData: ExtractedDataPage) => {
      setPages((prev) => {
        const next = [...prev];
        next[index] = {
          ...next[index],
          extractedData: newPageData,
        };
        return next;
      });
      setIsDirty(true);
    },
    [],
  );

  const handleDownloadExcel = useCallback(async () => {
    // If the data hasn't been edited, download the cached XLSX file
    if (!isDirty && xlsxBlob) {
      const url = URL.createObjectURL(xlsxBlob);
      const a = document.createElement("a");
      a.href = url;
      a.download = xlsxName;

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
      return;
    }

    if (pages.length === 0) return;

    // If edited, regenerate the Excel sheet with the new values
    setIsRegenerating(true);
    try {
      const res = await fetch("/api/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          extractedData: {
            pages: pages.map((p) => p.extractedData),
          },
          filename: xlsxName,
        }),
      });

      if (!res.ok) {
        throw new Error("Failed to regenerate Excel spreadsheet");
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

      setXlsxBlob(blob);
      setIsDirty(false);

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = xlsxName;

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
    } catch (err) {
      console.error("Regeneration failed:", err);
      alert("Failed to export edited Excel file.");
    } finally {
      setIsRegenerating(false);
    }
  }, [isDirty, xlsxBlob, xlsxName, pages]);

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
            <p className="text-mirror-gray inline text-sm font-semibold">
              Scanning Status:{" "}
            </p>
            <p className="text-mirror-dark-blue inline text-sm font-normal">
              {uploadedFiles.length > 0
                ? "Files Ready for Processing"
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
            <p className="text-mirror-gray inline text-sm font-semibold">
              Generating Status:{" "}
            </p>
            <p className="text-mirror-dark-blue inline text-sm font-normal">
              {status === "idle" && "Waiting for generation..."}
              {status === "loading" && "Processing document..."}
              {status === "done" && "Template ready"}
              {status === "error" && "Generation failed"}
            </p>
          </div>

          {/* Tab page selector */}
          {status === "done" && pages.length > 1 && (
            <div className="border-mirror-light-blue mb-4 flex flex-wrap gap-2 border-b pb-2 print:hidden">
              {pages.map((p, index) => (
                <button
                  key={index}
                  onClick={() => setActivePageIndex(index)}
                  className={`cursor-pointer rounded-lg px-3 py-1.5 text-xs font-bold transition-all duration-200 ${
                    activePageIndex === index
                      ? "bg-mirror-cyan text-mirror-white shadow-sm"
                      : "bg-mirror-light-blue text-mirror-dark-blue hover:bg-mirror-cyan/20"
                  }`}
                >
                  {p.extractedData.title || `Page ${index + 1}`}
                </button>
              ))}
            </div>
          )}

          {status !== "done" ? (
            <div className="bg-mirror-light-blue border-mirror-light-blue flex min-h-[55vh] flex-col items-center justify-center gap-6 rounded-2xl border p-8">
              {status === "idle" && (
                <p className="text-mirror-gray text-sm font-medium">
                  No template generated yet
                </p>
              )}

              {status === "loading" && (
                <div className="flex flex-col items-center gap-4">
                  <FaSpinner className="text-mirror-cyan h-12 w-12 animate-spin" />
                  <p className="text-mirror-dark-blue text-sm font-semibold">
                    Running OCR pipeline...
                  </p>
                  <p className="text-mirror-gray text-xs">
                    This may take up to a minute
                  </p>
                </div>
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
                onExtractedDataChange={(newData) =>
                  handlePageDataChange(activePageIndex, newData)
                }
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
