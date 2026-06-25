"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import Image from "next/image";
import { FaPaperclip, FaCamera, FaTimes, FaFileAlt } from "react-icons/fa";

interface MirrorProps {
  uploadedFile: File | null;
  onClear: () => void;
  onFileSelect: (file: File) => void;
}

const Mirror = ({ uploadedFile, onClear, onFileSelect }: MirrorProps) => {
  const imageUrl = useMemo<string | null>(() => {
    if (uploadedFile && uploadedFile.type.startsWith("image/")) {
      return URL.createObjectURL(uploadedFile);
    }
    return null;
  }, [uploadedFile]);
  const [isDragging, setIsDragging] = useState(false);
  const localInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    return () => {
      if (imageUrl) URL.revokeObjectURL(imageUrl);
    };
  }, [imageUrl]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      const allowedTypes = [
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "application/pdf",
      ];
      const fileExtension = file.name.split(".").pop()?.toLowerCase();
      const allowedExtensions = ["jpg", "jpeg", "png", "webp", "pdf"];

      if (
        allowedTypes.includes(file.type) ||
        (fileExtension && allowedExtensions.includes(fileExtension))
      ) {
        onFileSelect(file);
      } else {
        alert("Only JPEG, PNG, PDF, and WebP files are allowed.");
      }
    }
  };

  const triggerUpload = () => {
    localInputRef.current?.click();
  };

  const formatBytes = (bytes: number, decimals = 2) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
  };

  const isImage = uploadedFile && uploadedFile.type.startsWith("image/");

  return (
    <div
      className="mx-auto w-full max-w-[90vw] grow"
      style={{ padding: "4vh 3vw" }}
    >
      <div
        className="relative grid grid-cols-1 gap-8 md:grid-cols-2"
        style={{ gap: "4vw" }}
      >
        <div
          className="flex flex-col md:border-r"
          style={{
            paddingRight: "4vw",
            borderColor: "var(--color-mirror-light-blue)",
          }}
        >
          <div
            className="flex items-center justify-between"
            style={{ marginBottom: "1vh" }}
          >
            <p
              className="text-mirror-dark-blue font-bold tracking-wide uppercase"
              style={{ fontSize: "2.4vh" }}
            >
              document source
            </p>
            {uploadedFile && (
              <p
                className="bg-mirror-green/20 text-mirror-dark-blue rounded-full font-semibold"
                style={{ fontSize: "1.4vh", padding: "0.4vh 1vw" }}
              >
                Loaded
              </p>
            )}
          </div>
          <div style={{ marginBottom: "2vh" }}>
            <p className="text-mirror-gray text-sm font-semibold">
              Scanning Status:{" "}
            </p>
            <p className="text-mirror-dark-blue text-sm font-normal">
              {uploadedFile
                ? "File Ready for Processing"
                : "Waiting for file upload..."}
            </p>
          </div>

          {!uploadedFile ? (
            <div className="flex flex-col">
              <div
                onClick={triggerUpload}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className="bg-mirror-light-blue flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed transition-all duration-300"
                style={{
                  minHeight: "55vh",
                  borderColor: isDragging
                    ? "var(--color-mirror-cyan)"
                    : "var(--color-mirror-gray)",
                  opacity: isDragging ? 0.8 : 1,
                  transform: isDragging ? "scale(0.99)" : "none",
                }}
              >
                <div
                  className="flex flex-col items-center text-center"
                  style={{
                    gap: "2vh",
                    paddingLeft: "3vw",
                    paddingRight: "3vw",
                  }}
                >
                  <div
                    className="bg-mirror-cyan/10 text-mirror-cyan flex items-center justify-center rounded-full shadow-sm transition-transform duration-300 hover:scale-110"
                    style={{ width: "8vh", height: "8vh" }}
                  >
                    <FaPaperclip
                      className="rotate-45"
                      style={{ width: "3.5vh", height: "3.5vh" }}
                    />
                  </div>
                  <div className="flex flex-col" style={{ gap: "0.8vh" }}>
                    <p className="text-mirror-dark-blue text-base font-bold">
                      Drag & drop your document here
                    </p>
                    <p className="text-mirror-gray max-w-[20vw] text-xs leading-relaxed">
                      Supports JPEG, PNG, WebP, or PDF. Click to browse.
                    </p>
                  </div>
                  <p
                    className="bg-mirror-cyan hover:bg-mirror-dark-blue text-mirror-white inline-flex cursor-pointer items-center rounded-lg text-xs font-bold shadow-sm transition-colors duration-200"
                    style={{ padding: "1vh 2vw" }}
                  >
                    Select File
                  </p>
                </div>
              </div>
              <input
                type="file"
                ref={localInputRef}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    const allowedTypes = [
                      "image/jpeg",
                      "image/jpg",
                      "image/png",
                      "image/webp",
                      "application/pdf",
                    ];
                    const fileExtension = file.name
                      .split(".")
                      .pop()
                      ?.toLowerCase();
                    const allowedExtensions = [
                      "jpg",
                      "jpeg",
                      "png",
                      "webp",
                      "pdf",
                    ];

                    if (
                      allowedTypes.includes(file.type) ||
                      (fileExtension &&
                        allowedExtensions.includes(fileExtension))
                    ) {
                      onFileSelect(file);
                    } else {
                      alert("Only JPEG, PNG, PDF, and WebP files are allowed.");
                    }
                  }
                }}
                accept=".jpg,.jpeg,.png,.webp,.pdf,image/jpeg,image/png,image/webp,application/pdf"
                className="hidden"
              />
            </div>
          ) : (
            <div className="flex flex-col" style={{ gap: "2vh" }}>
              <div
                className="bg-mirror-light-blue flex items-center justify-between rounded-xl border shadow-sm"
                style={{
                  padding: "2vh 2vw",
                  borderColor: "var(--color-mirror-light-blue)",
                }}
              >
                <div
                  className="flex items-center overflow-hidden"
                  style={{ gap: "1.5vw" }}
                >
                  <div
                    className="bg-mirror-cyan/10 text-mirror-cyan flex shrink-0 items-center justify-center rounded-lg shadow-sm"
                    style={{ width: "5vh", height: "5vh" }}
                  >
                    {isImage ? (
                      <FaCamera style={{ width: "2.5vh", height: "2.5vh" }} />
                    ) : (
                      <FaPaperclip
                        style={{ width: "2.5vh", height: "2.5vh" }}
                      />
                    )}
                  </div>
                  <div className="overflow-hidden">
                    <p className="text-mirror-dark-blue truncate text-sm font-bold">
                      {uploadedFile.name}
                    </p>
                    <p className="text-mirror-gray text-xs">
                      {formatBytes(uploadedFile.size)} •{" "}
                      {uploadedFile.type || "unknown file type"}
                    </p>
                  </div>
                </div>
                <button
                  onClick={onClear}
                  className="text-mirror-gray hover:text-mirror-cyan flex cursor-pointer items-center justify-center rounded transition-colors focus:outline-none"
                  style={{ padding: "0.5vh 0.5vw" }}
                  title="Remove document"
                >
                  <FaTimes style={{ width: "2vh", height: "2vh" }} />
                </button>
              </div>

              <div
                className="bg-mirror-dark-blue/95 relative flex animate-[fadeIn_0.2s_ease-out] items-center justify-center overflow-hidden rounded-2xl border shadow-inner"
                style={{
                  minHeight: "55vh",
                  padding: "2vh 2vw",
                  borderColor: "var(--color-mirror-light-blue)",
                }}
              >
                {isImage && imageUrl ? (
                  <div className="relative w-full" style={{ height: "48vh" }}>
                    <Image
                      src={imageUrl}
                      alt="Uploaded document source"
                      fill
                      style={{ objectFit: "contain", borderRadius: "2vh" }}
                      className="shadow-md"
                    />
                  </div>
                ) : (
                  <div
                    className="text-mirror-light-blue flex flex-col items-center justify-center text-center"
                    style={{ padding: "4vh 4vw" }}
                  >
                    <div
                      className="text-mirror-cyan bg-mirror-cyan/10 flex items-center justify-center rounded-full"
                      style={{ marginBottom: "2vh", padding: "2vh" }}
                    >
                      <FaFileAlt style={{ width: "5vh", height: "5vh" }} />
                    </div>
                    <p
                      className="text-mirror-white text-base font-bold"
                      style={{ marginBottom: "1vh" }}
                    >
                      Non-Image Source Loaded
                    </p>
                    <div
                      className="bg-mirror-dark-blue/80 text-mirror-green w-full overflow-auto rounded-xl border text-left font-mono text-[10px] shadow-lg"
                      style={{
                        maxWidth: "25vw",
                        maxHeight: "25vh",
                        padding: "2vh",
                        borderColor: "var(--color-mirror-gray)",
                      }}
                    >
                      <p
                        className="text-mirror-gray border-b pb-1"
                        style={{
                          marginBottom: "1vh",
                          borderColor: "var(--color-mirror-gray)",
                        }}
                      >
                        {"// Metadata Registry"}
                      </p>
                      <div className="text-mirror-white">
                        <p className="text-mirror-cyan inline">File Name:</p>{" "}
                        &quot;{uploadedFile.name}&quot;
                      </div>
                      <div className="text-mirror-white">
                        <p className="text-mirror-cyan inline">File Size:</p>{" "}
                        {uploadedFile.size} B
                      </div>
                      <div className="text-mirror-white">
                        <p className="text-mirror-cyan inline">File Type:</p>{" "}
                        &quot;{uploadedFile.type}&quot;
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-col md:pl-4">
          <div style={{ marginBottom: "1vh" }}>
            <p
              className="text-mirror-dark-blue font-bold tracking-wide uppercase"
              style={{ fontSize: "2.4vh" }}
            >
              generated template
            </p>
          </div>
          <div style={{ marginBottom: "2vh" }}>
            <p className="text-mirror-gray text-sm font-semibold">
              Generating Status:
            </p>
          </div>
          <div
            className="bg-mirror-light-blue flex items-center justify-center rounded-2xl border"
            style={{
              minHeight: "55vh",
              borderColor: "var(--color-mirror-light-blue)",
            }}
          >
            <p className="text-mirror-gray text-sm font-medium">
              No template generated yet
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Mirror;
