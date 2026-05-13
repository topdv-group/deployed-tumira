// 1. DOM Element Selectors
const phoneInput = document.getElementById('Phone');
const passwordInput = document.getElementById('Password');
const emailInput = document.getElementById('email');
const referralInput = document.getElementById('referal-input');
const signupButton = document.getElementById('loginBtn');
const errorMsg = document.getElementById('error');

// Create and add loading spinner to body
const loadingSpinner = document.createElement('div');
loadingSpinner.className = 'loading-spinner';
loadingSpinner.innerHTML = `
  <div class="spinner-overlay">
    <div class="spinner-content">
      <div class="spinner-circle"></div>
      <p id="spinnerMessage">Creating your account...</p>
    </div>
  </div>
`;
document.body.appendChild(loadingSpinner);

// Function to show/hide loading spinner
function showLoading(show, message = 'Processing...') {
  const messageElement = document.getElementById('spinnerMessage');
  if (messageElement) messageElement.textContent = message;
  loadingSpinner.style.display = show ? 'flex' : 'none';
  
  if (signupButton) {
    signupButton.disabled = show;
    signupButton.style.opacity = show ? '0.7' : '1';
  }
}

// 2. Real-time Input Filters
phoneInput.addEventListener('input', (e) => { 
  e.target.value = e.target.value.replace(/\D/g, '').slice(0, 9);
});

// 3. Validation Logic
signupButton.addEventListener('click', async () => {
  console.log("Processing form submission...");

  const phoneValue = phoneInput.value.trim();
  const passwordValue = passwordInput.value;
  const emailValue = emailInput.value.trim();
  const referralValue = referralInput.value.trim();

  if (phoneValue.length !== 9) {
    showFeedback("Phone number must be exactly 9 digits.", "red");
    return; 
  }

  if (passwordValue.trim() === "") {
    showFeedback("Please enter your password.", "red");
    return;
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(emailValue)) {
    showFeedback("Please enter a valid email address.", "red");
    return;
  }

  // Show loading spinner
  showLoading(true, "Creating your account...");

  const payload = {
    phone: phoneValue,
    password: passwordValue,
    email: emailValue,
    referralCode: referralValue || "None"
  };

  try {
    const response = await fetch('/api/register', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (data.status === "success") {
      showLoading(false);
      showFeedback("Registration successful! Redirecting to login...", "green");
      
      setTimeout(() => {
        clearFormFields();
        window.location.href = 'login.html';
      }, 2000);
    } else {
      showLoading(false);
      showFeedback("❌ " + data.message, "red");
    }
  } catch (error) {
    console.error("Network Error:", error);
    showLoading(false);
    showFeedback("server connect failed, is running on http://127.0.0.1:5000", "red");
  }
});

function showFeedback(text, color) {
  errorMsg.textContent = text;
  errorMsg.style.color = color;
  errorMsg.style.display = "block";
  setTimeout(() => {
    errorMsg.style.display = "none";
  }, 3000);
}

function clearFormFields() {
  phoneInput.value = "";
  passwordInput.value = "";
  emailInput.value = "";
  referralInput.value = "";
}
