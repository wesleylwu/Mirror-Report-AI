"use client";

import { useState, useEffect, useCallback } from "react";
import { FaSpinner, FaExclamationCircle } from "react-icons/fa";
import { ExtractedData, MatchedTemplate } from "../types/template";
import DocumentUploader from "./DocumentUploader";
import DocumentPreview from "./DocumentPreview";
import TemplateViewer from "./TemplateViewer";

interface MirrorProps {
  uploadedFile: File | null;
  onClear: () => void;
  onFileSelect: (file: File) => void;
}

type ConvertStatus = "idle" | "loading" | "done" | "error";

const Mirror = ({ uploadedFile, onClear, onFileSelect }: MirrorProps) => {
  const [status, setStatus] = useState<ConvertStatus>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [xlsxBlob, setXlsxBlob] = useState<Blob | null>(null);
  const [xlsxName, setXlsxName] = useState("");
  const [extractedData, setExtractedData] = useState<ExtractedData | null>(
    null,
  );
  const [matchedTemplate, setMatchedTemplate] =
    useState<MatchedTemplate | null>(null);

  // Editing state trackers
  const [isDirty, setIsDirty] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);

  const handleGenerate = useCallback(async () => {
    if (!uploadedFile) return;
    setStatus("loading");
    setErrorMsg(null);
    setXlsxBlob(null);
    setExtractedData(null);
    setMatchedTemplate(null);
    setIsDirty(false);

    try {
      const form = new FormData();
      form.append("file", uploadedFile);
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
      setExtractedData(result.extractedData);
      setMatchedTemplate(result.template);
      setStatus("done");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Unknown error");
      setStatus("error");
    }
  }, [uploadedFile]);

  useEffect(() => {
    setStatus("idle");
    setXlsxBlob(null);
    setExtractedData(null);
    setMatchedTemplate(null);
    setErrorMsg(null);
    setIsDirty(false);
  }, [uploadedFile]);

  const handleExtractedDataChange = useCallback((newData: ExtractedData) => {
    setExtractedData(newData);
    setIsDirty(true);
  }, []);

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

    if (!extractedData) return;

    // If edited, regenerate the Excel sheet with the new values
    setIsRegenerating(true);
    try {
      const res = await fetch("/api/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ extractedData, filename: xlsxName }),
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
  }, [isDirty, xlsxBlob, xlsxName, extractedData]);

  return (
    <div className="mx-auto w-full max-w-[90vw] grow px-6 py-8 md:px-12 print:m-0 print:w-full print:max-w-none print:p-0">
      <div className="relative grid grid-cols-1 gap-8 md:grid-cols-2 md:gap-16 print:m-0 print:block print:w-full print:p-0">
        <div className="border-mirror-light-blue flex flex-col pr-8 md:border-r md:pr-16 print:hidden">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-mirror-dark-blue text-xl font-bold tracking-wide uppercase md:text-2xl">
              document source
            </p>
            {uploadedFile && (
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
              {uploadedFile
                ? "File Ready for Processing"
                : "Waiting for file upload..."}
            </p>
          </div>

          {!uploadedFile ? (
            <DocumentUploader onFileSelect={onFileSelect} />
          ) : (
            <div className="flex flex-col gap-4">
              <DocumentPreview uploadedFile={uploadedFile} onClear={onClear} />
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
            matchedTemplate &&
            extractedData && (
              <TemplateViewer
                matchedTemplate={matchedTemplate}
                extractedData={extractedData}
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
