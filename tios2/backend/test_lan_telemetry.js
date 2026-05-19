/**
 * Test script to simulate LAN wire telemetry
 * Sends a UDP packet to localhost:14555
 */

const dgram = require('dgram');
const client = dgram.createSocket('udp4');

const data = {
  lat: 14.4547222,
  lon: 75.9088691,
  alt: 612.06,
  roll: 0.0038001947104930878,
  pitch: 0.014238245785236359,
  yaw: 3.0493319034576416,
  battery_voltage: 22.4, // Changed to a realistic 6S value for testing
  system_timestamp_utc: 1775657977.1558697
};

// Send as a string with single quotes (as seen in user sample)
const message = JSON.stringify(data).replace(/"/g, "'");

client.send(message, 14555, 'localhost', (err) => {
  if (err) {
    console.error('Error sending UDP packet:', err);
  } else {
    console.log('LAN Telemetry packet sent to localhost:14555');
    console.log('Data:', message);
  }
  client.close();
});
