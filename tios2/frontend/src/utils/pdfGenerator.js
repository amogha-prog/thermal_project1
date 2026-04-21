/**
 * TIOS PDF Generator — Backend report trigger
 *
 * This function triggers the Python generate_report.py script on the backend,
 * which formats the report using ReportLab, and then downloads it.
 */

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || `http://${window.location.hostname}:4000`;

/**
 * Triggers the backend to generate the PDF report using the Python pipeline 
 * and downloads it.
 */
export async function generateInspectionReport(captures, meta = {}) {
  // We hit the backend /api/report/generate endpoint
  const res = await fetch(`${BACKEND_URL}/api/report/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ captures, missionId: meta.missionId })
  });
  
  if (!res.ok) {
    let err = 'Server error';
    try {
      const data = await res.json();
      err = data.error || err;
    } catch (e) {}
    throw new Error(err);
  }

  // The backend streams the PDF blob
  const blob = await res.blob();
  if (blob.size === 0) throw new Error('Empty PDF file returned');

  // Trigger browser download
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  
  // Format filename with date
  const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  a.download = `TIOS_Mission_Report_${ts}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  
  return a.download;
}
