"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { FaTimes, FaCamera, FaPaperclip, FaFileAlt } from "react-icons/fa";

interface DocumentPreviewProps {
  uploadedFile: File;
  onClear: () => void;
}

const DocumentPreview = ({ uploadedFile, onClear }: DocumentPreviewProps) => {
  const isImage = uploadedFile.type.startsWith("image/");
  const [imageUrl, setImageUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!isImage) {
      setImageUrl(null);
      return;
    }
    const url = URL.createObjectURL(uploadedFile);
    setImageUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [uploadedFile, isImage]);

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
      <div className="bg-mirror-light-blue border-mirror-light-blue flex items-center justify-between rounded-xl border p-4 shadow-sm">
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="bg-mirror-cyan/10 text-mirror-cyan flex h-10 w-10 shrink-0 items-center justify-center rounded-lg shadow-sm">
            {isImage ? (
              <FaCamera className="h-5 w-5" />
            ) : (
              <FaPaperclip className="h-5 w-5" />
            )}
          </div>
          <div className="overflow-hidden">
            <p className="text-mirror-dark-blue truncate text-sm font-bold">
              {uploadedFile.name}
            </p>
            <p className="text-mirror-gray text-xs">
              {formatBytes(uploadedFile.size)} •{" "}
              {uploadedFile.type || "unknown"}
            </p>
          </div>
        </div>
        <button
          onClick={onClear}
          className="text-mirror-gray hover:text-mirror-cyan flex cursor-pointer items-center justify-center rounded p-1 transition-colors focus:outline-none"
        >
          <FaTimes className="h-4 w-4" />
        </button>
      </div>
      <div className="bg-mirror-dark-blue/95 border-mirror-light-blue relative flex min-h-[55vh] items-center justify-center overflow-hidden rounded-2xl border p-4">
        {isImage && imageUrl ? (
          <div className="relative h-[48vh] w-full">
            <Image
              src={imageUrl}
              alt="Uploaded document"
              fill
              className="rounded-2xl object-contain shadow-md"
            />
          </div>
        ) : (
          <div className="text-mirror-light-blue flex flex-col items-center justify-center p-8 text-center">
            <div className="text-mirror-cyan bg-mirror-cyan/10 mb-4 flex items-center justify-center rounded-full p-4">
              <FaFileAlt className="h-10 w-10" />
            </div>
            <p className="text-mirror-white mb-2 text-base font-bold">
              Non-Image Source Loaded
            </p>
            <div className="bg-mirror-dark-blue/80 text-mirror-green border-mirror-gray max-h-[25vh] w-full max-w-[25vw] overflow-auto rounded-xl border p-4 text-left font-mono text-xs shadow-lg">
              <p className="text-mirror-gray border-mirror-gray mb-2 border-b pb-1">
                {"// Metadata Registry"}
              </p>
              <div className="text-mirror-white">
                <p className="text-mirror-cyan inline">File Name:</p> &quot;
                {uploadedFile.name}&quot;
              </div>
              <div className="text-mirror-white">
                <p className="text-mirror-cyan inline">File Size:</p>{" "}
                {uploadedFile.size} B
              </div>
              <div className="text-mirror-white">
                <p className="text-mirror-cyan inline">File Type:</p> &quot;
                {uploadedFile.type}&quot;
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DocumentPreview;
