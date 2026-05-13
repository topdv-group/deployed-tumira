// ---------- CONFIGURATION ----------
const API_BASE = 'http://127.0.0.1:5000';
const STARTUP_FEE = 2000;
let currentUser = null;        // { phone, email, paid, referralId, totalEarned, referrals }
let pollingInterval = null;
let paymentCheckInterval = null;

// Helper: show/hide loader
function showLoader(show, message = "Processing...") {
    const loaderDiv = document.getElementById('globalLoader');
    const msgSpan = document.getElementById('loaderMsg');
    if (msgSpan) msgSpan.innerText = message;
    if (loaderDiv) loaderDiv.style.visibility = show ? 'visible' : 'hidden';
}

// Toast notification
function showToast(message, isError = false) {
    const toast = document.createElement('div');
    toast.className = 'toast-msg';
    toast.style.backgroundColor = isError ? '#dc2626' : '#059669';
    toast.style.color = 'white';
    toast.style.padding = '12px 24px';
    toast.style.borderRadius = '50px';
    toast.style.fontWeight = '500';
    toast.style.zIndex = '10000';
    toast.innerText = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Generate random referral ID (8 characters, alphanumeric)
function generateRandomReferralId() {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789';
    let result = '';
    for (let i = 0; i < 8; i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
}

// Copy referral code to clipboard
function copyReferralCode(code) {
    if (!code) {
        showToast("No referral code available. Please complete payment first.", true);
        return;
    }
    navigator.clipboard.writeText(code).then(() => {
        showToast(`✅ Referral ID "${code}" copied! Share to earn 5,000 FRW per referral.`);
    }).catch(() => {
        showToast("❌ Could not copy. Please select and copy manually.", true);
    });
}

// Update UI based on payment status
function updateUIForPaidStatus(isPaid, referralIdFromDb = null) {
    const referralIdSpan = document.getElementById('referralIdValue');
    const lockIconSpan = document.getElementById('lockIcon');
    const dynamicArea = document.getElementById('dynamicReferralArea');
    const paymentStatusSpan = document.getElementById('paymentStatusRender');
    const payButton = document.getElementById('payNowActionBtn');
    const badgeFlag = document.getElementById('paymentFlagBadge');
    const paymentSection = document.getElementById('paymentBlock');
    
    if (isPaid && referralIdFromDb) {
        // PAID USER - Show everything
        if (referralIdSpan) {
            referralIdSpan.innerText = referralIdFromDb;
            referralIdSpan.classList.remove('blurred-id');
            referralIdSpan.classList.add('revealed');
        }
        if (lockIconSpan) lockIconSpan.innerHTML = '🔓 unlocked';
        
        // Build shareable referral UI
        if (dynamicArea) {
            dynamicArea.innerHTML = `
                <div class="code-area">
                    <span class="ref-code-text" id="liveReferralCode">${referralIdFromDb}</span>
                    <button class="copy-btn-sm" id="copyRefBtn">
                        📋 Copy ID
                    </button>
                </div>
                <p style="font-size: 12px; color: #059669; margin-top: 12px;">
                    ✅ Active: Share this code & earn <strong>5,000 FRW</strong> per referral
                </p>
                <p style="font-size: 11px; color: #6b7280; margin-top: 8px;">
                    💡 Each friend who joins using your code and pays activation fee earns you 5,000 FRW
                </p>
            `;
            const copyBtn = document.getElementById('copyRefBtn');
            if (copyBtn) {
                copyBtn.onclick = () => copyReferralCode(referralIdFromDb);
            }
        }
        
        // Update payment section
        if (paymentStatusSpan) {
            paymentStatusSpan.innerHTML = '<span class="badge-status badge-paid">✅ Activated · Fully Unlocked</span>';
        }
        if (payButton) {
            payButton.disabled = true;
            payButton.innerText = '✓ Startup Fee Paid';
            payButton.style.opacity = '0.6';
            payButton.style.cursor = 'not-allowed';
        }
        if (badgeFlag) {
            badgeFlag.innerText = 'Active Member';
            badgeFlag.className = 'badge-status badge-paid';
        }
        if (paymentSection) {
            paymentSection.style.borderColor = '#10b981';
            paymentSection.style.background = '#f0fdf4';
        }
    } else {
        // UNPAID USER - Hide referral ID, show paywall
        if (referralIdSpan) {
            referralIdSpan.innerText = '●●●●●●●●';
            referralIdSpan.classList.add('blurred-id');
            referralIdSpan.classList.remove('revealed');
        }
        if (lockIconSpan) lockIconSpan.innerHTML = '🔒 locked';
        
        // Show paywall message
        if (dynamicArea) {
            dynamicArea.innerHTML = `
                <div class="hidden-badge">
                     Referral ID Locked
                </div>
                <p style="font-size: 13px; margin-top: 12px; color: #6b7280;">
                    Complete the startup fee payment to unlock your unique referral ID and start earning.
                </p>
                <p style="font-size: 11px; color: #f59e0b; margin-top: 8px;">
                     Pay 2,000 FRW once → Earn 5,000 FRW per referral forever
                </p>
            `;
        }
        
        // Update payment section
        if (paymentStatusSpan) {
            paymentStatusSpan.innerHTML = '<span class="badge-status badge-unpaid">⚠️ Not Activated · Pay to Unlock</span>';
        }
        if (payButton) {
            payButton.disabled = false;
            payButton.innerText = '💸 Activate Now (2,000 FRW)';
            payButton.style.opacity = '1';
            payButton.style.cursor = 'pointer';
        }
        if (badgeFlag) {
            badgeFlag.innerText = 'Pending Activation';
            badgeFlag.className = 'badge-status badge-unpaid';
        }
        if (paymentSection) {
            paymentSection.style.borderColor = '#f59e0b';
            paymentSection.style.background = '#fffbeb';
        }
    }
}

// Fetch user data from backend and refresh UI
// Replace your refreshUserData function with this enhanced version
async function refreshUserData(phone) {
    try {
        console.log(`🔄 Fetching user data for: ${phone}`);
        showLoader(true, "Loading your dashboard...");
        
        const resp = await fetch(`${API_BASE}/api/user/${phone}`);
        console.log(`📡 API Response status: ${resp.status}`);
        
        const data = await resp.json();
        console.log("📦 User data received:", data);
        
        if (data.status === 'success' && data.user) {
            const user = data.user;
            const isPaid = user.paid === true || user.paid === 'true';
            
            console.log(`💰 User paid status: ${isPaid}`);
            console.log(`🔑 Referral ID: ${user.referralId}`);
            console.log(`📊 Total earned: ${user.totalEarned}`);
            
            // Ensure paid users have a valid random referral ID
            let finalReferralId = user.referralId;
            
            if (isPaid && (!finalReferralId || finalReferralId === user.phone || finalReferralId === "")) {
                console.log("⚠️ Paid user has invalid referral ID, generating new one...");
                const newRefId = generateRandomReferralId();
                
                try {
                    await fetch(`${API_BASE}/api/update-referral-id`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ phone: user.phone, newReferralId: newRefId })
                    });
                    finalReferralId = newRefId;
                    console.log(`✅ New referral ID generated: ${finalReferralId}`);
                } catch (err) {
                    console.warn("Failed to update referral ID:", err);
                }
            }
            
            // Update currentUser cache
            currentUser = {
                phone: user.phone,
                email: user.email,
                paid: isPaid,
                referralId: isPaid ? finalReferralId : null,
                totalEarned: user.totalEarned || 0,
                referrals: user.referrals || []
            };
            
            console.log("✅ Current user cached:", currentUser);
            
            // Update user info display
            const displayPhone = document.getElementById('displayPhone');
            const displayEmail = document.getElementById('displayEmail');
            const totalEarnedDisplay = document.getElementById('totalEarnedDisplay');
            
            if (displayPhone) displayPhone.innerText = user.phone || '—';
            if (displayEmail) displayEmail.innerText = user.email || '—';
            if (totalEarnedDisplay) {
                totalEarnedDisplay.innerText = (currentUser.totalEarned || 0).toLocaleString();
                console.log(`💰 Displaying total earned: ${currentUser.totalEarned}`);
            }
            
            // Update referral history
            updateReferralHistory(currentUser.referrals);
            
            // Update UI based on payment status
            updateUIForPaidStatus(isPaid, isPaid ? finalReferralId : null);
            
            showLoader(false);
            return { isPaid, refId: finalReferralId };
        } else {
            console.error("❌ API returned error:", data);
            showLoader(false);
            showToast("Failed to load user data: " + (data.message || "Unknown error"), true);
            return null;
        }
    } catch (err) {
        console.error('🔥 Refresh user error:', err);
        showLoader(false);
        showToast("Network error: Cannot connect to server", true);
        return null;
    }
}
// Update referral history display
function updateReferralHistory(referralsList) {
    const historyDiv = document.getElementById('historyContainer');
    if (!historyDiv) return;
    
    if (!referralsList || referralsList.length === 0) {
        historyDiv.innerHTML = `
            <div style="color: #9ca3af; text-align: center; padding: 20px;">
                📭 No referrals yet<br>
                <span style="font-size: 12px;">Share your referral ID after activation to start earning</span>
            </div>
        `;
        return;
    }
    
    historyDiv.innerHTML = '';
    referralsList.forEach(ref => {
        const row = document.createElement('div');
        row.className = 'history-item';
        row.innerHTML = `
            <span>📱 ${ref.phone || 'Friend'} · ${ref.date || 'Recent'}</span>
            <span class="amount-plus">+${(ref.amount || 5000).toLocaleString()} FRW</span>
        `;
        historyDiv.appendChild(row);
    });
}

// Initiate payment
async function startPayment() {
    if (!currentUser || !currentUser.phone) {
        showToast("User session error. Please login again.", true);
        return;
    }
    
    if (currentUser.paid) {
        showToast("You're already activated! Your referral ID is ready to share.", false);
        return;
    }
    
    showLoader(true, "Initiating payment...");
    
    try {
        const response = await fetch(`${API_BASE}/api/initiate-payment`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                phone: currentUser.phone,
                amount: STARTUP_FEE,
                email: currentUser.email
            })
        });
        
        const data = await response.json();
        showLoader(false);
        
        if (data.status === 'success') {
            showToast("✅ Payment prompt sent! Check your mobile money app and complete payment.", false);
            showToast("⏳ Waiting for payment confirmation...", false);
            
            // Start polling for payment confirmation
            startPollingForPayment(currentUser.phone);
        } else {
            showToast("Payment initiation failed: " + (data.message || "Unknown error"), true);
        }
    } catch (err) {
        showLoader(false);
        showToast("Connection error: Payment gateway unreachable", true);
        console.error("Payment error:", err);
    }
}

// Poll for payment confirmation
function startPollingForPayment(phone) {
    // Clear any existing polling
    if (paymentCheckInterval) {
        clearInterval(paymentCheckInterval);
    }
    
    let attempts = 0;
    const maxAttempts = 40; // 40 * 3 seconds = 2 minutes timeout
    
    paymentCheckInterval = setInterval(async () => {
        attempts++;
        
        // Timeout after 2 minutes
        if (attempts > maxAttempts) {
            clearInterval(paymentCheckInterval);
            paymentCheckInterval = null;
            showToast("Payment confirmation timeout. Please contact support if you completed payment.", true);
            return;
        }
        
        try {
            const resp = await fetch(`${API_BASE}/api/user/${phone}`);
            const data = await resp.json();
            
            if (data.status === 'success' && data.user) {
                const isPaidNow = data.user.paid === true || data.user.paid === 'true';
                
                if (isPaidNow) {
                    // Payment confirmed!
                    clearInterval(paymentCheckInterval);
                    paymentCheckInterval = null;
                    
                    showToast("🎉 Payment successful! Your referral ID is now active!", false);
                    
                    // Refresh user data
                    await refreshUserData(phone);
                    
                    // Update session storage
                    const sessionUser = sessionStorage.getItem('loggedInUser');
                    if (sessionUser) {
                        let usr = JSON.parse(sessionUser);
                        usr.paid = true;
                        sessionStorage.setItem('loggedInUser', JSON.stringify(usr));
                    }
                    
                    // Reload page to ensure fresh state
                    setTimeout(() => {
                        window.location.reload();
                    }, 1500);
                } else if (attempts % 10 === 0) {
                    // Show status message every 30 seconds
                    showToast(`⏳ Waiting for payment confirmation... (${Math.floor(attempts * 3 / 10)}s)`, false);
                }
            }
        } catch (err) {
            console.warn("Polling error:", err);
        }
    }, 3000); // Poll every 3 seconds
}

// Logout function
function logout() {
    // Clear all intervals
    if (pollingInterval) clearInterval(pollingInterval);
    if (paymentCheckInterval) clearInterval(paymentCheckInterval);
    
    // Clear session storage
    sessionStorage.removeItem('loggedInUser');
    currentUser = null;
    
    showToast("Logged out successfully", false);
    
    // Redirect to login page
    setTimeout(() => {
        window.location.href = 'login.html';
    }, 500);
}

// Manual payment confirmation (for testing)
async function manualConfirmPayment(adminKey, phone) {
    try {
        const response = await fetch(`${API_BASE}/api/manual-confirm-payment`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                adminKey: adminKey,
                phone: phone,
                transactionId: `MANUAL_${Date.now()}`
            })
        });
        
        const data = await response.json();
        if (data.status === 'success') {
            showToast("✅ Payment manually confirmed!", false);
            await refreshUserData(phone);
            return true;
        } else {
            showToast("Manual confirmation failed: " + (data.message || "Unknown error"), true);
            return false;
        }
    } catch (err) {
        showToast("Manual confirmation error", true);
        return false;
    }
}

// Initialize dashboard
// ui.js - Add this at the beginning of initDashboard function
async function initDashboard() {
    // Check for logged in user
    const savedRaw = sessionStorage.getItem('loggedInUser');
    
    console.log("Checking session storage:", savedRaw); // Debug log
    
    if (!savedRaw) {
        console.log("No user found in session, redirecting to login");
        window.location.href = 'login.html';  // Make sure this path is correct
        return;
    }
    
    try {
        const sessionData = JSON.parse(savedRaw);
        const phoneNum = sessionData.phone;
        
        console.log("Found user in session:", phoneNum); // Debug log
        
        if (!phoneNum) {
            throw new Error("No phone number in session");
        }
        
        // Add session validation - check if session is too old (e.g., 24 hours)
        const loginTime = sessionStorage.getItem('loginTime');
        if (loginTime) {
            const hoursSinceLogin = (Date.now() - parseInt(loginTime)) / (1000 * 60 * 60);
            if (hoursSinceLogin > 24) {
                console.log("Session expired, logging out");
                logout();
                return;
            }
        }
        
        // Fetch user data from backend
        const result = await refreshUserData(phoneNum);
        
        if (!result) {
            console.log("Failed to fetch user data");
            showToast("Failed to load dashboard. Please login again.", true);
            setTimeout(() => logout(), 2000);
            return;
        }
        
        // Attach payment button event (with safety check)
        const payBtn = document.getElementById('payNowActionBtn');
        if (payBtn) {
            // Remove any existing listeners by cloning
            const newPayBtn = payBtn.cloneNode(true);
            payBtn.parentNode.replaceChild(newPayBtn, payBtn);
            newPayBtn.addEventListener('click', startPayment);
            console.log("Payment button attached"); // Debug log
        } else {
            console.warn("Payment button not found in DOM");
        }
        
        // Attach logout button event
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            const newLogoutBtn = logoutBtn.cloneNode(true);
            logoutBtn.parentNode.replaceChild(newLogoutBtn, logoutBtn);
            newLogoutBtn.addEventListener('click', logout);
            console.log("Logout button attached"); // Debug log
        }
        
        // If not paid, start polling for payment
        if (!result.isPaid) {
            console.log("User not paid, starting payment polling");
            startPollingForPayment(phoneNum);
        } else {
            console.log("User is paid, showing referral ID");
        }
        
        showLoader(false);
        
    } catch (err) {
        console.error("Init error:", err);
        showLoader(false);
        showToast("Session error. Please login again.", true);
        setTimeout(() => {
            // Clear invalid session
            sessionStorage.removeItem('loggedInUser');
            window.location.href = 'login.html';
        }, 1500);
    }
}

// Add this right after the configuration
console.log("🚀 UI.js loaded - Version 2.0");

// Add a manual refresh function for debugging
async function manualRefresh() {
    if (currentUser && currentUser.phone) {
        console.log("🔄 Manual refresh triggered");
        await refreshUserData(currentUser.phone);
        showToast("Dashboard refreshed!", false);
    } else {
        showToast("No user logged in", true);
    }
}

// Add a function to check backend connection
async function checkBackend() {
    try {
        const response = await fetch(`${API_BASE}/api/debug/users`);
        const data = await response.json();
        console.log("📊 Backend status:", data);
        if (data.status === 'success') {
            showToast(`✅ Connected! ${data.count} users found`, false);
        } else {
            showToast("⚠️ Backend error", true);
        }
    } catch (err) {
        console.error("Backend connection failed:", err);
        showToast("❌ Cannot connect to backend", true);
    }
}



// Copy function for global use
window.copyReferralCode = copyReferralCode;
// Expose debug functions globally
window.manualRefresh = manualRefresh;
window.checkBackend = checkBackend;
window.showCurrentUser = () => console.log("Current user:", currentUser);

// Start the application when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    initDashboard();
});

// Keep session alive (optional)
setInterval(() => {
    if (currentUser && currentUser.phone) {
        // Refresh user data every 2 minutes to keep session fresh
        refreshUserData(currentUser.phone).catch(console.warn);
    }
}, 120000); // 2 minutes