// Shared helper: ask the browser for the user's location and remember it in the
// Flask session (see app/location.py). Call it only after a user action.

// Resolves to {latitude, longitude, accuracy} or null. Never rejects.
async function requestUserLocation() {
  var meta = document.querySelector('meta[name="csrf-token"]');
  var token = meta ? meta.content : '';
  var headers = { 'Content-Type': 'application/json', 'X-CSRFToken': token };

  var position = await new Promise(function (resolve) {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(resolve, function () { resolve(null); },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 });
  });

  if (!position) {
    // Forget any older location so the server never uses a stale one.
    try { await fetch('/location', { method: 'DELETE', headers: headers }); } catch (e) {}
    return null;
  }

  var location = {
    latitude: position.coords.latitude,
    longitude: position.coords.longitude,
    accuracy: position.coords.accuracy
  };
  try {
    var response = await fetch('/location', {
      method: 'POST', headers: headers, body: JSON.stringify(location)
    });
    // A CSRF failure redirects to an HTML page (200), so only 204 counts.
    return response.status === 204 ? location : null;
  } catch (e) {
    return null;
  }
}
