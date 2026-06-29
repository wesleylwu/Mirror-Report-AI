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
} from "react-icons/fa";
import { motion } from "motion/react";

interface CaptureProps {
  onFileSelect: (file: File) => void;
  onClose: () => void;
}

const Capture = ({ onFileSelect, onClose }: CaptureProps) => {
  const [facingMode, setFacingMode] = useState<"environment" | "user">(
    "environment",
  );
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [showGrid, setShowGrid] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

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
        setStream(mediaStream);

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

    if (!capturedImage) {
      startCamera();
    }

    return () => {
      if (activeStream) {
        activeStream.getTracks().forEach((track) => track.stop());
      }
    };
  }, [facingMode, capturedImage]);

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
        setCapturedImage(dataUrl);

        if (stream) {
          stream.getTracks().forEach((track) => track.stop());
          setStream(null);
        }
      }
    }
  };

  const handleRetake = () => {
    setCapturedImage(null);
  };

  const handleUsePhoto = () => {
    if (capturedImage) {
      fetch(capturedImage)
        .then((res) => res.blob())
        .then((blob) => {
          const file = new File([blob], `captured_doc_${Date.now()}.jpg`, {
            type: "image/jpeg",
          });
          onFileSelect(file);
          onClose();
        })
        .catch((err) => {
          console.error("Error creating file from captured image:", err);
          alert("Failed to process captured image.");
        });
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
      <div className="from-mirror-black/80 absolute top-0 right-0 left-0 z-10 flex items-center justify-between bg-linear-to-b to-transparent px-6 py-4">
        <button
          onClick={onClose}
          className="bg-mirror-dark-gray/60 border-mirror-white/10 text-mirror-white hover:bg-mirror-dark-gray/80 flex h-10 w-10 items-center justify-center rounded-full border backdrop-blur-md transition-all active:scale-95"
        >
          <FaTimes className="h-5 w-5" />
        </button>
        <p className="text-mirror-light-gray text-sm font-semibold tracking-wider uppercase">
          {capturedImage ? "Preview Document" : "Scan Document"}
        </p>
        <button
          onClick={() => setShowGrid(!showGrid)}
          disabled={!!capturedImage}
          className={`flex h-10 w-10 items-center justify-center rounded-full border transition-all active:scale-95 ${
            showGrid
              ? "bg-mirror-cyan border-mirror-cyan/40 text-mirror-white"
              : "bg-mirror-dark-gray/60 border-mirror-white/10 text-mirror-light-gray hover:bg-mirror-dark-gray/80"
          } disabled:pointer-events-none disabled:opacity-40`}
        >
          <FaTh className="h-4 w-4" />
        </button>
      </div>

      <div className="bg-mirror-black relative flex flex-1 items-center justify-center overflow-hidden">
        {loading && !error && !capturedImage && (
          <div className="z-10 flex flex-col items-center justify-center gap-3">
            <div className="border-mirror-cyan h-12 w-12 animate-spin rounded-full border-4 border-t-transparent"></div>
            <p className="text-mirror-gray text-sm font-medium">
              Starting Camera...
            </p>
          </div>
        )}

        {error && !capturedImage && (
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
                setCapturedImage(null);
                setFacingMode("environment");
              }}
              className="bg-mirror-cyan hover:bg-mirror-cyan/90 text-mirror-white rounded-lg px-6 py-2.5 text-sm font-bold shadow-md transition-all active:scale-95"
            >
              Retry Connection
            </button>
          </div>
        )}

        {!capturedImage && !error && (
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className={`h-full w-full object-cover transition-opacity duration-300 ${
              loading ? "opacity-0" : "opacity-100"
            }`}
          />
        )}

        {capturedImage && (
          <Image
            src={capturedImage}
            alt="Captured document preview"
            fill
            unoptimized
            style={{ objectFit: "contain" }}
            className="bg-mirror-black"
          />
        )}

        {!capturedImage && !loading && !error && showGrid && (
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

        {!capturedImage && !loading && !error && (
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

      <div className="bg-mirror-black border-mirror-dark-gray/60 z-10 flex min-h-36 items-center justify-between border-t px-6 py-8">
        {!capturedImage ? (
          <>
            <div className="h-14 w-14"></div>

            <button
              onClick={handleCapture}
              disabled={loading || !!error}
              className="bg-mirror-white border-mirror-dark-gray relative flex h-20 w-20 items-center justify-center rounded-full border-8 shadow-xl transition-all hover:scale-105 active:scale-95 disabled:pointer-events-none disabled:opacity-50"
            >
              <div className="bg-mirror-white hover:bg-mirror-light-blue h-14 w-14 rounded-full transition-colors"></div>
            </button>

            <button
              onClick={toggleFacingMode}
              disabled={loading || !!error}
              className="bg-mirror-dark-gray/60 border-mirror-white/10 text-mirror-white hover:bg-mirror-dark-gray/80 flex h-14 w-14 items-center justify-center rounded-full border transition-all active:scale-95 disabled:opacity-40"
              title="Switch Camera"
            >
              <FaSyncAlt className="text-mirror-light-gray h-5 w-5" />
            </button>
          </>
        ) : (
          <div className="mx-auto flex w-full max-w-sm items-center justify-around gap-4">
            <button
              onClick={handleRetake}
              className="bg-mirror-dark-gray border-mirror-white/10 hover:bg-mirror-dark-gray/80 text-mirror-white flex flex-1 items-center justify-center gap-2 rounded-xl border py-3.5 font-bold shadow-md transition-all active:scale-95"
            >
              <FaTrash className="text-mirror-red h-4 w-4" />
              <span>Retake</span>
            </button>

            <button
              onClick={handleUsePhoto}
              className="bg-mirror-cyan hover:bg-mirror-cyan/90 text-mirror-white flex flex-1 items-center justify-center gap-2 rounded-xl py-3.5 font-bold shadow-lg transition-all active:scale-95"
            >
              <FaCheck className="h-4 w-4" />
              <span>Use Photo</span>
            </button>
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default Capture;
