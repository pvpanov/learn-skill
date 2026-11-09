/* submit-to-tutor.js: the shared per-answer "Submit to tutor" for learn study pages (owner, 2026-11-09).
 *
 * Load it once, after the page content:  <script src="submit-to-tutor.js" [data-drafts="KEY"|"off"]></script>
 * Publish it as a supporting file:       files: {"submit-to-tutor.js": "<abs path of this file>"}
 * and declare                            capabilities: {comments: {}}  (plus whatever else the page uses, e.g. db).
 *
 * What it does
 * - Every textarea[data-q], including ones the page renders later, gets a Submit button and a status line.
 *   data-q is the label the tutor sees ("r003", "Q1a"); keep it unique on the page.
 * - Anchor (where the comment thread sits): closest [data-tutor-anchor], else the closest .part (one sub-question),
 *   else the closest .box / .item / section.
 * - Question text sent with the answer: textarea[data-question] when set; otherwise the outer box's stem
 *   ([data-stem] or its first <p>) plus the .part's first <p>.
 * - Text sent (one line, under 4 KiB): "<q> answer: <answer> || Question: <question>".
 * - A second submit from the same box in the same visit replies into the same thread (data-thread="new" opts out).
 * - Bar placement: after the textarea, or after the element whose id is in data-submit-after.
 * - data-clear-on-send empties the box after a successful send (roleplay turns typed into one box).
 * - Drafts: kept in localStorage per data-q (key = data-drafts, else "tutor-drafts:" + document.title);
 *   data-drafts="off" when the page keeps its own drafts.
 * - Falls back to copying (or selecting) the answer when comments are unavailable or the send fails.
 *
 * Hooks for pages with their own saving (e.g. a db form)
 * - "tutor-before-submit" (bubbles, cancelable) on the textarea; detail {q, answer}. Change detail.answer to add
 *   context; preventDefault() cancels the send.
 * - "tutor-submitted" (bubbles) after a successful send; detail {q, answer, text, threadId, el}. Fired on the
 *   textarea, or on document if the page re-rendered it away meanwhile. Save to your db here.
 * - window.TutorSubmit.send({q, answer, question, el, kind, threadKey, newThread}) -> Promise<{threadId, text}>,
 *   rejects {code}. Call it straight from a click handler (sendToClaude needs the viewer's recent gesture), e.g.
 *   before awaiting a db write. kind replaces the word "answer" ("question", "fix").
 * - window.TutorSubmit.wire(): attach now (a MutationObserver also does it).
 * - A button[data-tutor-copy-all] copies every answer on the page.
 *
 * Keep this file ASCII: invisible or line-separator characters go in as \u escapes (check_page.py checks).
 */
(function () {
  'use strict';
  if (window.TutorSubmit) return;

  var me = document.currentScript;
  var draftsAttr = me ? me.getAttribute('data-drafts') : null;
  var KEY = draftsAttr === 'off' ? null : (draftsAttr || 'tutor-drafts:' + (document.title || location.pathname));
  var saved = {};
  if (KEY) { try { saved = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { saved = {}; } }
  function persist() { if (KEY) { try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) {} } }

  var MAX_ANSWER = 2800, MAX_QUESTION = 700, MAX_BYTES = 4000;
  function clean(x) {
    return String(x == null ? '' : x)
      .replace(/[\u0000-\u001F\u007F\u00A0\u200B-\u200F\u2028\u2029\uFEFF]+/g, ' ')
      .replace(/\s+/g, ' ').trim();
  }
  function bytes(s) { try { return new TextEncoder().encode(s).length; } catch (e) { return s.length * 3; } }

  var commentsP = null;
  function comments() {
    if (!commentsP) {
      commentsP = (window.claude && window.claude.use)
        ? Promise.resolve(window.claude.use('comments')).catch(function () { return null; })
        : Promise.resolve(null);
    }
    return commentsP;
  }

  function anchorEl(t) {
    return t.closest('[data-tutor-anchor]') || t.closest('.part') || t.closest('.box, .item, section') || t;
  }
  function questionText(t) {
    if (t.hasAttribute('data-question')) return clean(t.getAttribute('data-question')).slice(0, MAX_QUESTION);
    var part = t.closest('.part');
    var outer = t.closest('.box, .item, section') || part;
    var stem = outer ? (outer.querySelector('[data-stem]') || outer.querySelector('p')) : null;
    if (stem && part && part.contains(stem) && outer !== part) stem = null;
    var own = part ? part.querySelector('p') : null;
    if (own === stem) own = null;
    return clean((stem ? stem.textContent.slice(0, 300) : '') + (own ? ' ' + own.textContent : '')).slice(0, MAX_QUESTION);
  }

  var threads = {};  // threadKey -> threadId, this visit only
  function send(o) {
    return comments().then(function (c) {
      if (!c) throw { code: 'no_comments' };
      var ans = clean(o.answer);
      if (!ans) throw { code: 'empty' };
      if (ans.length > MAX_ANSWER) ans = ans.slice(0, MAX_ANSWER) + ' [cut at ' + MAX_ANSWER + ' characters]';
      var text = o.q + ' ' + (o.kind || 'answer') + ': ' + ans + (o.question ? ' || Question: ' + clean(o.question) : '');
      while (bytes(text) > MAX_BYTES) text = text.slice(0, text.length - 200);
      var key = o.threadKey || o.q;
      var el = o.el;
      if (el && !el.isConnected && el.id) el = document.getElementById(el.id) || el;
      var fresh = function () {
        return c.anchorFor(el).then(function (anchor) { return c.sendToClaude({ anchor: anchor, text: text }); });
      };
      var tid = o.newThread ? null : threads[key];
      var p = tid
        ? c.sendToClaude({ threadId: tid, text: text }).catch(function (err) {
            if (err && err.code === 'not_found') { delete threads[key]; return fresh(); }
            throw err;
          })
        : fresh();
      return p.then(function (r) {
        if (r && r.threadId && !o.newThread) threads[key] = r.threadId;
        return { threadId: r && r.threadId, text: text };
      });
    });
  }

  function failMessage(code) {
    if (code === 'no_comments') return 'Sending is not available in this view.';
    if (code === 'claude_unavailable') return 'No tutor session is listening right now.';
    if (code === 'consent_required') return 'Not sent: commenting from this page was not allowed.';
    if (code === 'forbidden') return 'Commenting from this page is off here.';
    return 'Sending failed (' + (code || 'error') + ').';
  }

  var bars = {};   // q -> {b, s}: the live controls (pages may re-render textareas)
  var state = {};  // q -> {msg, busy}: survives re-renders
  function say(q, msg, busy) {
    state[q] = { msg: msg, busy: !!busy };
    var x = bars[q];
    if (x) { x.s.textContent = msg; x.b.disabled = !!busy; }
  }
  function liveBox(q, t) {
    if (t && t.isConnected) return t;
    var all = document.querySelectorAll('textarea[data-q]');
    for (var i = 0; i < all.length; i++) if (all[i].getAttribute('data-q') === q) return all[i];
    return t;
  }
  function copyFallback(q, t, answer, why) {
    var txt = q + ': ' + String(answer || '').trim();
    var sel = function () {
      var box = liveBox(q, t);
      if (box && box.isConnected) { box.focus(); box.select(); }
      say(q, why + ' The answer is selected: press Ctrl+C and paste it into the chat.');
    };
    try {
      navigator.clipboard.writeText(txt).then(function () { say(q, why + ' Copied instead: paste it into the chat.'); }, sel);
    } catch (e) { sel(); }
  }
  function fire(t, name, detail) {
    var target = t && t.isConnected ? t : document;
    target.dispatchEvent(new CustomEvent(name, { bubbles: true, detail: detail }));
  }

  function wire(t) {
    if (t.__tutorWired) return;
    var q = t.getAttribute('data-q');
    if (!q) return;
    t.__tutorWired = true;
    if (KEY) {
      if (!t.value && (saved[q] || (t.id && saved[t.id]))) t.value = saved[q] || saved[t.id];
      t.addEventListener('input', function () { saved[q] = t.value; persist(); });
    }
    var bar = document.createElement('div'); bar.className = 'bar tutor-bar';
    var b = document.createElement('button'); b.type = 'button'; b.className = 'tutor-submit'; b.textContent = 'Submit to tutor';
    var s = document.createElement('span'); s.className = 'status'; s.setAttribute('role', 'status');
    bar.appendChild(b); bar.appendChild(s);
    var afterId = t.getAttribute('data-submit-after');
    var ref = (afterId && document.getElementById(afterId)) || t;
    ref.insertAdjacentElement('afterend', bar);
    bars[q] = { b: b, s: s };
    if (state[q]) { s.textContent = state[q].msg; b.disabled = state[q].busy; }

    b.addEventListener('click', function () {
      if (!clean(t.value)) { say(q, 'Write an answer first.'); return; }
      var ev = new CustomEvent('tutor-before-submit', { bubbles: true, cancelable: true, detail: { q: q, answer: t.value } });
      if (!t.dispatchEvent(ev)) return;
      var answer = ev.detail.answer;
      say(q, 'Sending...', true);
      send({ q: q, answer: answer, question: questionText(t), el: anchorEl(t), newThread: t.getAttribute('data-thread') === 'new' })
        .then(function (r) {
          say(q, 'Sent to the tutor. The reply arrives in the comment thread on this box.');
          if (t.hasAttribute('data-clear-on-send')) { t.value = ''; if (KEY) { delete saved[q]; persist(); } }
          fire(t, 'tutor-submitted', { q: q, answer: answer, text: r.text, threadId: r.threadId, el: t });
        })
        .catch(function (err) {
          var code = err && err.code;
          if (code === 'rate_limited') { say(q, 'Too many sends in a row: wait a minute, then press Submit again.'); return; }
          if (code === 'empty') { say(q, 'Write an answer first.'); return; }
          say(q, '', false);
          copyFallback(q, t, answer, failMessage(code));
        });
    });
  }

  function wireCopyAll(btn) {
    if (btn.__tutorWired) return;
    btn.__tutorWired = true;
    var s = document.createElement('span'); s.className = 'status'; s.setAttribute('role', 'status');
    btn.insertAdjacentElement('afterend', s);
    btn.addEventListener('click', function () {
      var all = Array.prototype.slice.call(document.querySelectorAll('textarea[data-q]'));
      var text = all.map(function (t) { return t.getAttribute('data-q') + ': ' + (t.value.trim() || '(blank)'); }).join('\n\n');
      var fallback = function () {
        var fb = document.getElementById('tutorCopyFallback');
        if (!fb) {
          fb = document.createElement('textarea'); fb.id = 'tutorCopyFallback'; fb.setAttribute('aria-label', 'Answers to copy');
          fb.style.minHeight = '10rem';
          s.insertAdjacentElement('afterend', fb);
        }
        fb.value = text; fb.hidden = false; fb.focus(); fb.select();
        s.textContent = 'Copy blocked here. The text is selected below; press Ctrl+C.';
      };
      try { navigator.clipboard.writeText(text).then(function () { s.textContent = 'Copied. Paste it into the chat.'; }, fallback); }
      catch (e) { fallback(); }
    });
  }

  function wireAll() {
    var boxes = document.querySelectorAll('textarea[data-q]');
    for (var i = 0; i < boxes.length; i++) wire(boxes[i]);
    var copies = document.querySelectorAll('button[data-tutor-copy-all]');
    for (var j = 0; j < copies.length; j++) wireCopyAll(copies[j]);
  }

  var queued = false;
  function schedule() {
    if (queued) return;
    queued = true;
    Promise.resolve().then(function () { queued = false; wireAll(); });
  }

  window.TutorSubmit = { send: send, wire: wireAll, clean: clean, version: '2026-11-09' };
  comments();  // resolve the namespace early, so a click sends straight away
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wireAll);
  else wireAll();
  try { new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true }); } catch (e) {}
})();
