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

  data.points.forEach((point) => {
    L.circleMarker([point.lat, point.lng], { radius: 5, color: '#1f77b4' })
      .addTo(layerGroup)
      .bindPopup(`<b>${point.category}</b><br>${point.street}<br>${point.month}<br>${point.outcome}`);
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
