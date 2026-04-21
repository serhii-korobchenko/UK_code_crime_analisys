const form = document.getElementById('analysis-form');
const statusEl = document.getElementById('status');
const outPostcode = document.getElementById('out-postcode');
const outTotal = document.getElementById('out-total');
const outTop = document.getElementById('out-top');

let categoryChart;
let monthlyChart;
const map = L.map('map').setView([51.5074, -0.1278], 11);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

let layerGroup = L.layerGroup().addTo(map);

function markerColorByFrequency(freq, maxFreq) {
  if (maxFreq <= 1) return '#1f77b4';
  const ratio = (freq - 1) / (maxFreq - 1);
  const hue = 120 - (120 * ratio); // 120=green, 0=red
  return `hsl(${hue}, 85%, 45%)`;
}

function renderCharts(data) {
  const categoryLabels = Object.keys(data.all_categories);
  const categoryValues = Object.values(data.all_categories);
  const monthlyLabels = Object.keys(data.monthly_counts);
  const monthlyValues = Object.values(data.monthly_counts);

  categoryChart?.destroy();
  monthlyChart?.destroy();

  categoryChart = new Chart(document.getElementById('categoryChart'), {
    type: 'bar',
    data: {
      labels: categoryLabels,
      datasets: [{ label: 'Crimes by category', data: categoryValues }]
    }
  });

  monthlyChart = new Chart(document.getElementById('monthlyChart'), {
    type: 'line',
    data: {
      labels: monthlyLabels,
      datasets: [{ label: 'Crimes by month', data: monthlyValues, fill: false }]
    }
  });
}

function renderMap(data) {
  layerGroup.clearLayers();

  const center = [data.center.lat, data.center.lng];
  L.circle(center, { radius: data.radius, color: 'red', fillOpacity: 0.05 }).addTo(layerGroup);
  L.marker(center).addTo(layerGroup).bindPopup(`Center: ${data.postcode}`);

  const frequencyByPoint = new Map();
  data.points.forEach((point) => {
    const key = `${point.lat.toFixed(5)},${point.lng.toFixed(5)}`;
    frequencyByPoint.set(key, (frequencyByPoint.get(key) || 0) + 1);
  });

  const maxFreq = Math.max(...frequencyByPoint.values(), 1);

  data.points.forEach((point) => {
    const key = `${point.lat.toFixed(5)},${point.lng.toFixed(5)}`;
    const frequency = frequencyByPoint.get(key) || 1;
    const pointColor = markerColorByFrequency(frequency, maxFreq);

    L.circleMarker([point.lat, point.lng], { radius: 5, color: pointColor, fillColor: pointColor, fillOpacity: 0.7 })
      .addTo(layerGroup)
      .bindPopup(
        `<b>${point.category}</b><br>${point.street}<br>${point.month}<br>${point.outcome}<br>Frequency at this point: ${frequency}`
      );
  });

  map.fitBounds(L.circle(center, { radius: data.radius }).getBounds());
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  statusEl.textContent = 'Loading...';

  try {
    const startMonth = document.getElementById('start-month').value;
    const endMonth = document.getElementById('end-month').value;
    const payload = {
      postcode: document.getElementById('postcode').value,
      radius: Number(document.getElementById('radius').value),
      start_month: startMonth || undefined,
      end_month: endMonth || undefined,
    };

    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Request failed');

    outPostcode.textContent = data.postcode;
    outTotal.textContent = data.total_crimes;
    const top = data.top_categories[0];
    outTop.textContent = top ? `${top.name} (${top.count})` : 'No data';

    renderCharts(data);
    renderMap(data);
    const period = data.period?.start_month && data.period?.end_month
      ? ` for ${data.period.start_month} — ${data.period.end_month}`
      : '';
    statusEl.textContent = `Done. Found ${data.total_crimes} incidents${period}.`;
  } catch (error) {
    statusEl.textContent = error.message;
  }
});
