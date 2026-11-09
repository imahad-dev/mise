"use client";

import React, { useEffect, useId, useLayoutEffect, useRef } from "react";

export interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

/**
 * Bottom sheet (centred from 640px) on the native <dialog> element: the browser traps focus,
 * closes on Esc and returns focus to the element that opened it.
 */
export function Sheet({ open, onClose, title, children, footer }: SheetProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const gone = useRef(false);

  // Close on unmount too, so the browser returns focus to the opener. The close event comes
  // later: `gone` (or a dialog StrictMode has reopened) keeps it from reaching onClose.
  useLayoutEffect(() => {
    const dialog = ref.current;
    gone.current = false;
    return () => {
      gone.current = true;
      if (dialog?.open) dialog.close();
    };
  }, []);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="sheet"
      aria-labelledby={titleId}
      onClose={() => {
        if (!gone.current && !ref.current?.open) onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) e.currentTarget.close(); // click on the backdrop
      }}
    >
      <div className="flex max-h-[90vh] flex-col">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 id={titleId} className="text-xl text-ink">
            {title}
          </h2>
          <button
            type="button"
            onClick={() => ref.current?.close()}
            aria-label="Close"
            className="btn-ghost btn-icon text-base"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto p-5">{children}</div>
        {footer && <div className="space-y-3 border-t border-line p-5">{footer}</div>}
      </div>
    </dialog>
  );
}
