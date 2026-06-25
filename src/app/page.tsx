"use client";

import { useState } from "react";
import NavBar from "@/src/components/NavBar";
import Mirror from "@/src/components/Mirror";
import Footer from "@/src/components/Footer";

const Page = () => {
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);

  const handleFileSelect = (file: File) => {
    setUploadedFile(file);
  };

  const handleClear = () => {
    setUploadedFile(null);
  };

  return (
    <div className="bg-mirror-white font-mirror-noto flex min-h-screen flex-col">
      <NavBar onFileSelect={handleFileSelect} />
      <Mirror
        uploadedFile={uploadedFile}
        onClear={handleClear}
        onFileSelect={handleFileSelect}
      />
      <Footer />
    </div>
  );
};

export default Page;
