"use client";

import { useState, useCallback } from "react";
import NavBar from "@/src/components/NavBar";
import Mirror from "@/src/components/Mirror";
import Footer from "@/src/components/Footer";
import Capture from "@/src/components/Capture";
import { AnimatePresence } from "motion/react";

const Page = () => {
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [isCapturing, setIsCapturing] = useState(false);

  const handleFilesSelect = useCallback((files: File[]) => {
    setUploadedFiles(files);
  }, []);

  const handleClear = useCallback(() => {
    setUploadedFiles([]);
  }, []);

  const handleCaptureFileSelect = useCallback((file: File) => {
    setUploadedFiles([file]);
    setIsCapturing(false);
  }, []);

  return (
    <div className="bg-mirror-white font-mirror-noto flex min-h-screen flex-col">
      <NavBar
        onFilesSelect={handleFilesSelect}
        onCaptureClick={() => setIsCapturing(true)}
      />
      <Mirror
        uploadedFiles={uploadedFiles}
        onClear={handleClear}
        onFilesSelect={handleFilesSelect}
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
