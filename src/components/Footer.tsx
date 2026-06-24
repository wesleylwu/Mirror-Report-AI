"use client";

const Footer = () => {
  return (
    <div className="text-mirror-white bg-mirror-dark-blue mt-auto w-full shadow-md transition-all duration-300 select-none">
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
          <div className="flex items-center">
            <p className="text-mirror-white text-lg font-bold">smartNexus®</p>
          </div>
          <div className="flex items-center">
            <p className="text-mirror-cyan-footer/80 text-sm">
              (C) 2026 Suncreer All rights Reserved.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Footer;
