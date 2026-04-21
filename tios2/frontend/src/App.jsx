/**
 * TIOS App — Root Component
 *
 * Storage philosophy:
 *   - All captures live in Zustand (React memory) for the session
 *   - Individual images → saved to user's Downloads via browser API
 *   - PDF report       → saved to user's Downloads via browser API
 *   - Zero server calls for storage — everything is local
 *
 * Layout:
 *   ┌───────────────────────────── TopBar ─────────────────────────────┐
 *   │  ┌─────────────────────────────┐  ┌──────────────────────────┐  │
 *   │  │   VideoPanel (Thermal)      │  │                          │  │
 *   │  │                             │  │   TelemetrySidebar       │  │
 *   │  │   VideoPanel (RGB)          │  │                          │  │
 *   │  └─────────────────────────────┘  └──────────────────────────┘  │
 *   └───────────────────────────── ScanBar ────────────────────────────┘
 */

import React, { useRef, useCallback } from 'react';

import TopBar           from './components/TopBar.jsx';
import SideNav          from './components/SideNav.jsx';
import VideoPanel       from './components/video/VideoPanel.jsx';
import OfflineMap       from './components/map/OfflineMap.jsx';
import TelemetrySidebar from './components/telemetry/TelemetrySidebar.jsx';
import ScanBar          from './components/ScanBar.jsx';
import CaptureModal     from './components/capture/CaptureModal.jsx';
import ToastContainer   from './components/ToastContainer.jsx';
import CaptureBrowserModal from './components/capture/CaptureBrowserModal.jsx';

import { useTIOSStore }   from './store/useTIOSStore.js';
import { useSocket }      from './hooks/useSocket.js';
import {
  captureFrame,
  captureThumbnail,
  buildCaptureUnit,
  saveAllImagesLocally,
} from './utils/captureEngine.js';
import { generateInspectionReport } from './utils/pdfGenerator.js';

// App component

export default function App() {
  // Establish Socket.io connection → feeds telemetry into Zustand store
  useSocket();

  // Canvas refs for both video panels — used by captureFrame()
  const thermalRef = useRef(null);
  const rgbRef     = useRef(null);

  // Modal states
  const [showBrowser, setShowBrowser] = React.useState(false);
  const [mobileTelemOpen, setMobileTelemOpen] = React.useState(false);

  // Store selectors
  const telemetry     = useTIOSStore((s) => s.telemetry);
  const missionId     = useTIOSStore((s) => s.missionId);
  const missionName   = useTIOSStore((s) => s.missionName);
  const operatorName  = useTIOSStore((s) => s.operatorName);
  const captures      = useTIOSStore((s) => s.captures);
  const feedsSwapped  = useTIOSStore((s) => s.feedsSwapped);
  const addCapture    = useTIOSStore((s) => s.addCapture);
  const addToast      = useTIOSStore((s) => s.addToast);
  const selectedId    = useTIOSStore((s) => s.selectedCapture);
  const setSelectedId = useTIOSStore((s) => s.setSelectedCapture);
  const activeTab     = useTIOSStore((s) => s.activeTab);

  // ── CAPTURE ────────────────────────────────────────────────────────────────
  // Grabs both canvas frames + telemetry in the same event-loop tick.
  // The result is stored in Zustand only — no network call.
  const handleCapture = useCallback(() => {
    // Account for feed swap
    const tCanvas = feedsSwapped ? rgbRef    : thermalRef;
    const rCanvas = feedsSwapped ? thermalRef : rgbRef;

    const thermalFrame = captureFrame(tCanvas);
    const rgbFrame     = captureFrame(rCanvas);

    if (!thermalFrame || !rgbFrame) {
      addToast('Canvas not ready — try again', 'warn');
      return;
    }

    const unit = buildCaptureUnit({
      thermalFrame,
      rgbFrame,
      thermalThumb: captureThumbnail(tCanvas),
      rgbThumb:     captureThumbnail(rCanvas),
      telemetry:    { ...telemetry },       // snapshot frozen at this exact millisecond
      missionId,
      index: captures.length + 1,
    });

    addCapture(unit);
    addToast(`Captured ${unit.id}`, 'success');
  }, [telemetry, missionId, captures.length, feedsSwapped, addCapture, addToast]);

  // ── SAVE IMAGES ───────────────────────────────────────────────────────────
  // Downloads the most recent capture's thermal + RGB as JPEG files
  // directly to the user's local Downloads folder.
  const handleSaveImages = useCallback(() => {
    if (!captures.length) {
      addToast('No captures yet', 'warn');
      return;
    }
    const latest = captures[captures.length - 1];
    saveAllImagesLocally(latest);
    addToast(`Saving images for ${latest.id}`, 'info');
  }, [captures, addToast]);

  // ── GENERATE PDF ──────────────────────────────────────────────────────────
  // Builds the full inspection report and triggers a browser download.
  // Runs entirely in the browser — no server involved.
  const handleGeneratePDF = useCallback(async () => {
    if (!captures.length) {
      addToast('No captures to export', 'warn');
      return;
    }
    try {
      addToast('Building PDF report…', 'info');
      const filename = await generateInspectionReport(captures, {
        missionId,
        missionName,
        operatorName,
      });
      addToast(`PDF saved: ${filename}`, 'success');
    } catch (err) {
      console.error('[PDF]', err);
      addToast('PDF generation failed', 'error');
    }
  }, [captures, missionId, missionName, operatorName, addToast]);
  // ── EXPORT CSV ────────────────────────────────────────────────────────────
  const handleExportCSV = useCallback(() => {
    if (!captures.length) {
      addToast('No captures to export', 'warn');
      return;
    }
    // dynamic import so it doesn't block main bundle if not used
    import('./utils/csvExport.js').then((m) => {
      m.exportCapturesCSV(captures);
      addToast('CSV exported!', 'success');
    });
  }, [captures, addToast]);

  // Resolve which canvas ref maps to which panel after possible swap
  const leftRef   = feedsSwapped ? rgbRef     : thermalRef;
  const rightRef  = feedsSwapped ? thermalRef : rgbRef;
  const leftType  = feedsSwapped ? 'rgb'      : 'thermal';
  const rightType = feedsSwapped ? 'thermal'  : 'rgb';

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-bg">

      {/* ── Mobile telemetry toggle button (visible < lg only) ──────── */}
      <button
        onClick={() => setMobileTelemOpen(true)}
        className="lg:hidden fixed bottom-20 right-3 z-[1050] w-11 h-11 rounded-full
                   bg-accent/90 text-white shadow-lg shadow-accent/30
                   flex items-center justify-center hover:bg-accent transition-all active:scale-90"
        title="Open Telemetry"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
        </svg>
      </button>

      {/* ── Top bar ─────────────────────────────────────────────────────── */}
      <TopBar
        onCapture={handleCapture}
        onSaveImages={handleSaveImages}
        onGeneratePDF={handleGeneratePDF}
        onExportCSV={handleExportCSV}
        captureCount={captures.length}
      />

      {/* ── Main content ────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        
        {/* New Navigation Sidebar */}
        <SideNav />

        {/* Dynamic Content Area: Dashboard (Video) or Map */}
        <div className="flex-1 overflow-hidden relative">
          {activeTab === 'dashboard' ? (
            <div className="flex flex-col lg:grid lg:grid-cols-2 gap-px bg-border h-full overflow-y-auto lg:overflow-hidden">
              <div className="h-[50vh] lg:h-full"><VideoPanel ref={leftRef}  type={leftType} /></div>
              <div className="h-[50vh] lg:h-full"><VideoPanel ref={rightRef} type={rightType} /></div>
            </div>
          ) : (
            <OfflineMap captures={captures} />
          )}
        </div>

        {/* Telemetry sidebar */}
        <TelemetrySidebar 
          onSelectCapture={setSelectedId} 
          onShowBrowser={() => setShowBrowser(true)}
          mobileOpen={mobileTelemOpen}
          onCloseMobile={() => setMobileTelemOpen(false)}
        />
      </div>

      {/* ── Bottom scan bar ──────────────────────────────────────────────── */}
      <div className="hidden md:block">
        <ScanBar />
      </div>

      {/* ── Capture detail modal ─────────────────────────────────────────── */}
      {selectedId && (
        <CaptureModal
          captureId={selectedId}
          onClose={() => setSelectedId(null)}
        />
      )}

      {/* ── Capture browser modal ────────────────────────────────────────── */}
      {showBrowser && (
        <CaptureBrowserModal onClose={() => setShowBrowser(false)} />
      )}

      {/* ── Toast notifications ──────────────────────────────────────────── */}
      <ToastContainer />
    </div>
  );
}
