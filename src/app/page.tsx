"use client";

import { useState, useCallback, useEffect } from "react";
import NavBar from "@/src/components/NavBar";
import Mirror from "@/src/components/Mirror";
import Footer from "@/src/components/Footer";
import Capture from "@/src/components/Capture";
import { AnimatePresence } from "motion/react";

const DB_URL_KEY = "mirrorDbUrl";

const Page = () => {
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [isCapturing, setIsCapturing] = useState(false);
  const [dbUrl, setDbUrl] = useState("");

  useEffect(() => {
    const saved = localStorage.getItem(DB_URL_KEY);
    if (saved) setDbUrl(saved);
  }, []);

  const handleDbUrlChange = useCallback((url: string) => {
    setDbUrl(url);
    if (url) {
      localStorage.setItem(DB_URL_KEY, url);
    } else {
      localStorage.removeItem(DB_URL_KEY);
    }
  }, []);

  const handleCaptureFileSelect = useCallback((file: File) => {
    setUploadedFiles([file]);
    setIsCapturing(false);
  }, []);

  const handleFilesSelect = useCallback((files: File[]) => {
    setUploadedFiles(files);
  }, []);

  const handleClear = useCallback(() => {
    setUploadedFiles([]);
  }, []);

  return (
    <div className="bg-mirror-white font-mirror-noto flex min-h-screen flex-col">
      <NavBar
        onFilesSelect={handleFilesSelect}
        onCaptureClick={() => setIsCapturing(true)}
        dbUrl={dbUrl}
        onDbUrlChange={handleDbUrlChange}
      />
      <Mirror
        uploadedFiles={uploadedFiles}
        onClear={handleClear}
        onFilesSelect={handleFilesSelect}
        dbUrl={dbUrl}
      />
      <Footer />
      <AnimatePresence>
        {isCapturing && (
          <Capture
            onFileSelect={handleCaptureFileSelect}
            onClose={() => setIsCapturing(false)}
          />
        )}
      </AnimatePresence>
    </div>
  );
};

export default Page;
