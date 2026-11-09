// SmartGram Map Services (Leaflet.js & OpenStreetMap)

// 1. Initialize Public Problem Map
function initPublicProblemMap(containerId, complaintsData, defaultLat = 25.2818, defaultLng = 82.9739, defaultZoom = 12) {
  const map = L.map(containerId).setView([defaultLat, defaultLng], defaultZoom);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors | SmartGram'
  }).addTo(map);

  const markers = [];

  const icons = {
    'Resolved': L.icon({
      iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
      shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
      iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
    }),
    'In Progress': L.icon({
      iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png',
      shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
      iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
    }),
    'Assigned': L.icon({
      iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-yellow.png',
      shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
      iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
    }),
    'Pending': L.icon({
      iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
      shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
      iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
    })
  };

  complaintsData.forEach(c => {
    if (c.latitude && c.longitude) {
      const icon = icons[c.status] || icons['Pending'];
      const marker = L.marker([c.latitude, c.longitude], { icon: icon }).addTo(map);

      const popupContent = `
        <div style="font-family: sans-serif; font-size: 13px; line-height: 1.4; min-width: 200px;">
          <div style="font-size: 11px; font-weight: bold; color: #1e3a8a; margin-bottom: 2px;">
            ${c.tracking_id} • ${c.panchayat_name || 'Gram Panchayat'}
          </div>
          <strong style="font-size: 13px; color: #0f172a;">${c.title}</strong>
          <div style="margin: 6px 0;">
            <span style="display:inline-block; padding: 2px 6px; font-size: 10px; font-weight: bold; border-radius: 4px; background: #e2e8f0; color: #334155;">
              ${c.category}
            </span>
            <span style="display:inline-block; padding: 2px 6px; font-size: 10px; font-weight: bold; border-radius: 4px; background: ${c.status === 'Resolved' ? '#dcfce7' : (c.status === 'In Progress' ? '#dbeafe' : '#fef3c7')}; color: ${c.status === 'Resolved' ? '#166534' : (c.status === 'In Progress' ? '#1e40af' : '#92400e')};">
              ${c.status}
            </span>
          </div>
          <div style="color: #64748b; font-size: 11px; margin-bottom: 8px;">
            ${c.location_address || 'Village area'}
          </div>
          <a href="/complaint/${c.id}" class="btn btn-sm btn-primary" style="display: inline-block; padding: 4px 8px; font-size: 11px; color: white; background: #1e3a8a; border-radius: 4px; text-decoration: none;">
            View Details & Progress &rarr;
          </a>
        </div>
      `;
      marker.bindPopup(popupContent);
      markers.push(marker);
    }
  });

  if (markers.length > 0) {
    const group = new L.featureGroup(markers);
    map.fitBounds(group.getBounds().pad(0.15));
  }

  return map;
}

// 2. Location Picker for Complaint Submission
function initComplaintLocationPicker(mapContainerId, latInputId, lngInputId, addressInputId, initialLat = 25.2818, initialLng = 82.9739) {
  const map = L.map(mapContainerId).setView([initialLat, initialLng], 13);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap'
  }).addTo(map);

  let currentMarker = null;

  function updateMarker(lat, lng) {
    if (currentMarker) {
      currentMarker.setLatLng([lat, lng]);
    } else {
      currentMarker = L.marker([lat, lng], { draggable: true }).addTo(map);
      currentMarker.on('dragend', function(e) {
        const position = currentMarker.getLatLng();
        setCoords(position.lat, position.lng);
      });
    }
    setCoords(lat, lng);
  }

  function setCoords(lat, lng) {
    document.getElementById(latInputId).value = lat.toFixed(6);
    document.getElementById(lngInputId).value = lng.toFixed(6);
    
    // Optional reverse geocoding via OpenStreetMap Nominatim
    const addressInput = document.getElementById(addressInputId);
    if (addressInput && !addressInput.value) {
      fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`)
        .then(res => res.json())
        .then(data => {
          if (data && data.display_name) {
            addressInput.value = data.display_name.split(',').slice(0, 3).join(',');
          }
        })
        .catch(err => console.log("Nominatim reverse geocode error:", err));
    }
  }

  map.on('click', function(e) {
    updateMarker(e.latlng.lat, e.latlng.lng);
  });

  // GPS Geolocation button
  const gpsBtn = document.getElementById("useGpsBtn");
  if (gpsBtn) {
    gpsBtn.addEventListener("click", function() {
      if (navigator.geolocation) {
        gpsBtn.innerText = "Locating GPS...";
        navigator.geolocation.getCurrentPosition(
          function(pos) {
            const userLat = pos.coords.latitude;
            const userLng = pos.coords.longitude;
            map.setView([userLat, userLng], 15);
            updateMarker(userLat, userLng);
            gpsBtn.innerText = "GPS Location Detected ✓";
          },
          function(err) {
            alert("Unable to retrieve your location: " + err.message);
            gpsBtn.innerText = "Use Current GPS Location";
          }
        );
      } else {
        alert("Geolocation is not supported by your browser.");
      }
    });
  }

  return map;
}
