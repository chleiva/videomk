/* VideoMK owner console (docs/ADMIN_CONSOLE_DESIGN_2026-11-28.md, slice one). One file, no library, no outside request except the admin pool's own
   Cognito endpoint. Tokens live in this page's memory only: closing or reloading the tab signs out. Nothing here is secret: the page is an empty shell
   and the API answers nothing without a valid token. */
(function () {
  'use strict';
  var cfg = null;
  var session = null;            // {access, id, refresh, exp, authTime}
  var refreshTimer = null, reloadTimer = null;
  var home = null, lastError = null, open = {};
  var app = document.getElementById('app');
  var USER_KEY = 'vmk-console-user';   // the sign-in name only (not a secret), so the passkey button works with one tap

  // ---------------------------------------------------------------- small helpers
  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v; else if (k.slice(0, 2) === 'on') n.addEventListener(k.slice(2), v); else n.setAttribute(k, v === true ? '' : v);
    });
    (Array.isArray(kids) ? kids : kids === undefined ? [] : [kids]).forEach(function (c) { if (c !== null && c !== undefined && c !== false) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return n;
  }
  function svg(tag, attrs) {
    var n = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    return n;
  }
  function show() { app.replaceChildren.apply(app, Array.prototype.slice.call(arguments).filter(Boolean)); }
  function known(v) { return v !== null && v !== undefined && !(typeof v === 'number' && isNaN(v)); }
  function usd(v) { return known(v) ? '$' + Number(v).toFixed(v >= 100 ? 0 : 2) : 'not available'; }
  function pct(v) { return known(v) ? (v * 100).toFixed(v * 100 >= 10 || v === 0 ? 0 : 1) + ' %' : 'no finished videos'; }
  function dur(s) { if (!known(s)) return 'not available'; s = Math.round(s); return s >= 60 ? Math.floor(s / 60) + ' m ' + ('0' + (s % 60)).slice(-2) + ' s' : s + ' s'; }
  function hhmm(iso) { return iso ? String(iso).slice(11, 16) : ''; }
  function ago(iso) {
    if (!iso) return 'never';
    var m = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
    return m < 1 ? 'just now' : m < 60 ? m + ' min ago' : m < 1440 ? Math.floor(m / 60) + ' h ' + (m % 60) + ' min ago' : Math.floor(m / 1440) + ' days ago';
  }
  function dayLabel(day) { var d = new Date(day + 'T00:00:00Z'); return ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getUTCDay()] + ' ' + d.getUTCDate(); }
  function b64uToBuf(s) { s = s.replace(/-/g, '+').replace(/_/g, '/'); while (s.length % 4) s += '='; var b = atob(s), a = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) a[i] = b.charCodeAt(i); return a.buffer; }
  function bufToB64u(buf) { var a = new Uint8Array(buf), s = ''; for (var i = 0; i < a.length; i++) s += String.fromCharCode(a[i]); return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); }
  function jwtPayload(t) { try { return JSON.parse(new TextDecoder().decode(b64uToBuf(t.split('.')[1]))); } catch (e) { return {}; } }
  function savedUser() { try { return localStorage.getItem(USER_KEY) || ''; } catch (e) { return ''; } }
  function saveUser(u) { try { localStorage.setItem(USER_KEY, u); } catch (e) { /* private mode: typed each time */ } }

  // ---------------------------------------------------------------- Cognito (the admin pool only), plain HTTPS calls
  function cognito(action, body) {
    return fetch('https://cognito-idp.' + cfg.region + '.amazonaws.com/', {
      method: 'POST', cache: 'no-store', referrerPolicy: 'no-referrer',
      headers: { 'Content-Type': 'application/x-amz-json-1.1', 'X-Amz-Target': 'AWSCognitoIdentityProviderService.' + action },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) { var e = new Error(j.message || j.Message || 'Sign-in service error'); e.code = String(j.__type || '').split('#').pop(); throw e; }
        return j;
      });
    });
  }
  function plainError(e) {
    var c = e && e.code;
    if (c === 'NotAuthorizedException' || c === 'UserNotFoundException') return 'That did not match. Check the name, the password or the code and try again.';
    if (c === 'CodeMismatchException' || c === 'EnableSoftwareTokenMFAException') return 'That code is not right. Wait for the next code in your authenticator app and try again.';
    if (c === 'InvalidPasswordException') return 'That password does not meet the rules: at least 20 characters with a lower-case letter, a capital letter and a number.';
    if (c === 'PasswordResetRequiredException') return 'The password must be reset from the command line (see the runbook).';
    if (c === 'TooManyRequestsException' || c === 'LimitExceededException') return 'Too many tries. Wait a minute and try again.';
    if (e && e.name === 'NotAllowedError') return 'The passkey check was cancelled or timed out. Try again.';
    if (e && e.name === 'InvalidStateError') return 'This device already has a passkey for the console.';
    if (e && e.name === 'SecurityError') return 'The passkey does not belong to this address.';
    return (e && e.message) || 'Something went wrong. Try again.';
  }
  function setSession(r) {
    var a = r.AuthenticationResult, p = jwtPayload(a.AccessToken);
    session = { access: a.AccessToken, id: a.IdToken, refresh: a.RefreshToken || (session && session.refresh), exp: (p.exp || 0) * 1000, authTime: (p.auth_time || 0) * 1000 };
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(renew, Math.max(15000, session.exp - Date.now() - 90000));
  }
  function renew() {
    if (!session || !session.refresh) return signOut('Your session ended. Sign in again.');
    cognito('InitiateAuth', { AuthFlow: 'REFRESH_TOKEN_AUTH', ClientId: cfg.clientId, AuthParameters: { REFRESH_TOKEN: session.refresh } })
      .then(setSession).catch(function () { signOut('Your session ended (sessions last at most an hour). Sign in again.'); });
  }
  function signOut(message) {
    var s = session;
    session = null; home = null; clearTimeout(refreshTimer); clearInterval(reloadTimer);
    if (s && s.refresh) cognito('RevokeToken', { ClientId: cfg.clientId, Token: s.refresh }).catch(function () {});
    viewSignIn(message || 'You are signed out.');
  }
  function credentialJson(cred) {
    if (typeof cred.toJSON === 'function') { try { return cred.toJSON(); } catch (e) { /* fall through */ } }
    var r = cred.response, out = { id: cred.id, rawId: bufToB64u(cred.rawId), type: cred.type, clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {}, response: { clientDataJSON: bufToB64u(r.clientDataJSON) } };
    if (cred.authenticatorAttachment) out.authenticatorAttachment = cred.authenticatorAttachment;
    if (r.attestationObject) { out.response.attestationObject = bufToB64u(r.attestationObject); out.response.transports = r.getTransports ? r.getTransports() : []; }
    if (r.authenticatorData) out.response.authenticatorData = bufToB64u(r.authenticatorData);
    if (r.signature) out.response.signature = bufToB64u(r.signature);
    if (r.userHandle) out.response.userHandle = bufToB64u(r.userHandle);
    return out;
  }
  function requestOptions(o) {
    var out = Object.assign({}, o, { challenge: b64uToBuf(o.challenge) });
    if (o.allowCredentials) out.allowCredentials = o.allowCredentials.map(function (c) { return Object.assign({}, c, { id: b64uToBuf(c.id) }); });
    return out;
  }
  function creationOptions(o) {
    var out = Object.assign({}, o, { challenge: b64uToBuf(o.challenge), user: Object.assign({}, o.user, { id: b64uToBuf(o.user.id) }) });
    if (o.excludeCredentials) out.excludeCredentials = o.excludeCredentials.map(function (c) { return Object.assign({}, c, { id: b64uToBuf(c.id) }); });
    return out;
  }
  // the normal way in, and the "confirm" before a switch: one passkey check (Face ID, fingerprint or the device passcode)
  function passkeySignIn(user) {
    return cognito('InitiateAuth', { AuthFlow: 'USER_AUTH', ClientId: cfg.clientId, AuthParameters: { USERNAME: user, PREFERRED_CHALLENGE: 'WEB_AUTHN' } }).then(function (r) {
      if (r.ChallengeName !== 'WEB_AUTHN') { var e = new Error('There is no passkey for this name yet. Use the recovery sign-in below, then add a passkey.'); e.code = 'NoPasskey'; throw e; }
      var opts = JSON.parse(r.ChallengeParameters.CREDENTIAL_REQUEST_OPTIONS);
      return navigator.credentials.get({ publicKey: requestOptions(opts) }).then(function (cred) {
        return cognito('RespondToAuthChallenge', { ChallengeName: 'WEB_AUTHN', ClientId: cfg.clientId, Session: r.Session, ChallengeResponses: { USERNAME: user, CREDENTIAL: JSON.stringify(credentialJson(cred)) } });
      });
    }).then(function (r) {
      if (!r.AuthenticationResult) throw new Error('The sign-in did not finish. Try again.');
      setSession(r); saveUser(user);
    });
  }
  function addPasskey() {
    return cognito('StartWebAuthnRegistration', { AccessToken: session.access }).then(function (r) {
      return navigator.credentials.create({ publicKey: creationOptions(r.CredentialCreationOptions) });
    }).then(function (cred) { return cognito('CompleteWebAuthnRegistration', { AccessToken: session.access, Credential: credentialJson(cred) }); });
  }
  function randomPassword() {
    var set = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789', a = new Uint32Array(40), s = '';
    crypto.getRandomValues(a);
    for (var i = 0; i < a.length; i++) s += set[a[i] % set.length];
    return 'aA2' + s.slice(3);   // always has the three kinds the rules ask for
  }

  // ---------------------------------------------------------------- sign-in screens
  function form(title, intro, fields, button, onsubmit, extra) {
    var err = el('p', { class: 'err', hidden: true, role: 'alert' });
    var btn = el('button', { class: 'primary', type: 'submit', text: button });
    var f = el('form', { novalidate: true, onsubmit: function (ev) {
      ev.preventDefault(); err.hidden = true; btn.disabled = true;
      Promise.resolve().then(function () { return onsubmit(f); }).catch(function (e) { err.textContent = plainError(e); err.hidden = false; }).then(function () { btn.disabled = false; });
    } }, [el('h1', { text: title })].concat(intro || [], fields, [err, btn], extra || []));
    show(f);
    var first = f.querySelector('input:not([value]), input'); if (first && !('ontouchstart' in window)) first.focus();
    return f;
  }
  function field(name, label, attrs) { return [el('label', { for: 'f-' + name, text: label }), el('input', Object.assign({ id: 'f-' + name, name: name, autocapitalize: 'none', autocorrect: 'off', spellcheck: 'false' }, attrs || {}))]; }

  function viewSignIn(message) {
    var canPasskey = cfg.passkeys && window.PublicKeyCredential;
    form('Sign in', [message ? el('p', { class: 'note', text: message }) : null,
      !cfg.passkeys ? el('p', { class: 'note', text: 'Passkeys are not switched on for this console yet. Use the password and the authenticator code.' }) : null],
      field('user', 'Sign-in name (your email)', { type: 'email', autocomplete: 'username webauthn', value: savedUser() || null, required: true }),
      canPasskey ? 'Sign in with passkey' : 'Continue',
      function (f) {
        var user = f.elements.user.value.trim();
        if (!user) throw new Error('Type your sign-in name.');
        if (!canPasskey) return viewRecovery(user);
        return passkeySignIn(user).then(afterSignIn);
      },
      [el('button', { class: 'link', type: 'button', text: 'Recovery or first sign-in: password and authenticator code', onclick: function () { viewRecovery((document.getElementById('f-user') || {}).value || savedUser()); } })]);
  }
  function viewRecovery(user) {
    form('Password sign-in', [el('p', { class: 'note', text: 'For the first sign-in (with the temporary password from the invitation email) and for recovery. Never type these into a page reached from a link in an email: open this address yourself.' })],
      field('user', 'Sign-in name (your email)', { type: 'email', autocomplete: 'username', value: (user || '').trim() || null, required: true }).concat(field('password', 'Password', { type: 'password', autocomplete: 'current-password', required: true })),
      'Continue',
      function (f) {
        var u = f.elements.user.value.trim();
        return cognito('InitiateAuth', { AuthFlow: 'USER_AUTH', ClientId: cfg.clientId, AuthParameters: { USERNAME: u, PREFERRED_CHALLENGE: 'PASSWORD', PASSWORD: f.elements.password.value } }).then(function (r) { return challenge(u, r); });
      },
      [el('button', { class: 'link', type: 'button', text: 'Back to passkey sign-in', onclick: function () { viewSignIn(); } })]);
  }
  // Cognito answers each step with what it needs next; this walks them until tokens arrive.
  function challenge(user, r) {
    if (r.AuthenticationResult) { setSession(r); saveUser(user); return afterSignIn(true); }
    var respond = function (name, answers) { return cognito('RespondToAuthChallenge', { ChallengeName: name, ClientId: cfg.clientId, Session: r.Session, ChallengeResponses: Object.assign({ USERNAME: user }, answers) }).then(function (n) { return challenge(user, n); }); };
    if (r.ChallengeName === 'SELECT_CHALLENGE') {
      return form('Password', [], field('password', 'Password', { type: 'password', autocomplete: 'current-password', required: true }), 'Continue', function (f) { return respond('SELECT_CHALLENGE', { ANSWER: 'PASSWORD', PASSWORD: f.elements.password.value }); });
    }
    if (r.ChallengeName === 'NEW_PASSWORD_REQUIRED') {
      var made = randomPassword();
      return form('Choose your recovery password', [
        el('p', { class: 'note', text: 'This password is only for recovery; day to day you will use the passkey. Use a long random one and keep it OFF this phone (a password manager on another device, or printed). Here is one made on this device just now:' }),
        el('p', { class: 'secret', text: made }),
        el('p', { class: 'note', text: 'Save it before you continue: it is not shown again and nobody can read it back.' })],
        field('np', 'New password (at least 20 characters)', { type: 'text', autocomplete: 'new-password', value: made, required: true, minlength: 20 }), 'I saved it. Continue',
        function (f) { return respond('NEW_PASSWORD_REQUIRED', { NEW_PASSWORD: f.elements.np.value }); });
    }
    if (r.ChallengeName === 'MFA_SETUP') {
      return cognito('AssociateSoftwareToken', { Session: r.Session }).then(function (a) {
        var link = 'otpauth://totp/' + encodeURIComponent('VideoMK console (' + cfg.stage + ')') + '?secret=' + a.SecretCode + '&issuer=' + encodeURIComponent('VideoMK console');
        return form('Add your authenticator app', [
          el('p', { class: 'note', text: 'The authenticator code is the second half of the recovery sign-in. Add this key to an authenticator app (best on another device than this phone):' }),
          el('p', { class: 'secret', text: a.SecretCode }),
          el('p', {}, el('a', { href: link, text: 'Open in an authenticator app on this device' })),
          el('p', { class: 'note', text: 'Then type the 6-digit code the app shows.' })],
          field('code', 'Code from the app', { type: 'text', inputmode: 'numeric', autocomplete: 'one-time-code', pattern: '[0-9]*', maxlength: 6, required: true }), 'Continue',
          function (f) {
            return cognito('VerifySoftwareToken', { Session: a.Session, UserCode: f.elements.code.value.trim(), FriendlyDeviceName: 'authenticator' }).then(function (v) {
              return cognito('RespondToAuthChallenge', { ChallengeName: 'MFA_SETUP', ClientId: cfg.clientId, Session: v.Session, ChallengeResponses: { USERNAME: user } });
            }).then(function (n) { return challenge(user, n); });
          });
      });
    }
    if (r.ChallengeName === 'SOFTWARE_TOKEN_MFA') {
      return form('Authenticator code', [], field('code', 'Code from your authenticator app', { type: 'text', inputmode: 'numeric', autocomplete: 'one-time-code', pattern: '[0-9]*', maxlength: 6, required: true }), 'Sign in',
        function (f) { return respond('SOFTWARE_TOKEN_MFA', { SOFTWARE_TOKEN_MFA_CODE: f.elements.code.value.trim() }); });
    }
    throw new Error('This sign-in step is not supported here (' + (r.ChallengeName || 'unknown') + ').');
  }
  function afterSignIn(byPassword) {
    if (byPassword === true && cfg.passkeys && window.PublicKeyCredential) {
      return cognito('ListWebAuthnCredentials', { AccessToken: session.access }).then(function (l) { return (l.Credentials || []).length; }).catch(function () { return 1; }).then(function (n) {
        if (n) return viewHome();
        form('Add a passkey', [el('p', { class: 'note', text: 'A passkey is how you sign in from now on: one Face ID or fingerprint check, nothing to type, and it only works on this address. It is also the check asked before a switch.' })],
          [], 'Add a passkey on this device', function () { return addPasskey().then(function () { viewHome('Passkey added. Next time, sign in with it.'); }); },
          [el('button', { class: 'link', type: 'button', text: 'Not now', onclick: function () { viewHome(); } })]);
      });
    }
    return viewHome();
  }

  // ---------------------------------------------------------------- the one screen
  function api(method, path, body) {
    return fetch(path, { method: method, cache: 'no-store', credentials: 'omit', referrerPolicy: 'no-referrer',
      headers: Object.assign({ Authorization: 'Bearer ' + session.access }, body ? { 'Content-Type': 'application/json' } : {}), body: body ? JSON.stringify(body) : undefined })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) { var e = new Error(j.message || ('The console answered ' + r.status)); e.status = r.status; e.code = j.code; throw e; } return j; }); });
  }
  function viewHome(notice) {
    clearInterval(reloadTimer);
    reloadTimer = setInterval(function () { if (session && !document.hidden && !document.querySelector('dialog[open]')) load(); }, 60000);
    render(notice);
    return load();
  }
  function load() {
    if (!session) return Promise.resolve();
    return api('GET', '/api/home').then(function (j) { home = j; lastError = null; render(); }).catch(function (e) {
      if (e.status === 401 || e.status === 403) return signOut('Your session ended. Sign in again.');
      lastError = 'Could not load the numbers' + (e.message ? ': ' + e.message : '') + '.'; render();
    });
  }
  function series(days, key) { return days.map(function (d) { return { day: d.day, v: d.missing || !known(d[key]) ? null : Number(d[key]) }; }); }
  function spark(points, fmt, label) {
    var W = 160, H = 34, pad = 5, cap = el('div', { class: 'cap', text: '7 days' });
    var vals = points.filter(function (p) { return p.v !== null; }).map(function (p) { return p.v; });
    var s = svg('svg', { class: 'spark', viewBox: '0 0 ' + W + ' ' + H, preserveAspectRatio: 'none', role: 'img', 'aria-label': label + ', last 7 days: ' + points.map(function (p) { return dayLabel(p.day) + ' ' + (p.v === null ? 'no data' : fmt(p.v)); }).join(', ') });
    s.appendChild(svg('line', { class: 'base', x1: 0, x2: W, y1: H - 1, y2: H - 1 }));
    if (!vals.length) { cap.textContent = 'no history yet'; return [s, cap]; }
    var max = Math.max.apply(null, vals.concat([0])), min = Math.min.apply(null, vals.concat([0])), span = max - min || 1;
    var x = function (i) { return pad + i * (W - 2 * pad) / Math.max(1, points.length - 1); }, y = function (v) { return H - pad - (v - min) / span * (H - 2 * pad); };
    var d = '', pen = false, last = null;
    points.forEach(function (p, i) { if (p.v === null) { pen = false; return; } d += (pen ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(p.v).toFixed(1); pen = true; last = i; });
    s.appendChild(svg('path', { class: 'ln', d: d, 'vector-effect': 'non-scaling-stroke' }));
    var pick = svg('circle', { class: 'pick', r: 3, cx: -10, cy: -10 });
    s.appendChild(svg('circle', { class: 'dot', r: 3.5, cx: x(last), cy: y(points[last].v) }));
    s.appendChild(pick);
    points.forEach(function (p, i) {   // a wide target per day: tap or hover reads that day's value
      var hit = svg('rect', { class: 'hit', x: x(i) - (W / points.length) / 2, y: 0, width: W / points.length, height: H });
      var on = function () { cap.textContent = dayLabel(p.day) + ': ' + (p.v === null ? 'no data' : fmt(p.v)); if (p.v !== null) { pick.setAttribute('cx', x(i)); pick.setAttribute('cy', y(p.v)); } };
      hit.addEventListener('pointerenter', on); hit.addEventListener('click', on);
      s.appendChild(hit);
    });
    s.addEventListener('pointerleave', function () { cap.textContent = '7 days'; pick.setAttribute('cx', -10); });
    return [s, cap];
  }
  function tile(title, big, sub, est, points, fmt) {
    return el('section', { class: 'card' }, [el('h2', { text: title }), el('div', { class: 'big num', text: big }), el('div', { class: 'sub num' + (est ? ' est' : ''), text: sub })].concat(spark(points, fmt, title)));
  }
  function statusOf(h) {
    var bad = [], warn = [], sw = h.switches || {}, meta = h.meta || {}, today = (h.days || [])[(h.days || []).length - 1] || {};
    var since = sw.updated_at ? ' since ' + hhmm(sw.updated_at) + ' UTC' : '';
    if (sw.stop_new_videos) bad.push('New videos are OFF' + since + '.');
    if (sw.stop_free_videos) warn.push('Free videos are OFF' + since + '.');
    if (sw.error) warn.push('The switches could not be read.');
    var hr = meta.hour || {}, fin = (hr.failed || 0) + (hr.complete || 0);
    if (hr.failed >= 3 && fin && hr.failed / fin > 0.2) bad.push('Videos are failing: ' + hr.failed + ' of ' + fin + ' in the last hour.');
    if (h.alarms && h.alarms.firing && h.alarms.firing.length) bad.push(h.alarms.firing.length + (h.alarms.firing.length === 1 ? ' alarm is' : ' alarms are') + ' firing.');
    if (meta.missing || !meta.updated_at) warn.push('No numbers yet: the hourly job has not finished a run.');
    else if (Date.now() - Date.parse(meta.updated_at) > 130 * 60000) bad.push('The numbers are old: last update ' + ago(meta.updated_at) + '.');
    if (meta.stuck && meta.stuck.length) warn.push(meta.stuck.length + (meta.stuck.length === 1 ? ' video has' : ' videos have') + ' been going for over 30 minutes.');
    if (h.running && h.running.oldest_minutes >= 30 && !(meta.stuck && meta.stuck.length)) warn.push('A video has been going for ' + h.running.oldest_minutes + ' minutes.');
    var b = h.budget || {};
    if (!b.error && !b.unlimited && b.limit > 0 && b.spent >= b.limit) warn.push('Today\'s free budget is used up: free videos are paused until 00:00 UTC.');
    else if (!b.error && !b.unlimited && b.limit > 0 && b.spent >= 0.8 * b.limit) warn.push('The free budget is at ' + Math.round(100 * b.spent / b.limit) + ' %.');
    if ((meta.partial || []).length) warn.push('Some numbers could not be worked out this hour (' + meta.partial.join(', ').replace(/_/g, ' ') + ').');
    ['days', 'failures', 'running', 'budget', 'alarms'].forEach(function (k) { if (h[k] && h[k].error) warn.push('Part of the page could not be loaded (' + k + ').'); });
    if (known(today.failure_rate) && today.failure_rate > 0.2 && today.failed >= 3 && !bad.length) warn.push('Today\'s failure rate is ' + pct(today.failure_rate) + '.');
    return { level: bad.length ? 'bad' : warn.length ? 'warn' : 'good', lines: bad.concat(warn) };
  }
  function render(notice) {
    document.getElementById('clock').textContent = new Date().toISOString().slice(11, 16) + ' UTC';
    var parts = [];
    if (notice) parts.push(el('p', { class: 'note', text: notice }));
    if (lastError) parts.push(el('div', { class: 'err', role: 'alert' }, [lastError + ' ', el('button', { class: 'link', type: 'button', text: 'Try again', onclick: load })]));
    if (!home) { parts.push(lastError ? null : el('p', { class: 'muted pad', text: 'Loading the numbers…' })); parts.push(footer()); return show.apply(null, parts); }
    var h = home, days = Array.isArray(h.days) ? h.days : [], t = days[days.length - 1] || { missing: true }, meta = h.meta || {}, st = statusOf(h);
    parts.push(el('div', { class: 'status ' + st.level, role: 'status' }, [
      el('span', { class: 'mark', 'aria-hidden': 'true', text: st.level === 'good' ? '✓' : st.level === 'warn' ? '!' : '✕' }),
      el('div', { class: 'grow' }, [el('div', { text: st.level === 'good' ? 'All good' : st.level === 'warn' ? 'Look at this' : 'Needs you now' }), st.lines.length ? el('ul', { class: 'why' }, st.lines.map(function (l) { return el('li', { text: l }); })) : null]),
      el('span', { class: 'upd', text: 'updated ' + ago(meta.updated_at) })]));
    var no = t.missing, run = h.running || {};
    var runText = run.error ? 'in progress: not available' : (run.count || 0) + (run.more ? '+' : '') + ' in progress now';
    var seven = function (k) { return days.reduce(function (a, d) { return a + (d.missing ? 0 : Number(d[k] || 0)); }, 0); };
    parts.push(el('div', { class: 'grid' }, [
      tile('Made today', no ? 'no data' : String(t.complete), runText + (no ? '' : ' · ' + t.started + ' started'), false, series(days, 'complete'), function (v) { return v + ' made'; }),
      tile('Failure rate', no ? 'no data' : pct(t.failure_rate), no ? '' : t.failed + ' failed of ' + (t.failed + t.complete) + ' finished', false, series(days, 'failure_rate'), pct),
      tile('Time to make', no ? 'no data' : dur(t.make_p50_s), no ? '' : known(t.make_p95_s) ? 'slowest 1 in 20: ' + dur(t.make_p95_s) : 'no finished video today', false, series(days, 'make_p50_s'), dur),
      tile('Cost today', no ? 'no data' : usd(t.cost_all_in), no ? '' : known(t.cost_per_video) ? usd(t.cost_per_video) + ' a video' : 'no finished video today', !no, series(days, 'cost_all_in'), usd),
      tile('Lost on failed', no ? 'no data' : usd(t.lost_usd), no ? '' : usd(seven('lost_usd')) + ' in 7 days · ' + t.failed + ' failed, ' + t.cancelled + ' cancelled', !no, series(days, 'lost_usd'), usd),
      tile('People', no ? 'no data' : (known(t.signups) ? t.signups + ' sign-up' + (t.signups === 1 ? '' : 's') : 'sign-ups n/a'), no ? '' : t.active_accounts + ' active today', false, series(days, 'active_accounts'), function (v) { return v + ' active'; })
    ]));
    if (meta.includes_test_accounts) parts.push(el('p', { class: 'muted', text: 'On this stage the numbers include test accounts.' }));
    parts.push(budgetCard(h.budget || { error: true }));
    parts.push(failuresCard(h.failures));
    parts.push(switchesCard(h.switches || { error: true }));
    parts.push(alarmsCard(h.alarms || { error: true }));
    parts.push(tableCard(days));
    parts.push(aboutCard(meta));
    parts.push(footer());
    show.apply(null, parts);
  }
  function budgetCard(b) {
    var kids = [el('h2', { text: 'Free budget today' })];
    if (b.error) kids.push(el('p', { class: 'note', text: 'Not available right now.' }));
    else if (b.unlimited) kids.push(el('p', { class: 'num', text: b.spent + ' free credits used. No daily limit is set (about ' + usd(b.spent_usd) + ').' }));
    else if (!b.limit) kids.push(el('p', { class: 'num', text: 'The budget is 0: no free videos today.' }));
    else {
      var share = Math.min(1, b.spent / b.limit), g = svg('svg', { class: 'gauge', viewBox: '0 0 100 14', preserveAspectRatio: 'none', role: 'img', 'aria-label': b.spent + ' of ' + b.limit + ' free credits used' });
      g.appendChild(svg('rect', { class: 'track', x: 0, y: 0, width: 100, height: 14, rx: 4 }));
      if (share > 0) g.appendChild(svg('rect', { class: 'fill' + (share >= 1 ? ' bad' : share >= 0.8 ? ' warn' : ''), x: 0, y: 0, width: Math.max(3, share * 100), height: 14, rx: 4 }));
      kids.push(g, el('div', { class: 'num', text: b.spent + ' of ' + b.limit + ' credits' + (share >= 1 ? ' · used up, free videos paused until 00:00 UTC' : '') }), el('div', { class: 'sub num', text: 'about ' + usd(b.spent_usd) + ' of ' + usd(b.limit_usd) + ' · live' }));
    }
    return el('section', { class: 'card' }, kids);
  }
  function failuresCard(list) {
    var kids = [el('h2', { text: 'Failed and cancelled' })];
    if (!Array.isArray(list)) { kids.push(el('p', { class: 'note', text: 'Not available right now.' })); return el('section', { class: 'card' }, kids); }
    if (!list.length) { kids.push(el('p', { class: 'note', text: 'None in the last 7 days.' })); return el('section', { class: 'card' }, kids); }
    var today = new Date().toISOString().slice(0, 10), all = open.failures;
    kids.push(el('ul', { class: 'rows' }, (all ? list : list.slice(0, 5)).map(function (f) {
      var key = f.at + f.video_id, when = String(f.at).slice(0, 10) === today ? hhmm(f.at) : String(f.at).slice(5, 10);
      var short = f.status === 'CANCELLED' ? 'cancelled by the person' : String(f.cause || 'unknown').split(' (')[0];
      return el('li', {}, [
        el('button', { class: 'rowbtn', type: 'button', 'aria-expanded': open[key] ? 'true' : 'false', onclick: function () { open[key] = !open[key]; render(); } },
          [el('span', { class: 'num', text: when }), el('span', { text: f.status === 'CANCELLED' ? '' : (f.step || 'step n/a') }), el('span', { class: 'c', text: short }), el('span', { class: 'num', text: usd(f.cost_usd) })]),
        open[key] ? el('dl', { class: 'detail' }, [['When', String(f.at).replace('T', ' ').replace('Z', ' UTC')], ['What', f.status === 'CANCELLED' ? 'Cancelled by the person' : 'Failed'],
          ['Step', f.status === 'CANCELLED' ? 'n/a' : (f.step || 'not known')], ['Cause', f.cause || 'unknown'], ['Error name', f.code || 'n/a'], ['Cost (tracked)', usd(f.cost_usd)], ['Plan', f.plan || 'unknown'],
          ['Length', known(f.length_s) ? dur(f.length_s) : (f.credits ? 'not rendered; asked for up to ' + f.credits + ' min' : 'not rendered')], ['Shape', [f.aspect, f.resolution].filter(Boolean).join(' · ') || 'not known'],
          ['Tries', String((f.retries || 0) + 1)], ['Video', f.video_id]].reduce(function (a, p) { return a.concat([el('dt', { text: p[0] }), el('dd', { text: p[1] })]); }, [])) : null]);
    })));
    if (list.length > 5) kids.push(el('button', { class: 'link', type: 'button', text: all ? 'Show fewer' : 'Show all ' + list.length, onclick: function () { open.failures = !all; render(); } }));
    return el('section', { class: 'card' }, kids);
  }
  var WORDS = {
    stop_new_videos: { name: 'New videos', off: 'Nobody can start or retry a video. Videos being made finish. Watching, the library and sign-in keep working.', on: 'Everyone can make videos.' },
    stop_free_videos: { name: 'Free videos', off: 'Free credits cannot be spent. Paid credits work.', on: 'Free credits can be spent, within the daily budget.' }
  };
  function switchesCard(sw) {
    var kids = [el('h2', { text: 'Switches' })];
    if (sw.error) kids.push(el('p', { class: 'note', text: 'The switches could not be read. The runbook has the command to read and set them.' }));
    else Object.keys(WORDS).forEach(function (k) {
      var stopped = sw[k] === true, w = WORDS[k];
      kids.push(el('div', { class: 'switch' }, [el('div', { class: 'what' }, [w.name, el('small', { text: stopped ? w.off : w.on })]),
        el('button', { class: 'toggle' + (stopped ? ' off' : ''), type: 'button', 'aria-pressed': stopped ? 'false' : 'true', 'aria-label': w.name + ': ' + (stopped ? 'off' : 'on') + '. Change', text: stopped ? 'OFF' : 'ON', onclick: function () { confirmSwitch(k, !stopped); } })]));
    });
    kids.push(el('p', { class: 'muted', text: 'A change asks for your passkey, takes about a minute to apply, and emails you.' }));
    return el('section', { class: 'card' }, kids);
  }
  function confirmSwitch(name, stop) {
    var w = WORDS[name], err = el('p', { class: 'err', hidden: true, role: 'alert' });
    var go = el('button', { class: 'primary', type: 'button', text: stop ? 'Switch ' + w.name.toLowerCase() + ' OFF' : 'Switch ' + w.name.toLowerCase() + ' back ON' });
    var d = el('dialog', {}, [el('h1', { text: (stop ? 'Stop ' : 'Allow ') + w.name.toLowerCase() + '?' }), el('p', { text: stop ? w.off : w.on }), el('p', { class: 'note', text: 'You will be asked for your passkey.' }), err, go,
      el('button', { class: 'plain', type: 'button', text: 'Cancel', onclick: function () { d.close(); d.remove(); } })]);
    go.addEventListener('click', function () {
      go.disabled = true; err.hidden = true;
      var fresh = session && Date.now() - session.authTime < (cfg.stepUpSeconds - 20) * 1000;
      var check = fresh ? Promise.resolve() : (cfg.passkeys && window.PublicKeyCredential && savedUser() ? passkeySignIn(savedUser()) : Promise.reject(new Error('Sign out and sign in again, then change the switch within 5 minutes.')));
      check.then(function () { return api('POST', '/api/switches', { 'switch': name, stopped: stop }); }).then(function (j) {
        if (home) home.switches = j.switches;
        d.close(); d.remove(); render(w.name + ' are now ' + (stop ? 'OFF' : 'ON') + '. It applies within about a minute.');
      }).catch(function (e) { err.textContent = e.code === 'step_up_required' ? 'The passkey check was too long ago. Try again.' : plainError(e); err.hidden = false; go.disabled = false; });
    });
    document.body.appendChild(d); d.showModal();
  }
  function alarmsCard(a) {
    if (a.error) return el('section', { class: 'card' }, [el('h2', { text: 'Alarms' }), el('p', { class: 'note', text: 'Not available right now.' })]);
    var firing = a.firing || [];
    return el('section', { class: 'card' }, [el('h2', { text: 'Alarms' }), el('p', { class: 'num', text: firing.length + ' firing of ' + a.total })].concat(
      firing.map(function (f) { return el('p', { class: 'note', text: f.name + ' since ' + hhmm(f.since) + ' UTC. ' + (f.what || '') }); })));
  }
  function tableCard(days) {
    var head = ['Day', 'Made', 'Failed', 'Cancelled', 'Rate', 'p50', 'p95', 'Cost', 'Lost', 'Sign-ups', 'Active'];
    var rows = days.slice().reverse().map(function (d) {
      return el('tr', {}, (d.missing ? [dayLabel(d.day)].concat(head.slice(1).map(function () { return '–'; })) :
        [dayLabel(d.day), d.complete, d.failed, d.cancelled, known(d.failure_rate) ? pct(d.failure_rate) : '–', known(d.make_p50_s) ? dur(d.make_p50_s) : '–', known(d.make_p95_s) ? dur(d.make_p95_s) : '–', usd(d.cost_all_in), usd(d.lost_usd), known(d.signups) ? d.signups : '–', d.active_accounts])
        .map(function (v) { return el('td', { class: 'num', text: String(v) }); }));
    });
    return el('details', { class: 'card' }, [el('summary', { text: 'The last 7 days as a table' }), el('div', { class: 'scroll' }, el('table', {}, [el('thead', {}, el('tr', {}, head.map(function (x) { return el('th', { scope: 'col', text: x }); }))), el('tbody', {}, rows)]))]);
  }
  function aboutCard(meta) {
    var lines = [
      'Days are UTC days. The numbers are worked out once an hour from the video records; "updated" says when. Runs in progress, the free budget, the switches and the alarms are read live.',
      'Made: videos started that day that are complete. Failure rate: failed / (complete + failed); cancelled and refused requests are not in it.',
      'Time to make: from the start of the workflow to its end, for videos that finished on their first run. The middle value, and the value 19 of 20 videos stay under.',
      'Cost: what the models, speech and searches cost (recorded on each video) plus the compute of the render functions for the day. Compute is known per day, so its share per video is an estimate.',
      'Lost on failed: the cost of failed and cancelled videos (their credits are given back), plus their share of the compute.',
      'People: new confirmed accounts that day, and accounts that started at least one video.',
      'No prompt text, account name or email address is shown or stored by this console.'
    ];
    if (meta && meta.source === 'scan') lines.push('Note: the day index is not deployed yet, so the job reads the videos table with a scan of the same small fields.');
    return el('details', { class: 'card' }, [el('summary', { text: 'What these numbers mean' })].concat(lines.map(function (l) { return el('p', { class: 'note', text: l }); })));
  }
  function footer() {
    return el('div', { class: 'foot' }, [el('button', { class: 'link', type: 'button', text: 'Refresh', onclick: load }), el('span', { class: 'grow' }),
      cfg.passkeys && window.PublicKeyCredential && session ? el('button', { class: 'link', type: 'button', text: 'Add a passkey', onclick: function () { addPasskey().then(function () { render('Passkey added.'); }).catch(function (e) { render(plainError(e)); }); } }) : null,
      el('button', { class: 'link', type: 'button', text: 'Sign out', onclick: function () { signOut(); } })]);
  }

  // ---------------------------------------------------------------- start
  fetch('config.json', { cache: 'no-store' }).then(function (r) { if (!r.ok) throw new Error('config'); return r.json(); }).then(function (c) {
    cfg = c;
    var badge = document.getElementById('stage'); badge.textContent = c.stage; badge.hidden = false;
    viewSignIn();
  }).catch(function () { show(el('p', { class: 'err', text: 'The console could not start (its settings did not load). Reload the page; if it stays like this, use the runbook.' })); });
})();
