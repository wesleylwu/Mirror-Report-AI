"use client";

import { useRef, useState } from "react";
import { FaPaperclip } from "react-icons/fa";

interface DocumentUploaderProps {
  onFileSelect: (file: File) => void;
}

const DocumentUploader = ({ onFileSelect }: DocumentUploaderProps) => {
  const [isDragging, setIsDragging] = useState(false);
  const localInputRef = useRef<HTMLInputElement>(null);

  const validateAndSelect = (file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase();
    const allowedTypes = [
      "image/jpeg",
      "image/jpg",
      "image/png",
      "image/webp",
      "application/pdf",
    ];
    const allowedExts = ["jpg", "jpeg", "png", "webp", "pdf"];
    if (
      allowedTypes.includes(file.type) ||
      (ext && allowedExts.includes(ext))
    ) {
      onFileSelect(file);
    } else {
      alert("Only JPEG, PNG, WebP, or PDF files are allowed.");
    }
  };

  return (
    <div className="flex flex-col">
      <div
        onClick={() => localInputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          const f = e.dataTransfer.files?.[0];
          if (f) validateAndSelect(f);
        }}
        className={`bg-mirror-light-blue flex min-h-[55vh] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed transition-all duration-300 ${
          isDragging
            ? "border-mirror-cyan scale-[0.99] opacity-80"
            : "border-mirror-gray opacity-100"
        }`}
      >
        <div className="flex flex-col items-center gap-4 px-6 text-center md:px-12">
          <div className="bg-mirror-cyan/10 text-mirror-cyan flex h-16 w-16 items-center justify-center rounded-full shadow-sm transition-transform duration-300 hover:scale-110 md:h-20 md:w-20">
            <FaPaperclip className="h-8 w-8 rotate-45" />
          </div>
          <div className="flex flex-col items-center gap-2 text-center">
            <p className="text-mirror-dark-blue text-base font-bold">
              Drag & drop your document here
            </p>
            <p className="text-mirror-gray max-w-[70vw] text-center text-xs leading-relaxed md:max-w-[20vw]">
              Supports JPEG, PNG, WebP, or PDF. Click to browse.
            </p>
          </div>
          <p className="bg-mirror-cyan hover:bg-mirror-dark-blue text-mirror-white inline-flex cursor-pointer items-center rounded-lg px-4 py-2 text-xs font-bold shadow-sm transition-colors duration-200">
            Select File
          </p>
        </div>
      </div>
      <input
        type="file"
        ref={localInputRef}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) validateAndSelect(f);
        }}
        accept=".jpg,.jpeg,.png,.webp,.pdf,image/jpeg,image/png,image/webp,application/pdf"
        className="hidden"
      />
    </div>
  );
};

export default DocumentUploader;
