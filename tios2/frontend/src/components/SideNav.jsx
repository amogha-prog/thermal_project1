import React from 'react';
import { useTIOSStore } from '../store/useTIOSStore';

const NavIcon = ({ active, onClick, children, label }) => (
  <button
    onClick={onClick}
    title={label}
    className={`w-12 h-12 flex items-center justify-center transition-all duration-200 relative group
      ${active ? 'text-accent bg-accent/10' : 'text-muted hover:text-white hover:bg-white/5'}`}
  >
    {children}
    {active && <div className="absolute left-0 top-2 bottom-2 w-1 bg-accent rounded-r-full shadow-[0_0_8px_#00e5ff]" />}
    
    {/* Tooltip */}
    <div className="absolute left-14 opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity
                    bg-black/90 text-[10px] text-white px-2 py-1 rounded border border-white/10 whitespace-nowrap z-[2000] font-mono">
      {label}
    </div>
  </button>
);

export default function SideNav() {
  const activeTab = useTIOSStore((s) => s.activeTab);
  const setActiveTab = useTIOSStore((s) => s.setActiveTab);

  return (
    <div className="hidden md:flex w-14 h-full glass-panel border-r border-white/5 flex-col items-center py-6 shrink-0 z-[1001]">
      {/* Dashboard / Video */}
      <NavIcon 
        label="DASHBOARD"
        active={activeTab === 'dashboard'} 
        onClick={() => setActiveTab('dashboard')}
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="14" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" />
        </svg>
      </NavIcon>

      <div className="w-8 h-px bg-white/10 my-2" />

      {/* Map */}
      <NavIcon 
        label="SATELLITE MAP"
        active={activeTab === 'map'} 
        onClick={() => setActiveTab('map')}
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
          <circle cx="12" cy="10" r="3" />
        </svg>
      </NavIcon>

      <div className="mt-auto opacity-40 hover:opacity-100 transition-opacity">
        {/* Settings */}
        <NavIcon label="SETTINGS" active={false} onClick={() => {}}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </NavIcon>
      </div>
    </div>
  );
}
