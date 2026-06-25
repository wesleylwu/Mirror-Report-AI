"use client";

const Mirror = () => {
  return (
    <div className="mx-auto w-full max-w-7xl flex-grow px-4 py-8 sm:px-6 lg:px-8">
      <div className="relative grid grid-cols-1 gap-8 md:grid-cols-2 md:gap-12">
        <div className="border-mirror-border flex flex-col md:border-r md:pr-12">
          <div className="mb-2">
            <p className="text-mirror-text-dark text-xl font-bold tracking-wide uppercase">
              document source
            </p>
          </div>
          <div className="mb-4">
            <p className="text-mirror-text-muted text-sm font-semibold">
              Scanning Status:
            </p>
          </div>
          <div className="border-mirror-border bg-mirror-light-blue flex min-h-[500px] w-full items-center justify-center rounded-2xl border">
            <p className="text-mirror-text-light text-sm font-medium">
              No document uploaded yet
            </p>
          </div>
        </div>
        <div className="flex flex-col md:pl-4">
          <div className="mb-2">
            <p className="text-mirror-text-dark text-xl font-bold tracking-wide uppercase">
              generated template
            </p>
          </div>
          <div className="mb-4">
            <p className="text-mirror-text-muted text-sm font-semibold">
              Generating Status:
            </p>
          </div>
          <div className="border-mirror-border bg-mirror-light-blue flex min-h-[500px] w-full items-center justify-center rounded-2xl border">
            <p className="text-mirror-text-light text-sm font-medium">
              No template generated yet
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Mirror;
