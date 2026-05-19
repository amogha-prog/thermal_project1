import React from 'react';
import { useTIOSStore } from '../store/useTIOSStore';

const STYLES = {
  success: 'bg-green-500 text-black',
  warn:    'bg-warn     text-black',
  error:   'bg-thermal  text-white',
  info:    'bg-accent   text-black',
};

export default function ToastContainer() {
  const toasts = useTIOSStore((s) => s.toasts);
  return (
    <div className="fixed bottom-5 right-5 z-[9999] flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`font-mono text-[11px] font-bold tracking-widest px-4 py-2 rounded shadow-lg animate-fadeIn ${STYLES[t.type] || STYLES.info}`}
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}
