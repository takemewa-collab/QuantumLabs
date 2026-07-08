"use client";

import { forwardRef } from "react";
import { ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

// Paylasilan composer — hem /new (hero) hem session (alt sabit) ayni kutuyu kullanir.
// Persistent: parent value/onChange'i tutar; gonderimden sonra temizleme/refocus
// karari parent'ta (onSubmit sonrasi). Enter->gonder, Shift+Enter->yeni satir.
interface ComposerProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  autoFocus?: boolean;
  placeholder?: string;
}

export const Composer = forwardRef<HTMLTextAreaElement, ComposerProps>(
  function Composer(
    { value, onChange, onSubmit, disabled, autoFocus, placeholder },
    ref
  ) {
    const canSend = !disabled && value.trim().length > 0;
    return (
      <div className="rounded-[20px] border border-border bg-surface shadow-sm transition-shadow focus-within:ring-1 focus-within:ring-ring">
        <Textarea
          ref={ref}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder ?? "Message the agent…"}
          rows={3}
          autoFocus={autoFocus}
          onKeyDown={(e) => {
            // Enter -> send; Shift+Enter -> newline. isComposing: IME Enter'i yeme.
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              if (canSend) onSubmit();
            }
          }}
          className="min-h-[80px] resize-none border-0 bg-transparent px-4 pt-3.5 text-base shadow-none focus-visible:border-0 focus-visible:ring-0"
        />
        <div className="flex items-center justify-between px-3 pb-2.5">
          <span className="text-xs text-muted-foreground">
            Enter to send · Shift+Enter for a newline
          </span>
          <Button
            onClick={onSubmit}
            disabled={!canSend}
            size="icon"
            aria-label="Send"
            className="size-8 rounded-full bg-brand text-primary-foreground hover:opacity-90 disabled:opacity-40"
          >
            <ArrowUp className="size-4" />
          </Button>
        </div>
      </div>
    );
  }
);
