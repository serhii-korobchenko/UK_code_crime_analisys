const form = document.getElementById('analysis-form');
const statusEl = document.getElementById('status');
const outPostcode = document.getElementById('out-postcode');
const outTotal = document.getElementById('out-total');
const outTop = document.getElementById('out-top');
const selectedPointsList = document.getElementById('selected-points-list');
const clearSelectedPointsButton = document.getElementById('clear-selected-points');

let categoryChart;
let monthlyChart;
const map = L.map('map').setView([51.5074, -0.1278], 11);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

let layerGroup = L.layerGroup().addTo(map);
let currentMapData = null;
let selectedMapCategory = 'all';
let categoryFilterSelect = null;
const selectedPointKeys = new Set();
const markerByPointKey = new Map();
const pointDetailsByKey = new Map();

function markerColorByFrequency(freq, maxFreq) {
  if (maxFreq <= 1) return '#1f77b4';
  const ratio = (freq - 1) / (maxFreq - 1);
  const hue = 120 - (120 * ratio); // 120=green, 0=red
  return `hsl(${hue}, 85%, 45%)`;
}

function buildPointKey(point, index) {
  return `${point.lat}|${point.lng}|${point.category}|${point.month}|${point.street}|${index}`;
}

function updateSelectedPointsList() {
  const selectedEntries = [...selectedPointKeys].map((key) => pointDetailsByKey.get(key)).filter(Boolean);
  selectedPointsList.innerHTML = '';

  if (!selectedEntries.length) {
    selectedPointsList.innerHTML = '<li>No points selected yet. Click map markers to select multiple incidents.</li>';
    return;
  }

  selectedEntries.forEach((point) => {
    const item = document.createElement('li');
    item.innerHTML = `<strong>${point.category}</strong> — ${point.street} (${point.month || 'n/a'})<br>Outcome: ${point.outcome}`;
    selectedPointsList.appendChild(item);
  });
}

function applyMarkerSelectionState(pointKey) {
  const marker = markerByPointKey.get(pointKey);
  if (!marker) return;

  if (selectedPointKeys.has(pointKey)) {
    marker.setStyle({ radius: 8, weight: 3, color: '#111', fillOpacity: 0.9 });
  } else {
    const baseColor = marker.options.baseColor || marker.options.color;
    marker.setStyle({ radius: 5, weight: 1, color: baseColor, fillColor: baseColor, fillOpacity: 0.7 });
  }
}

function initMapCategoryControl() {
  const CategoryControl = L.Control.extend({
    options: { position: 'topright' },
    onAdd() {
      const container = L.DomUtil.create('div', 'map-category-control');
      container.innerHTML = `
        <label for="map-category-filter"><strong>Category</strong></label>
        <select id="map-category-filter">
          <option value="all">All categories</option>
        </select>
      `;
      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.disableScrollPropagation(container);
      return container;
    },
  });

  map.addControl(new CategoryControl());
  categoryFilterSelect = document.getElementById('map-category-filter');
  categoryFilterSelect.addEventListener('change', () => {
    selectedMapCategory = categoryFilterSelect.value;
    if (currentMapData) renderMap(currentMapData, { preserveFilter: true });
  });
}

function updateCategoryFilterOptions(points) {
  if (!categoryFilterSelect) return;

  const categories = [...new Set(points.map((point) => point.category).filter(Boolean))].sort();
  const previousValue = selectedMapCategory;
  categoryFilterSelect.innerHTML = `<option value="all">All categories</option>${
    categories.map((category) => `<option value="${category}">${category}</option>`).join('')
  }`;

  selectedMapCategory = categories.includes(previousValue) || previousValue === 'all' ? previousValue : 'all';
  categoryFilterSelect.value = selectedMapCategory;
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

function renderMap(data, options = {}) {
  layerGroup.clearLayers();
  currentMapData = data;
  markerByPointKey.clear();
  pointDetailsByKey.clear();

  if (!options.preserveFilter) selectedMapCategory = 'all';
  updateCategoryFilterOptions(data.points);

  const center = [data.center.lat, data.center.lng];
  L.circle(center, { radius: data.radius, color: 'red', fillOpacity: 0.05 }).addTo(layerGroup);
  L.marker(center).addTo(layerGroup).bindPopup(`Center: ${data.postcode}`);

  const visiblePoints = data.points.filter(
    (point) => selectedMapCategory === 'all' || point.category === selectedMapCategory
  );

  const frequencyByPoint = new Map();
  visiblePoints.forEach((point) => {
    const key = `${point.lat.toFixed(5)},${point.lng.toFixed(5)}`;
    frequencyByPoint.set(key, (frequencyByPoint.get(key) || 0) + 1);
  });

  const maxFreq = Math.max(...frequencyByPoint.values(), 1);

  visiblePoints.forEach((point, index) => {
    const key = `${point.lat.toFixed(5)},${point.lng.toFixed(5)}`;
    const frequency = frequencyByPoint.get(key) || 1;
    const pointColor = markerColorByFrequency(frequency, maxFreq);
    const pointKey = buildPointKey(point, index);

    const marker = L.circleMarker([point.lat, point.lng], {
      radius: 5,
      color: pointColor,
      fillColor: pointColor,
      fillOpacity: 0.7,
      baseColor: pointColor,
    })
      .addTo(layerGroup)
      .bindPopup(
        `<b>${point.category}</b><br>${point.street}<br>${point.month}<br>${point.outcome}<br>Frequency at this point: ${frequency}`
      );

    markerByPointKey.set(pointKey, marker);
    pointDetailsByKey.set(pointKey, point);

    marker.on('click', () => {
      if (selectedPointKeys.has(pointKey)) {
        selectedPointKeys.delete(pointKey);
      } else {
        selectedPointKeys.add(pointKey);
      }
      applyMarkerSelectionState(pointKey);
      updateSelectedPointsList();
    });

    applyMarkerSelectionState(pointKey);
  });

  updateSelectedPointsList();
  map.fitBounds(L.circle(center, { radius: data.radius }).getBounds());
}

initMapCategoryControl();
updateSelectedPointsList();

clearSelectedPointsButton.addEventListener('click', () => {
  selectedPointKeys.clear();
  markerByPointKey.forEach((_, pointKey) => applyMarkerSelectionState(pointKey));
  updateSelectedPointsList();
});

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
