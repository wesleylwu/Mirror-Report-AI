"use client";

import { useState, useRef } from "react";
import NavBar from "@/src/components/NavBar";
import Mirror from "@/src/components/Mirror";
import Footer from "@/src/components/Footer";

const Page = () => {
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const generateRef = useRef<(() => void) | null>(null);
  const downloadRef = useRef<(() => void) | null>(null);
  const [canGenerate, setCanGenerate] = useState(false);
  const [canDownload, setCanDownload] = useState(false);

  return (
    <div className="bg-mirror-white font-mirror-noto flex min-h-screen flex-col">
      <NavBar
        onFileSelect={(f) => { setUploadedFile(f); setCanDownload(false); }}
        onGenerate={() => generateRef.current?.()}
        onDownload={() => downloadRef.current?.()}
        canGenerate={canGenerate}
        canDownload={canDownload}
      />
      <Mirror
        uploadedFile={uploadedFile}
        onClear={() => { setUploadedFile(null); setCanDownload(false); setCanGenerate(false); }}
        onFileSelect={(f) => { setUploadedFile(f); setCanDownload(false); }}
        onGenerateReady={(fn) => { generateRef.current = fn; setCanGenerate(true); }}
        onDownloadReady={(fn) => { downloadRef.current = fn; setCanDownload(true); }}
        onDownloadCleared={() => setCanDownload(false)}
      />
      <Footer />
    </div>
  );
};

export default Page;
