"use client";

import { useRef, useState } from "react";
import { FaPaperclip } from "react-icons/fa";

interface DocumentUploaderProps {
  onFilesSelect: (files: File[]) => void;
}

const DocumentUploader = ({ onFilesSelect }: DocumentUploaderProps) => {
  const [isDragging, setIsDragging] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const localInputRef = useRef<HTMLInputElement>(null);

  const validateAndSelect = (fileList: FileList | File[]) => {
    const list = Array.from(fileList);
    const allowedTypes = [
      "image/jpeg",
      "image/jpg",
      "image/png",
      "image/webp",
      "application/pdf",
    ];
    const allowedExts = ["jpg", "jpeg", "png", "webp", "pdf"];
    const MAX_FILE_SIZE = 5 * 1024 * 1024;

    const validFiles: File[] = [];
    const errors: string[] = [];

    for (const file of list) {
      const ext = file.name.split(".").pop()?.toLowerCase();
      const isAllowedType =
        allowedTypes.includes(file.type) || (ext && allowedExts.includes(ext));

      if (!isAllowedType) {
        errors.push(
          `"${file.name}" is not supported (use JPEG, PNG, WebP, PDF)`,
        );
      } else if (file.size > MAX_FILE_SIZE) {
        const sizeInMB = (file.size / (1024 * 1024)).toFixed(1);
        errors.push(`"${file.name}" exceeds 5MB size limit (${sizeInMB}MB)`);
      } else {
        validFiles.push(file);
      }
    }

    if (errors.length > 0) {
      setErrorMessage(errors.join(" | "));
    } else {
      setErrorMessage(null);
    }

    if (validFiles.length > 0) {
      onFilesSelect(validFiles);
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
          if (e.dataTransfer.files) validateAndSelect(e.dataTransfer.files);
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
              Supports JPEG, PNG, WebP, or PDF. Select multiple files for bulk
              processing.
            </p>
          </div>
          {errorMessage && (
            <div className="bg-mirror-red/10 border-mirror-red/20 text-mirror-red max-w-md rounded-lg border px-4 py-2.5 text-center text-xs font-semibold">
              {errorMessage}
            </div>
          )}
          <p className="bg-mirror-cyan hover:bg-mirror-dark-blue text-mirror-white inline-flex cursor-pointer items-center rounded-lg px-4 py-2 text-xs font-bold shadow-sm transition-colors duration-200">
            Select Files
          </p>
        </div>
      </div>
      <input
        type="file"
        ref={localInputRef}
        onChange={(e) => {
          if (e.target.files) validateAndSelect(e.target.files);
        }}
        accept=".jpg,.jpeg,.png,.webp,.pdf,image/jpeg,image/png,image/webp,application/pdf"
        multiple={true}
        className="hidden"
      />
    </div>
  );
};

export default DocumentUploader;
