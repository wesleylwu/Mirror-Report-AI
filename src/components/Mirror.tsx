"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import Image from "next/image";
import {
  FaPaperclip, FaCamera, FaTimes, FaFileAlt,
  FaFileExcel, FaSpinner, FaCheckCircle, FaExclamationCircle,
} from "react-icons/fa";

interface MirrorProps {
  uploadedFile: File | null;
  onClear: () => void;
  onFileSelect: (file: File) => void;
  onGenerateReady: (fn: () => void) => void;
  onDownloadReady: (fn: () => void) => void;
  onDownloadCleared: () => void;
}

type ConvertStatus = "idle" | "loading" | "done" | "error";

const Mirror = ({
  uploadedFile, onClear, onFileSelect,
  onGenerateReady, onDownloadReady, onDownloadCleared,
}: MirrorProps) => {
  const imageUrl = useMemo<string | null>(() => {
    if (uploadedFile?.type.startsWith("image/")) return URL.createObjectURL(uploadedFile);
    return null;
  }, [uploadedFile]);

  const [isDragging, setIsDragging] = useState(false);
  const [status, setStatus] = useState<ConvertStatus>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [xlsxBlob, setXlsxBlob] = useState<Blob | null>(null);
  const [xlsxName, setXlsxName] = useState("");
  const localInputRef = useRef<HTMLInputElement>(null);

  // Reset when file changes
  useEffect(() => {
    setStatus("idle");
    setXlsxBlob(null);
    setErrorMsg(null);
    onDownloadCleared();
    if (uploadedFile) onGenerateReady(handleGenerate);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uploadedFile]);

  useEffect(() => {
    return () => { if (imageUrl) URL.revokeObjectURL(imageUrl); };
  }, [imageUrl]);

  const handleGenerate = async () => {
    if (!uploadedFile) return;
    setStatus("loading");
    setErrorMsg(null);
    setXlsxBlob(null);
    onDownloadCleared();

    try {
      const form = new FormData();
      form.append("file", uploadedFile);
      const res = await fetch("/api/convert", { method: "POST", body: form });

      if (!res.ok) {
        const { error } = await res.json();
        throw new Error(error || "Conversion failed");
      }

      const blob = await res.blob();
      const name =
        res.headers.get("Content-Disposition")?.match(/filename="(.+?)"/)?.[1] ??
        `${uploadedFile.name.replace(/\.[^.]+$/, "")}.xlsx`;

      setXlsxBlob(blob);
      setXlsxName(name);
      setStatus("done");
      onDownloadReady(() => triggerDownload(blob, name));
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Unknown error");
      setStatus("error");
    }
  };

  const triggerDownload = (blob: Blob, name: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  };

  const validateAndSelect = (file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase();
    const allowedTypes = ["image/jpeg", "image/jpg", "image/png", "image/webp", "application/pdf"];
    const allowedExts = ["jpg", "jpeg", "png", "webp", "pdf"];
    if (allowedTypes.includes(file.type) || (ext && allowedExts.includes(ext))) {
      onFileSelect(file);
    } else {
      alert("Only JPEG, PNG, WebP, or PDF files are allowed.");
    }
  };

  const isImage = uploadedFile?.type.startsWith("image/");

  const formatBytes = (bytes: number, decimals = 2) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(decimals)) + " " + sizes[i];
  };

  return (
    <div className="mx-auto w-full max-w-[90vw] grow" style={{ padding: "4vh 3vw" }}>
      <div className="relative grid grid-cols-1 gap-8 md:grid-cols-2" style={{ gap: "4vw" }}>

        {/* Left — document source */}
        <div className="flex flex-col md:border-r" style={{ paddingRight: "4vw", borderColor: "var(--color-mirror-light-blue)" }}>
          <div className="flex items-center justify-between" style={{ marginBottom: "1vh" }}>
            <p className="text-mirror-dark-blue font-bold tracking-wide uppercase" style={{ fontSize: "2.4vh" }}>document source</p>
            {uploadedFile && (
              <p className="bg-mirror-green/20 text-mirror-dark-blue rounded-full font-semibold" style={{ fontSize: "1.4vh", padding: "0.4vh 1vw" }}>Loaded</p>
            )}
          </div>
          <div style={{ marginBottom: "2vh" }}>
            <p className="text-mirror-gray text-sm font-semibold">Scanning Status: </p>
            <p className="text-mirror-dark-blue text-sm font-normal">
              {uploadedFile ? "File Ready for Processing" : "Waiting for file upload..."}
            </p>
          </div>

          {!uploadedFile ? (
            <div className="flex flex-col">
              <div
                onClick={() => localInputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(e) => { e.preventDefault(); setIsDragging(false); const f = e.dataTransfer.files?.[0]; if (f) validateAndSelect(f); }}
                className="bg-mirror-light-blue flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed transition-all duration-300"
                style={{
                  minHeight: "55vh",
                  borderColor: isDragging ? "var(--color-mirror-cyan)" : "var(--color-mirror-gray)",
                  opacity: isDragging ? 0.8 : 1,
                  transform: isDragging ? "scale(0.99)" : "none",
                }}
              >
                <div className="flex flex-col items-center text-center" style={{ gap: "2vh", paddingLeft: "3vw", paddingRight: "3vw" }}>
                  <div className="bg-mirror-cyan/10 text-mirror-cyan flex items-center justify-center rounded-full shadow-sm transition-transform duration-300 hover:scale-110" style={{ width: "8vh", height: "8vh" }}>
                    <FaPaperclip className="rotate-45" style={{ width: "3.5vh", height: "3.5vh" }} />
                  </div>
                  <div className="flex flex-col" style={{ gap: "0.8vh" }}>
                    <p className="text-mirror-dark-blue text-base font-bold">Drag & drop your document here</p>
                    <p className="text-mirror-gray max-w-[20vw] text-xs leading-relaxed">Supports JPEG, PNG, WebP, or PDF. Click to browse.</p>
                  </div>
                  <p className="bg-mirror-cyan hover:bg-mirror-dark-blue text-mirror-white inline-flex cursor-pointer items-center rounded-lg text-xs font-bold shadow-sm transition-colors duration-200" style={{ padding: "1vh 2vw" }}>
                    Select File
                  </p>
                </div>
              </div>
              <input type="file" ref={localInputRef} onChange={(e) => { const f = e.target.files?.[0]; if (f) validateAndSelect(f); }} accept=".jpg,.jpeg,.png,.webp,.pdf,image/jpeg,image/png,image/webp,application/pdf" className="hidden" />
            </div>
          ) : (
            <div className="flex flex-col" style={{ gap: "2vh" }}>
              <div className="bg-mirror-light-blue flex items-center justify-between rounded-xl border shadow-sm" style={{ padding: "2vh 2vw", borderColor: "var(--color-mirror-light-blue)" }}>
                <div className="flex items-center overflow-hidden" style={{ gap: "1.5vw" }}>
                  <div className="bg-mirror-cyan/10 text-mirror-cyan flex shrink-0 items-center justify-center rounded-lg shadow-sm" style={{ width: "5vh", height: "5vh" }}>
                    {isImage ? <FaCamera style={{ width: "2.5vh", height: "2.5vh" }} /> : <FaPaperclip style={{ width: "2.5vh", height: "2.5vh" }} />}
                  </div>
                  <div className="overflow-hidden">
                    <p className="text-mirror-dark-blue truncate text-sm font-bold">{uploadedFile.name}</p>
                    <p className="text-mirror-gray text-xs">{formatBytes(uploadedFile.size)} • {uploadedFile.type || "unknown"}</p>
                  </div>
                </div>
                <button onClick={onClear} className="text-mirror-gray hover:text-mirror-cyan flex cursor-pointer items-center justify-center rounded transition-colors focus:outline-none" style={{ padding: "0.5vh 0.5vw" }}>
                  <FaTimes style={{ width: "2vh", height: "2vh" }} />
                </button>
              </div>
              <div className="bg-mirror-dark-blue/95 relative flex items-center justify-center overflow-hidden rounded-2xl border shadow-inner" style={{ minHeight: "55vh", padding: "2vh 2vw", borderColor: "var(--color-mirror-light-blue)" }}>
                {isImage && imageUrl ? (
                  <div className="relative w-full" style={{ height: "48vh" }}>
                    <Image src={imageUrl} alt="Uploaded document" fill style={{ objectFit: "contain", borderRadius: "2vh" }} className="shadow-md" />
                  </div>
                ) : (
                  <div className="text-mirror-light-blue flex flex-col items-center justify-center text-center" style={{ padding: "4vh 4vw" }}>
                    <div className="text-mirror-cyan bg-mirror-cyan/10 flex items-center justify-center rounded-full" style={{ marginBottom: "2vh", padding: "2vh" }}>
                      <FaFileAlt style={{ width: "5vh", height: "5vh" }} />
                    </div>
                    <p className="text-mirror-white text-base font-bold" style={{ marginBottom: "1vh" }}>Non-Image Source Loaded</p>
                    <div className="bg-mirror-dark-blue/80 text-mirror-green w-full overflow-auto rounded-xl border text-left font-mono text-[10px] shadow-lg" style={{ maxWidth: "25vw", maxHeight: "25vh", padding: "2vh", borderColor: "var(--color-mirror-gray)" }}>
                      <p className="text-mirror-gray border-b pb-1" style={{ marginBottom: "1vh", borderColor: "var(--color-mirror-gray)" }}>{"// Metadata Registry"}</p>
                      <div className="text-mirror-white"><p className="text-mirror-cyan inline">File Name:</p> &quot;{uploadedFile.name}&quot;</div>
                      <div className="text-mirror-white"><p className="text-mirror-cyan inline">File Size:</p> {uploadedFile.size} B</div>
                      <div className="text-mirror-white"><p className="text-mirror-cyan inline">File Type:</p> &quot;{uploadedFile.type}&quot;</div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right — generated template */}
        <div className="flex flex-col md:pl-4">
          <div style={{ marginBottom: "1vh" }}>
            <p className="text-mirror-dark-blue font-bold tracking-wide uppercase" style={{ fontSize: "2.4vh" }}>generated template</p>
          </div>
          <div style={{ marginBottom: "2vh" }}>
            <p className="text-mirror-gray text-sm font-semibold">Generating Status: </p>
            <p className="text-mirror-dark-blue text-sm font-normal">
              {status === "idle" && "Waiting for generation..."}
              {status === "loading" && "Processing document..."}
              {status === "done" && "Template ready for download"}
              {status === "error" && "Generation failed"}
            </p>
          </div>

          <div
            className="bg-mirror-light-blue flex flex-col items-center justify-center rounded-2xl border"
            style={{ minHeight: "55vh", borderColor: "var(--color-mirror-light-blue)", padding: "4vh 4vw", gap: "3vh" }}
          >
            {status === "idle" && <p className="text-mirror-gray text-sm font-medium">No template generated yet</p>}

            {status === "loading" && (
              <div className="flex flex-col items-center" style={{ gap: "2vh" }}>
                <FaSpinner className="text-mirror-cyan animate-spin" style={{ width: "6vh", height: "6vh" }} />
                <p className="text-mirror-dark-blue text-sm font-semibold">Running OCR pipeline...</p>
                <p className="text-mirror-gray text-xs">This may take up to a minute</p>
              </div>
            )}

            {status === "done" && (
              <div className="flex flex-col items-center" style={{ gap: "2vh" }}>
                <FaCheckCircle className="text-mirror-green" style={{ width: "6vh", height: "6vh" }} />
                <p className="text-mirror-dark-blue text-sm font-semibold">Excel template generated</p>
                <button
                  onClick={() => xlsxBlob && triggerDownload(xlsxBlob, xlsxName)}
                  className="bg-mirror-cyan hover:bg-mirror-dark-blue text-mirror-white flex items-center rounded-lg text-sm font-bold shadow-sm transition-colors duration-200"
                  style={{ padding: "1.2vh 2vw", gap: "0.8vw" }}
                >
                  <FaFileExcel style={{ width: "2vh", height: "2vh" }} />
                  Download {xlsxName}
                </button>
              </div>
            )}

            {status === "error" && (
              <div className="flex flex-col items-center" style={{ gap: "2vh" }}>
                <FaExclamationCircle className="text-red-500" style={{ width: "6vh", height: "6vh" }} />
                <p className="text-mirror-dark-blue text-sm font-semibold">Generation failed</p>
                {errorMsg && <p className="text-mirror-gray max-w-[25vw] text-center text-xs">{errorMsg}</p>}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Mirror;
