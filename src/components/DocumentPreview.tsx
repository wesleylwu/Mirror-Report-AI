"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { FaTimes, FaCamera, FaPaperclip, FaFileAlt } from "react-icons/fa";

interface DocumentPreviewProps {
  uploadedFiles: File[];
  onClear: () => void;
}

const DocumentPreview = ({ uploadedFiles, onClear }: DocumentPreviewProps) => {
  const [activePreviewIndex, setActivePreviewIndex] = useState(0);

  const activeIndex =
    activePreviewIndex >= uploadedFiles.length ? 0 : activePreviewIndex;
  const activeFile = uploadedFiles[activeIndex];

  const isImage = activeFile?.type.startsWith("image/");
  const isPdf = activeFile?.type === "application/pdf" || activeFile?.name.toLowerCase().endsWith(".pdf");
  const [imageUrl, setImageUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!activeFile || (!isImage && !isPdf)) {
      setImageUrl(null);
      return;
    }
    const url = URL.createObjectURL(activeFile);
    setImageUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [activeFile, isImage, isPdf]);

  const formatBytes = (bytes: number, decimals = 2) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return (
      parseFloat((bytes / Math.pow(k, i)).toFixed(decimals)) + " " + sizes[i]
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="border-mirror-light-blue relative flex h-[70vh] items-center justify-center overflow-hidden rounded-2xl border bg-slate-100 p-4 shadow-inner">
        {activeFile && isImage && imageUrl ? (
          <div className="relative h-full w-full">
            <Image
              src={imageUrl}
              alt={activeFile.name}
              fill
              className="rounded-2xl object-contain shadow-md"
            />
          </div>
        ) : activeFile && isPdf && imageUrl ? (
          <div className="h-full w-full">
            <iframe
              src={imageUrl}
              className="h-full w-full rounded-2xl border-none shadow-md"
              title={activeFile.name}
            />
          </div>
        ) : (
          activeFile && (
            <div className="text-mirror-dark-blue flex flex-col items-center justify-center p-8 text-center">
              <div className="text-mirror-cyan bg-mirror-cyan/10 mb-4 flex items-center justify-center rounded-full p-4">
                <FaFileAlt className="h-10 w-10" />
              </div>
              <p className="text-mirror-dark-blue mb-2 text-base font-bold">
                Unsupported File Type Loaded
              </p>
              <div className="max-h-[25vh] w-full max-w-[25vw] overflow-auto rounded-xl border border-gray-200 bg-white p-4 text-left font-mono text-xs text-gray-800 shadow-md">
                <p className="mb-2 border-b border-gray-100 pb-1 text-gray-400">
                  {"// Metadata Registry"}
                </p>
                <div className="text-gray-700">
                  <p className="text-mirror-cyan inline font-bold">
                    File Name:
                  </p>{" "}
                  &quot;
                  {activeFile.name}&quot;
                </div>
                <div className="text-gray-700">
                  <p className="text-mirror-cyan inline font-bold">
                    File Size:
                  </p>{" "}
                  {activeFile.size} B
                </div>
                <div className="text-gray-700">
                  <p className="text-mirror-cyan inline font-bold">
                    File Type:
                  </p>{" "}
                  &quot;
                  {activeFile.type || "unknown"}&quot;
                </div>
              </div>
            </div>
          )
        )}
      </div>

      <div className="flex items-center justify-between">
        <p className="text-mirror-gray text-xs font-semibold">
          Uploaded Documents ({uploadedFiles.length})
        </p>
        <button
          onClick={onClear}
          className="text-mirror-gray hover:text-mirror-cyan flex cursor-pointer items-center justify-center gap-1 rounded p-1 text-xs transition-colors focus:outline-none"
        >
          <FaTimes className="h-3.5 w-3.5" /> Clear All
        </button>
      </div>

      <div className="scrollbar-thumb-mirror-cyan/20 flex w-full scrollbar-thin scrollbar-track-transparent gap-2 overflow-x-auto pb-2">
        {uploadedFiles.map((file, idx) => {
          const fileIsImage = file.type.startsWith("image/");
          const fileIsPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
          const isActive = idx === activeIndex;
          return (
            <div
              key={idx}
              onClick={() => setActivePreviewIndex(idx)}
              className={`flex shrink-0 cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 transition-all duration-200 ${
                isActive
                  ? "bg-mirror-light-blue border-mirror-cyan shadow-sm"
                  : "bg-mirror-white border-mirror-light-blue hover:bg-mirror-light-blue/20"
              }`}
            >
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-lg ${
                  isActive
                    ? "bg-mirror-cyan/20 text-mirror-cyan"
                    : "text-mirror-gray bg-mirror-light-blue/60"
                }`}
              >
                {fileIsImage ? (
                  <FaCamera className="h-4 w-4" />
                ) : fileIsPdf ? (
                  <FaFileAlt className="h-4 w-4" />
                ) : (
                  <FaPaperclip className="h-4 w-4" />
                )}
              </div>
              <div className="max-w-30 overflow-hidden">
                <p className="text-mirror-dark-blue truncate text-xs font-bold">
                  {file.name}
                </p>
                <p className="text-mirror-gray text-[10px]">
                  {formatBytes(file.size)}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default DocumentPreview;
