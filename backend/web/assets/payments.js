(() => {
  const API = '/api/v1';
  const $ = (selector, root = document) => root.querySelector(selector);
  const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const state = { config: null, tiers: [], selectedTier: null, ownerPin: '', ownerData: null, proofUrl: null };
  const money = value => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(value || 0));
  const period = days => Number(days) >= 36500 ? 'one-time' : `${days} days`;

  async function api(path, options = {}) {
    const response = await fetch(`${API}${path}`, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(body?.error?.message || body?.detail || `Request failed (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function toast(message) {
    const node = $('#toast');
    if (!node) return;
    node.textContent = message;
    node.classList.add('show');
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => node.classList.remove('show'), 3200);
  }

  async function loadPlans() {
    const grid = $('#plan-grid');
    if (!grid) return;
    grid.innerHTML = '<div class="loading-card"><span class="loader"></span>Loading plans…</div>';
    try {
      state.config = await api('/pay/public-config');
      state.tiers = state.config.tiers || [];
      renderPlans();
    } catch (error) {
      grid.innerHTML = `<div class="panel form-message">${escapeHTML(error.message)} <button class="button button-secondary" data-reload-plans>Retry</button></div>`;
    }
  }

  function renderPlans() {
    const grid = $('#plan-grid');
    if (!grid) return;
    if (!state.tiers.length) {
      grid.innerHTML = '<div class="panel">No plans are currently available.</div>';
      return;
    }
    grid.innerHTML = state.tiers.map((tier, index) => `
      <article class="plan-card ${index === 1 ? 'featured-plan' : ''}">
        <div class="plan-top"><span>${index === 0 ? 'ESSENTIAL' : index === 1 ? 'PILOT UPGRADE' : 'ORGANISATIONS'}</span><span class="plan-icon">${index === 0 ? '⌂' : index === 1 ? '✳' : '▦'}</span></div>
        <h2>${escapeHTML(tier.name)}</h2><div class="plan-price">${Number(tier.price_inr) === 0 ? 'Free' : money(tier.price_inr)} <small>${Number(tier.price_inr) ? `/ ${escapeHTML(period(tier.duration_days))}` : ''}</small></div>
        <ul>${(tier.features || []).map(feature => `<li>${escapeHTML(feature)}</li>`).join('')}</ul>
        <button class="button ${Number(tier.price_inr) ? 'button-primary' : 'button-secondary'} full-button" data-upgrade="${escapeHTML(tier.tier_code)}" ${Number(tier.price_inr) ? '' : 'disabled'}>${Number(tier.price_inr) ? 'Select plan' : 'Included'}</button>
        ${Number(tier.price_inr) ? '<p class="plan-note">Manual owner verification. No automatic activation.</p>' : ''}
      </article>`).join('');
  }

  function openCheckout(tierCode) {
    const tier = state.tiers.find(item => item.tier_code === tierCode);
    if (!tier) return;
    if (!state.config?.payments_ready) {
      toast('The owner has not configured a UPI ID yet.');
      return;
    }
    state.selectedTier = tier;
    $('#payment-modal-title').textContent = `${tier.name} · ${money(tier.price_inr)} / ${period(tier.duration_days)}`;
    $('#payment-modal-content').innerHTML = checkoutMarkup(tier);
    $('#payment-modal').hidden = false;
    $('#checkout-name').focus();
  }

  function checkoutMarkup(tier) {
    const upiLink = `upi://pay?pa=${encodeURIComponent(state.config.upi_id)}&pn=${encodeURIComponent(state.config.payee_name)}&am=${Number(tier.price_inr).toFixed(2)}&cu=INR&tn=${encodeURIComponent(`KISAN-X ${tier.name}`)}`;
    const qr = state.config.qr_image_url ? `<img class="payment-qr" src="${escapeHTML(state.config.qr_image_url)}" alt="Owner UPI QR code">` : '<p class="form-note">No QR image is configured. You can use the UPI ID below.</p>';
    return `<div class="checkout-layout"><div class="checkout-payment"><p>Pay <strong>${money(tier.price_inr)}</strong> to <strong>${escapeHTML(state.config.payee_name)}</strong></p>${qr}<div class="upi-row"><code>${escapeHTML(state.config.upi_id)}</code><button type="button" class="button button-secondary" id="copy-upi">Copy UPI ID</button></div><a class="button button-secondary full-button" href="${escapeHTML(upiLink)}">Open a UPI app</a><p class="form-note">Confirm the payee name and amount in your UPI app. Never share your UPI PIN or OTP with this site.</p></div>
      <form id="payment-claim-form" class="checkout-form"><label>Your name<input id="checkout-name" name="farmer_name" required minlength="2" maxlength="80"></label><label>Mobile number<input name="farmer_phone" required inputmode="numeric" autocomplete="tel" placeholder="10-digit Indian number" value="${escapeHTML($('#plan-phone')?.value || '')}"></label><label>UPI reference / UTR<input name="utr_number" required maxlength="22" autocomplete="off" placeholder="From your payment receipt"></label><label>Payment screenshot <span class="optional">(optional, max 5 MB)</span><input type="file" name="screenshot" accept="image/png,image/jpeg,image/webp"></label><button class="button button-primary full-button" type="submit">Submit payment proof</button><p class="form-message" id="claim-message" role="status"></p><p class="form-note">Your plan starts after the owner verifies the payment in their own account.</p></form></div>`;
  }

  function closeCheckout() {
    $('#payment-modal').hidden = true;
    state.selectedTier = null;
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  }

  function readPlan() {
    if (!state.selectedTier) return;
    if (!('speechSynthesis' in window)) { toast('Voice playback is not available in this browser.'); return; }
    const tier = state.selectedTier;
    const text = `${tier.name}, ${Number(tier.price_inr) ? `${tier.price_inr} rupees for ${period(tier.duration_days)}` : 'free'}. ${(tier.features || []).join('. ')}. ${state.config?.payments_ready ? 'Payment goes directly to the owner through UPI and is checked manually.' : ''}`;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text.slice(0, 950)));
  }

  async function submitClaim(form) {
    const message = $('#claim-message');
    const button = form.querySelector('[type="submit"]');
    message.textContent = '';
    const data = new FormData(form);
    data.set('tier_code', state.selectedTier.tier_code);
    button.disabled = true;
    try {
      const result = await api('/pay/submit-claim', { method: 'POST', body: data });
      $('#payment-modal-content').innerHTML = `<div class="claim-success"><div class="success-mark">✓</div><h3>Payment proof received</h3><p>Claim #${Number(result.claim_id)} is waiting for owner verification. The owner will check the payment before enabling the subscription.</p><button class="button button-secondary" id="checkout-done" type="button">Close</button></div>`;
      const phone = data.get('farmer_phone');
      $('#plan-phone').value = phone;
      checkPaymentStatus(phone).catch(() => {});
    } catch (error) {
      message.textContent = error.message;
      button.disabled = false;
    }
  }

  function setPaymentStatus(data) {
    const sub = data.active_subscription;
    const claims = data.recent_claims || [];
    const status = sub?.is_active ? `<strong>${escapeHTML(sub.tier_code)}</strong> active until ${new Date(sub.expires_at * 1000).toLocaleDateString()}` : 'No active paid subscription found.';
    const claimText = claims.length ? `<ul>${claims.map(item => `<li>Claim #${Number(item.id)} · ${escapeHTML(item.status)} · ${money(item.amount_inr)}</li>`).join('')}</ul>` : '';
    $('#payment-status-result').innerHTML = `<div class="status-result">${status}${claimText}</div>`;
  }

  async function checkPaymentStatus(rawPhone) {
    const phone = String(rawPhone || '').replace(/\D/g, '');
    if (!(phone.length === 10 || (phone.length === 12 && phone.startsWith('91')))) throw new Error('Enter a valid 10-digit Indian mobile number.');
    const data = await api(`/pay/status/${encodeURIComponent(phone)}`);
    setPaymentStatus(data);
    return data;
  }

  async function ownerApi(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set('X-Owner-Pin', state.ownerPin);
    return api(path, { ...options, headers });
  }

  function clearOwner() {
    state.ownerPin = '';
    state.ownerData = null;
    $('#owner-pin').value = '';
    $('#owner-dashboard').hidden = true;
    $('#owner-login').hidden = false;
    $('#owner-login-message').textContent = '';
  }

  async function unlockOwner() {
    state.ownerPin = $('#owner-pin').value;
    $('#owner-login-message').textContent = 'Checking access…';
    try {
      await refreshOwner();
      $('#owner-login').hidden = true;
      $('#owner-dashboard').hidden = false;
      $('#owner-pin').value = '';
    } catch (error) {
      clearOwner();
      $('#owner-login-message').textContent = error.message;
    }
  }

  async function refreshOwner() {
    const data = await ownerApi('/owner/dashboard');
    state.ownerData = data;
    renderOwner(data);
  }

  function renderOwner(data) {
    $('#owner-metrics').innerHTML = `<article class="metric-card"><span>VERIFIED PAYMENTS</span><b>${money(data.total_revenue_inr)}</b></article><article class="metric-card"><span>WAITING FOR REVIEW</span><b>${Number(data.pending_count)}</b></article><article class="metric-card"><span>ACTIVE SUBSCRIPTIONS</span><b>${Number(data.active_paid_farmers)}</b></article>`;
    $('#owner-settings [name="upi_id"]').value = data.settings.upi_id || '';
    $('#owner-settings [name="payee_name"]').value = data.settings.payee_name || '';
    $('#owner-qr-preview').innerHTML = data.settings.qr_image_url ? `<img class="payment-qr owner-qr" src="${escapeHTML(data.settings.qr_image_url)}" alt="Current owner QR code">` : '<p class="form-note">No QR code uploaded yet.</p>';
    $('#owner-claims-list').innerHTML = data.claims.length ? data.claims.map(claim => `<article class="claim-row"><div><b>${escapeHTML(claim.farmer_name)}</b><small>${escapeHTML(claim.farmer_phone)} · ${escapeHTML(claim.tier_code)} · ${money(claim.amount_inr)}</small><small>UTR: ${escapeHTML(claim.utr_number)} · ${escapeHTML(claim.status)}</small></div><div class="claim-actions">${claim.has_proof ? `<button type="button" class="button button-secondary" data-proof="${Number(claim.id)}">View proof</button>` : ''}${claim.status === 'PENDING' ? `<button type="button" class="button button-primary" data-verify="${Number(claim.id)}" data-decision="APPROVE">Approve</button><button type="button" class="button button-secondary" data-verify="${Number(claim.id)}" data-decision="REJECT">Reject</button>` : ''}</div></article>`).join('') : '<p class="form-note">No claims yet.</p>';
    $('#owner-tier-list').innerHTML = data.tiers.map(tier => `<div class="tier-edit" data-tier="${escapeHTML(tier.tier_code)}"><b>${escapeHTML(tier.tier_code)}</b><label>Name<input data-field="name" value="${escapeHTML(tier.name)}" maxlength="60"></label><label>Price (INR)<input data-field="price_inr" type="number" min="0" max="100000" value="${Number(tier.price_inr)}" ${tier.tier_code === 'FREE' ? 'readonly' : ''}></label><label>Features, one per line<textarea data-field="features" rows="3">${escapeHTML((tier.features || []).join('\n'))}</textarea></label><label class="tier-active"><input data-field="is_active" type="checkbox" ${tier.is_active ? 'checked' : ''}> Active</label></div>`).join('');
  }

  async function saveOwnerSettings(form) {
    const message = $('#owner-settings-message'); message.textContent = '';
    const formData = new FormData(form);
    try {
      await ownerApi('/owner/update-settings', { method: 'POST', body: formData });
      form.reset(); message.textContent = 'Payment settings saved.'; message.classList.add('success');
      await refreshOwner(); state.config = null;
    } catch (error) { message.textContent = error.message; if ([401, 429, 503].includes(error.status)) clearOwner(); }
  }

  async function saveOwnerTiers() {
    const message = $('#owner-tier-message'); message.textContent = '';
    const updates = [...document.querySelectorAll('.tier-edit')].map(row => ({
      tier_code: row.dataset.tier,
      name: row.querySelector('[data-field="name"]').value.trim(),
      price_inr: Number(row.querySelector('[data-field="price_inr"]').value),
      features: row.querySelector('[data-field="features"]').value.split('\n').map(item => item.trim()).filter(Boolean),
      is_active: row.querySelector('[data-field="is_active"]').checked,
    }));
    const body = new FormData(); body.set('tier_updates_json', JSON.stringify(updates));
    try { await ownerApi('/owner/update-settings', { method: 'POST', body }); message.textContent = 'Plans saved.'; message.classList.add('success'); await refreshOwner(); state.config = null; }
    catch (error) { message.textContent = error.message; if ([401, 429, 503].includes(error.status)) clearOwner(); }
  }

  async function showProof(id) {
    const response = await fetch(`${API}/owner/claims/${id}/proof`, { headers: { 'X-Owner-Pin': state.ownerPin } });
    if (!response.ok) throw new Error('Could not load this private payment proof.');
    if (state.proofUrl) URL.revokeObjectURL(state.proofUrl);
    state.proofUrl = URL.createObjectURL(await response.blob());
    $('#proof-image').src = state.proofUrl;
    $('#proof-modal').hidden = false;
  }

  function closeProof() {
    $('#proof-modal').hidden = true;
    $('#proof-image').removeAttribute('src');
    if (state.proofUrl) URL.revokeObjectURL(state.proofUrl);
    state.proofUrl = null;
  }

  document.addEventListener('click', event => {
    const upgrade = event.target.closest('[data-upgrade]');
    if (upgrade) { openCheckout(upgrade.dataset.upgrade); return; }
    if (event.target.closest('#close-payment') || event.target.closest('#checkout-done')) closeCheckout();
    if (event.target.closest('#listen-plan')) readPlan();
    if (event.target.closest('#copy-upi')) navigator.clipboard?.writeText(state.config?.upi_id || '').then(() => toast('UPI ID copied.')).catch(() => toast('Copy the UPI ID shown above.'));
    if (event.target.closest('[data-reload-plans]')) loadPlans();
    if (event.target.closest('#check-payment-status')) checkPaymentStatus($('#plan-phone').value).catch(error => toast(error.message));
    const verify = event.target.closest('[data-verify]');
    if (verify) ownerApi('/owner/verify-claim', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ claim_id: Number(verify.dataset.verify), decision: verify.dataset.decision }) }).then(refreshOwner).catch(error => { toast(error.message); if ([401, 429, 503].includes(error.status)) clearOwner(); });
    const proof = event.target.closest('[data-proof]');
    if (proof) showProof(Number(proof.dataset.proof)).catch(error => toast(error.message));
    if (event.target.closest('#close-proof') || event.target === $('#proof-modal')) closeProof();
    if (event.target === $('#payment-modal')) closeCheckout();
    if (event.target.closest('#owner-unlock')) unlockOwner();
    if (event.target.closest('#owner-lock')) clearOwner();
    if (event.target.closest('#save-owner-tiers')) saveOwnerTiers();
  });

  document.addEventListener('submit', event => {
    if (event.target.id === 'payment-claim-form') { event.preventDefault(); submitClaim(event.target); }
    if (event.target.id === 'owner-settings') { event.preventDefault(); saveOwnerSettings(event.target); }
  });
  $('#owner-pin')?.addEventListener('keydown', event => { if (event.key === 'Enter') unlockOwner(); });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') { closeCheckout(); closeProof(); }
  });
  window.addEventListener('hashchange', () => {
    const view = location.hash.slice(1);
    if (view === 'plans') loadPlans();
    if (view !== 'owner' && state.ownerPin) { closeProof(); clearOwner(); }
  });
  loadPlans();
})();
