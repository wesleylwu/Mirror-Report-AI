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
  const activeFile = uploadedFiles[activePreviewIndex] || uploadedFiles[0];

  const isImage = activeFile?.type.startsWith("image/");
  const [imageUrl, setImageUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!activeFile || !isImage) {
      setImageUrl(null);
      return;
    }
    const url = URL.createObjectURL(activeFile);
    setImageUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [activeFile, isImage]);

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
      <div className="flex items-center justify-between">
        <p className="text-mirror-gray text-xs font-semibold">
          Uploaded Files ({uploadedFiles.length})
        </p>
        <button
          onClick={onClear}
          className="text-mirror-gray hover:text-mirror-red flex cursor-pointer items-center justify-center gap-1 rounded p-1 text-xs transition-colors focus:outline-none"
        >
          <FaTimes className="h-3.5 w-3.5" /> Clear All
        </button>
      </div>

      <div className="flex scrollbar-thin gap-2 overflow-x-auto pb-2">
        {uploadedFiles.map((file, idx) => {
          const fileIsImage = file.type.startsWith("image/");
          const isActive = idx === activePreviewIndex;
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
                className={`flex h-7 w-7 items-center justify-center rounded-lg ${
                  isActive
                    ? "bg-mirror-cyan/20 text-mirror-cyan"
                    : "text-mirror-gray bg-mirror-light-blue/60"
                }`}
              >
                {fileIsImage ? (
                  <FaCamera className="h-3.5 w-3.5" />
                ) : (
                  <FaPaperclip className="h-3.5 w-3.5" />
                )}
              </div>
              <div className="max-w-[120px]">
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

      <div className="bg-mirror-dark-blue/95 border-mirror-light-blue relative flex min-h-[55vh] items-center justify-center overflow-hidden rounded-2xl border p-4">
        {isImage && imageUrl ? (
          <div className="relative h-[48vh] w-full">
            <Image
              src={imageUrl}
              alt="Uploaded document"
              fill
              className="animate-fade-in rounded-2xl object-contain shadow-md"
            />
          </div>
        ) : (
          activeFile && (
            <div className="text-mirror-light-blue animate-fade-in flex flex-col items-center justify-center p-8 text-center">
              <div className="text-mirror-cyan bg-mirror-cyan/10 mb-4 flex items-center justify-center rounded-full p-4">
                <FaFileAlt className="h-10 w-10" />
              </div>
              <p className="text-mirror-white mb-2 text-base font-bold">
                Non-Image Source Loaded
              </p>
              <div className="bg-mirror-dark-blue/80 text-mirror-green border-mirror-gray max-h-[25vh] w-full max-w-[25vw] overflow-auto rounded-xl border p-4 text-left font-mono text-xs shadow-lg">
                <div className="text-mirror-white">
                  <p className="text-mirror-cyan inline">File Name:</p> &quot;
                  {activeFile.name}&quot;
                </div>
                <div className="text-mirror-white">
                  <p className="text-mirror-cyan inline">File Size:</p>{" "}
                  {activeFile.size} B
                </div>
                <div className="text-mirror-white">
                  <p className="text-mirror-cyan inline">File Type:</p> &quot;
                  {activeFile.type}&quot;
                </div>
              </div>
            </div>
          )
        )}
      </div>
    </div>
  );
};

export default DocumentPreview;
