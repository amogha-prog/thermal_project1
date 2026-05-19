export function exportCapturesCSV(captures) {
  if (!captures || captures.length === 0) return;

  // CSV Headers
  const headers = [
    'Capture ID',
    'Timestamp',
    'Latitude',
    'Longitude',
    'Altitude (m)',
    'Max Temp (°C)',
    'Avg Temp (°C)',
    'Severity',
    'Flight Mode'
  ].join(',');

  // CSV Rows
  const rows = captures.map(c => {
    const maxT = parseFloat(c.telemetry?.maxTemp || 0);
    const sev = maxT > 70 ? 'CRITICAL' : maxT > 50 ? 'WARNING' : maxT > 35 ? 'ELEVATED' : 'NORMAL';

    return [
      c.id,
      c.timestamp || '',
      parseFloat(c.location?.lat || 0).toFixed(6),
      parseFloat(c.location?.lon || 0).toFixed(6),
      parseFloat(c.location?.alt || 0).toFixed(2),
      maxT.toFixed(1),
      parseFloat(c.telemetry?.avgTemp || 0).toFixed(1),
      sev,
      c.telemetry?.flightMode || ''
    ].join(',');
  });

  const csvContent = [headers, ...rows].join('\n');
  
  // Trigger download
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', `TIOS_Export_${new Date().toISOString().slice(0, 10)}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
