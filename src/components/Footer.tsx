"use client";

const Footer = () => {
  return (
    <div className="text-mirror-white bg-mirror-dark-blue mt-auto w-full shadow-md select-none">
      <div className="mx-auto max-w-[80vw]" style={{ padding: "3vh 2vw" }}>
        <div
          className="flex flex-col items-center justify-between sm:flex-row"
          style={{ gap: "2vh" }}
        >
          <div className="flex items-center">
            <p className="text-mirror-white text-lg font-bold">smartNexus®</p>
          </div>
          <div className="flex items-center">
            <p className="text-mirror-light-blue/80 text-sm">
              (C) 2026 Suncreer All rights Reserved.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Footer;
