"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import {
  FaTimes,
  FaCamera,
  FaSyncAlt,
  FaTh,
  FaCheck,
  FaTrash,
  FaEye,
} from "react-icons/fa";
import { motion } from "motion/react";

interface CaptureProps {
  onFilesSelect: (files: File[]) => void;
  onClose: () => void;
}

const Capture = ({ onFilesSelect, onClose }: CaptureProps) => {
  const [facingMode, setFacingMode] = useState<"environment" | "user">(
    "environment",
  );
  const [capturedPhotos, setCapturedPhotos] = useState<string[]>([]);
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  const [showGrid, setShowGrid] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isFlashing, setIsFlashing] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    let activeStream: MediaStream | null = null;

    const startCamera = async () => {
      try {
        setLoading(true);
        setError(null);

        if (activeStream) {
          activeStream.getTracks().forEach((track) => track.stop());
        }

        const constraints = {
          video: {
            facingMode: { ideal: facingMode },
            width: { ideal: 1920 },
            height: { ideal: 1080 },
          },
          audio: false,
        };

        const mediaStream =
          await navigator.mediaDevices.getUserMedia(constraints);
        activeStream = mediaStream;
        streamRef.current = mediaStream;

        if (videoRef.current) {
          videoRef.current.srcObject = mediaStream;
        }
      } catch (err) {
        console.error("Camera access error:", err);
        setError(
          "Could not access your camera. Please check camera permissions or try another camera.",
        );
      } finally {
        setLoading(false);
      }
    };

    // Only run camera if we're not currently inspecting a preview image
    if (previewIndex === null) {
      startCamera();
    } else {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
    }

    return () => {
      if (activeStream) {
        activeStream.getTracks().forEach((track) => track.stop());
      }
    };
  }, [facingMode, previewIndex]);

  const handleCapture = () => {
    if (videoRef.current) {
      const video = videoRef.current;
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth || 1280;
      canvas.height = video.videoHeight || 720;

      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL("image/jpeg", 0.9);
        setCapturedPhotos((prev) => [...prev, dataUrl]);

        // Trigger shutter flash
        setIsFlashing(true);
        setTimeout(() => setIsFlashing(false), 150);
      }
    }
  };

  const handleDeletePhoto = (index: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setCapturedPhotos((prev) => prev.filter((_, idx) => idx !== index));
    if (previewIndex === index) {
      setPreviewIndex(null);
    } else if (previewIndex !== null && previewIndex > index) {
      setPreviewIndex(previewIndex - 1);
    }
  };

  const handleUploadAll = async () => {
    if (capturedPhotos.length === 0) return;
    try {
      const filePromises = capturedPhotos.map(async (dataUrl, idx) => {
        const res = await fetch(dataUrl);
        const blob = await res.blob();
        return new File([blob], `captured_doc_${Date.now()}_${idx + 1}.jpg`, {
          type: "image/jpeg",
        });
      });
      const files = await Promise.all(filePromises);
      onFilesSelect(files);
      onClose();
    } catch (err) {
      console.error("Error creating files from captured images:", err);
      alert("Failed to process captured images.");
    }
  };

  const toggleFacingMode = () => {
    setFacingMode((prev) => (prev === "environment" ? "user" : "environment"));
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="bg-mirror-black text-mirror-white fixed inset-0 z-50 flex flex-col transition-all duration-300 select-none"
    >
      {/* Top Header */}
      <div className="from-mirror-black/80 absolute top-0 right-0 left-0 z-10 flex items-center justify-between bg-linear-to-b to-transparent px-6 py-4">
        <button
          onClick={onClose}
          className="bg-mirror-dark-gray/60 border-mirror-white/10 text-mirror-white hover:bg-mirror-dark-gray/80 flex h-10 w-10 items-center justify-center rounded-full border backdrop-blur-md transition-all active:scale-95"
        >
          <FaTimes className="h-5 w-5" />
        </button>
        <p className="text-mirror-light-gray text-sm font-semibold tracking-wider uppercase">
          {previewIndex !== null
            ? `Preview Page ${previewIndex + 1}`
            : capturedPhotos.length > 0
              ? `Batch Scan (${capturedPhotos.length} Captured)`
              : "Scan Documents"}
        </p>
        <button
          onClick={() => setShowGrid(!showGrid)}
          disabled={previewIndex !== null}
          className={`flex h-10 w-10 items-center justify-center rounded-full border transition-all active:scale-95 ${
            showGrid
              ? "bg-mirror-cyan border-mirror-cyan/40 text-mirror-white"
              : "bg-mirror-dark-gray/60 border-mirror-white/10 text-mirror-light-gray hover:bg-mirror-dark-gray/80"
          } disabled:pointer-events-none disabled:opacity-40`}
        >
          <FaTh className="h-4 w-4" />
        </button>
      </div>

      {/* Main Viewport */}
      <div className="bg-mirror-black relative flex flex-1 items-center justify-center overflow-hidden">
        {loading && !error && previewIndex === null && (
          <div className="z-10 flex flex-col items-center justify-center gap-3">
            <div className="border-mirror-cyan h-12 w-12 animate-spin rounded-full border-4 border-t-transparent"></div>
            <p className="text-mirror-gray text-sm font-medium">
              Starting Camera...
            </p>
          </div>
        )}

        {error && previewIndex === null && (
          <div className="z-10 flex max-w-md flex-col items-center justify-center p-6 text-center">
            <div className="bg-mirror-red/10 text-mirror-red border-mirror-red/20 mb-4 flex h-16 w-16 items-center justify-center rounded-full border">
              <FaCamera className="h-8 w-8" />
            </div>
            <h3 className="mb-2 text-lg font-bold">Camera Access Failed</h3>
            <p className="text-mirror-gray mb-6 text-sm leading-relaxed">
              {error}
            </p>
            <button
              onClick={() => {
                setPreviewIndex(null);
                setFacingMode("environment");
              }}
              className="bg-mirror-cyan hover:bg-mirror-cyan/90 text-mirror-white rounded-lg px-6 py-2.5 text-sm font-bold shadow-md transition-all active:scale-95"
            >
              Retry Connection
            </button>
          </div>
        )}

        {/* Live Video Feed */}
        {previewIndex === null && !error && (
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className={`h-full w-full object-cover transition-all duration-75 ${
              loading
                ? "opacity-0"
                : isFlashing
                  ? "opacity-30 brightness-150"
                  : "opacity-100"
            }`}
          />
        )}

        {/* Full screen preview for captured photo */}
        {previewIndex !== null && capturedPhotos[previewIndex] && (
          <div className="relative flex h-full w-full items-center justify-center p-4">
            <Image
              src={capturedPhotos[previewIndex]}
              alt="Captured document preview"
              fill
              unoptimized
              style={{ objectFit: "contain" }}
              className="bg-mirror-black animate-fade-in"
            />
            <div className="absolute bottom-6 flex gap-4">
              <button
                onClick={() => setPreviewIndex(null)}
                className="bg-mirror-dark-gray hover:bg-mirror-dark-gray/80 border-mirror-white/10 flex items-center gap-2 rounded-xl border px-5 py-2.5 font-bold shadow-md transition-all active:scale-95"
              >
                Back to Camera
              </button>
              <button
                onClick={(e) => handleDeletePhoto(previewIndex, e)}
                className="text-mirror-white flex items-center gap-2 rounded-xl bg-red-600 px-5 py-2.5 font-bold shadow-md transition-all hover:bg-red-500 active:scale-95"
              >
                <FaTrash className="h-3.5 w-3.5" />
                Delete Photo
              </button>
            </div>
          </div>
        )}

        {/* Grid Overlay */}
        {previewIndex === null && !loading && !error && showGrid && (
          <div className="border-mirror-white/5 pointer-events-none absolute inset-0 z-10 grid grid-cols-3 grid-rows-3 border">
            <div className="border-mirror-white/15 border-r border-b"></div>
            <div className="border-mirror-white/15 border-r border-b"></div>
            <div className="border-mirror-white/15 border-b"></div>
            <div className="border-mirror-white/15 border-r border-b"></div>
            <div className="border-mirror-white/15 border-r border-b"></div>
            <div className="border-mirror-white/15 border-b"></div>
            <div className="border-mirror-white/15 border-r"></div>
            <div className="border-mirror-white/15 border-r"></div>
            <div></div>
          </div>
        )}

        {/* Alignment Border Guide */}
        {previewIndex === null && !loading && !error && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center p-6">
            <div className="border-mirror-cyan/50 bg-mirror-black/5 relative flex aspect-3/4 w-full max-w-[85vw] items-center justify-center rounded-2xl border-2 border-dashed">
              <div className="border-mirror-cyan absolute -top-1.5 -left-1.5 h-6 w-6 rounded-tl-lg border-t-4 border-l-4"></div>
              <div className="border-mirror-cyan absolute -top-1.5 -right-1.5 h-6 w-6 rounded-tr-lg border-t-4 border-r-4"></div>
              <div className="border-mirror-cyan absolute -bottom-1.5 -left-1.5 h-6 w-6 rounded-bl-lg border-b-4 border-l-4"></div>
              <div className="border-mirror-cyan absolute -right-1.5 -bottom-1.5 h-6 w-6 rounded-br-lg border-r-4 border-b-4"></div>

              <div className="text-mirror-cyan bg-mirror-black/70 border-mirror-cyan/20 animate-pulse rounded-full border px-3 py-1.5 text-xs font-bold tracking-wider uppercase backdrop-blur-sm">
                Align Document Here
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Captured Thumbnails Bar */}
      {capturedPhotos.length > 0 && previewIndex === null && (
        <div className="bg-mirror-black/90 border-mirror-dark-gray/30 z-10 flex max-h-24 scrollbar-none gap-3 overflow-x-auto border-t px-6 py-3">
          {capturedPhotos.map((photo, index) => (
            <div
              key={index}
              onClick={() => setPreviewIndex(index)}
              className="border-mirror-white/20 hover:border-mirror-cyan group relative aspect-3/4 h-16 shrink-0 cursor-pointer overflow-hidden rounded-lg border transition-all"
            >
              <Image
                src={photo}
                alt={`Captured photo ${index + 1}`}
                fill
                unoptimized
                style={{ objectFit: "cover" }}
              />
              <div className="bg-mirror-black/30 absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
                <FaEye className="text-mirror-white h-4 w-4" />
              </div>
              <button
                onClick={(e) => handleDeletePhoto(index, e)}
                className="absolute top-1 right-1 rounded-full bg-red-600/90 p-1 text-white shadow-sm transition-colors hover:bg-red-500"
              >
                <FaTimes className="h-2 w-2" />
              </button>
              <div className="bg-mirror-black/70 absolute bottom-1 left-1 rounded px-1 text-[9px] font-bold">
                {index + 1}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Bottom Camera Action Bar */}
      {previewIndex === null && (
        <div className="bg-mirror-black border-mirror-dark-gray/60 z-10 flex min-h-36 items-center justify-between border-t px-6 py-8">
          {/* Switch Camera */}
          <button
            onClick={toggleFacingMode}
            disabled={loading || !!error}
            className="bg-mirror-dark-gray/60 border-mirror-white/10 text-mirror-white hover:bg-mirror-dark-gray/80 flex h-14 w-14 items-center justify-center rounded-full border transition-all active:scale-95 disabled:opacity-40"
            title="Switch Camera"
          >
            <FaSyncAlt className="text-mirror-light-gray h-5 w-5" />
          </button>

          {/* Capture Trigger */}
          <button
            onClick={handleCapture}
            disabled={loading || !!error}
            className="bg-mirror-white border-mirror-dark-gray relative flex h-20 w-20 items-center justify-center rounded-full border-8 shadow-xl transition-all hover:scale-105 active:scale-95 disabled:pointer-events-none disabled:opacity-50"
          >
            <div className="bg-mirror-white hover:bg-mirror-light-blue h-14 w-14 rounded-full transition-colors"></div>
          </button>

          {/* Finish & Upload Batch */}
          {capturedPhotos.length > 0 ? (
            <button
              onClick={handleUploadAll}
              className="bg-mirror-cyan hover:bg-mirror-dark-blue text-mirror-white animate-fade-in flex h-14 items-center justify-center gap-2 rounded-full px-6 font-bold shadow-lg transition-all active:scale-95"
            >
              <FaCheck className="h-4 w-4" />
              <span>Done ({capturedPhotos.length})</span>
            </button>
          ) : (
            <div className="h-14 w-14"></div>
          )}
        </div>
      )}
    </motion.div>
  );
};

export default Capture;
