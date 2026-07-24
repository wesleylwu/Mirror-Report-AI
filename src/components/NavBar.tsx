"use client";

import { useRef, useState } from "react";
import { FaPaperclip, FaCamera, FaBars, FaTimes, FaDatabase } from "react-icons/fa";
import { motion, AnimatePresence } from "motion/react";

interface NavBarProps {
  onFilesSelect: (files: File[]) => void;
  onCaptureClick: () => void;
  dbUrl: string;
  onDbUrlChange: (url: string) => void;
}

const NavBar = ({ onFilesSelect, onCaptureClick, dbUrl, onDbUrlChange }: NavBarProps) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isDbPanelOpen, setIsDbPanelOpen] = useState(false);
  const [dbUrlInput, setDbUrlInput] = useState(dbUrl);

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

  const handleDbPanelOpen = () => {
    setDbUrlInput(dbUrl);
    setIsDbPanelOpen(true);
  };

  const handleDbConnect = () => {
    onDbUrlChange(dbUrlInput.trim());
    setIsDbPanelOpen(false);
  };

  const handleDbConnectFromMenu = (value: string) => {
    onDbUrlChange(value.trim());
    setIsMenuOpen(false);
  };

  const isConnected = dbUrl.trim().length > 0;

  return (
    <div className="text-mirror-white bg-mirror-dark-blue relative z-50 flex h-16 w-full flex-col items-center shadow-md select-none md:h-20 print:hidden">
      <div className="flex w-full items-center justify-between px-6 md:px-12 h-16 md:h-20">
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
          <button
            onClick={handleDbPanelOpen}
            className={`flex cursor-pointer items-center rounded px-3 py-1.5 text-sm font-medium transition-colors duration-200 focus:outline-none ${
              isConnected
                ? "text-mirror-cyan"
                : "text-mirror-white hover:text-mirror-cyan"
            }`}
          >
            <FaDatabase className="mr-2 h-4 w-4" />
            <p>{isConnected ? "Database (connected)" : "Database"}</p>
          </button>
        </div>

        <button
          onClick={() => setIsMenuOpen(true)}
          className="text-mirror-white hover:text-mirror-cyan flex cursor-pointer rounded p-2 transition-colors duration-200 focus:outline-none md:hidden"
        >
          <FaBars className="h-6 w-6" />
        </button>
      </div>

      <AnimatePresence>
        {isDbPanelOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              onClick={() => setIsDbPanelOpen(false)}
              className="fixed inset-0 z-40"
            />
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.15 }}
              className="bg-mirror-dark-blue border-mirror-white/15 absolute top-full right-6 z-50 mt-1 flex w-96 flex-col gap-3 rounded-xl border p-4 shadow-2xl md:right-12"
            >
              <p className="text-mirror-white text-sm font-semibold">Database Connection</p>
              <input
                type="text"
                value={dbUrlInput}
                onChange={(e) => setDbUrlInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleDbConnect()}
                placeholder="mssql://user:password@host:port/database"
                className="bg-mirror-black/30 border-mirror-white/15 text-mirror-white placeholder-mirror-white/30 w-full rounded-lg border px-3 py-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-mirror-cyan"
              />
              <div className="flex items-center gap-2">
                <button
                  onClick={handleDbConnect}
                  className="bg-mirror-cyan hover:bg-mirror-cyan/80 text-mirror-white flex-1 cursor-pointer rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors focus:outline-none"
                >
                  Connect
                </button>
                {isConnected && (
                  <button
                    onClick={() => { onDbUrlChange(""); setDbUrlInput(""); setIsDbPanelOpen(false); }}
                    className="text-mirror-white/50 hover:text-mirror-white cursor-pointer rounded-lg px-3 py-1.5 text-sm transition-colors focus:outline-none"
                  >
                    Disconnect
                  </button>
                )}
              </div>
              {isConnected && (
                <p className="text-mirror-white/40 truncate text-xs font-mono">{dbUrl}</p>
              )}
            </motion.div>
          </>
        )}
      </AnimatePresence>

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

                <div className="border-mirror-white/5 flex flex-col gap-2 rounded-lg border p-3">
                  <div className="flex items-center gap-3">
                    <FaDatabase className={`h-5 w-5 shrink-0 ${isConnected ? "text-mirror-cyan" : "text-mirror-white"}`} />
                    <p className="text-mirror-white text-base font-medium">Database</p>
                    {isConnected && (
                      <span className="text-mirror-cyan ml-auto text-xs font-semibold">Connected</span>
                    )}
                  </div>
                  <input
                    type="text"
                    value={dbUrlInput}
                    onChange={(e) => setDbUrlInput(e.target.value)}
                    placeholder="mssql://user:pass@host/db"
                    className="bg-mirror-black/30 border-mirror-white/10 text-mirror-white placeholder-mirror-white/30 w-full rounded-lg border px-3 py-2 text-xs font-mono focus:outline-none"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleDbConnectFromMenu(dbUrlInput)}
                      className="bg-mirror-cyan text-mirror-white flex-1 cursor-pointer rounded-lg px-3 py-1.5 text-sm font-semibold focus:outline-none"
                    >
                      Connect
                    </button>
                    {isConnected && (
                      <button
                        onClick={() => { onDbUrlChange(""); setDbUrlInput(""); setIsMenuOpen(false); }}
                        className="text-mirror-white/50 hover:text-mirror-white cursor-pointer rounded-lg px-3 py-1.5 text-sm focus:outline-none"
                      >
                        Clear
                      </button>
                    )}
                  </div>
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
