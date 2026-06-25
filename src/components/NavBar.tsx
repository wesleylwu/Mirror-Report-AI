"use client";

import { useRef } from "react";
import { FaPaperclip, FaCamera, FaFileExcel, FaUser } from "react-icons/fa";

interface NavBarProps {
  onFileSelect: (file: File) => void;
}

const NavBar = ({ onFileSelect }: NavBarProps) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div
      className="text-mirror-white bg-mirror-dark-blue z-50 flex w-full items-center shadow-md select-none"
      style={{ height: "8vh" }}
    >
      <div
        className="flex w-full items-center justify-between"
        style={{ paddingLeft: "3vw", paddingRight: "3vw" }}
      >
        <div className="flex shrink-0 cursor-pointer items-center">
          <p
            className="text-mirror-white font-bold"
            style={{ fontSize: "2.2vh" }}
          >
            smartNexus® | Mirror Report AI
          </p>
        </div>
        <div className="flex items-center" style={{ gap: "1.5vw" }}>
          <button
            onClick={handleUploadClick}
            className="text-mirror-white hover:text-mirror-cyan flex cursor-pointer items-center rounded text-sm font-medium transition-colors duration-200 focus:outline-none"
            style={{ padding: "0.5vh 1vw" }}
          >
            <FaPaperclip
              style={{ marginRight: "0.5vw", width: "1.8vh", height: "1.8vh" }}
            />
            <p>Upload</p>
          </button>
          <input
            type="file"
            ref={fileInputRef}
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
            }}
            accept=".jpg,.jpeg,.png,.webp,.pdf,image/jpeg,image/png,image/webp,application/pdf"
            className="hidden"
          />
          <button
            className="text-mirror-white hover:text-mirror-cyan flex cursor-pointer items-center rounded text-sm font-medium transition-colors duration-200 focus:outline-none"
            style={{ padding: "0.5vh 1vw" }}
          >
            <FaCamera
              style={{ marginRight: "0.5vw", width: "1.8vh", height: "1.8vh" }}
            />
            <p>Capture</p>
          </button>
          <button
            className="text-mirror-white hover:text-mirror-cyan flex cursor-pointer items-center rounded text-sm font-medium transition-colors duration-200 focus:outline-none"
            style={{ padding: "0.5vh 1vw" }}
          >
            <FaFileExcel
              style={{ marginRight: "0.5vw", width: "1.8vh", height: "1.8vh" }}
            />
            <p>Excel</p>
          </button>
          <button
            className="bg-mirror-white/10 hover:bg-mirror-white/20 active:bg-mirror-white/30 text-mirror-white border-mirror-white/20 cursor-pointer rounded-lg border text-sm font-semibold shadow-sm transition-all duration-200 focus:outline-none"
            style={{ padding: "0.8vh 1.5vw" }}
          >
            <p>Generate</p>
          </button>
          <button
            className="bg-mirror-white/10 hover:bg-mirror-white/20 border-mirror-white/20 flex cursor-pointer items-center justify-center rounded-full border transition-all duration-200 focus:outline-none"
            style={{ width: "4vh", height: "4vh" }}
          >
            <FaUser
              className="text-mirror-white"
              style={{ width: "1.8vh", height: "1.8vh" }}
            />
          </button>
        </div>
      </div>
    </div>
  );
};

export default NavBar;
