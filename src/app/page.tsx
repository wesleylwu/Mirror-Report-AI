"use client";

import { useState, useRef, useCallback } from "react";
import NavBar from "@/src/components/NavBar";
import Mirror from "@/src/components/Mirror";
import Footer from "@/src/components/Footer";
import Capture from "@/src/components/Capture";
import { AnimatePresence } from "motion/react";

const Page = () => {
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const [canDownload, setCanDownload] = useState(false);
  const [canGenerate, setCanGenerate] = useState(false);
  const generateRef = useRef<(() => void) | null>(null);
  const downloadRef = useRef<(() => void) | null>(null);

  const handleFileSelect = useCallback((file: File) => {
    setUploadedFile(file);
  }, []);

  const handleClear = useCallback(() => {
    setUploadedFile(null);
    setCanDownload(false);
    setCanGenerate(false);
  }, []);

  const handleFileSelectFromMirror = useCallback((f: File) => {
    setUploadedFile(f);
    setCanDownload(false);
  }, []);

  const handleGenerateReady = useCallback((fn: () => void) => {
    generateRef.current = fn;
    setCanGenerate(true);
  }, []);

  const handleDownloadReady = useCallback((fn: () => void) => {
    downloadRef.current = fn;
    setCanDownload(true);
  }, []);

  const handleDownloadCleared = useCallback(() => setCanDownload(false), []);

  return (
    <div className="bg-mirror-white font-mirror-noto flex min-h-screen flex-col">
      <NavBar
        onFileSelect={handleFileSelect}
        onCaptureClick={() => setIsCapturing(true)}
        onGenerate={() => generateRef.current?.()}
        onDownload={() => downloadRef.current?.()}
        canGenerate={canGenerate}
        canDownload={canDownload}
      />
      <Mirror
        uploadedFile={uploadedFile}
        onClear={handleClear}
        onFileSelect={handleFileSelectFromMirror}
        onGenerateReady={handleGenerateReady}
        onDownloadReady={handleDownloadReady}
        onDownloadCleared={handleDownloadCleared}
      />
      <Footer />
      <AnimatePresence>
        {isCapturing && (
          <Capture
            onFileSelect={handleFileSelect}
            onClose={() => setIsCapturing(false)}
          />
        )}
      </AnimatePresence>
    </div>
  );
};

export default Page;
