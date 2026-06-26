"use client";

import { useState } from "react";
import NavBar from "@/src/components/NavBar";
import Mirror from "@/src/components/Mirror";
import Footer from "@/src/components/Footer";
import Capture from "@/src/components/Capture";
import { AnimatePresence } from "motion/react";

const Page = () => {
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [isCapturing, setIsCapturing] = useState(false);

  const handleFileSelect = (file: File) => {
    setUploadedFile(file);
  };

  const handleClear = () => {
    setUploadedFile(null);
  };

  return (
    <div className="bg-mirror-white font-mirror-noto flex min-h-screen flex-col">
      <NavBar
        onFileSelect={handleFileSelect}
        onCaptureClick={() => setIsCapturing(true)}
      />
      <Mirror
        uploadedFile={uploadedFile}
        onClear={handleClear}
        onFileSelect={handleFileSelect}
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
