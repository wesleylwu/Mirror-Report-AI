"use client";

import { useRef, useState } from "react";
import {
  FaPaperclip,
  FaCamera,
  FaFileExcel,
  FaUser,
  FaBars,
  FaTimes,
} from "react-icons/fa";
import { motion, AnimatePresence } from "motion/react";

interface NavBarProps {
  onFileSelect: (file: File) => void;
  onCaptureClick: () => void;
  onDownload: () => void;
  canDownload: boolean;
}

const NavBar = ({
  onFileSelect,
  onCaptureClick,
  onDownload,
  canDownload,
}: NavBarProps) => {
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

  const handleDownloadClick = () => {
    onDownload();
    setIsMenuOpen(false);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
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
  };

  return (
    <div
      className="text-mirror-white bg-mirror-dark-blue relative z-50 flex w-full items-center shadow-md select-none"
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

        <div className="hidden items-center md:flex" style={{ gap: "1.5vw" }}>
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

          <button
            onClick={onDownload}
            disabled={!canDownload}
            className="text-mirror-white hover:text-mirror-cyan flex cursor-pointer items-center rounded text-sm font-medium transition-colors duration-200 focus:outline-none disabled:cursor-not-allowed disabled:opacity-40"
            style={{ padding: "0.5vh 1vw" }}
          >
            <FaFileExcel
              style={{ marginRight: "0.5vw", width: "1.8vh", height: "1.8vh" }}
            />
            <p>Excel</p>
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

        <button
          onClick={() => setIsMenuOpen(true)}
          className="text-mirror-white hover:text-mirror-cyan flex cursor-pointer rounded p-2 transition-colors duration-200 focus:outline-none md:hidden"
        >
          <FaBars style={{ width: "2.4vh", height: "2.4vh" }} />
        </button>
      </div>

      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept=".jpg,.jpeg,.png,.webp,.pdf,image/jpeg,image/png,image/webp,application/pdf"
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
                  <FaTimes style={{ width: "2.4vh", height: "2.4vh" }} />
                </button>
              </div>

              <div className="flex flex-col gap-4">
                <button
                  onClick={handleUploadClick}
                  className="text-mirror-white hover:text-mirror-cyan hover:bg-mirror-white/5 border-mirror-white/5 flex w-full cursor-pointer items-center rounded-lg border p-3 text-base font-medium transition-all duration-200 focus:outline-none"
                >
                  <FaPaperclip
                    className="mr-4"
                    style={{ width: "2.2vh", height: "2.2vh" }}
                  />
                  <p>Upload Document</p>
                </button>

                <button
                  onClick={handleCaptureClick}
                  className="text-mirror-white hover:text-mirror-cyan hover:bg-mirror-white/5 border-mirror-white/5 flex w-full cursor-pointer items-center rounded-lg border p-3 text-base font-medium transition-all duration-200 focus:outline-none"
                >
                  <FaCamera
                    className="mr-4"
                    style={{ width: "2.2vh", height: "2.2vh" }}
                  />
                  <p>Capture Document</p>
                </button>

                <button
                  onClick={handleDownloadClick}
                  disabled={!canDownload}
                  className="text-mirror-white hover:text-mirror-cyan hover:bg-mirror-white/5 border-mirror-white/5 flex w-full cursor-pointer items-center rounded-lg border p-3 text-base font-medium transition-all duration-200 focus:outline-none disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <FaFileExcel
                    className="mr-4"
                    style={{ width: "2.2vh", height: "2.2vh" }}
                  />
                  <p>Excel Template</p>
                </button>



                <div className="border-mirror-white/10 my-4 flex items-center justify-between border-t pt-4">
                  <p className="text-mirror-light-gray text-sm">
                    Account Profile
                  </p>
                  <button
                    className="bg-mirror-white/10 hover:bg-mirror-white/20 border-mirror-white/20 flex cursor-pointer items-center justify-center rounded-full border transition-all duration-200 focus:outline-none"
                    style={{ width: "5vh", height: "5vh" }}
                  >
                    <FaUser
                      className="text-mirror-white"
                      style={{ width: "2vh", height: "2vh" }}
                    />
                  </button>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};

export default NavBar;
