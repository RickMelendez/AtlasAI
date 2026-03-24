import { Mic } from "lucide-react";
import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";

interface AIVoiceInputProps {
  onStart?: () => void;
  onStop?: (duration: number) => void;
  /** External control: when provided, overrides internal submitted state */
  isActive?: boolean;
  visualizerBars?: number;
  demoMode?: boolean;
  demoInterval?: number;
  className?: string;
}

export function AIVoiceInput({
  onStart,
  onStop,
  isActive,
  visualizerBars = 48,
  demoMode = false,
  demoInterval = 3000,
  className,
}: AIVoiceInputProps) {
  const [internalSubmitted, setInternalSubmitted] = useState(false);
  const [time, setTime] = useState(0);
  const [isClient, setIsClient] = useState(false);
  const [isDemo, setIsDemo] = useState(demoMode);

  // Controlled vs uncontrolled
  const submitted = isActive !== undefined ? isActive : internalSubmitted;

  useEffect(() => {
    setIsClient(true);
  }, []);

  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval>;
    if (submitted) {
      if (isActive === undefined) onStart?.();
      intervalId = setInterval(() => {
        setTime((t) => t + 1);
      }, 1000);
    } else {
      if (isActive === undefined) onStop?.(time);
      setTime(0);
    }
    return () => clearInterval(intervalId);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submitted]);

  useEffect(() => {
    if (!isDemo) return;
    let timeoutId: ReturnType<typeof setTimeout>;
    const runAnimation = () => {
      setInternalSubmitted(true);
      timeoutId = setTimeout(() => {
        setInternalSubmitted(false);
        timeoutId = setTimeout(runAnimation, 1000);
      }, demoInterval);
    };
    const initialTimeout = setTimeout(runAnimation, 100);
    return () => {
      clearTimeout(timeoutId);
      clearTimeout(initialTimeout);
    };
  }, [isDemo, demoInterval]);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const handleClick = () => {
    if (isActive !== undefined) {
      // Controlled mode — delegate to parent
      if (isActive) { onStop?.(time); } else { onStart?.(); }
      return;
    }
    if (isDemo) {
      setIsDemo(false);
      setInternalSubmitted(false);
    } else {
      setInternalSubmitted((prev) => !prev);
    }
  };

  return (
    <div className={cn("w-full py-2", className)}>
      <div className="relative w-full flex items-center flex-col gap-1">
        <button
          className={cn(
            "group w-12 h-12 rounded-xl flex items-center justify-center transition-colors",
            submitted
              ? "bg-none"
              : "bg-none hover:bg-white/10"
          )}
          type="button"
          onClick={handleClick}
        >
          {submitted ? (
            <div
              className="w-5 h-5 rounded-sm animate-spin bg-white cursor-pointer pointer-events-auto"
              style={{ animationDuration: "3s" }}
            />
          ) : (
            <Mic className="w-5 h-5 text-white/70" />
          )}
        </button>

        <span
          className={cn(
            "font-mono text-xs transition-opacity duration-300",
            submitted ? "text-white/70" : "text-white/30"
          )}
        >
          {formatTime(time)}
        </span>

        <div className="h-4 w-full flex items-center justify-center gap-0.5 px-2">
          {[...Array(visualizerBars)].map((_, i) => (
            <div
              key={i}
              className={cn(
                "w-0.5 rounded-full transition-all duration-300",
                submitted
                  ? "bg-white/50 animate-pulse"
                  : "bg-white/10 h-1"
              )}
              style={
                submitted && isClient
                  ? {
                      height: `${20 + Math.random() * 80}%`,
                      animationDelay: `${i * 0.05}s`,
                    }
                  : undefined
              }
            />
          ))}
        </div>

        <p className="h-4 text-xs text-white/70">
          {submitted ? "Listening..." : "Click to speak"}
        </p>
      </div>
    </div>
  );
}
