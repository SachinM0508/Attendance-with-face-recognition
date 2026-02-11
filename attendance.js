// attendance.js - capture webcam frame and send to server to mark attendance

document.addEventListener("DOMContentLoaded", async () => {
  const video = document.getElementById("att-video");
  const canvas = document.getElementById("att-canvas");
  const captureBtn = document.getElementById("att-capture");
  let stream = null;

  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: true });
    video.srcObject = stream;
  } catch (e) {
    alert("Camera error: " + e.message);
    return;
  }

  captureBtn.addEventListener("click", async () => {
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    const data = canvas.toDataURL('image/png');
    // send to /api/mark_attendance
    const res = await fetch('/api/mark_attendance', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ image: data })
    });
    const result = await res.json();
    if (!result.success) {
      alert(result.message || "Server error");
      return;
    }
    // show matched students
    if (result.matched && result.matched.length > 0) {
      alert("Marked present: " + result.matched.map(m=>m.name).join(', '));
      loadAttendance();
    } else {
      alert(result.message || "No matches");
    }
  });

  loadAttendance();
});

async function loadAttendance(){
  const res = await fetch('/api/get_attendance');
  const rows = await res.json();
  const tbody = document.querySelector("#attendance-table tbody");
  tbody.innerHTML = "";
  rows.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.id}</td><td>${r.name||''}</td><td>${r.roll_no||''}</td><td>${r.date}</td><td>${r.time_in}</td><td>${r.status}</td>`;
    tbody.appendChild(tr);
  });
}

document.getElementById("exportCsv")?.addEventListener("click", () => {
  window.location.href = "/export_csv";
});
