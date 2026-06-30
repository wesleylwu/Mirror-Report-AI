"use client";

import { useRef, useState } from "react";
import { FaPaperclip, FaCamera, FaBars, FaTimes } from "react-icons/fa";
import { motion, AnimatePresence } from "motion/react";

interface NavBarProps {
  onFilesSelect: (files: File[]) => void;
  onCaptureClick: () => void;
}

const NavBar = ({ onFilesSelect, onCaptureClick }: NavBarProps) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const handleUploadClick = () => {
    fileInputRef.current?.click();
    setIsMenuOpen(false);
  };

  const handleCaptureClick = () => {
    onCaptureClick();
    setIsMenuOpen(false);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      const allowedExtensions = ["jpg", "jpeg", "png", "webp", "pdf"];
      const validFiles = files.filter((file) => {
        const ext = file.name.split(".").pop()?.toLowerCase();
        return ext && allowedExtensions.includes(ext);
      });

      if (validFiles.length > 0) {
        onFilesSelect(validFiles);
      }
      if (validFiles.length < files.length) {
        alert(
          "Some files were ignored. Only JPEG, PNG, WebP, and PDF files are allowed.",
        );
      }
    }
  };

  return (
    <div className="text-mirror-white bg-mirror-dark-blue relative z-50 flex h-16 w-full items-center shadow-md select-none md:h-20 print:hidden">
      <div className="flex w-full items-center justify-between px-6 md:px-12">
        <div className="flex shrink-0 cursor-pointer items-center">
          <p className="text-mirror-white text-lg font-bold md:text-xl">
            smartNexus® | Mirror Report AI
          </p>
        </div>

        <div className="hidden items-center gap-4 md:flex md:gap-6">
          <button
            onClick={handleUploadClick}
            className="text-mirror-white hover:text-mirror-cyan flex cursor-pointer items-center rounded px-3 py-1.5 text-sm font-medium transition-colors duration-200 focus:outline-none"
          >
            <FaPaperclip className="mr-2 h-4 w-4" />
            <p>Upload</p>
          </button>
        </div>

        <button
          onClick={() => setIsMenuOpen(true)}
          className="text-mirror-white hover:text-mirror-cyan flex cursor-pointer rounded p-2 transition-colors duration-200 focus:outline-none md:hidden"
        >
          <FaBars className="h-6 w-6" />
        </button>
      </div>

      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept=".jpg,.jpeg,.png,.webp,.pdf,image/jpeg,image/png,image/webp,application/pdf"
        multiple
        className="hidden"
      />

      <AnimatePresence>
        {isMenuOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={() => setIsMenuOpen(false)}
              className="bg-mirror-black/50 fixed inset-0 z-40 backdrop-blur-sm"
            />
            <motion.div
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="bg-mirror-dark-blue border-mirror-white/10 fixed inset-y-0 right-0 z-50 flex w-72 flex-col border-l p-6 shadow-2xl"
            >
              <div className="border-mirror-white/10 mb-6 flex items-center justify-between border-b pb-4">
                <p className="text-mirror-white text-lg font-bold">Menu</p>
                <button
                  onClick={() => setIsMenuOpen(false)}
                  className="text-mirror-white hover:text-mirror-cyan cursor-pointer rounded p-1 transition-colors focus:outline-none"
                >
                  <FaTimes className="h-6 w-6" />
                </button>
              </div>

              <div className="flex flex-col gap-4">
                <button
                  onClick={handleUploadClick}
                  className="text-mirror-white hover:text-mirror-cyan hover:bg-mirror-white/5 border-mirror-white/5 flex w-full cursor-pointer items-center rounded-lg border p-3 text-base font-medium transition-all duration-200 focus:outline-none"
                >
                  <FaPaperclip className="mr-4 h-5 w-5" />
                  <p>Upload Document</p>
                </button>

                <button
                  onClick={handleCaptureClick}
                  className="text-mirror-white hover:text-mirror-cyan hover:bg-mirror-white/5 border-mirror-white/5 flex w-full cursor-pointer items-center rounded-lg border p-3 text-base font-medium transition-all duration-200 focus:outline-none"
                >
                  <FaCamera className="mr-4 h-5 w-5" />
                  <p>Capture Document</p>
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};

export default NavBar;
