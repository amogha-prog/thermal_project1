import React, { useState, useMemo } from 'react';
import { useTIOSStore } from '../../store/useTIOSStore';
import OfflineMap from '../map/OfflineMap.jsx';

export default function CaptureBrowserModal({ onClose }) {
  const captures = useTIOSStore((s) => s.captures);
  const setSelectedId = useTIOSStore((s) => s.setSelectedCapture);
  
  const [filter, setFilter] = useState('');
  const [sortField, setSortField] = useState('time'); // time, temp, location
  const [sortDir, setSortDir] = useState('desc');
  const [viewMode, setViewMode] = useState('list'); // 'list' | 'map'

  const processedCaptures = useMemo(() => {
    let result = [...captures];

    if (filter.trim()) {
      const q = filter.toLowerCase();
      result = result.filter(c => 
        c.id.toLowerCase().includes(q) || 
        (c.notes && c.notes.toLowerCase().includes(q)) || 
        (c.location && `${c.location.lat},${c.location.lon}`.includes(q))
      );
    }

    result.sort((a, b) => {
      let aVal, bVal;
      if (sortField === 'time') {
        aVal = new Date(a.timestamp).getTime();
        bVal = new Date(b.timestamp).getTime();
      } else if (sortField === 'temp') {
        aVal = parseFloat(a.telemetry?.maxTemp || 0);
        bVal = parseFloat(b.telemetry?.maxTemp || 0);
      } else if (sortField === 'location') {
        aVal = parseFloat(a.location?.lat || 0);
        bVal = parseFloat(b.location?.lat || 0); // crude sorting by lat alone
      }

      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });

    return result;
  }, [captures, filter, sortField, sortDir]);

  const toggleSort = (field) => {
    if (sortField === field) setSortDir(sortDir === 'desc' ? 'asc' : 'desc');
    else { setSortField(field); setSortDir('desc'); }
  };

  const handleSelect = (id) => {
    onClose();
    setSelectedId(id);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/80 backdrop-blur-sm animate-in fade-in">
      <div className="flex flex-col w-full max-w-5xl h-full max-h-[85vh] bg-[#0c142c] border border-accent/40 rounded-lg shadow-2xl overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border bg-[#101a36]">
          <div className="flex items-center gap-6">
            <h2 className="font-mono text-[14px] font-bold text-accent tracking-widest flex items-center gap-3">
              <span className="text-white text-[16px]">▤</span> CAPTURE HISTORY 
              <span className="text-[10px] bg-accent/20 px-2 py-0.5 rounded text-accent">
                {processedCaptures.length} RECORDS
              </span>
            </h2>
            <div className="flex gap-2">
              <button 
                onClick={() => setViewMode('list')}
                className={`font-mono text-[11px] px-3 py-1 rounded transition-colors ${viewMode === 'list' ? 'bg-accent text-white' : 'border border-border text-muted hover:text-white'}`}
              >
                LIST VIEW
              </button>
              <button 
                onClick={() => setViewMode('map')}
                className={`font-mono text-[11px] px-3 py-1 rounded transition-colors ${viewMode === 'map' ? 'bg-accent text-white' : 'border border-border text-muted hover:text-white'}`}
              >
                OFFLINE MAP
              </button>
            </div>
          </div>
          <button onClick={onClose} className="p-2 text-muted hover:text-white transition-colors">
            ✕
          </button>
        </div>

        {viewMode === 'list' ? (
          <>
            {/* Toolbar */}
            <div className="flex items-center gap-4 p-4 border-b border-border/50 bg-[#0a1020]">
              <input
                type="text"
                placeholder="Search ID, notes, coordinates..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="flex-1 bg-[#1a2135] border border-border rounded px-4 py-2 font-mono text-[11px] text-white focus:outline-none focus:border-accent"
              />
              <div className="flex gap-2">
                {['time', 'temp', 'location'].map(f => (
                  <button 
                    key={f}
                    onClick={() => toggleSort(f)}
                   className={`font-mono text-[10px] uppercase px-3 py-1.5 rounded transition-colors ${sortField === f ? 'bg-accent/20 border border-accent text-white' : 'bg-transparent border border-border text-muted hover:text-white'}`}
                  >
                    Sort: {f} {sortField === f ? (sortDir === 'desc' ? '↓' : '↑') : ''}
                  </button>
                ))}
              </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {processedCaptures.map(c => {
                 const maxT = parseFloat(c.telemetry?.maxTemp || 0);
                 const sev = maxT > 70 ? 'bg-red-900/40 border-red-500/50 text-red-300' 
                           : maxT > 50 ? 'bg-amber-900/40 border-amber-500/50 text-amber-300'
                           : 'bg-[#151f38] border-border text-white';

                 return (
                  <div 
                    key={c.id} 
                    onClick={() => handleSelect(c.id)}
                    className={`flex gap-4 p-3 rounded border hover:border-accent cursor-pointer transition-all ${sev}`}
                  >
                    <div className="flex items-center gap-2 w-48 shrink-0 border-r border-border/50">
                       {c.thumbnails?.thermal ? (
                         <img src={c.thumbnails.thermal} className="w-12 h-[34px] rounded object-cover" alt="thm" />
                       ) : <div className="w-12 h-[34px] bg-black/40 rounded" />}
                       <div className="flex flex-col">
                         <span className="font-mono text-[11px] font-bold">{c.id}</span>
                         <span className="font-mono text-[9px] opacity-70">{c.timeStr}</span>
                       </div>
                    </div>

                    <div className="flex flex-col justify-center w-32 shrink-0 border-r border-border/50">
                      <span className="font-mono text-[14px] font-bold">{maxT.toFixed(1)}°C</span>
                      <span className="font-mono text-[9px] opacity-70">MAX TEMP</span>
                    </div>

                    <div className="flex flex-col justify-center flex-1 min-w-0">
                      <span className="font-mono text-[10px] break-words">
                        LAT: {parseFloat(c.location?.lat || 0).toFixed(6)} · LON: {parseFloat(c.location?.lon || 0).toFixed(6)}
                      </span>
                      {c.notes && <span className="font-mono text-[9px] opacity-70 mt-1 truncate max-w-md">{c.notes}</span>}
                    </div>
                  </div>
                );
              })}
              
              {processedCaptures.length === 0 && (
                 <div className="p-10 text-center font-mono text-[11px] text-muted">NO CAPTURES MATCH SEARCH</div>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 w-full h-full relative z-0 flex flex-col min-h-[500px]">
            <OfflineMap captures={processedCaptures} />
          </div>
        )}
      </div>
    </div>
  );
}
