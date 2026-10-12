/**
 * PROJECT: Datacom Kudos System
 * FILE: static/js/app.js
 * DESCRIPTION: Frontend Client Application Logic.
 *              Manages persona switching (mock testbed), recipient selection,
 *              quick praise chips, real-time character counting, anti-spam feedback,
 *              live feed rendering with DTO segregation, and administrative moderation modals.
 */

// Global Application State
const state = {
    currentUser: null,       // Currently selected active user profile
    users: [],               // List of all active colleagues fetched from backend
    kudos: [],               // Currently displayed kudos
    currentFilter: 'all',    // Admin feed filter ('all', 'flagged', 'hidden')
    cooldownTimer: null,     // Interval ID for anti-spam timer
    cooldownRemaining: 0,    // Remaining cooldown seconds
    activeModalKudoId: null, // Target kudo ID for active modal action
    activeModalAction: null  // Action type for active modal
};

// ============================================================================
// 1. INITIALIZATION & SETUP
// ============================================================================

document.addEventListener('DOMContentLoaded', async () => {
    initEventListeners();
    await loadUsersAndInitializeProfile();
    await fetchLiveFeed();
});

/**
 * Registers all core event listeners across UI components.
 */
function initEventListeners() {
    // User / Persona Switcher change
    const userSelector = document.getElementById('userSelector');
    userSelector.addEventListener('change', handleUserSwitch);

    // Kudo Form Submission
    const kudoForm = document.getElementById('kudoForm');
    kudoForm.addEventListener('submit', handleKudoSubmit);

    // Textarea input for live character count
    const messageInput = document.getElementById('messageInput');
    messageInput.addEventListener('input', handleMessageInput);

    // Quick Praise Chips
    const praiseChips = document.getElementById('praiseChips');
    praiseChips.addEventListener('click', handlePraiseChipClick);

    // Refresh Feed Button
    const refreshBtn = document.getElementById('refreshFeedBtn');
    refreshBtn.addEventListener('click', () => fetchLiveFeed());

    // Admin Filter Tabs
    const adminFilterTabs = document.getElementById('adminFilterTabs');
    adminFilterTabs.addEventListener('click', handleFilterTabClick);

    // Modal Close Buttons (delegated)
    document.querySelectorAll('[data-close-modal]').forEach(btn => {
        btn.addEventListener('click', () => {
            const modalId = btn.getAttribute('data-close-modal');
            closeModal(modalId);
        });
    });

    // Close modal when clicking outside card
    document.querySelectorAll('.modal-overlay').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeModal(modal.id);
            }
        });
    });

    // Modal Confirm Action Handlers
    document.getElementById('confirmModerateBtn').addEventListener('click', submitModeration);
    document.getElementById('confirmDismissBtn').addEventListener('click', submitDismissFlag);
    document.getElementById('confirmDeleteBtn').addEventListener('click', submitDeleteKudo);
}

// ============================================================================
// 2. USER PROFILE & PERSONA SWITCHER (REQ-GAP-01)
// ============================================================================

/**
 * Fetches active colleagues from GET /api/v1/users and sets initial testbed profile.
 */
async function loadUsersAndInitializeProfile() {
    try {
        // Fallback default user header for initial directory fetch
        const defaultId = localStorage.getItem('datacom_user_id') || 'u-01';
        
        const response = await fetch('/api/v1/users', {
            headers: { 'X-User-Id': defaultId }
        });

        if (!response.ok) {
            throw new Error(`Failed to fetch users: HTTP ${response.status}`);
        }

        state.users = await response.json();

        // Populate testbed switcher dropdown
        const userSelector = document.getElementById('userSelector');
        userSelector.innerHTML = '';

        state.users.forEach(user => {
            const opt = document.createElement('option');
            opt.value = user.id;
            opt.textContent = `${user.name} (${user.role.toUpperCase()}) - ${user.department}`;
            userSelector.appendChild(opt);
        });

        // Set active user (default to Sarah Connor u-01 or saved ID)
        const savedUserId = localStorage.getItem('datacom_user_id') || 'u-01';
        const foundUser = state.users.find(u => u.id === savedUserId) || state.users[0];
        
        setActiveUser(foundUser);
        userSelector.value = foundUser.id;

    } catch (err) {
        console.error('Error loading users:', err);
        showToast('error', 'Directory Error', 'Could not load colleague directory. Check server connection.');
    }
}

/**
 * Updates application state and UI elements for the currently active persona.
 */
function setActiveUser(user) {
    state.currentUser = user;
    localStorage.setItem('datacom_user_id', user.id);

    // Update Header Badge
    document.getElementById('headerAvatar').src = user.avatar;
    document.getElementById('headerUserName').textContent = user.name;

    const roleBadge = document.getElementById('headerUserRole');
    const adminBanner = document.getElementById('adminModerationBanner');
    if (user.role === 'admin') {
        roleBadge.textContent = 'Admin / Modérateur';
        roleBadge.className = 'role-pill role-admin';
        if (adminBanner) adminBanner.classList.remove('hidden');
    } else {
        roleBadge.textContent = 'Employé';
        roleBadge.className = 'role-pill role-user';
        if (adminBanner) adminBanner.classList.add('hidden');
        state.currentFilter = 'all';
    }

    // Populate recipient dropdown excluding current user (BR-01 Self-Kudos prevention)
    populateRecipientDropdown();
}

/**
 * Handles persona switch via topbar dropdown.
 */
async function handleUserSwitch(e) {
    const selectedId = e.target.value;
    const selectedUser = state.users.find(u => u.id === selectedId);
    if (!selectedUser) return;

    setActiveUser(selectedUser);
    showToast('info', 'Changement de profil', `Session active : ${selectedUser.name} (${selectedUser.role.toUpperCase()})`);

    // Reset admin filter pills to 'all'
    document.querySelectorAll('.filter-pill').forEach(pill => {
        pill.classList.toggle('active', pill.getAttribute('data-filter') === 'all');
    });
    state.currentFilter = 'all';

    // Re-fetch feed with new user context
    await fetchLiveFeed();
}

/**
 * Fills the recipient dropdown with active colleagues, omitting current user.
 */
function populateRecipientDropdown() {
    const select = document.getElementById('recipientSelect');
    select.innerHTML = '<option value="" disabled selected>Choose an active team member...</option>';

    state.users.forEach(user => {
        // Enforce Rule BR-01: Cannot send kudos to oneself
        if (state.currentUser && user.id === state.currentUser.id) {
            return;
        }

        const opt = document.createElement('option');
        opt.value = user.id;
        opt.textContent = `${user.name} — ${user.department}`;
        select.appendChild(opt);
    });
}

// ============================================================================
// 3. KUDO COMPOSITION & ANTI-SPAM (PHASE P4)
// ============================================================================

/**
 * Inserts pre-composed text when a quick praise chip is clicked.
 */
function handlePraiseChipClick(e) {
    const chip = e.target.closest('.praise-chip');
    if (!chip) return;

    const text = chip.getAttribute('data-text');
    const messageInput = document.getElementById('messageInput');
    messageInput.value = text;
    handleMessageInput();
    messageInput.focus();
}

/**
 * Validates message length and updates the character counter in real time.
 */
function handleMessageInput() {
    const messageInput = document.getElementById('messageInput');
    const counter = document.getElementById('charCounter');
    const hint = document.getElementById('validationHint');
    const submitBtn = document.getElementById('submitKudoBtn');

    const len = messageInput.value.trim().length;
    counter.textContent = `${len} / 500`;

    // Dynamic styling based on length boundaries (BR-04: 3 to 500 chars)
    if (len === 0) {
        counter.className = 'char-counter';
        hint.textContent = 'Minimum 3 characters required.';
        hint.style.color = 'var(--text-muted)';
        submitBtn.disabled = true;
    } else if (len < 3) {
        counter.className = 'char-counter warning';
        hint.textContent = `Too short: ${3 - len} more character(s) required.`;
        hint.style.color = 'var(--status-warning)';
        submitBtn.disabled = true;
    } else if (len > 500) {
        counter.className = 'char-counter danger';
        hint.textContent = 'Character limit exceeded (maximum 500).';
        hint.style.color = 'var(--status-danger)';
        submitBtn.disabled = true;
    } else {
        counter.className = 'char-counter valid';
        hint.textContent = 'Message length is optimal.';
        hint.style.color = 'var(--status-success)';
        submitBtn.disabled = false;
    }
}

/**
 * Submits the kudo form to POST /api/v1/kudos with the current user's session header.
 */
async function handleKudoSubmit(e) {
    e.preventDefault();

    if (!state.currentUser) {
        showToast('error', 'Auth Error', 'No active user session selected.');
        return;
    }

    const recipientSelect = document.getElementById('recipientSelect');
    const recipientId = recipientSelect.value;
    const categoryInput = document.querySelector('input[name="category"]:checked');
    const category = categoryInput ? categoryInput.value : 'Teamwork';
    const messageInput = document.getElementById('messageInput');
    const message = messageInput.value.trim();

    // Client-side pre-validations
    if (!recipientId) {
        showToast('warning', 'Recipient Required', 'Please select a colleague to appreciate.');
        recipientSelect.focus();
        return;
    }

    if (message.length < 3 || message.length > 500) {
        showToast('warning', 'Invalid Length', 'Appreciation message must be between 3 and 500 characters.');
        messageInput.focus();
        return;
    }

    const submitBtn = document.getElementById('submitKudoBtn');
    const btnText = submitBtn.querySelector('.btn-text');
    const btnSpinner = submitBtn.querySelector('.btn-spinner');

    // Loading state
    submitBtn.disabled = true;
    btnText.classList.add('hidden');
    btnSpinner.classList.remove('hidden');

    try {
        const response = await fetch('/api/v1/kudos', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-User-Id': state.currentUser.id
            },
            body: JSON.stringify({
                recipient_id: recipientId,
                category: category,
                message: message
            })
        });

        const data = await response.json();

        if (response.status === 201) {
            // Check if message was placed in automated quarantine by AI
            if (data.quarantined) {
                showToast('warning', 'En attente de modération ⏳', 'Votre message a été placé en quarantaine pour vérification par un modérateur avant d\'être transmis.');
            } else {
                showToast('success', 'Kudo Publié ! 🎉', 'Votre appréciation a été publiée avec succès sur le flux public.');
            }
            
            // Reset form
            messageInput.value = '';
            recipientSelect.value = '';
            handleMessageInput();

            // Trigger client-side cooldown countdown (10s anti-spam BR-05)
            startCooldownTimer(10);

            // Re-fetch feed to display newly posted kudo
            await fetchLiveFeed();

        } else if (response.status === 429) {
            // Anti-spam or duplicate violation (BR-05)
            const errorMsg = data.error?.message || 'Please wait before submitting another kudo.';
            showToast('warning', 'Rate Limit / Anti-Spam', errorMsg);
            startCooldownTimer(10);

        } else if (response.status === 422) {
            // Business rule validation error
            const issue = data.error?.details?.[0]?.issue || data.error?.message || 'Validation failed.';
            showToast('error', 'Validation Error', issue);

        } else {
            const msg = data.error?.message || `Server error (HTTP ${response.status})`;
            showToast('error', 'Submission Failed', msg);
        }

    } catch (err) {
        console.error('Error submitting kudo:', err);
        showToast('error', 'Network Error', 'Could not reach server. Please try again.');
    } finally {
        submitBtn.disabled = false;
        btnText.classList.remove('hidden');
        btnSpinner.classList.add('hidden');
    }
}

/**
 * Displays a 10-second visual cooldown badge and countdown.
 */
function startCooldownTimer(seconds) {
    if (state.cooldownTimer) {
        clearInterval(state.cooldownTimer);
    }

    state.cooldownRemaining = seconds;
    const badge = document.getElementById('cooldownTimer');
    const secondsSpan = document.getElementById('cooldownSeconds');
    badge.classList.remove('hidden');
    secondsSpan.textContent = state.cooldownRemaining;

    state.cooldownTimer = setInterval(() => {
        state.cooldownRemaining -= 1;
        if (state.cooldownRemaining <= 0) {
            clearInterval(state.cooldownTimer);
            badge.classList.add('hidden');
        } else {
            secondsSpan.textContent = state.cooldownRemaining;
        }
    }, 1000);
}

// ============================================================================
// 4. LIVE FEED & RECOGNITION WALL
// ============================================================================

/**
 * Fetches recent kudos from GET /api/v1/kudos using active user context.
 */
async function fetchLiveFeed() {
    if (!state.currentUser) return;

    const feedList = document.getElementById('feedList');
    const emptyState = document.getElementById('feedEmptyState');
    const skeleton = document.getElementById('feedLoadingSkeleton');

    skeleton.classList.remove('hidden');

    try {
        const url = `/api/v1/kudos?limit=50&offset=0&filter=${state.currentFilter}`;
        const response = await fetch(url, {
            headers: { 'X-User-Id': state.currentUser.id }
        });

        if (!response.ok) {
            throw new Error(`Feed fetch failed: HTTP ${response.status}`);
        }

        const result = await response.json();
        state.kudos = result.data || [];

        renderFeed();

    } catch (err) {
        console.error('Error fetching kudos feed:', err);
        showToast('error', 'Feed Error', 'Unable to retrieve live kudos feed.');
    } finally {
        skeleton.classList.add('hidden');
    }
}

/**
 * Renders the list of kudos into the feed container.
 */
function renderFeed() {
    const feedList = document.getElementById('feedList');
    const emptyState = document.getElementById('feedEmptyState');
    feedList.innerHTML = '';

    const isAdmin = state.currentUser?.role === 'admin';

    // Update Admin Queue Badges if admin
    if (isAdmin) {
        const flaggedCount = state.kudos.filter(k => k.ai_flagged).length;
        const hiddenCount = state.kudos.filter(k => k.is_visible === false).length;
        const flaggedBadge = document.getElementById('flaggedCountBadge');
        const hiddenBadge = document.getElementById('hiddenCountBadge');
        if (flaggedBadge) flaggedBadge.textContent = flaggedCount;
        if (hiddenBadge) hiddenBadge.textContent = hiddenCount;
    }

    if (state.kudos.length === 0) {
        emptyState.classList.remove('hidden');
        return;
    }

    emptyState.classList.add('hidden');

    state.kudos.forEach(kudo => {
        const card = createKudoCardElement(kudo, isAdmin);
        feedList.appendChild(card);
    });
}

/**
 * Creates the DOM element for an individual kudo card.
 */
function createKudoCardElement(kudo, isAdmin) {
    const card = document.createElement('article');
    const isHidden = isAdmin && kudo.is_visible === false;
    card.className = `kudo-card ${isHidden ? 'is-hidden' : ''}`;
    card.id = `kudo-${kudo.id}`;

    // Clean relative timestamp
    const relativeTime = formatRelativeTime(kudo.created_at);

    // CSS class for category tag
    const catSlug = kudo.category.toLowerCase().replace(/[^a-z0-9]/g, '-');

    // Build Card HTML
    card.innerHTML = `
        <div class="kudo-card-top">
            <div class="kudo-actors">
                <img src="${kudo.sender.avatar}" alt="${escapeHtml(kudo.sender.name)}" class="actor-avatar">
                <div class="actor-names">
                    <span class="sender-name">${escapeHtml(kudo.sender.name)}</span>
                    <span class="recipient-target">appreciated <strong>${escapeHtml(kudo.recipient.name)}</strong></span>
                </div>
            </div>
            <div class="kudo-badges">
                <span class="badge-category badge-cat-${catSlug}">${escapeHtml(kudo.category)}</span>
                <span class="kudo-time">${relativeTime}</span>
            </div>
        </div>

        <!-- AI Quarantine or Flag Banner (Admin only) -->
        ${isAdmin && kudo.ai_flagged && !kudo.is_visible ? `
            <div class="quarantine-banner">
                <div class="quarantine-icon"><i class="fa-solid fa-hand"></i></div>
                <div class="quarantine-text">
                    <strong>⛔ EN QUARANTAINE IA (Non visible pour le destinataire)</strong>
                    <span>Motif de blocage : ${escapeHtml(kudo.ai_flag_reason || 'Termes sensibles détectés')}</span>
                </div>
            </div>
        ` : (isAdmin && kudo.ai_flagged ? `
            <div class="ai-alert-banner">
                <span class="ai-alert-text">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                    <strong>Alerte IA :</strong> ${escapeHtml(kudo.ai_flag_reason || 'Langage suspect détecté')}
                </span>
                <button class="btn-action-sm action-dismiss" onclick="openDismissModal('${kudo.id}')">
                    <i class="fa-solid fa-check"></i> Lever l'alerte
                </button>
            </div>
        ` : '')}

        <div class="kudo-body">
            "${escapeHtml(kudo.message)}"
        </div>

        <!-- Admin Moderation Controls (Admin only) -->
        ${isAdmin ? `
            <div class="admin-card-actions">
                ${!kudo.is_visible ? `
                    <button class="btn-action-sm action-approve" onclick="quickApproveKudo('${kudo.id}')" title="Rendre visible pour le destinataire et le public">
                        <i class="fa-solid fa-check"></i> Approuver & Publier
                    </button>
                ` : `
                    <button class="btn-action-sm action-hide" onclick="openModerateModal('${kudo.id}', 'hide')">
                        <i class="fa-solid fa-eye-slash"></i> Masquer
                    </button>
                `}
                <button class="btn-action-sm action-delete" onclick="openDeleteModal('${kudo.id}')">
                    <i class="fa-solid fa-trash-can"></i> Supprimer
                </button>
                <button class="btn-action-sm" onclick="openAuditModal('${kudo.id}')">
                    <i class="fa-solid fa-clock-rotate-left"></i> Audit
                </button>
            </div>
        ` : ''}
    `;

    return card;
}

/**
 * Quick 1-click approval for quarantined kudos by administrator.
 */
window.quickApproveKudo = async function(kudoId) {
    if (!state.currentUser || state.currentUser.role !== 'admin') return;

    try {
        const response = await fetch(`/api/v1/kudos/${kudoId}/moderate`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'X-User-Id': state.currentUser.id
            },
            body: JSON.stringify({
                is_visible: true,
                reason: "Approuvé manuellement par l'administrateur (Levée de quarantaine)"
            })
        });

        if (response.ok) {
            showToast('success', 'Kudo Approuvé ! ✅', 'Le message a été validé et est désormais visible par le destinataire.');
            await fetchLiveFeed();
        } else {
            const data = await response.json();
            showToast('error', 'Erreur d\'approbation', data.error?.message || 'Impossible d\'approuver.');
        }
    } catch (err) {
        console.error('Error approving kudo:', err);
        showToast('error', 'Erreur Réseau', 'Impossible de contacter le serveur.');
    }
};

/**
 * Handles clicks on admin filter pills (All, AI Flagged/Quarantined, Hidden).
 */
function handleFilterTabClick(e) {
    const pill = e.target.closest('.filter-pill');
    if (!pill) return;

    document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
    pill.classList.add('active');

    state.currentFilter = pill.getAttribute('data-filter');
    fetchLiveFeed();
}

// ============================================================================
// 5. MODERATION ACTIONS & MODALS (ADMIN ONLY)
// ============================================================================

function openModal(modalId) {
    document.getElementById(modalId).classList.remove('hidden');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.add('hidden');
}

// --- Moderate Visibility (Hide / Restore) ---
window.openModerateModal = function(kudoId, action) {
    state.activeModalKudoId = kudoId;
    state.activeModalAction = action;

    const modalTitle = document.getElementById('moderateModalTitle');
    const modalDesc = document.getElementById('moderateModalDesc');
    const reasonInput = document.getElementById('moderateReasonInput');
    reasonInput.value = '';

    if (action === 'hide') {
        modalTitle.innerHTML = '<i class="fa-solid fa-eye-slash"></i> Hide Kudo from Public Feed';
        modalDesc.textContent = 'This kudo will be hidden from standard employees. It will remain visible to administrators.';
    } else {
        modalTitle.innerHTML = '<i class="fa-solid fa-eye"></i> Restore Kudo Visibility';
        modalDesc.textContent = 'This kudo will be restored and made visible to all colleagues on the public feed.';
    }

    openModal('moderateModal');
};

async function submitModeration() {
    const reason = document.getElementById('moderateReasonInput').value.trim();
    if (!reason) {
        showToast('warning', 'Reason Required', 'A mandatory explanation is required for the audit trail.');
        return;
    }

    const isVisible = state.activeModalAction === 'restore';

    try {
        const response = await fetch(`/api/v1/kudos/${state.activeModalKudoId}/moderate`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'X-User-Id': state.currentUser.id
            },
            body: JSON.stringify({
                is_visible: isVisible,
                reason: reason
            })
        });

        if (response.ok) {
            closeModal('moderateModal');
            showToast('success', 'Moderation Saved', `Kudo visibility successfully ${isVisible ? 'restored' : 'hidden'}.`);
            await fetchLiveFeed();
        } else {
            const data = await response.json();
            showToast('error', 'Moderation Failed', data.error?.message || 'Error executing action.');
        }
    } catch (err) {
        console.error('Error during moderation:', err);
        showToast('error', 'Network Error', 'Failed to communicate with server.');
    }
}

// --- Dismiss AI Flag ---
window.openDismissModal = function(kudoId) {
    state.activeModalKudoId = kudoId;
    document.getElementById('dismissReasonInput').value = '';
    openModal('dismissModal');
};

async function submitDismissFlag() {
    const reason = document.getElementById('dismissReasonInput').value.trim();
    if (!reason) {
        showToast('warning', 'Reason Required', 'Please provide justification explaining why this flag is a false positive.');
        return;
    }

    try {
        const response = await fetch(`/api/v1/kudos/${state.activeModalKudoId}/dismiss-flag`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-User-Id': state.currentUser.id
            },
            body: JSON.stringify({ reason: reason })
        });

        if (response.ok) {
            closeModal('dismissModal');
            showToast('success', 'Flag Dismissed', 'AI alert cleared and recorded to audit trail.');
            await fetchLiveFeed();
        } else {
            const data = await response.json();
            showToast('error', 'Dismissal Failed', data.error?.message || 'Could not dismiss flag.');
        }
    } catch (err) {
        console.error('Error dismissing flag:', err);
        showToast('error', 'Network Error', 'Failed to communicate with server.');
    }
}

// --- Permanent Deletion ---
window.openDeleteModal = function(kudoId) {
    state.activeModalKudoId = kudoId;
    document.getElementById('deleteReasonInput').value = '';
    openModal('deleteModal');
};

async function submitDeleteKudo() {
    const reason = document.getElementById('deleteReasonInput').value.trim();
    if (!reason) {
        showToast('warning', 'Reason Required', 'Mandatory deletion reason is required for compliance.');
        return;
    }

    try {
        const response = await fetch(`/api/v1/kudos/${state.activeModalKudoId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-User-Id': state.currentUser.id
            },
            body: JSON.stringify({ reason: reason })
        });

        if (response.ok) {
            closeModal('deleteModal');
            showToast('success', 'Kudo Deleted', 'Kudo permanently deleted; full audit history retained (BR-09).');
            await fetchLiveFeed();
        } else {
            const data = await response.json();
            showToast('error', 'Deletion Failed', data.error?.message || 'Could not delete kudo.');
        }
    } catch (err) {
        console.error('Error deleting kudo:', err);
        showToast('error', 'Network Error', 'Failed to communicate with server.');
    }
}

// --- View Immutable Audit Trail ---
window.openAuditModal = async function(kudoId) {
    const timeline = document.getElementById('auditLogTimeline');
    timeline.innerHTML = '<div style="text-align:center; padding: 20px;"><i class="fa-solid fa-spinner fa-spin"></i> Loading audit history...</div>';
    openModal('auditModal');

    try {
        const response = await fetch(`/api/v1/kudos/${kudoId}/audit`, {
            headers: { 'X-User-Id': state.currentUser.id }
        });

        if (!response.ok) {
            throw new Error(`Audit fetch failed: HTTP ${response.status}`);
        }

        const logs = await response.json();
        renderAuditTimeline(logs);

    } catch (err) {
        console.error('Error fetching audit trail:', err);
        timeline.innerHTML = '<div class="warning-text">Could not retrieve audit history.</div>';
    }
};

function renderAuditTimeline(logs) {
    const timeline = document.getElementById('auditLogTimeline');
    if (!logs || logs.length === 0) {
        timeline.innerHTML = '<p class="audit-intro">No moderation events recorded for this kudo.</p>';
        return;
    }

    timeline.innerHTML = '';
    logs.forEach(log => {
        const entry = document.createElement('div');
        entry.className = `audit-entry action-${log.action}`;
        entry.innerHTML = `
            <div class="audit-entry-top">
                <span class="audit-action-tag">ACTION: ${escapeHtml(log.action)}</span>
                <span class="audit-time">${formatDate(log.created_at)}</span>
            </div>
            <div class="audit-moderator">
                <i class="fa-solid fa-user-shield"></i> Moderator: ${escapeHtml(log.moderator_name)} (${escapeHtml(log.moderator_email)})
            </div>
            <div class="audit-reason">
                "${escapeHtml(log.reason)}"
            </div>
        `;
        timeline.appendChild(entry);
    });
}

// ============================================================================
// 6. UTILITIES (TOASTS, FORMATTING, XSS ESCAPE)
// ============================================================================

/**
 * Creates and animates a toast notification message.
 */
function showToast(type, title, message) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = {
        success: 'fa-circle-check',
        error: 'fa-circle-exclamation',
        warning: 'fa-triangle-exclamation',
        info: 'fa-circle-info'
    };

    toast.innerHTML = `
        <div class="toast-icon">
            <i class="fa-solid ${icons[type] || 'fa-info'}"></i>
        </div>
        <div class="toast-content">
            <div class="toast-title">${escapeHtml(title)}</div>
            <div class="toast-message">${escapeHtml(message)}</div>
        </div>
    `;

    container.appendChild(toast);

    // Auto-dismiss after 4.5 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 4500);
}

/**
 * Formats ISO timestamps into relative "X minutes ago" or date.
 */
function formatRelativeTime(isoString) {
    if (!isoString) return '';
    try {
        const date = new Date(isoString);
        const now = new Date();
        const diffSeconds = Math.floor((now - date) / 1000);

        if (diffSeconds < 60) return 'just now';
        if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
        if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
        return date.toLocaleDateString('en-NZ', { month: 'short', day: 'numeric' });
    } catch {
        return isoString;
    }
}

/**
 * Formats ISO timestamp for audit log view.
 */
function formatDate(isoString) {
    if (!isoString) return '';
    try {
        const d = new Date(isoString);
        return d.toLocaleString('en-NZ', { 
            year: 'numeric', month: 'short', day: 'numeric', 
            hour: '2-digit', minute: '2-digit', second: '2-digit' 
        });
    } catch {
        return isoString;
    }
}

/**
 * Escapes HTML characters to prevent cross-site scripting (XSS).
 */
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
