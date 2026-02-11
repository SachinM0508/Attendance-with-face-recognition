// static/js/student.js
let capturedPhoto = null;
let selectedStudentId = null;

document.addEventListener("DOMContentLoaded", () => {
  loadStudents();

  // Buttons
  const saveBtn = document.querySelector(".save");
  const updateBtn = document.querySelector(".update");
  const deleteBtn = document.querySelector(".delete");
  const resetBtn = document.querySelector(".reset");

  if (saveBtn) saveBtn.addEventListener("click", addStudent);
  if (updateBtn) updateBtn.addEventListener("click", updateStudent);
  if (deleteBtn) deleteBtn.addEventListener("click", deleteCurrentStudent);
  if (resetBtn) resetBtn.addEventListener("click", resetForm);

  const showAllBtn = document.getElementById("show-all-btn");
  if (showAllBtn) showAllBtn.addEventListener("click", loadStudents);

  const searchBtn = document.getElementById("search-btn");
  if (searchBtn) searchBtn.addEventListener("click", searchStudents);

  // Camera modal elements
  const modal = document.getElementById("camera-modal");
  const video = document.getElementById("video");
  const canvas = document.getElementById("canvas");
  const captureBtn = document.getElementById("capture-btn");
  const photoOutput = document.getElementById("photo-output");

  const openCameraBtn = document.getElementById("open-camera");
  const closeButtons = document.querySelectorAll(".close");

  let stream = null;

  async function startCamera() {
    if (!modal) return;
    modal.style.display = "block";
    photoOutput.innerHTML = "";

    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: true });
      video.srcObject = stream;
    } catch (e) {
      alert("Camera error: " + e.message);
      modal.style.display = "none";
    }
  }

  function stopCamera() {
    if (stream) {
      stream.getTracks().forEach(t => t.stop());
      stream = null;
    }
    video.srcObject = null;
  }

  function closeModal() {
    modal.style.display = "none";
    stopCamera();
  }

  // FIXED — proper camera open
  if (openCameraBtn) openCameraBtn.addEventListener("click", startCamera);

  closeButtons.forEach(c => c.addEventListener("click", closeModal));

  if (captureBtn) {
    captureBtn.addEventListener("click", () => {
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      capturedPhoto = canvas.toDataURL("image/png");

      photoOutput.innerHTML = `<img src="${capturedPhoto}" width="200" style="border-radius:8px;">`;
      stopCamera();
    });
  }
});

// ---------------------- Form Helpers ----------------------
async function collectFormData() {
  return {
    roll_no: document.getElementById("roll-no").value.trim(),
    name: document.getElementById("student-name").value.trim(),
    gender: document.getElementById("gender").value,
    dob: document.getElementById("dob").value,
    department: document.getElementById("department").value,
    year: document.getElementById("year").value,
    semester: document.getElementById("semester").value,
    class_div: document.getElementById("class-div").value,
    phone: document.getElementById("phone").value,
    email: document.getElementById("email").value,
    address: document.getElementById("address").value,
    guardian_name: document.getElementById("guardian-name").value,
    guardian_phone: document.getElementById("guardian-phone").value,
    photo: capturedPhoto
  };
}

// ---------------------- CRUD ----------------------
async function addStudent() {
  const payload = await collectFormData();
  if (!payload.name || !payload.roll_no) return alert("Name and Roll No required.");

  try {
    const res = await fetch("/api/add_student_with_photo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    alert(data.message);
    resetForm();
    loadStudents();
  } catch (e) {
    alert("Error: " + e.message);
  }
}

async function updateStudent() {
  if (!selectedStudentId) return alert("Select student first.");

  const payload = await collectFormData();

  try {
    const res = await fetch(`/api/update_student/${selectedStudentId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    alert(data.message);
    resetForm();
    loadStudents();
  } catch (e) {
    alert("Update failed: " + e.message);
  }
}

// FIXED — delete button now works properly
async function deleteCurrentStudent() {
  if (!selectedStudentId) return alert("Select student first.");
  if (!confirm("Are you sure?")) return;

  try {
    const res = await fetch(`/api/delete_student/${selectedStudentId}`, {
      method: "DELETE"
    });

    const data = await res.json();
    alert(data.message);
    resetForm();
    loadStudents();
  } catch (e) {
    alert("Delete failed: " + e.message);
  }
}

// ---------------------- Load Table ----------------------
async function loadStudents() {
  try {
    const res = await fetch("/api/get_students");
    const list = await res.json();

    const tbody = document.querySelector("#student-table tbody");
    tbody.innerHTML = "";

    list.forEach(s => {
      const photo = s.photo_path || "/static/images/face.jpg";

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><img src="${photo}" width="60" height="60" style="border-radius:8px; object-fit:cover;"></td>
        <td>${s.student_id}</td>
        <td>${s.roll_no || ''}</td>
        <td>${s.name}</td>
        <td>${s.department || ''}</td>
        <td>${s.gender || ''}</td>
        <td>${s.dob || ''}</td>
        <td>${s.phone || ''}</td>
        <td>${s.email || ''}</td>
        <td>${(s.address || '').slice(0, 40)}</td>
        <td>
          <button onclick="fillForm(${s.student_id})">Edit</button>
          <button onclick="deleteCurrentStudent()">Delete</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    alert("Load failed: " + e.message);
  }
}

async function fillForm(id) {
  const res = await fetch("/api/get_students");
  const list = await res.json();
  const s = list.find(x => x.student_id === id);
  if (!s) return;

  selectedStudentId = id;

  document.getElementById("student-id").value = s.student_id;
  document.getElementById("student-name").value = s.name;
  document.getElementById("gender").value = s.gender || "";
  document.getElementById("dob").value = s.dob || "";
  document.getElementById("department").value = s.department || "";
  document.getElementById("year").value = s.year || "";
  document.getElementById("semester").value = s.semester || "";
  document.getElementById("roll-no").value = s.roll_no || "";
  document.getElementById("class-div").value = s.class_div || "";
  document.getElementById("phone").value = s.phone || "";
  document.getElementById("email").value = s.email || "";
  document.getElementById("address").value = s.address || "";
  document.getElementById("guardian-name").value = s.guardian_name || "";
  document.getElementById("guardian-phone").value = s.guardian_phone || "";
}

function resetForm() {
  selectedStudentId = null;
  capturedPhoto = null;
  document.querySelectorAll(".left-panel input, .left-panel select, .left-panel textarea")
    .forEach(i => i.value = "");

  const photoOutput = document.getElementById("photo-output");
  if (photoOutput) photoOutput.innerHTML = "";
}

async function searchStudents() {
  const term = document.getElementById("search-input").value.toLowerCase();
  const by = document.getElementById("search-by").value;

  const res = await fetch("/api/get_students");
  const list = await res.json();

  const filtered = list.filter(s =>
    (s[by] || "").toString().toLowerCase().includes(term)
  );

  const tbody = document.querySelector("#student-table tbody");
  tbody.innerHTML = "";

  filtered.forEach(s => {
    const photo = s.photo_path || "/static/images/face.jpg";

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><img src="${photo}" width="60" height="60" style="border-radius:8px; object-fit:cover;"></td>
      <td>${s.student_id}</td>
      <td>${s.roll_no||''}</td>
      <td>${s.name}</td>
      <td>${s.department||''}</td>
      <td>${s.gender||''}</td>
      <td>${s.dob||''}</td>
      <td>${s.phone||''}</td>
      <td>${s.email||''}</td>
      <td>${s.address||''}</td>
      <td>
        <button onclick="fillForm(${s.student_id})">Edit</button>
        <button onclick="deleteCurrentStudent()">Delete</button>
      </td>`;
    tbody.appendChild(tr);
  });
}
