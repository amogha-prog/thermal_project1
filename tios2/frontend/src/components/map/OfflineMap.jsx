import React, { useEffect, useState, useMemo } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';
import localforage from 'localforage';
import 'leaflet/dist/leaflet.css';
import { useTIOSStore } from '../../store/useTIOSStore';

// ── Configuration & Caching ──────────────────────────────────────────────────

const DEFAULT_CENTER = [14.454500, 75.909180]; // Your Test Field
const GOOGLE_SATELLITE_URL = 'https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}';

const tileStore = localforage.createInstance({
  name: 'TIOS_Map_Cache',
  storeName: 'tiles'
});

// Custom Leaflet TileLayer that prioritizes IndexedDB cache for offline use
const OfflineTileLayer = L.TileLayer.extend({
  createTile: function (coords, done) {
    const tile = document.createElement('img');
    const url = this.getTileUrl(coords);
    
    tileStore.getItem(url).then(blob => {
      if (blob) {
        tile.src = URL.createObjectURL(blob);
        done(null, tile);
      } else {
        // Fetch and cache if not in DB
        fetch(url, { mode: 'cors' })
          .then(res => res.ok ? res.blob() : Promise.reject())
          .then(newBlob => {
            tileStore.setItem(url, newBlob).catch(() => {});
            tile.src = URL.createObjectURL(newBlob);
            done(null, tile);
          })
          .catch(() => {
            tile.src = url; // Fallback to live URL if fetch fails
            done(null, tile);
          });
      }
    }).catch(() => {
      tile.src = url;
      done(null, tile);
    });
    return tile;
  }
});

// Wrapper for react-leaflet to use our custom OfflineTileLayer
function OfflineTileLayerWrapper(props) {
  const map = useMap();
  useEffect(() => {
    const layer = new OfflineTileLayer(props.url, props);
    layer.addTo(map);
    return () => { layer.remove(); };
  }, [map, props.url]);
  return null;
}

// ── Drone Assets ─────────────────────────────────────────────────────────────

const DRONE_SVG = `
<svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M20 5L35 32L20 26L5 32L20 5Z" fill="#00e5ff" stroke="white" stroke-width="2" stroke-linejoin="round"/>
  <circle cx="20" cy="18" r="3" fill="white" />
</svg>
`;

function MapAutoCenter({ center }) {
  const map = useMap();
  useEffect(() => {
    // Only auto-center if the drone has a valid non-zero GPS signal
    if (center && center[0] !== 0 && center[1] !== 0) {
      map.setView(center, map.getZoom());
    }
  }, [center, map]);
  return null;
}

// ── Main Component ───────────────────────────────────────────────────────────

export default function OfflineMap({ captures }) {
  const { telemetry, flightPath } = useTIOSStore();
  const [mapReady, setMapReady] = useState(false);

  // Use drone position if valid, otherwise field default
  const hasGps = telemetry.lat !== 0 && telemetry.lon !== 0;
  const mapCenter = hasGps ? [telemetry.lat, telemetry.lon] : DEFAULT_CENTER;
  
  const droneIcon = L.divIcon({
    className: 'drone-marker-container',
    html: `<div style="transform: rotate(${telemetry.heading}deg); transition: transform 0.2s ease-out; width: 40px; height: 40px;">${DRONE_SVG}</div>`,
    iconSize: [40, 40],
    iconAnchor: [20, 20],
  });

  return (
    <div className="w-full h-full relative" style={{ minHeight: '500px' }}>
      <MapContainer
        center={mapCenter}
        zoom={17}
        className="w-full h-full bg-[#0c142c]"
        zoomControl={false}
        attributionControl={false}
        whenReady={() => setMapReady(true)}
      >
        <OfflineTileLayerWrapper url={GOOGLE_SATELLITE_URL} maxZoom={20} />

        <Polyline 
          positions={flightPath} 
          pathOptions={{ color: '#00e5ff', weight: 3, opacity: 0.7, dashArray: '5, 10' }} 
        />

        {hasGps && (
          <Marker position={mapCenter} icon={droneIcon}>
            <Popup>
              <div className="font-mono text-[11px] text-black">
                <b className="text-[#005cbb]">DRONE-01</b><br/>
                ALT: {telemetry.alt.toFixed(1)}m | HDG: {telemetry.heading}°
              </div>
            </Popup>
          </Marker>
        )}

        {captures?.map((c) => {
          const lat = parseFloat(c?.location?.lat);
          const lon = parseFloat(c?.location?.lon);
          if (isNaN(lat) || isNaN(lon) || (lat === 0 && lon === 0)) return null;
          return (
            <Marker key={c.id} position={[lat, lon]}>
              <Popup>
                <div className="font-mono text-[11px] text-black"><b>CAPTURE {c.id}</b></div>
              </Popup>
            </Marker>
          );
        })}

        <MapAutoCenter center={hasGps ? mapCenter : null} />
      </MapContainer>

      {/* GCS UI Overlays */}
      <div className="absolute bottom-6 right-6 z-[1000] flex flex-col gap-2 pointer-events-auto">
        {!hasGps && (
          <div className="bg-red-900/80 backdrop-blur-md border border-red-500/50 rounded-lg p-3 shadow-2xl animate-pulse">
            <span className="text-[10px] text-white font-mono font-bold tracking-widest">NO DRONE GPS SIGNAL</span>
            <div className="text-[9px] text-red-200 mt-1 uppercase">Centering on Test Field</div>
          </div>
        )}
        <div className="bg-black/80 backdrop-blur-md border border-accent/30 rounded-lg p-3 shadow-2xl">
          <div className="flex flex-col gap-1">
            <span className="text-[9px] text-muted font-bold uppercase tracking-widest">Mapping System</span>
            <span className="text-[11px] text-accent font-mono uppercase">HYBRID OFFLINE CACHE</span>
          </div>
        </div>
      </div>

      {!mapReady && (
        <div className="absolute inset-0 flex items-center justify-center bg-[#0c142c] z-[1]">
          <span className="font-mono text-[11px] text-muted animate-pulse tracking-[0.2em]">BOOTING OFFLINE GCS CORE...</span>
        </div>
      )}
    </div>
  );
}
