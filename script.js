const texts = [
  "Welcome to the Secure Smart Attendance System",
  "Track Attendance with Face Recognition",
  "Easy, Fast, and Secure"
];
const typingElement = document.getElementById("typing-text");

let textIndex = 0;
let charIndex = 0;
let deleting = false;

function typeLoop() {
  const currentText = texts[textIndex];
  
  if (!deleting) {
    typingElement.textContent = currentText.substring(0, charIndex + 1);
    charIndex++;
    if (charIndex === currentText.length) {
      deleting = true;
      setTimeout(typeLoop, 1500); // pause before deleting
      return;
    }
  } else {
    typingElement.textContent = currentText.substring(0, charIndex - 1);
    charIndex--;
    if (charIndex === 0) {
      deleting = false;
      textIndex = (textIndex + 1) % texts.length; // move to next text
    }
  }
  
  setTimeout(typeLoop, deleting ? 50 : 100); // speed of delete/type
}

window.onload = typeLoop;
