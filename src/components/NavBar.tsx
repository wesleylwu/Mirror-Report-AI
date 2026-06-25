"use client";

import { FaPaperclip, FaCamera, FaFileExcel, FaUser } from "react-icons/fa";

const NavBar = () => {
  return (
    <div className="text-mirror-white bg-mirror-dark-blue w-full shadow-md transition-all duration-300 select-none">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex flex-shrink-0 cursor-pointer items-center">
            <p className="text-mirror-white text-xl font-bold">
              smartNexus® | Mirror Report AI
            </p>
          </div>
          <div className="flex items-center space-x-6 sm:space-x-8">
            <button className="text-mirror-white hover:text-mirror-hover-blue flex cursor-pointer items-center rounded px-2 py-1 text-sm font-medium transition-colors duration-200 focus:outline-none">
              <FaPaperclip className="mr-2 h-4 w-4" />
              <p>Upload</p>
            </button>
            <button className="text-mirror-white hover:text-mirror-hover-blue flex cursor-pointer items-center rounded px-2 py-1 text-sm font-medium transition-colors duration-200 focus:outline-none">
              <FaCamera className="mr-2 h-4 w-4" />
              <p>Capture</p>
            </button>
            <button className="text-mirror-white hover:text-mirror-hover-blue flex cursor-pointer items-center rounded px-2 py-1 text-sm font-medium transition-colors duration-200 focus:outline-none">
              <FaFileExcel className="mr-2 h-4 w-4" />
              <p>Excel</p>
            </button>
            <button className="bg-mirror-white/10 hover:bg-mirror-white/20 active:bg-mirror-white/30 text-mirror-white border-mirror-white/20 cursor-pointer rounded-lg border px-4 py-2 text-sm font-semibold shadow-sm transition-all duration-200 focus:outline-none">
              <p>Generate</p>
            </button>
            <button className="bg-mirror-white/10 hover:bg-mirror-white/20 border-mirror-white/20 flex h-8 w-8 cursor-pointer items-center justify-center rounded-full border transition-all duration-200 focus:outline-none">
              <FaUser className="text-mirror-white h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default NavBar;
