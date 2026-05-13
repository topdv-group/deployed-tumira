// login.js - COMPLETE FIXED VERSION
const phoneInput = document.getElementById('Phone');
const passwordInput = document.getElementById('Password');
const loginButton = document.getElementById('loginBtn');
const errorMsg = document.getElementById('error');

// Create and add loading spinner
const loadingSpinner = document.createElement('div');
loadingSpinner.className = 'loading-spinner';
loadingSpinner.innerHTML = `
  <div class="spinner-overlay">
    <div class="spinner-content">
      <div class="spinner-circle"></div>
      <p id="spinnerMessage">Verifying credentials...</p>
    </div>
  </div>
`;
document.body.appendChild(loadingSpinner);

// Function to show/hide loading spinner
function showLoading(show, message = 'Processing...') {
  const messageElement = document.getElementById('spinnerMessage');
  if (messageElement) messageElement.textContent = message;
  loadingSpinner.style.display = show ? 'flex' : 'none';
  
  if (loginButton) {
    loginButton.disabled = show;
    loginButton.style.opacity = show ? '0.7' : '1';
    loginButton.style.cursor = show ? 'not-allowed' : 'pointer';
  }
}

// Show error message
function showError(message) {
  errorMsg.textContent = message;
  errorMsg.style.color = "red";
  errorMsg.style.display = "block";
  setTimeout(() => {
    errorMsg.style.display = "none";
  }, 3000);
}

// Show success message
function showSuccess(message) {
  errorMsg.textContent = message;
  errorMsg.style.color = "#28a745";
  errorMsg.style.display = "block";
  setTimeout(() => {
    errorMsg.style.display = "none";
  }, 2000);
}

// Load user dashboard and redirect to ui.html
function loadUserDashboard(userData) {
  console.log("Loading dashboard for user:", userData);
  
  // Store user data in session storage
  sessionStorage.setItem('loggedInUser', JSON.stringify(userData));
  sessionStorage.setItem('userPhone', userData.phone);
  sessionStorage.setItem('userEmail', userData.email);
  sessionStorage.setItem('loginTime', Date.now().toString());
  
  // Redirect to ui.html - USE CORRECT PATH
  window.location.href = 'ui.html';  // Changed from '../UI/ui.html'
}

// Check if already logged in
function checkExistingLogin() {
  const savedUser = sessionStorage.getItem('loggedInUser');
  if (savedUser) {
    console.log("Found existing login, redirecting to dashboard");
    window.location.href = 'ui.html';
    return true;
  }
  return false;
}

// Login validation and authentication
loginButton.addEventListener('click', async () => {
  console.log("Login button clicked!"); 

  const phoneValue = phoneInput.value.trim();
  const passwordValue = passwordInput.value;

  console.log("Phone:", phoneValue);
  console.log("Password:", passwordValue);

  // Validation
  if (phoneValue.length !== 9) {
    showError("Phone number must be exactly 9 digits.");
    return; 
  }

  if (passwordValue.trim() === "") {
    showError("Please enter your password.");
    return;
  }

  showLoading(true, "Verifying credentials...");

  try {
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        phone: phoneValue,
        password: passwordValue
      })
    });

    const data = await response.json();

    if (response.status === 200 && data.status === 'success') {
      console.log("Login successful!", data.user);
      showSuccess("✅ Login successful! Loading dashboard...");
      
      setTimeout(() => {
        loadUserDashboard(data.user);
      }, 1000);
    } else {
      showLoading(false);
      showError(data.message || "Invalid phone number or password");
    }
  } catch (error) {
    console.error("Network Error:", error);
    showLoading(false);
    showError("Failed to connect to server. Please check if Flask is running on http://127.0.0.1:5000");
  }
});

// Allow Enter key to submit
passwordInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    loginButton.click();
  }
});

phoneInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    loginButton.click();
  }
});

// Restrict phone input to numbers only
phoneInput.addEventListener('input', (e) => {
  e.target.value = e.target.value.replace(/\D/g, '').slice(0, 9);
});

// Check for existing login on page load
document.addEventListener('DOMContentLoaded', () => {
  checkExistingLogin();
});
