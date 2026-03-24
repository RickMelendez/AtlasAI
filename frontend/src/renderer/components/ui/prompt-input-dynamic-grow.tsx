import React, {
  createContext, useEffect, useState,
  useRef, useCallback, memo, useMemo,
} from "react";
import { Plus } from "lucide-react";

// ===== TYPES =====

type MenuOption = "Voice" | "Screen" | "Search" | "Plan";

interface RippleEffect { x: number; y: number; id: number; }
interface Position     { x: number; y: number; }

export interface ChatInputProps {
  placeholder?:       string;
  onSubmit?:          (value: string) => void;
  disabled?:          boolean;
  glowIntensity?:     number;
  animationDuration?: number;
  menuOptions?:       MenuOption[];
  /** Extra content rendered left of textarea (e.g. mic button) */
  leftSlot?:          React.ReactNode;
}

interface InputAreaProps {
  value:            string;
  setValue:         React.Dispatch<React.SetStateAction<string>>;
  placeholder:      string;
  handleKeyDown:    (e: React.KeyboardEvent) => void;
  disabled:         boolean;
  isSubmitDisabled: boolean;
}

interface GlowEffectsProps {
  glowIntensity:     number;
  mousePosition:     Position;
  animationDuration: number;
}

interface RippleEffectsProps { ripples: RippleEffect[]; }

interface MenuButtonProps {
  toggleMenu:    () => void;
  menuRef:       React.RefObject<HTMLDivElement>;
  isMenuOpen:    boolean;
  onSelectOption:(option: MenuOption) => void;
  menuOptions:   MenuOption[];
}

interface SelectedOptionsProps {
  options:  MenuOption[];
  onRemove: (option: MenuOption) => void;
}

interface SendButtonProps { isDisabled: boolean; }

interface OptionsMenuProps {
  isOpen:     boolean;
  onSelect:   (option: MenuOption) => void;
  menuOptions:MenuOption[];
}

interface OptionTagProps {
  option:   MenuOption;
  onRemove: (option: MenuOption) => void;
}

// ===== CONTEXT =====

interface ChatInputContextProps {
  mousePosition:     Position;
  ripples:           RippleEffect[];
  addRipple:         (x: number, y: number) => void;
  animationDuration: number;
  glowIntensity:     number;
}

const ChatInputContext = createContext<ChatInputContextProps | undefined>(undefined);

// ===== SUB-COMPONENTS =====

const SendButton = memo(({ isDisabled }: SendButtonProps) => (
  <button
    type="submit"
    aria-label="Send message"
    disabled={isDisabled}
    className={`ml-auto self-center h-8 w-8 flex items-center justify-center rounded-full border-0 p-0 transition-all z-20 flex-shrink-0 ${
      isDisabled
        ? "opacity-40 cursor-not-allowed bg-white/20 text-white/40"
        : "opacity-90 bg-gradient-to-br from-cyan-400/80 to-violet-500/80 text-white hover:opacity-100 cursor-pointer hover:shadow-lg hover:shadow-cyan-500/25"
    }`}
  >
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg"
      className={`block ${isDisabled ? "opacity-50" : "opacity-100"}`}>
      <path d="M16 22L16 10M16 10L11 15M16 10L21 15"
        stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  </button>
));
SendButton.displayName = "SendButton";

const OptionsMenu = memo(({ isOpen, onSelect, menuOptions }: OptionsMenuProps) => {
  if (!isOpen) return null;
  return (
    <div className="absolute top-full left-0 mt-1 bg-gray-900/95 border border-white/10 rounded-xl shadow-xl overflow-hidden z-30 min-w-[130px] backdrop-blur-xl">
      <ul className="py-1">
        {menuOptions.map((option) => (
          <li key={option}
            className="px-4 py-2 hover:bg-white/10 cursor-pointer text-white/80 text-sm font-medium transition-colors"
            onClick={() => onSelect(option)}>
            {option}
          </li>
        ))}
      </ul>
    </div>
  );
});
OptionsMenu.displayName = "OptionsMenu";

const OptionTag = memo(({ option, onRemove }: OptionTagProps) => (
  <div className="flex items-center gap-1 bg-white/10 px-2 py-1 rounded-md text-xs text-white/80">
    <span>{option}</span>
    <button type="button" onClick={() => onRemove(option)}
      className="h-4 w-4 flex items-center justify-center rounded-full hover:bg-white/20 text-white/60">
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  </div>
));
OptionTag.displayName = "OptionTag";

const GlowEffects = memo(({ glowIntensity, mousePosition, animationDuration }: GlowEffectsProps) => (
  <>
    {/* Liquid glass bg */}
    <div className="absolute inset-0 bg-gradient-to-r from-white/5 via-white/8 to-white/5 backdrop-blur-2xl rounded-2xl" />

    {/* Border glow on hover */}
    <div className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity pointer-events-none"
      style={{
        boxShadow: `0 0 0 1px rgba(0,217,255,${0.25 * glowIntensity}), 0 0 10px rgba(0,217,255,${0.3 * glowIntensity}), 0 0 20px rgba(123,47,255,${0.15 * glowIntensity})`,
        transition: `opacity ${animationDuration}ms`,
      }} />

    {/* Cursor gradient */}
    <div className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-20 transition-opacity duration-300 pointer-events-none blur-sm"
      style={{ background: `radial-gradient(circle 120px at ${mousePosition.x}% ${mousePosition.y}%, rgba(0,217,255,0.1) 0%, rgba(123,47,255,0.06) 50%, transparent 100%)` }} />

    {/* Shimmer */}
    <div className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-20 transition-opacity duration-300 bg-gradient-to-r from-transparent via-white/5 to-transparent animate-pulse blur-sm" />
  </>
));
GlowEffects.displayName = "GlowEffects";

const RippleEffects = memo(({ ripples }: RippleEffectsProps) => (
  <>
    {ripples.map((ripple) => (
      <div key={ripple.id} className="absolute pointer-events-none blur-sm"
        style={{ left: ripple.x - 25, top: ripple.y - 25, width: 50, height: 50 }}>
        <div className="w-full h-full rounded-full bg-gradient-to-r from-cyan-400/15 via-violet-400/10 to-cyan-400/15 animate-ping" />
      </div>
    ))}
  </>
));
RippleEffects.displayName = "RippleEffects";

const InputArea = memo(({
  value, setValue, placeholder, handleKeyDown, disabled, isSubmitDisabled,
}: InputAreaProps) => {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      const scrollHeight = textareaRef.current.scrollHeight;
      textareaRef.current.style.height = Math.min(scrollHeight, 104) + "px";
    }
  }, [value]);

  return (
    <div className="flex-1 relative flex items-center min-w-0">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        aria-label="Message Input"
        rows={1}
        className="w-full min-h-8 max-h-24 bg-transparent text-sm font-normal text-white/90 placeholder-white/30 border-0 outline-none px-2 py-1 z-20 relative resize-none overflow-y-auto"
        style={{ letterSpacing: "-0.14px", lineHeight: "22px" }}
        disabled={disabled}
      />
      <SendButton isDisabled={isSubmitDisabled} />
    </div>
  );
});
InputArea.displayName = "InputArea";

const MenuButton = memo(({ toggleMenu, menuRef, isMenuOpen, onSelectOption, menuOptions }: MenuButtonProps) => (
  <div className="relative flex-shrink-0" ref={menuRef}>
    <button type="button" onClick={toggleMenu} aria-label="Menu options"
      className="h-8 w-8 flex items-center justify-center rounded-full bg-white/10 hover:bg-white/20 text-white/70 hover:text-white transition-all mr-1">
      <Plus size={16} />
    </button>
    <OptionsMenu isOpen={isMenuOpen} onSelect={onSelectOption} menuOptions={menuOptions} />
  </div>
));
MenuButton.displayName = "MenuButton";

const SelectedOptions = memo(({ options, onRemove }: SelectedOptionsProps) => {
  if (options.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2 mt-2 pl-2 pr-2 z-20 relative">
      {options.map((option) => (
        <OptionTag key={option} option={option} onRemove={onRemove} />
      ))}
    </div>
  );
});
SelectedOptions.displayName = "SelectedOptions";

// ===== MAIN COMPONENT =====

export default function PromptInputDynamicGrow({
  placeholder       = "Ask Atlas anything…",
  onSubmit,
  disabled          = false,
  glowIntensity     = 0.6,
  animationDuration = 300,
  menuOptions       = ["Voice", "Screen", "Search", "Plan"] as MenuOption[],
  leftSlot,
}: ChatInputProps) {
  const [value,           setValue          ] = useState("");
  const [isMenuOpen,      setIsMenuOpen     ] = useState(false);
  const [selectedOptions, setSelectedOptions] = useState<MenuOption[]>([]);
  const [ripples,         setRipples        ] = useState<RippleEffect[]>([]);
  const [mousePosition,   setMousePosition  ] = useState<Position>({ x: 50, y: 50 });

  const containerRef = useRef<HTMLDivElement | null>(null);
  const menuRef      = useRef<HTMLDivElement | null>(null);
  const throttleRef  = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Close menu on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setIsMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (value.trim() && !disabled) {
      onSubmit?.(value.trim());
      setValue("");
    }
  }, [value, onSubmit, disabled]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(e as unknown as React.FormEvent); }
  }, [handleSubmit]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (containerRef.current && !throttleRef.current) {
      throttleRef.current = setTimeout(() => {
        const rect = containerRef.current?.getBoundingClientRect();
        if (rect) {
          setMousePosition({
            x: ((e.clientX - rect.left) / rect.width) * 100,
            y: ((e.clientY - rect.top) / rect.height) * 100,
          });
        }
        throttleRef.current = null;
      }, 50);
    }
  }, []);

  const addRipple = useCallback((x: number, y: number) => {
    if (ripples.length >= 5) return;
    const newRipple: RippleEffect = { x, y, id: Date.now() };
    setRipples((prev) => [...prev, newRipple]);
    setTimeout(() => setRipples((prev) => prev.filter((r) => r.id !== newRipple.id)), 600);
  }, [ripples]);

  const handleClick = useCallback((e: React.MouseEvent) => {
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      addRipple(e.clientX - rect.left, e.clientY - rect.top);
    }
  }, [addRipple]);

  const toggleMenu    = useCallback(() => setIsMenuOpen((p) => !p), []);
  const selectOption  = useCallback((opt: MenuOption) => {
    setSelectedOptions((p) => p.includes(opt) ? p : [...p, opt]);
    setIsMenuOpen(false);
  }, []);
  const removeOption  = useCallback((opt: MenuOption) => {
    setSelectedOptions((p) => p.filter((o) => o !== opt));
  }, []);

  const contextValue = useMemo(() => ({
    mousePosition, ripples, addRipple, animationDuration, glowIntensity,
  }), [mousePosition, ripples, addRipple, animationDuration, glowIntensity]);

  const isSubmitDisabled = disabled || !value.trim();

  return (
    <ChatInputContext.Provider value={contextValue}>
      <form onSubmit={handleSubmit} className="w-full">
        <div
          ref={containerRef}
          onMouseMove={handleMouseMove}
          onClick={handleClick}
          className="relative flex flex-col w-full bg-white/8 backdrop-blur-xl rounded-2xl p-2 overflow-visible group"
          style={{ boxShadow: "0 2px 12px rgba(0,0,0,0.25)", border: "1px solid rgba(255,255,255,0.1)" }}
        >
          <GlowEffects glowIntensity={glowIntensity} mousePosition={mousePosition} animationDuration={animationDuration} />
          <RippleEffects ripples={ripples} />

          {/* Input row */}
          <div className="flex items-center relative z-20">
            {/* Left slot (mic button) */}
            {leftSlot && <div className="flex-shrink-0 mr-1">{leftSlot}</div>}

            <MenuButton
              toggleMenu={toggleMenu}
              menuRef={menuRef as React.RefObject<HTMLDivElement>}
              isMenuOpen={isMenuOpen}
              onSelectOption={selectOption}
              menuOptions={menuOptions}
            />

            <InputArea
              value={value}
              setValue={setValue}
              placeholder={placeholder}
              handleKeyDown={handleKeyDown}
              disabled={disabled}
              isSubmitDisabled={isSubmitDisabled}
            />
          </div>

          <SelectedOptions options={selectedOptions} onRemove={removeOption} />
        </div>
      </form>
    </ChatInputContext.Provider>
  );
}
