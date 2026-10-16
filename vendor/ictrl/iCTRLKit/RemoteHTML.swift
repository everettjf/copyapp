import Foundation

/// Static HTML for GET /remote — a browser control page: plays the live MPEG-TS
/// stream in <video> (via mpegts.js) and drives the device with the same JSON-RPC
/// as the desktop GUI (tap/swipe/scroll/keyboard + a side panel of buttons).
/// The visual style is a light-touch shadcn/ui port — Tailwind-flavor tokens,
/// Radix-ish surfaces (zinc, subtle border, rounded, focus rings) — hand-written
/// in CSS so the page stays a single self-contained file.
///
/// The page has NO external network dependency: CSS is inline, mpegts.js is
/// vendored into MpegtsJS.swift and inlined at build time. Works fully offline.
///
/// The page holds the 32-byte pairing key and does the protocol-v1 crypto in
/// the browser (WebCrypto HMAC-SHA256): every /rpc body is sealed locally and
/// the key itself is never transmitted.
enum RemoteHTML {
    /// Web app manifest for GET /remote/manifest.webmanifest. Added to the Home
    /// Screen, the page opens in full screen with nothing of the browser around it.
    static let manifest: String = #"""
{
  "name": "iCTRL Remote",
  "short_name": "iCTRL Remote",
  "start_url": "/remote?fullscreen=1",
  "scope": "/remote",
  "display": "fullscreen",
  "background_color": "#000000",
  "theme_color": "#000000",
  "icons": [{ "src": "/remote/icon.png", "sizes": "180x180", "type": "image/png" }]
}
"""#

    /// Full HTML for GET /remote. The stream is fragmented MP4 (`Content-Type:
    /// video/mp4`) via MSE — every major browser decodes it natively, so this
    /// page has zero JS decoder dependency.
    static let page: String = #"""
<!doctype html>
<html lang="en" class="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<!-- Opened from the Home Screen, the page runs without Safari's bars: the only
     full screen an iPhone offers a page that isn't a bare <video>. -->
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#09090b">
<meta name="apple-mobile-web-app-title" content="iCTRL Remote">
<link rel="manifest" href="/remote/manifest.webmanifest">
<link rel="apple-touch-icon" href="/remote/icon.png">
<link rel="icon" type="image/png" href="/remote/icon.png">
<title>iCTRL Remote</title>
<style>
  /* ── shadcn-inspired tokens (dark) ── */
  :root {
    --bg: #09090b;          /* zinc-950 */
    --card: #18181b;        /* zinc-900 */
    --card-hi: #27272a;     /* zinc-800 */
    --border: #27272a;
    --border-hi: #3f3f46;   /* zinc-700 */
    --fg: #fafafa;          /* zinc-50 */
    --muted: #a1a1aa;       /* zinc-400 */
    --muted-2: #71717a;     /* zinc-500 */
    --primary: #fafafa;
    --primary-fg: #18181b;
    --accent: #22c55e;      /* green-500 */
    --danger: #ef4444;      /* red-500 */
    --warn: #f59e0b;        /* amber-500 */
    --ring: rgba(250,250,250,.35);
    --radius: 10px;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; overscroll-behavior: none; }
  body {
    margin: 0;
    font: 14px/1.4 -apple-system, BlinkMacSystemFont, "SF Pro Text", ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif;
    color: var(--fg); background: var(--bg);
    -webkit-font-smoothing: antialiased;
  }
  .app {
    display: grid;
    grid-template-columns: minmax(0, 1fr) clamp(280px, 26vw, 340px);
    gap: 12px;
    padding: 12px;
    padding-bottom: 44px;   /* leave room for the fixed #status bar */
    height: 100vh;
    height: 100dvh;         /* mobile: exclude URL bar */
  }
  /* ── panels ── */
  .panel {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
  }
  /* A sidebar panel must keep its natural height. As flex items they default to
     flex-shrink:1, so an overfull sidebar squashed each panel instead of
     scrolling — and `overflow:hidden` then clipped the contents away with no
     scrollbar anywhere. Pinning the basis to the content height makes the
     overflow real, which is what lets aside's own scrollbar appear. */
  aside > .panel { flex: 0 0 auto; }
  .stage {
    position: relative; display: flex; align-items: center; justify-content: center;
    background: #000; user-select: none;
    min-height: 0; min-width: 0;
  }
  #video {
    width: 100%; height: 100%; display: block; background: #000;
    object-fit: contain;
    outline: none;
  }
  .stage .overlay {
    position: absolute; inset: 0;
    /* invisible input catcher — sits above <video>, receives clicks/keys */
    cursor: crosshair;
    /* On a phone, a drag here is a swipe for the device — not a page scroll,
       pinch-zoom or double-tap zoom of this page. */
    touch-action: none;
  }
  /* Shown while disconnected: nothing connects on its own (each connection
     streams video and polls the device), and on a phone the Connect button
     in the drawer is out of sight. */
  #connectCta {
    position: absolute; z-index: 6;
    left: 50%; top: 50%; transform: translate(-50%, -50%);
    display: flex; flex-direction: column; align-items: center; gap: 10px;
    color: var(--muted); font-size: 12px; text-align: center;
  }
  #connectCta[hidden] { display: none; }
  #connectCta .btn { min-height: 44px; padding: 10px 28px; font-size: 15px; }
  .stage .hud {
    position: absolute; top: 10px; left: 12px; right: 12px;
    display: flex; flex-direction: column; align-items: flex-start; gap: 8px;
    color: var(--muted); font-size: 12px; pointer-events: none;
    /* Above the input overlay, which comes later in the stage and would
       otherwise take the clicks meant for the HUD's buttons. */
    z-index: 5;
  }
  /* Device badge and connection state stay on one line, full stage width. */
  .hud-row {
    align-self: stretch;
    display: flex; justify-content: space-between; align-items: center;
  }
  .badge {
    background: rgba(0,0,0,.5); border: 1px solid var(--border);
    padding: 2px 8px; border-radius: 999px;
  }
  .hud-end { display: flex; align-items: center; gap: 6px; }
  .hud-btn {
    pointer-events: auto;
    background: rgba(0,0,0,.5); border: 1px solid var(--border); color: var(--fg);
    border-radius: 999px; width: 26px; height: 26px; padding: 0;
    font-size: 13px; line-height: 1; cursor: pointer;
  }
  .hud-btn:hover { border-color: var(--border-hi); }
  /* ── device health overlay ──
     Sits in the HUD directly under the device badge, so identity and live state
     read as one top-left cluster. A portrait phone on a landscape stage leaves
     letterbox margin here, so it lands beside the video rather than on it; the
     blur covers the case where a wide device does reach across. */
  .sysmon {
    position: relative; z-index: 5;
    background: rgba(9,9,11,.72);
    border: 1px solid var(--border);
    border-radius: 8px;
    /* Right padding leaves a lane for the collapse button, which is positioned
       in the corner — without it the value column runs underneath. */
    padding: 6px 22px 6px 8px;
    font-size: 11px; line-height: 1.5;
    color: var(--muted);
    backdrop-filter: blur(8px);
    max-width: 190px;
    pointer-events: auto;   /* the collapse button needs clicks */
    transition: opacity .15s;
  }
  .sysmon.collapsed .sysmon-body { display: none; }
  .sysmon.collapsed { padding: 2px 6px; }
  .sysmon-toggle {
    position: absolute; top: 2px; right: 4px;
    background: none; border: none; color: var(--muted-2);
    font-size: 10px; cursor: pointer; padding: 2px 4px; line-height: 1;
  }
  .sysmon-toggle:hover { color: var(--fg); }
  .sysmon-row { display: flex; justify-content: space-between; gap: 10px; }
  .sysmon-row .k { color: var(--muted-2); }
  .sysmon-row .v { color: var(--fg); font-variant-numeric: tabular-nums; }
  .sysmon .warn { color: var(--warn); }
  .sysmon .bad  { color: var(--danger); }
  /* No letterbox margin to hide in on a narrow stage — shrink out of the way. */
  @media (max-width: 900px) {
    .sysmon { max-width: 140px; font-size: 10px; }
  }
  .dot { display:inline-block; width:6px; height:6px; border-radius: 999px; margin-right:6px; vertical-align: middle; }
  .dot.on { background: var(--accent); }
  .dot.off { background: var(--muted-2); }
  .dot.err { background: var(--danger); }

  /* ── sidebar ── */
  aside {
    display: flex; flex-direction: column; gap: 12px;
    overflow-y: auto; overflow-x: hidden;
    /* Bound the sidebar to the grid row so overflow triggers the scrollbar
       instead of the whole page scrolling. */
    min-height: 0; max-height: 100%;
    /* subtle scrollbar */
    scrollbar-width: thin;
    scrollbar-color: var(--border-hi) transparent;
  }
  aside::-webkit-scrollbar { width: 8px; }
  aside::-webkit-scrollbar-track { background: transparent; }
  aside::-webkit-scrollbar-thumb {
    background: var(--border-hi); border-radius: 999px; border: 2px solid var(--card);
  }
  aside::-webkit-scrollbar-thumb:hover { background: #52525b; }
  .section { padding: 12px; }
  .section h3 {
    margin: 0 0 10px; font-size: 12px; font-weight: 600;
    color: var(--muted); text-transform: uppercase; letter-spacing: .06em;
  }
  .row { display: flex; gap: 8px; }
  .row + .row { margin-top: 8px; }
  .col { display: flex; flex-direction: column; gap: 8px; }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }

  /* ── buttons (shadcn variants) ── */
  .btn {
    appearance: none; border: 1px solid var(--border-hi);
    background: var(--card-hi); color: var(--fg);
    padding: 8px 12px; border-radius: 8px;
    font-size: 13px; font-weight: 500;
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    cursor: pointer; transition: background .12s, border-color .12s, transform .06s;
    min-height: 34px;
  }
  .btn:hover { background: #2d2d31; border-color: #52525b; }
  .btn:active { transform: translateY(1px); }
  .btn:focus-visible { outline: 2px solid var(--ring); outline-offset: 1px; }
  .btn.primary { background: var(--fg); color: var(--primary-fg); border-color: var(--fg); }
  .btn.primary:hover { background: #e4e4e7; }
  .btn.ghost { background: transparent; border-color: var(--border); }
  .btn.ghost:hover { background: var(--card-hi); }
  .btn.danger { color: #fca5a5; border-color: #7f1d1d; background: transparent; }
  .btn.danger:hover { background: #7f1d1d33; }
  .btn.icon { padding: 8px; min-width: 34px; }
  .btn:disabled { opacity: .5; cursor: not-allowed; }
  .btn.full { width: 100%; }
  a.btn { text-decoration: none; }

  /* ── inputs ── */
  .input {
    background: var(--bg); color: var(--fg); border: 1px solid var(--border-hi);
    padding: 8px 10px; border-radius: 8px; font-size: 13px; width: 100%;
  }
  .input:focus { outline: 2px solid var(--ring); outline-offset: 0; border-color: var(--border-hi); }
  .label { font-size: 12px; color: var(--muted); margin-bottom: 4px; display: block; }

  /* ── status bar (fixed bottom, always visible) ── */
  #status {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 40;
    padding: 8px 12px;
    padding-bottom: calc(8px + env(safe-area-inset-bottom));
    border-top: 1px solid var(--border);
    font-size: 12px; color: var(--muted);
    background: rgba(24,24,27,.92);
    backdrop-filter: blur(6px);
    display: flex; align-items: center; gap: 8px;
    min-height: 30px;
  }
  #status .sep { color: var(--border-hi); }
  #status .toast {
    padding: 1px 8px; border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--card-hi);
    color: var(--fg);
    animation: toastIn .18s ease;
  }
  #status .toast.ok    { color: #86efac; border-color: #14532d; background: #052e16; }
  #status .toast.err   { color: #fca5a5; border-color: #7f1d1d; background: #450a0a; }
  #status .toast.warn  { color: #fcd34d; border-color: #78350f; background: #451a03; }
  @keyframes toastIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
  .kbd {
    background: var(--card-hi); border: 1px solid var(--border-hi);
    padding: 1px 6px; border-radius: 4px; font-size: 11px; color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  .hint { color: var(--muted-2); font-size: 11px; margin-top: 6px; }

  /* ── drawer mode: on a phone, and in full screen, the sidebar becomes a
     bottom sheet and a floating ball is the only control left on screen ── */
  #scrim {
    display: none;
    position: fixed; inset: 0; background: rgba(0,0,0,.55); z-index: 20;
    backdrop-filter: blur(2px);
  }
  .app.drawer { grid-template-columns: minmax(0, 1fr); }
  .app.drawer > aside {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 25;
    max-height: 78dvh; overflow-y: auto; overscroll-behavior: contain;
    background: var(--card);
    border-top: 1px solid var(--border);
    border-top-left-radius: 16px; border-top-right-radius: 16px;
    padding: 8px 12px calc(24px + env(safe-area-inset-bottom));
    transform: translateY(105%);
    transition: transform .22s ease;
  }
  .app.drawer > aside::before {
    content: ''; display: block; width: 44px; height: 4px; margin: 6px auto 10px;
    background: var(--border-hi); border-radius: 999px;
  }
  .app.drawer.open > aside { transform: translateY(0); }
  .app.drawer.open ~ #scrim { display: block; }

  /* Translucent, draggable; tap it for the quick controls. It snaps to the
     nearest side when let go, so it never parks over the middle of the screen. */
  #ball {
    display: none;
    position: fixed; right: 12px; bottom: calc(56px + env(safe-area-inset-bottom)); z-index: 30;
    width: 48px; height: 48px; border-radius: 999px; padding: 0;
    background: rgba(250,250,250,.16); color: var(--fg);
    border: 1px solid rgba(250,250,250,.3);
    backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
    box-shadow: 0 4px 16px rgba(0,0,0,.45);
    font-size: 20px; cursor: grab;
    align-items: center; justify-content: center;
    opacity: .55; transition: opacity .15s, background-color .3s, border-color .3s;
    touch-action: none; user-select: none; -webkit-user-select: none;
    -webkit-tap-highlight-color: transparent;
  }
  /* Over a light part of the picture the pale glass disappears, so the ball
     turns dark there (the script samples the frame beneath it). */
  #ball.on-light {
    background: rgba(24,24,27,.55); border-color: rgba(0,0,0,.55);
    box-shadow: 0 4px 16px rgba(0,0,0,.25); opacity: .7;
  }
  #ball:hover, #ball.active { opacity: 1; }
  #ball.dragging { cursor: grabbing; opacity: 1; }
  .app.drawer ~ #ball { display: inline-flex; }
  .app.drawer.open ~ #ball { display: none; }   /* the sheet is open: it would sit on its controls */

  #quick {
    position: fixed; z-index: 31;
    display: grid; grid-template-columns: repeat(4, 64px); gap: 6px;
    padding: 8px; border-radius: 16px;
    background: rgba(24,24,27,.82); border: 1px solid var(--border-hi);
    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    box-shadow: 0 10px 30px rgba(0,0,0,.5);
  }
  #quick[hidden] { display: none; }
  #quick button {
    appearance: none; border: none; border-radius: 12px;
    background: rgba(250,250,250,.06); color: var(--fg);
    height: 60px; padding: 4px 0; cursor: pointer;
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px;
    font-size: 20px; -webkit-tap-highlight-color: transparent;
  }
  #quick button span { font-size: 11px; color: var(--muted); }
  #quick button:active { background: rgba(250,250,250,.16); }

  /* Modal sheets: Add to Home Screen steps, screenshot preview. */
  .sheet {
    position: fixed; inset: 0; z-index: 50;
    display: flex; align-items: center; justify-content: center;
    background: rgba(0,0,0,.6); padding: 16px;
  }
  .sheet[hidden] { display: none; }
  .sheet .card {
    background: var(--card); border: 1px solid var(--border-hi); border-radius: 16px;
    padding: 18px; max-width: 360px; width: 100%;
  }
  .sheet h4 { margin: 0 0 10px; font-size: 16px; }
  .sheet ol { margin: 0 0 12px; padding-left: 20px; line-height: 1.6; }
  .sheet .hint { margin: 0 0 14px; }
  #shotImg {
    display: block; width: 100%; max-height: 62dvh; object-fit: contain;
    border-radius: 10px; background: #000; margin-bottom: 12px;
    /* A long-press would otherwise start a Live Text selection. */
    -webkit-user-select: none; user-select: none;
  }

  .check { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--fg); cursor: pointer; }
  .check + .check { margin-top: 8px; }

  /* ── display preferences (Display panel) ── */
  body.hide-hud .hud-row { display: none; }
  body.hide-sysmon #sysmon { display: none; }
  /* Without the status bar, a short action result still shows, as a pill at
     the top. */
  body.hide-statusbar #status, body.immersive #status {
    top: calc(10px + env(safe-area-inset-top)); bottom: auto; left: 50%; right: auto;
    transform: translateX(-50%);
    background: none; border: none; backdrop-filter: none; -webkit-backdrop-filter: none;
    padding: 0; min-height: 0; pointer-events: none;
  }
  body.hide-statusbar #status > :not(.toast),
  body.immersive #status > :not(.toast) { display: none; }
  body.hide-statusbar .app { padding-bottom: 12px; }

  /* Opened from the Home Screen the page runs under the status bar. */
  body.standalone .app { padding-top: max(8px, env(safe-area-inset-top)); }

  /* ── full screen: the picture edge to edge, nothing but the ball on top ── */
  body.immersive { background: #000; }
  body.immersive .app { padding: 0; gap: 0; }
  body.immersive .stage { border: none; border-radius: 0; }
  /* Safari on iPhone (iOS 26 and later) floats its toolbar over the page and
     shows whatever part of the document lies beneath it. In full screen with
     the picture filling the window, the page is made as tall as the screen
     below the status bar (the height is set from script), so the picture runs
     to the bottom edge behind the toolbar, as it would on the phone itself.
     Safari paints the colour of anything fixed to the bottom edge across that
     strip, over the picture, and keeps doing so after the element has moved
     away; only display:none clears it. So the closed drawer is taken out of
     the layout there, and so is the status bar except while it shows a
     message (as a pill at the top). */
  html.under-bars, html.under-bars body { height: auto; }
  html.under-bars .app.drawer:not(.open) > aside { display: none; }
  html.under-bars #status:not(.has-toast) { display: none; }
  html.under-bars .app.drawer.open > aside { transform: none; animation: sheetIn .22s ease; }
  @keyframes sheetIn { from { transform: translateY(105%); } to { transform: none; } }

  /* How the picture meets the window in full screen (Display → Picture). */
  body.immersive[data-fit="cover"] #video { object-fit: cover; }
  body.immersive[data-fit="fill"] #video { object-fit: fill; }
  body.immersive .hud { display: none; }

  @media (max-width: 720px) {
    .app { padding: 8px; padding-bottom: calc(40px + env(safe-area-inset-bottom)); }
    .stage { border-radius: 12px; }
    .section { padding: 10px; }
    .grid-3 { max-width: 240px; }
    /* iOS Safari zooms the page into any field under 16px when it gains focus. */
    .input { font-size: 16px; }
  }
  /* landscape phones: keep video full width, drawer larger */
  @media (max-width: 720px) and (orientation: landscape) {
    #ball { bottom: 12px; }
    .app.drawer > aside { max-height: 92dvh; }
  }
</style>
</head>
<body>
<div class="app" id="app">
  <!-- ── LEFT: video stage ── -->
  <section class="panel stage" id="stage">
    <video id="video" autoplay muted playsinline></video>
    <div class="hud">
      <div class="hud-row">
        <span class="badge" id="hudDevice">—</span>
        <span class="hud-end">
          <span class="badge"><span id="statusDot" class="dot off"></span><span id="hudState">Disconnected</span></span>
          <button class="hud-btn" data-fs title="Full screen">⛶</button>
        </span>
      </div>
      <!-- Device health, directly under the device badge: same top-left
           cluster, so identity and live state read as one block. The stage
           letterboxes the video, so this sits in the margin rather than over
           the picture. -->
      <div class="sysmon" id="sysmon" hidden>
        <button class="sysmon-toggle" id="sysmonToggle" title="Hide">▾</button>
        <div class="sysmon-body" id="sysmonBody"></div>
      </div>
    </div>
    <!-- overlay catches pointer + keyboard events -->
    <div class="overlay" id="overlay" tabindex="0"></div>
    <div id="connectCta">
      <button class="btn primary" id="ctaBtn">Connect</button>
      <span id="ctaNote">Not connected — streaming starts when you connect.</span>
    </div>
  </section>

  <!-- ── RIGHT: control panel ── -->
  <aside>
    <div class="panel section">
      <h3>Connection</h3>
      <label class="label">Pairing key <span style="opacity:.6">(optional)</span></label>
      <input class="input" id="tokenInput" type="password" placeholder="leave empty to pair now" autocomplete="off">
      <div class="row" style="margin-top: 8px">
        <button class="btn primary" id="connectBtn">Connect</button>
        <button class="btn ghost" id="stopBtn" disabled>Stop</button>
      </div>
      <div class="hint">Leave it empty and hit Connect — the device will ask you to approve,
      then the key is saved in this browser. Paste an existing key only to reuse one.
      The key never leaves this browser; every request is encrypted locally.</div>
    </div>

    <div class="panel section">
      <h3>Stream</h3>
      <div class="grid-2">
        <div>
          <label class="label">FPS</label>
          <select class="input" id="fpsSel"
                  title="Requested rate. Capture sets the real limit: up to 30 on a cool device, less when it is hot.">
            <option value="2">2</option>
            <option value="5">5</option>
            <option value="10">10</option>
            <option value="15" selected>15</option>
            <option value="20">20</option>
            <option value="24">24</option>
            <option value="30">30</option>
          </select>
        </div>
        <div>
          <label class="label">Quality</label>
          <select class="input" id="qSel" title="Bitrate + resolution preset — auto lets VideoToolbox pick.">
            <option value="auto" selected>auto</option>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
        </div>
      </div>
      <label class="hint" style="display:flex;align-items:center;gap:6px;margin-top:8px;cursor:pointer">
        <input type="checkbox" id="verboseChk">
        Verbose encoder log <span class="kbd">/logs</span>
      </label>
    </div>

    <div class="panel section">
      <h3>Display</h3>
      <label class="check"><input type="checkbox" data-pref="hud" checked> Device and connection badges</label>
      <label class="check"><input type="checkbox" data-pref="sysmon" checked> Device health (thermal, CPU, memory)</label>
      <label class="check"><input type="checkbox" data-pref="statusbar" checked> Status bar</label>
      <label class="label" style="margin-top:10px">Picture in full screen</label>
      <select class="input" id="fitSel">
        <option value="cover">Fill the screen (crops the edges)</option>
        <option value="contain">Whole picture (black bars)</option>
        <option value="fill">Stretch to the window</option>
      </select>
      <button class="btn full" style="margin-top:10px" data-fs>⛶ Full screen</button>
      <button class="btn full" style="margin-top:8px" id="installBtn">📲 Add to Home Screen</button>
      <div class="hint">Full screen leaves only the floating ball: drag it anywhere, tap it
      for quick controls. In a Safari tab on iPhone the picture runs behind the
      browser's toolbar, and what lies under the toolbar can't be tapped there; added
      to the Home Screen it opens with no browser bars at all.</div>
    </div>

    <div class="panel section">
      <h3>Device</h3>
      <div class="grid-2">
        <button class="btn" data-act="home">🏠 Home</button>
        <button class="btn" data-act="lock-confirm">🔒 Lock</button>
        <button class="btn" data-act="unlock">🔓 Unlock</button>
        <button class="btn" data-act="screenshot">📷 Shot</button>
      </div>
      <button class="btn full" style="margin-top:8px" data-act="open-app">📱 Open App…</button>
    </div>

    <div class="panel section">
      <h3>Navigate</h3>
      <div class="grid-3" style="max-width: 200px; margin: 0 auto">
        <div></div>
        <button class="btn icon" data-nav="up">↑</button>
        <div></div>
        <button class="btn icon" data-nav="left">←</button>
        <button class="btn icon" data-nav="center">•</button>
        <button class="btn icon" data-nav="right">→</button>
        <div></div>
        <button class="btn icon" data-nav="down">↓</button>
        <div></div>
      </div>
      <div class="row" style="margin-top:8px">
        <button class="btn full" data-page="up">⇞ PgUp</button>
        <button class="btn full" data-page="down">⇟ PgDn</button>
      </div>
    </div>

    <div class="panel section">
      <h3>Text</h3>
      <button class="btn full" data-act="type-text">⌨️ Type text…</button>
      <div class="row" style="margin-top:8px">
        <button class="btn full" data-act="clear-text">⌫ Clear field</button>
        <button class="btn full" data-act="submit">⏎ Submit</button>
      </div>
      <div class="hint">Click the video, then type — keys go to the focused field on the device. Enter = submit.</div>
    </div>
  </aside>
</div>

<div id="scrim"></div>
<button id="ball" aria-label="Controls" title="Controls — drag to move">◎</button>
<div id="quick" hidden>
  <button data-act="home">🏠<span>Home</span></button>
  <button data-act="type-text">⌨️<span>Type</span></button>
  <button data-act="screenshot">📷<span>Shot</span></button>
  <button data-act="open-app">📱<span>Open app</span></button>
  <button id="quickConn">⏻<span>Connect</span></button>
  <button data-fs>⛶<span>Full screen</span></button>
  <button id="quickMore">⚙︎<span>More</span></button>
</div>

<div id="installSheet" class="sheet" hidden>
  <div class="card">
    <h4>Add to Home Screen</h4>
    <ol id="installSteps">
      <li>Open Safari's Share menu (on iOS 26: the menu button in the address bar, then Share).</li>
      <li>Choose <b>Add to Home Screen</b>.</li>
      <li>Keep <b>Open as Web App</b> on and tap <b>Add</b>.</li>
    </ol>
    <div class="hint">The icon opens this page full screen, with no browser bars.
    It keeps its own storage, so pair once more the first time.</div>
    <button class="btn primary full" id="installClose">OK</button>
  </div>
</div>

<div id="shotSheet" class="sheet" hidden>
  <div class="card">
    <img id="shotImg" alt="Screenshot">
    <div class="hint" id="shotHint">On iPhone, Download saves it to Files › Downloads (the ↓ in Safari's address bar).</div>
    <div class="row">
      <a class="btn primary full" id="shotSave" download>Download</a>
      <button class="btn full" id="shotClose">Close</button>
    </div>
  </div>
</div>

<div id="status">
  <span class="dot off" id="statusDotBar"></span>
  <span id="statusText">Idle</span>
  <span class="sep">•</span>
  <span id="lastAction" class="toast" style="display:none"></span>
</div>

<script>
(() => {
  // ── DOM ──
  const $ = s => document.querySelector(s);
  const video = $('#video'), stage = $('#stage'), overlay = $('#overlay');
  const tokenInput = $('#tokenInput'), fpsSel = $('#fpsSel'), qSel = $('#qSel'), verboseChk = $('#verboseChk');
  const connectBtn = $('#connectBtn'), stopBtn = $('#stopBtn');
  const statusText = $('#statusText'), statusDot = $('#statusDotBar');
  const lastAction = $('#lastAction');
  const hudState = $('#hudState'), hudDevice = $('#hudDevice'), hudDot = $('#statusDot');
  let toastTimer = null;

  // ── state ──
  let player = null;
  // The page holds the 32-byte pairing key K (hex) and its derived id `tok`.
  // localStorage is scoped per (host, port), so switching between devices is
  // safe; we only persist after a successful connect. There is no plaintext
  // bearer token anywhere — K signs and encrypts every request locally and is
  // never transmitted.
  const STORE_KEY = 'ictrl.key';
  let key = null, tok = '';
  function useKeyHex(hexKey) {
    if (!/^[0-9a-f]{64}$/i.test(hexKey || '')) return false;
    key = unhex(hexKey.toLowerCase());
    return true;   // `tok` is derived in connect(), where we can await SHA-256
  }
  const savedKey = localStorage.getItem(STORE_KEY) || '';
  if (savedKey) tokenInput.value = savedKey;
  let deviceInfo = null;   // {point_width, point_height}
  let dragStart = null;

  // ── status ──
  // Two channels:
  //   setConn(msg, kind)  → the LEFT half of the status bar + video HUD,
  //                         a sticky connection state ("connected", "streaming …").
  //   setToast(msg, kind) → a transient badge on the RIGHT of the status bar,
  //                         auto-clears after ~2.4s. Used for per-action feedback
  //                         (tap ok, swipe ok, rpc failed, …).
  function setConn(msg, kind = 'idle') {
    statusText.textContent = msg;
    hudState.textContent = msg;
    const cls = 'dot ' + (kind === 'ok' ? 'on' : kind === 'err' ? 'err' : 'off');
    statusDot.className = cls; hudDot.className = cls;
  }
  // In full screen the page should look like the phone itself, so only
  // failures (and the few hints passed with force) are shown.
  function setToast(msg, kind = 'ok', ttl = 2400, force = false) {
    if (document.body.classList.contains('immersive') && kind !== 'err' && !force) return;
    lastAction.textContent = msg;
    lastAction.className = 'toast ' + (kind || '');
    lastAction.style.display = '';
    lastAction.parentElement.classList.add('has-toast');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      lastAction.style.display = 'none';
      lastAction.parentElement.classList.remove('has-toast');
    }, ttl);
  }
  // Legacy shim: existing call sites use setStatus(msg, kind). Route lifecycle
  // words to the sticky connection line, everything else to the toast.
  const CONN_WORDS = ['idle','connecting','stopped','connected','streaming','switching','waiting'];
  function setStatus(msg, kind = 'idle') {
    const isConn = CONN_WORDS.some(w => msg.toLowerCase().startsWith(w));
    if (isConn) setConn(msg, kind);
    else setToast(msg, kind === 'err' ? 'err' : kind === 'ok' ? 'ok' : 'warn');
  }

  // ── crypto (protocol v1) ──
  // Every /rpc body is sealed: HMAC-CTR stream cipher + encrypt-then-MAC, a
  // fresh 16-byte nonce per request, and a timestamp the server bounds to
  // ±120s. Identical construction to the Python/Swift clients, so all three
  // interoperate.
  //
  // IMPORTANT: `crypto.subtle` only exists in a SECURE CONTEXT (https, or
  // localhost). This page is normally opened as http://<lan-ip>:8200/remote,
  // which is NOT secure context — there `crypto.subtle` is undefined outright,
  // not merely missing an algorithm. So every primitive has a pure-JS fallback
  // and we never touch `crypto.subtle` without checking. (`getRandomValues` is
  // not part of subtle and is always available.)
  const enc = new TextEncoder(), dec = new TextDecoder();
  const hex = (buf) => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
  const unhex = (s) => new Uint8Array(s.match(/../g).map(h => parseInt(h, 16)));
  const b64 = (u8) => btoa(String.fromCharCode(...u8));
  const unb64 = (s) => Uint8Array.from(atob(s), c => c.charCodeAt(0));
  const SUBTLE = (typeof crypto !== 'undefined' && crypto.subtle) ? crypto.subtle : null;

  // ── SHA-256 / HMAC-SHA256 fallback (FIPS 180-4, RFC 2104) ──
  // Validated against the FIPS 180-4 and RFC 4231 vectors and cross-checked
  // against WebCrypto. Only used when SUBTLE is null.
  const SHAJS = (() => {
    const K = new Uint32Array([
      0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
      0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
      0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
      0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
      0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
      0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
      0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
      0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2]);
    const rotr = (x, n) => (x >>> n) | (x << (32 - n));
    const cat = (...a) => { const o = new Uint8Array(a.reduce((n,x)=>n+x.length,0));
      let p = 0; for (const x of a) { o.set(x,p); p += x.length; } return o; };
    function sha256(msg) {
      const len = msg.length, bitLen = len * 8;
      // Message + 0x80 + 8-byte length, rounded UP to a whole 64-byte block.
      // Getting this wrong by one block silently corrupts every digest whose
      // length lands in [56,63] mod 64, which is exactly the case that broke
      // the response MAC on longer replies.
      const padded = new Uint8Array(Math.ceil((len + 9) / 64) * 64);
      padded.set(msg); padded[len] = 0x80;
      const dv = new DataView(padded.buffer);
      dv.setUint32(padded.length - 4, bitLen >>> 0);
      dv.setUint32(padded.length - 8, Math.floor(bitLen / 0x100000000));
      const H = new Uint32Array([0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
                                 0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]);
      const w = new Uint32Array(64);
      for (let off = 0; off < padded.length; off += 64) {
        for (let i = 0; i < 16; i++) w[i] = dv.getUint32(off + i * 4);
        for (let i = 16; i < 64; i++) {
          const s0 = rotr(w[i-15],7) ^ rotr(w[i-15],18) ^ (w[i-15] >>> 3);
          const s1 = rotr(w[i-2],17) ^ rotr(w[i-2],19) ^ (w[i-2] >>> 10);
          w[i] = (w[i-16] + s0 + w[i-7] + s1) >>> 0;
        }
        let [a,b,c,d,e,f,g,h] = H;
        for (let i = 0; i < 64; i++) {
          const S1 = rotr(e,6) ^ rotr(e,11) ^ rotr(e,25), ch = (e & f) ^ (~e & g);
          const t1 = (h + S1 + ch + K[i] + w[i]) >>> 0;
          const S0 = rotr(a,2) ^ rotr(a,13) ^ rotr(a,22);
          const maj = (a & b) ^ (a & c) ^ (b & c), t2 = (S0 + maj) >>> 0;
          h=g; g=f; f=e; e=(d+t1)>>>0; d=c; c=b; b=a; a=(t1+t2)>>>0;
        }
        H[0]=(H[0]+a)>>>0; H[1]=(H[1]+b)>>>0; H[2]=(H[2]+c)>>>0; H[3]=(H[3]+d)>>>0;
        H[4]=(H[4]+e)>>>0; H[5]=(H[5]+f)>>>0; H[6]=(H[6]+g)>>>0; H[7]=(H[7]+h)>>>0;
      }
      const out = new Uint8Array(32), odv = new DataView(out.buffer);
      for (let i = 0; i < 8; i++) odv.setUint32(i*4, H[i]);
      return out;
    }
    function hmacSha256(key, msg) {
      const B = 64, k = key.length > B ? sha256(key) : key;
      const pad = new Uint8Array(B); pad.set(k);
      const ip = new Uint8Array(B), op = new Uint8Array(B);
      for (let i = 0; i < B; i++) { ip[i] = pad[i] ^ 0x36; op[i] = pad[i] ^ 0x5c; }
      return sha256(cat(op, sha256(cat(ip, msg))));
    }
    return { sha256, hmacSha256 };
  })();

  async function sha256(bytes) {
    if (SUBTLE) return new Uint8Array(await SUBTLE.digest('SHA-256', bytes));
    return SHAJS.sha256(new Uint8Array(bytes));
  }

  async function hmac(keyBytes, msg) {
    if (!SUBTLE) return SHAJS.hmacSha256(new Uint8Array(keyBytes), new Uint8Array(msg));
    const k = await SUBTLE.importKey('raw', keyBytes, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    return new Uint8Array(await SUBTLE.sign('HMAC', k, msg));
  }
  const concat = (...arrs) => {
    const out = new Uint8Array(arrs.reduce((n, a) => n + a.length, 0));
    let off = 0; for (const a of arrs) { out.set(a, off); off += a.length; }
    return out;
  };
  /// keystream_i = HMAC(key, nonce || be32(i)), truncated to len.
  async function keystreamXor(key, nonce, data) {
    const out = new Uint8Array(data.length);
    for (let off = 0, ctr = 0; off < data.length; off += 32, ctr++) {
      const be = new Uint8Array(4); new DataView(be.buffer).setUint32(0, ctr);
      const block = await hmac(key, concat(nonce, be));
      for (let i = 0; i < 32 && off + i < data.length; i++) out[off + i] = data[off + i] ^ block[i];
    }
    return out;
  }
  const be64 = (n) => {
    const b = new Uint8Array(8); new DataView(b.buffer).setBigUint64(0, BigInt(n)); return b;
  };

  // ── X25519 fallback (RFC 7748) ──
  // Used only when WebCrypto lacks X25519 (Chrome <133, Safari <17, Firefox
  // <132). ~40 lines of BigInt instead of a WASM blob: it runs exactly once per
  // pairing, so speed is irrelevant and auditability is worth more. Validated
  // against the RFC 7748 §5.2/§6.1 vectors and cross-checked against WebCrypto.
  //
  // The ladder is branch-free over the scalar bits, but BigInt arithmetic is not
  // constant-time — acceptable here: the key is ephemeral, used once, for a
  // pairing the user is actively watching. Everything after pairing is HMAC.
  const X25519JS = (() => {
    const P = (1n << 255n) - 19n, A24 = 121665n;
    const fe = (x) => ((x % P) + P) % P;
    const powm = (b, e) => { let r = 1n; b = fe(b);
      while (e > 0n) { if (e & 1n) r = fe(r * b); b = fe(b * b); e >>= 1n; } return r; };
    const inv = (x) => powm(x, P - 2n);
    const toBig = (b) => { let n = 0n; for (let i = b.length - 1; i >= 0; i--) n = (n << 8n) | BigInt(b[i]); return n; };
    const toBytes = (n) => { const o = new Uint8Array(32);
      for (let i = 0; i < 32; i++) { o[i] = Number(n & 255n); n >>= 8n; } return o; };
    function scalarMult(scalar, uBytes) {
      const e = Uint8Array.from(scalar);
      e[0] &= 248; e[31] &= 127; e[31] |= 64;                 // clamp
      const k = toBig(e), u = fe(toBig(uBytes) & ((1n << 255n) - 1n));
      let x1 = u, x2 = 1n, z2 = 0n, x3 = u, z3 = 1n, swap = 0n;
      for (let t = 254; t >= 0; t--) {
        const kt = (k >> BigInt(t)) & 1n;
        swap ^= kt;
        if (swap) { [x2, x3] = [x3, x2]; [z2, z3] = [z3, z2]; }
        swap = kt;
        const a = fe(x2 + z2), aa = fe(a * a), b = fe(x2 - z2), bb = fe(b * b);
        const ee = fe(aa - bb), c = fe(x3 + z3), d = fe(x3 - z3);
        const da = fe(d * a), cb = fe(c * b);
        x3 = fe((da + cb) * (da + cb));
        z3 = fe(x1 * fe((da - cb) * (da - cb)));
        x2 = fe(aa * bb);
        z2 = fe(ee * (aa + fe(A24 * ee)));
      }
      if (swap) { [x2, x3] = [x3, x2]; [z2, z3] = [z3, z2]; }
      return toBytes(fe(x2 * inv(z2)));
    }
    const BASE = (() => { const b = new Uint8Array(32); b[0] = 9; return b; })();
    return { scalarMult, publicKey: (priv) => scalarMult(priv, BASE) };
  })();

  // ── pairing ──
  // Do the whole handshake in-page so the user never has to run curl. Over the
  // LAN the device only grants a key wrapped against an ephemeral X25519 key
  // (a plaintext grant is refused off 127.0.0.1), so this needs X25519 — from
  // WebCrypto where available, else the bundled BigInt implementation. Either
  // way pairing works in every browser, with no terminal step.
  //
  // Two backends, same shape: WebCrypto where available, otherwise the BigInt
  // implementation below. Only pairing needs X25519 — every request afterwards
  // uses HMAC-SHA256, which every browser has had for a decade.
  async function makeEphemeralKey() {
    try {
      if (!SUBTLE) throw new Error('no subtle');
      const kp = await SUBTLE.generateKey({ name: 'X25519' }, true, ['deriveBits']);
      return {
        pub: new Uint8Array(await SUBTLE.exportKey('raw', kp.publicKey)),
        deriveShared: async (peer) => new Uint8Array(await SUBTLE.deriveBits(
          { name: 'X25519', public: await SUBTLE.importKey('raw', peer, { name: 'X25519' }, false, []) },
          kp.privateKey, 256)),
      };
    } catch (_) {
      const priv = crypto.getRandomValues(new Uint8Array(32));
      return {
        pub: X25519JS.publicKey(priv),
        deriveShared: async (peer) => X25519JS.scalarMult(priv, peer),
      };
    }
  }

  async function pairInPage(clientName) {
    const eph = await makeEphemeralKey();
    // Shown so the user can match it against the on-device prompt.
    const fp = hex(await sha256(eph.pub)).slice(0, 8);
    setConn('waiting for approval on the device… (key ' + fp + ')');

    const r = await fetch('/pair', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_name: clientName, pub: b64(eph.pub) }),
    });
    const j = await r.json();
    if (!r.ok) throw new Error((j.error && j.error.message) || ('pair failed (' + r.status + ')'));

    // K = token_ct XOR HMAC(HMAC(shared,"ictrl-pair"||c_pub||d_pub), "ictrl-wrap")
    const devPub = unb64(j.pub);
    const shared = await eph.deriveShared(devPub);
    const kWrap = await hmac(shared, concat(enc.encode('ictrl-pair'), eph.pub, devPub));
    const pad = await hmac(kWrap, enc.encode('ictrl-wrap'));
    const ctk = unhex(j.token_ct);
    return hex(ctk.map((b, i) => b ^ pad[i]));
  }

  // ── RPC ──
  // A person watching the live stream is the settle check: waiting for the
  // screen to stop changing would only hold the reply (and the device's UI
  // thread, which the stream's capture also needs) for up to seconds.
  const NO_SETTLE = new Set(['tap', 'double_tap', 'long_press', 'swipe', 'scroll', 'drag',
                             'page', 'page_down', 'page_up', 'type', 'clear_text']);
  async function rpc(method, params = {}) {
    if (!key) throw new Error('not paired');
    if (NO_SETTLE.has(method) && params.settle === undefined) params = { ...params, settle: false };
    const body = enc.encode(JSON.stringify({ jsonrpc: '2.0', method, params, id: Date.now() }));
    const nonce = crypto.getRandomValues(new Uint8Array(16));
    const ts = Math.floor(Date.now() / 1000);

    const kEnc = await hmac(key, concat(enc.encode('ictrl-v1|enc-req'), nonce));
    const kMac = await hmac(key, concat(enc.encode('ictrl-v1|mac'), nonce));
    const ct = await keystreamXor(kEnc, nonce, body);
    const tag = await hmac(kMac, concat(enc.encode('v1'), unhex(tok), be64(ts), nonce, ct));

    const r = await fetch('/rpc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ v: 1, tok, ts, nonce: hex(nonce), ct: b64(ct), tag: hex(tag) }),
    });
    if (r.status === 401 || r.status === 403) {
      // Key rejected/expired — drop it so the next visit prompts to re-pair.
      try { localStorage.removeItem(STORE_KEY); } catch (_) {}
      key = null;
      throw new Error('key rejected (' + r.status + ') — re-pair');
    }

    // Reply is sealed under the same nonce with the response-direction key.
    const env = await r.json();
    const respCt = unb64(env.ct);
    const expect = await hmac(kMac, concat(enc.encode('resp'), nonce, respCt));
    if (hex(expect) !== env.tag) throw new Error('response MAC mismatch');
    const kEncResp = await hmac(key, concat(enc.encode('ictrl-v1|enc-resp'), nonce));
    const j = JSON.parse(dec.decode(await keystreamXor(kEncResp, nonce, respCt)));
    if (j.error) throw new Error(j.error.message || 'rpc failed');
    return j.result || {};
  }

  // ── HUD device badge (short label + full details on hover) ──
  // ── device health overlay ──
  // Polls device_info on a slow cadence: it is a real RPC on a device we are
  // also streaming from, so asking often would itself cost frames.
  const sysmon = $('#sysmon'), sysmonBody = $('#sysmonBody'), sysmonToggle = $('#sysmonToggle');
  let sysmonTimer = null;
  const SYSMON_INTERVAL_MS = 5000;

  try {
    if (localStorage.getItem('ictrl.sysmon.collapsed') === '1') sysmon.classList.add('collapsed');
  } catch (_) {}
  sysmonToggle.addEventListener('click', () => {
    const collapsed = sysmon.classList.toggle('collapsed');
    sysmonToggle.textContent = collapsed ? '▸' : '▾';
    sysmonToggle.title = collapsed ? 'Show' : 'Hide';
    try { localStorage.setItem('ictrl.sysmon.collapsed', collapsed ? '1' : '0'); } catch (_) {}
  });

  function renderSysmon(sys) {
    if (!sys) { sysmon.hidden = true; return; }
    sysmon.hidden = false;
    const rows = [];
    const row = (k, v, cls) => rows.push(
      `<div class="sysmon-row"><span class="k">${k}</span><span class="v ${cls || ''}">${v}</span></div>`);

    // Thermal first: it is the one that explains a stream slowing down.
    if (sys.thermal_state) {
      const t = sys.thermal_state;
      row('Thermal', t, t === 'critical' ? 'bad' : (t === 'serious' || t === 'fair') ? 'warn' : '');
    }
    if (sys.process_cpu_percent != null) {
      const c = sys.process_cpu_percent;
      row('CPU', c.toFixed(0) + '%', c > 150 ? 'bad' : c > 80 ? 'warn' : '');
    }
    if (sys.process_memory_mb != null) {
      const total = sys.total_memory_mb;
      row('Memory', sys.process_memory_mb + ' MB' + (total ? ` / ${total}` : ''));
    }
    if (sys.system_free_memory_mb != null) row('Free', sys.system_free_memory_mb + ' MB');

    // Disk: show free space in the unit that stays readable, and colour by how
    // full the volume is — a nearly-full device fails installs and screenshots
    // in confusing ways, so it is worth seeing before it bites.
    if (sys.disk_free_mb != null) {
      const gb = sys.disk_free_mb / 1024;
      const free = gb >= 1 ? gb.toFixed(1) + ' GB' : sys.disk_free_mb + ' MB';
      const pct = sys.disk_used_percent;
      row('Disk', free + ' free', pct != null && pct > 95 ? 'bad' : pct != null && pct > 85 ? 'warn' : '');
    }

    if (sys.battery_percent != null) {
      const b = sys.battery_percent;
      const charging = sys.battery_state === 'charging' || sys.battery_state === 'full';
      row('Battery', b + '%' + (charging ? ' ⚡' : ''),
          !charging && b <= 10 ? 'bad' : !charging && b <= 20 ? 'warn' : '');
    }

    if (sys.low_power_mode) row('Power', 'low-power', 'warn');
    sysmonBody.innerHTML = rows.join('');
  }

  async function pollSysmon() {
    try {
      const info = await rpc('device_info');
      renderSysmon(info.system);
    } catch (_) {
      // A failed poll is not worth surfacing — the status bar already reports
      // connection trouble, and the last-known values stay on screen.
    }
  }

  function startSysmon() {
    stopSysmon();
    pollSysmon();
    sysmonTimer = setInterval(pollSysmon, SYSMON_INTERVAL_MS);
  }
  function stopSysmon() {
    if (sysmonTimer) { clearInterval(sysmonTimer); sysmonTimer = null; }
    sysmon.hidden = true;
  }

  function updateHudDevice(info) {
    if (!info) { hudDevice.textContent = '—'; hudDevice.title = ''; return; }
    const name = info.device_name || info.model || 'iPhone';
    const os = info.system_version ? ` · iOS ${info.system_version}` : '';
    hudDevice.textContent = name + os;
    const lines = [
      `Name:    ${info.device_name || '—'}`,
      `Model:   ${info.model || '—'}`,
      `iOS:     ${info.system_version || '—'}`,
      `Screen:  ${info.point_width}×${info.point_height} pt (${info.pixel_width}×${info.pixel_height} px, ${info.scale}x)`,
      `Server:  ${info.server_version || '—'}${info.protocol_version != null ? ' (proto ' + info.protocol_version + ')' : ''}`,
    ];
    hudDevice.title = lines.join('\n');
  }

  // ── coordinate conversion ──
  // The video element shows the encoded frame; we map a click on it to device
  // POINTS via device_info's point_width/point_height. video.videoWidth/Height
  // is the encoded pixel size; the letterboxed layout inside the element uses
  // getBoundingClientRect for the visible box.
  //
  // In full screen the picture can also fill the window (object-fit: cover,
  // edges cropped) or be stretched to it (fill); the box below follows
  // whichever is in effect, so a touch still lands where it is drawn.
  function videoBox() {
    const rect = video.getBoundingClientRect();
    const vw = video.videoWidth || rect.width;
    const vh = video.videoHeight || rect.height;
    if (!vw || !vh) return null;
    const fit = getComputedStyle(video).objectFit;
    let sx = Math.min(rect.width / vw, rect.height / vh), sy = sx;
    if (fit === 'cover') sx = sy = Math.max(rect.width / vw, rect.height / vh);
    else if (fit === 'fill') { sx = rect.width / vw; sy = rect.height / vh; }
    const w = vw * sx, h = vh * sy;
    const x0 = rect.left + (rect.width - w) / 2;
    const y0 = rect.top + (rect.height - h) / 2;
    return { x0, y0, w, h, vw, vh };
  }
  function clientToPoint(cx, cy) {
    if (!deviceInfo) return null;
    const b = videoBox(); if (!b) return null;
    if (cx < b.x0 || cx > b.x0 + b.w || cy < b.y0 || cy > b.y0 + b.h) return null;
    // fraction inside the image → device points
    const fx = (cx - b.x0) / b.w, fy = (cy - b.y0) / b.h;
    return { x: fx * deviceInfo.point_width, y: fy * deviceInfo.point_height };
  }

  // ── input handling on the video ──
  // Every touch on the picture belongs to the phone being controlled. Without
  // this the browser also reads a sideways drag as its own back/forward swipe
  // and leaves the page mid-gesture; touch-action doesn't cover navigation
  // gestures, cancelling the touch events does. Input itself comes from the
  // pointer events below, which still fire.
  for (const type of ['touchstart', 'touchmove']) {
    overlay.addEventListener(type, e => { if (e.cancelable) e.preventDefault(); }, { passive: false });
  }
  overlay.addEventListener('pointerdown', e => {
    // Left button (or a touch) only: the right button is Home.
    lastPointerType = e.pointerType;
    if (e.button !== 0) return;
    overlay.setPointerCapture(e.pointerId);
    dragStart = { x: e.clientX, y: e.clientY, t: Date.now() };
    overlay.focus();
  });
  overlay.addEventListener('pointerup', async e => {
    if (!dragStart) return;
    const s = dragStart; dragStart = null;
    const dx = e.clientX - s.x, dy = e.clientY - s.y;
    const dist = Math.hypot(dx, dy);
    try {
      if (dist < 6) {
        const p = clientToPoint(e.clientX, e.clientY); if (!p) return;
        // Held in place → long press, for as long as it was held.
        const held = (Date.now() - s.t) / 1000;
        if (held >= 0.5) {
          await rpc('long_press', { x: Math.round(p.x), y: Math.round(p.y),
                                    duration: Math.min(3, Math.max(0.6, held)) });
          setStatus(`long_press (${Math.round(p.x)},${Math.round(p.y)})`, 'ok');
          return;
        }
        await rpc('tap', { x: Math.round(p.x), y: Math.round(p.y) });
        setStatus(`tap (${Math.round(p.x)},${Math.round(p.y)})`, 'ok');
      } else {
        // The server distinguishes the two arbitrary-A→B gesture APIs:
        //   swipe(x, y, direction, distance)          fixed axes, from a point
        //   drag (from_x, from_y, to_x, to_y)         truly arbitrary two-point
        // Browser pointer drag is the second — send drag, not swipe.
        const p1 = clientToPoint(s.x, s.y), p2 = clientToPoint(e.clientX, e.clientY);
        if (!p1 || !p2) return;
        // Duration proportional to gesture time makes flicks feel like flicks
        // and slow drags feel deliberate — capped for sanity.
        const dur = Math.max(0.15, Math.min(0.8, (Date.now() - s.t) / 1000));
        await rpc('drag', {
          from_x: Math.round(p1.x), from_y: Math.round(p1.y),
          to_x:   Math.round(p2.x), to_y:   Math.round(p2.y),
          duration: dur,
        });
        setStatus(`drag → (${Math.round(p2.x)},${Math.round(p2.y)})`, 'ok');
      }
    } catch (err) { setStatus(err.message, 'err'); }
  });
  // Double-click → double_tap
  overlay.addEventListener('dblclick', async e => {
    const p = clientToPoint(e.clientX, e.clientY); if (!p) return;
    try { await rpc('double_tap', { x: Math.round(p.x), y: Math.round(p.y) }); setStatus(`double_tap`, 'ok'); }
    catch (err) { setStatus(err.message, 'err'); }
  });
  // Right-click → Home (long press is a left press held in place). A held
  // finger on a touch screen also raises contextmenu; that one is the long
  // press already handled on pointerup, not Home.
  let lastPointerType = 'mouse';
  overlay.addEventListener('contextmenu', async e => {
    e.preventDefault();
    if (lastPointerType !== 'mouse') return;
    try { await rpc('home'); setStatus('home', 'ok'); }
    catch (err) { setStatus(err.message, 'err'); }
  });
  // Wheel → page (vertical) or a horizontal swipe. Trackpad up = feed moves
  // down = swipe up gesture. Sideways (trackpad, tilt wheel, shift+wheel) is
  // a swipe from under the pointer: carousels, pagers, back gestures.
  // deltaX > 0 means "scroll right", i.e. the finger moves left.
  let wheelAcc = 0, wheelTimer = null;
  let sideAcc = 0, sideLock = null, sidePoint = null;
  overlay.addEventListener('wheel', e => {
    e.preventDefault();
    const dx = e.deltaX || (e.shiftKey ? e.deltaY : 0);
    const sideways = Math.abs(dx) > Math.abs(e.deltaY) || (e.shiftKey && !e.deltaX);
    if (sideways || sideLock) {
      // One swipe per gesture: a trackpad keeps sending (momentum) events
      // after the fingers lift; they extend the lock instead of swiping again.
      if (sideLock) {
        clearTimeout(sideLock);
        sideLock = setTimeout(() => { sideLock = null; sideAcc = 0; }, 350);
        return;
      }
      if (!sidePoint) sidePoint = clientToPoint(e.clientX, e.clientY);
      sideAcc += dx;
      if (Math.abs(sideAcc) < 30 || !sidePoint || !deviceInfo) return;
      const w = deviceInfo.point_width;
      const dist = w * 0.45;
      const dir = sideAcc > 0 ? -1 : 1;
      // Keep both ends on the screen.
      const fromX = Math.max(8 + (dir < 0 ? dist : 0), Math.min(w - 8 - (dir > 0 ? dist : 0), sidePoint.x));
      const y = Math.round(sidePoint.y);
      sidePoint = null; sideAcc = 0;
      sideLock = setTimeout(() => { sideLock = null; }, 350);
      rpc('drag', { from_x: Math.round(fromX), from_y: y, to_x: Math.round(fromX + dir * dist), to_y: y, duration: 0.2 })
        .then(() => setStatus(`swipe ${dir < 0 ? 'left' : 'right'}`, 'ok'))
        .catch(err => setStatus(err.message, 'err'));
      return;
    }
    sidePoint = null; sideAcc = 0;
    wheelAcc += e.deltaY;
    if (wheelTimer) clearTimeout(wheelTimer);
    wheelTimer = setTimeout(async () => {
      const acc = wheelAcc; wheelAcc = 0;
      if (Math.abs(acc) < 40) return;
      try {
        const dir = acc > 0 ? 'down' : 'up';
        await rpc('page', { direction: dir });
        setStatus(`page ${dir}`, 'ok');
      } catch (err) { setStatus(err.message, 'err'); }
    }, 100);
  }, { passive: false });
  // Keyboard → type. Enter → submit; printable char → type; Backspace → clear one char via clear_text is heavy — send a delete via type of \b? iCTRL clear_text empties the whole field; skip that on Backspace and let user use the Clear button.
  overlay.addEventListener('keydown', async e => {
    if (e.key === 'Enter') {
      e.preventDefault();
      try { await rpc('type', { text: '', submit: true }); setStatus('submit', 'ok'); } catch (err) { setStatus(err.message, 'err'); }
      return;
    }
    if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      try { await rpc('type', { text: e.key }); setStatus(`type '${e.key}'`, 'ok'); } catch (err) { setStatus(err.message, 'err'); }
    }
  });

  // ── screenshot ──
  // Shown in a sheet rather than downloaded straight away, so the result is
  // visible: on iPhone a download only asks once and then lands silently in
  // Files › Downloads.
  const shotSheet = $('#shotSheet'), shotImg = $('#shotImg'), shotSave = $('#shotSave');
  let shotURL = null;
  async function showScreenshot() {
    const scale = Math.min(3, deviceInfo?.screen_scale || 2);
    const s = await rpc('screenshot', { scale, quality: 0.92 });
    const mime = s.format === 'png' ? 'image/png' : 'image/jpeg';
    const bytes = Uint8Array.from(atob(s.data), c => c.charCodeAt(0));
    if (shotURL) URL.revokeObjectURL(shotURL);
    shotURL = URL.createObjectURL(new Blob([bytes], { type: mime }));
    shotImg.src = shotURL;
    shotSave.href = shotURL;
    shotSave.download = `ictrl-shot-${Date.now()}.${s.format === 'png' ? 'png' : 'jpg'}`;
    $('#shotHint').hidden = !/iPhone|iPad|iPod/.test(navigator.userAgent);
    closeDrawer(); hideQuick();
    shotSheet.hidden = false;
  }
  $('#shotClose').addEventListener('click', () => { shotSheet.hidden = true; });
  shotSheet.addEventListener('click', e => { if (e.target === shotSheet) shotSheet.hidden = true; });

  // ── side-panel buttons ──
  document.querySelectorAll('[data-act]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const act = btn.dataset.act;
      try {
        if (act === 'home') { await rpc('home'); setStatus('home', 'ok'); }
        else if (act === 'unlock') { await rpc('unlock'); setStatus('unlock', 'ok'); }
        else if (act === 'lock-confirm') {
          if (!confirm('Lock the phone?\nUnlocking may need the passcode entered on the device.')) return;
          await rpc('lock'); setStatus('lock', 'ok');
        }
        else if (act === 'screenshot') { await showScreenshot(); }
        else if (act === 'open-app') {
          const name = prompt('App name to open:'); if (!name) return;
          setStatus(`resolving "${name}"…`);
          const r = await rpc('resolve_app', { text: name });
          const app = (r.apps || [])[0];
          if (!app) { setStatus(`no app "${name}"`, 'err'); return; }
          await rpc('launch_app', { bundle_id: app.bundle_id });
          setStatus(`opened ${app.name}`, 'ok');
        }
        else if (act === 'type-text') {
          const text = prompt('Text to type into the focused field:'); if (!text) return;
          const submit = confirm('Submit (press Return) after typing?');
          await rpc('type', { text, submit });
          setStatus(`type "${text}"` + (submit ? ' + submit' : ''), 'ok');
        }
        else if (act === 'clear-text') { await rpc('clear_text'); setStatus('clear_text', 'ok'); }
        else if (act === 'submit') { await rpc('type', { text: '', submit: true }); setStatus('submit', 'ok'); }
      } catch (err) { setStatus(err.message, 'err'); }
    });
  });
  // Direction pad: swipe from center of the video image.
  document.querySelectorAll('[data-nav]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const dir = btn.dataset.nav;
      if (!deviceInfo) return setStatus('not connected', 'err');
      const w = deviceInfo.point_width, h = deviceInfo.point_height;
      const cx = w/2, cy = h/2, d = Math.min(w, h) * 0.35;
      const vec = { up: [0,-d], down: [0,d], left: [-d,0], right: [d,0], center: [0,0] }[dir];
      try {
        if (dir === 'center') {
          await rpc('tap', { x: Math.round(cx), y: Math.round(cy) });
          setStatus('tap center', 'ok');
        } else {
          await rpc('swipe', {
            from_x: Math.round(cx), from_y: Math.round(cy),
            to_x:   Math.round(cx + vec[0]), to_y: Math.round(cy + vec[1]),
            velocity: 'normal',
          });
          setStatus(`swipe ${dir}`, 'ok');
        }
      } catch (err) { setStatus(err.message, 'err'); }
    });
  });
  document.querySelectorAll('[data-page]').forEach(btn => {
    btn.addEventListener('click', async () => {
      try { await rpc('page', { direction: btn.dataset.page }); setStatus(`page ${btn.dataset.page}`, 'ok'); }
      catch (err) { setStatus(err.message, 'err'); }
    });
  });

  // ── connection lifecycle ──
  async function connect() {
    let hexKey = tokenInput.value.trim();
    // No key yet (or a malformed one) → pair right here rather than telling the
    // user to go run curl. The device will prompt for approval on its screen.
    if (!/^[0-9a-f]{64}$/i.test(hexKey)) {
      if (hexKey) { setStatus('that is not a 64-hex key — pairing instead…', 'warn'); }
      try {
        hexKey = await pairInPage('browser @ ' + (navigator.platform || 'web'));
        tokenInput.value = hexKey;
      } catch (err) { setConn('pair: ' + err.message, 'err'); return; }
    }
    if (!useKeyHex(hexKey)) { setStatus('invalid pairing key', 'err'); return; }
    // tok = first 4 bytes of SHA-256(K) — the public lookup id sent on the wire.
    tok = hex(await sha256(key)).slice(0, 8);
    setStatus('connecting…');
    // Prime device_info for coord conversion + title.
    try {
      deviceInfo = await rpc('device_info');
      updateHudDevice(deviceInfo);
      renderSysmon(deviceInfo.system);
      startSysmon();
      // Auth confirmed by a successful RPC — remember the key for next visit.
      try { localStorage.setItem(STORE_KEY, hexKey.toLowerCase()); } catch (_) {}
    } catch (err) { setStatus('rpc: ' + err.message, 'err'); return; }

    // Native MSE — Chrome / Firefox / Edge / desktop Safari support fMP4 via
    // MediaSource. No JS decoder library needed. Safari on iPhone has no
    // MediaSource, only ManagedMediaSource (iOS 17.1+).
    if (!MSE) {
      setStatus('this browser can\'t play the stream (on iPhone it needs iOS 17.1 or later)', 'err');
      return;
    }

    const fps = fpsSel.value;
    const quality = qSel?.value || 'auto';
    const verbose = verboseChk?.checked ? '&verbose=1' : '';
    // The stream is a long-lived byte pipe, so it can't carry a per-request
    // envelope. Mint a single-use, ~60s ticket over the encrypted channel and
    // spend it on the URL: nothing long-lived is ever exposed there.
    let ticket;
    try {
      ticket = (await rpc('stream_ticket')).ticket;
    } catch (err) { setStatus('ticket: ' + err.message, 'err'); return; }
    const src = `/stream?ticket=${encodeURIComponent(ticket)}&fps=${fps}&quality=${quality}${verbose}`;

    // Tear any previous MSE + fetch down before starting a new one.
    if (player) { try { player.stop(); } catch(_){} player = null; }
    // "streaming" is shown once the first frame is decoded, not when the
    // SourceBuffer opens: the stream headers can arrive before play() resolves,
    // and the later "waiting" status would otherwise stick.
    let mime = '';
    player = mseFragmentPlayer(video, src, {
      onOpen: (info) => { mime = info?.mime || ''; },
      onError: (msg) => setStatus('stream: ' + msg, 'err'),
    });
    const current = player;
    video.addEventListener('loadeddata', () => {
      // The codec string is long and wraps on a phone; it goes in the tooltip.
      if (player === current) { setStatus('streaming', 'ok'); hudState.title = mime; }
    }, { once: true });
    setStatus('connected — waiting for first frame…', 'ok');
    connectBtn.disabled = true; stopBtn.disabled = false;
    connectCta.hidden = true;
    try { await video.play(); } catch (_) {
      setStatus('autoplay blocked — click the video', 'err');
    }
    overlay.focus();
  }
  function stop() {
    if (player) { try { player.stop(); } catch(_){} player = null; }
    stopSysmon();
    connectBtn.disabled = false; stopBtn.disabled = true;
    connectCta.hidden = false;
    setStatus('stopped');
    hudDot.className = 'dot off';
  }

  // --- Minimal fMP4-over-HTTP MSE player -------------------------------
  // Streams /stream via fetch, pumps chunks into a SourceBuffer.
  //
  // Design notes (learned the hard way — see git log):
  //
  //  1) `sb.updating` covers BOTH appendBuffer and remove. Doing them
  //     back-to-back in the same updateend handler would set `updating`
  //     again and the next pump() sees updating=true → nothing appends.
  //     If the following updateend also fires remove, pump is starved
  //     forever. Fix: a single state machine drives one op at a time
  //     (append preferred over cleanup) and every updateend re-enters
  //     it.
  //
  //  2) Setting `videoEl.currentTime` while `sb.updating === true` is
  //     illegal → InvalidStateError. Do the seek only from tick(), not
  //     from updateend.
  //
  //  3) The server's X-Codec header carries the REAL profile/level
  //     from the SPS. Guessing (avc1.42E01F) makes MSE silently
  //     reject appends and the picture stays black.
  //
  //  4) Safari on iPhone only has ManagedMediaSource. It never opens unless
  //     remote playback (AirPlay) is disabled or given an alternative source,
  //     and it may evict buffered data on its own, which a live stream that
  //     keeps only the last few seconds doesn't mind.
  const MSE = window.MediaSource || window.ManagedMediaSource || null;
  function mseFragmentPlayer(videoEl, url, { onOpen, onError }) {
    const ms = new MSE();
    if (window.ManagedMediaSource && ms instanceof window.ManagedMediaSource) {
      videoEl.disableRemotePlayback = true;
    }
    videoEl.src = URL.createObjectURL(ms);
    const ac = new AbortController();
    let sb = null;
    const queue = [];              // pending Uint8Arrays
    let running = true;
    let sourceOpen = false;
    let pendingCodec = null;
    let removePending = false;     // set by maintenance, cleared in tick

    function reportError(where, err) {
      const msg = (err && err.name === 'QuotaExceededError')
        ? 'MSE buffer full' : (err?.message || where);
      onError?.(where + ': ' + msg);
    }

    // Single serialized state machine. Called after every updateend, after
    // every new chunk, and from a rescue watchdog. It picks the next legal
    // action and does exactly one of them.
    function tick() {
      if (!running || !sb || sb.updating) return;
      // 1) Drain the append queue first — never let bytes stall.
      if (queue.length) {
        try { sb.appendBuffer(queue.shift()); }
        catch (err) { reportError('append', err); running = false; ac.abort(); }
        return;
      }
      // 2) Trim old data when the window grows past ~4 s behind currentTime.
      if (removePending) {
        removePending = false;
        try {
          if (videoEl.buffered.length) {
            const start = videoEl.buffered.start(0);
            const cutoff = Math.max(start, videoEl.currentTime - 2);
            if (cutoff - start > 0.5) sb.remove(start, cutoff);
          }
        } catch (_) {}
        return;
      }
    }

    function attachSourceBuffer(codec) {
      const mime = `video/mp4; codecs="${codec}"`;
      if (!MSE.isTypeSupported(mime)) {
        onError?.(`browser doesn't support ${mime}`);
        return false;
      }
      sb = ms.addSourceBuffer(mime);
      sb.mode = 'segments';
      sb.addEventListener('updateend', tick);
      sb.addEventListener('error', (e) => reportError('sourceBuffer', e));
      onOpen?.({ mime });
      return true;
    }

    function maybeStart() {
      if (sourceOpen && pendingCodec && !sb) {
        if (!attachSourceBuffer(pendingCodec)) return;
        tick();
      }
    }

    ms.addEventListener('sourceopen', () => { sourceOpen = true; maybeStart(); });
    ms.addEventListener('sourceclose', () => { running = false; });

    // Live edge: every 100 ms. Frame timestamps follow the device clock, so
    // after the stream stalls (capture blocked, network hiccup) the player is
    // behind by exactly the stall. A small lag is caught up by playing faster
    // — no visible jump; a large one (a long stall, a hidden tab) by a seek,
    // only when sb is idle (seeking during an update throws).
    const live = setInterval(() => {
      if (!running || !sb) return;
      try {
        const bl = videoEl.buffered.length;
        if (!bl) return;
        const lag = videoEl.buffered.end(bl - 1) - videoEl.currentTime;
        if (lag > 1.0 && !sb.updating) {
          videoEl.currentTime = videoEl.buffered.end(bl - 1) - 0.05;
          videoEl.playbackRate = 1;
        } else {
          const rate = lag > 0.35 ? Math.min(2, 1 + lag) : 1;
          if (videoEl.playbackRate !== rate) videoEl.playbackRate = rate;
        }
        if (videoEl.paused && running) videoEl.play().catch(() => {});
      } catch (_) {}
    }, 100);

    // Watchdog: every 500 ms, mark old data for removal. Done OUTSIDE
    // updateend so it can't compete with the append pipeline.
    const watchdog = setInterval(() => {
      if (!running || !sb) return;
      // Ask tick to remove a chunk next time it's idle.
      try {
        if (videoEl.buffered.length &&
            videoEl.currentTime - videoEl.buffered.start(0) > 4) {
          removePending = true;
        }
      } catch (_) {}
      // If updateend was somehow missed (shouldn't happen, but observed on
      // Chrome after long uptime) — force-progress the state machine.
      tick();
    }, 500);

    (async () => {
      let resp;
      try {
        resp = await fetch(url, { signal: ac.signal });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
      } catch (err) {
        if (err.name !== 'AbortError') onError?.(err.message);
        return;
      }
      // Codec string from the server (real profile+level from SPS).
      pendingCodec = resp.headers.get('X-Codec') || 'avc1.42E01F';
      maybeStart();

      const reader = resp.body.getReader();
      while (running) {
        let value, done;
        try { ({ value, done } = await reader.read()); }
        catch (err) {
          if (err.name !== 'AbortError') onError?.('read: ' + err.message);
          break;
        }
        if (done) { onError?.('stream ended'); break; }
        queue.push(value); tick();
      }
    })();

    return {
      stop() {
        running = false;
        clearInterval(watchdog);
        clearInterval(live);
        try { ac.abort(); } catch (_) {}
        try { if (ms.readyState === 'open') ms.endOfStream(); } catch (_) {}
        try { URL.revokeObjectURL(videoEl.src); } catch (_) {}
      },
    };
  }
  connectBtn.addEventListener('click', connect);
  stopBtn.addEventListener('click', stop);
  // Changing FPS mid-stream: reconnect so the server sees the new ?fps=…
  // (broadcaster restarts the encoder at the new rate).
  fpsSel.addEventListener('change', () => {
    if (player) { setStatus(`switching to ${fpsSel.value} fps…`); connect(); }
  });
  qSel?.addEventListener('change', () => {
    if (player) { setStatus(`switching to quality ${qSel.value}…`); connect(); }
  });
  verboseChk?.addEventListener('change', () => {
    if (player) { setStatus(`verbose ${verboseChk.checked ? 'on' : 'off'}…`); connect(); }
  });

  // ── preferences ──
  // Per-browser display choices; storage can be unavailable (private mode),
  // in which case the defaults simply apply.
  const pref = {
    get(k, d) { try { const v = localStorage.getItem('ictrl.' + k); return v === null ? d : v; } catch (_) { return d; } },
    set(k, v) { try { localStorage.setItem('ictrl.' + k, v); } catch (_) {} },
  };
  document.querySelectorAll('[data-pref]').forEach(chk => {
    const name = chk.dataset.pref;
    const apply = () => document.body.classList.toggle('hide-' + name, !chk.checked);
    chk.checked = pref.get('show.' + name, '1') === '1';
    apply();
    chk.addEventListener('change', () => { apply(); pref.set('show.' + name, chk.checked ? '1' : '0'); });
  });

  // How the picture meets the window in full screen. Filling it crops the
  // edges when the window's shape differs from the phone's (a Safari tab);
  // from the Home Screen the shapes match and nothing visible is lost.
  const fitSel = document.getElementById('fitSel');
  fitSel.value = pref.get('fit', 'cover');
  document.body.dataset.fit = fitSel.value;
  fitSel.addEventListener('change', () => {
    document.body.dataset.fit = fitSel.value;
    pref.set('fit', fitSel.value);
    updateUnderBars();
  });

  // ── drawer (a bottom sheet on a phone and in full screen) ──
  const app = document.getElementById('app');
  const ball = document.getElementById('ball');
  const quick = document.getElementById('quick');
  const scrim = document.getElementById('scrim');
  const narrow = window.matchMedia('(max-width: 720px)');
  let immersive = false;
  const drawerMode = () => app.classList.contains('drawer');
  function updateDrawerMode() {
    const on = narrow.matches || immersive;
    app.classList.toggle('drawer', on);
    if (!on) { app.classList.remove('open'); hideQuick(); }
    updateUnderBars();
    placeBall();
  }
  function openDrawer() { hideQuick(); app.classList.add('open'); }
  function closeDrawer() { app.classList.remove('open'); }
  scrim.addEventListener('click', closeDrawer);
  // Close the sheet after a control is used, so the picture is visible again.
  document.querySelectorAll('aside [data-act], aside [data-nav], aside [data-page]').forEach(el => {
    el.addEventListener('click', () => { if (drawerMode()) setTimeout(closeDrawer, 120); });
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closeDrawer(); hideQuick(); }
  });

  // ── floating ball ──
  // Its spot is kept as a side plus a fraction of the height, so it survives
  // rotation and window resizes.
  const BALL_MARGIN = 10;
  let ballSpot = (() => {
    try { return JSON.parse(pref.get('ball', '')) || null; } catch (_) { return null; }
  })();
  function placeBall() {
    if (!ballSpot) { ball.style.left = ball.style.top = ''; return; }
    const size = ball.offsetWidth || 48;
    const top = Math.min(Math.max(ballSpot.y * innerHeight, BALL_MARGIN), innerHeight - size - BALL_MARGIN);
    ball.style.left = (ballSpot.side === 'left' ? BALL_MARGIN : innerWidth - size - BALL_MARGIN) + 'px';
    ball.style.top = top + 'px';
    ball.style.right = ball.style.bottom = 'auto';
  }
  let ballDrag = null;
  // Dragging the ball sideways must not start the browser's back swipe either.
  for (const type of ['touchstart', 'touchmove']) {
    ball.addEventListener(type, e => { if (e.cancelable) e.preventDefault(); }, { passive: false });
  }
  ball.addEventListener('pointerdown', e => {
    const r = ball.getBoundingClientRect();
    ballDrag = { id: e.pointerId, sx: e.clientX, sy: e.clientY, dx: e.clientX - r.left, dy: e.clientY - r.top, moved: false };
    ball.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  ball.addEventListener('pointermove', e => {
    if (!ballDrag || e.pointerId !== ballDrag.id) return;
    if (!ballDrag.moved && Math.hypot(e.clientX - ballDrag.sx, e.clientY - ballDrag.sy) < 6) return;
    if (!ballDrag.moved) { ballDrag.moved = true; ball.classList.add('dragging'); hideQuick(); }
    const size = ball.offsetWidth;
    ball.style.left = Math.min(Math.max(e.clientX - ballDrag.dx, 0), innerWidth - size) + 'px';
    ball.style.top = Math.min(Math.max(e.clientY - ballDrag.dy, 0), innerHeight - size) + 'px';
    ball.style.right = ball.style.bottom = 'auto';
  });
  function endBallDrag(e) {
    if (!ballDrag || e.pointerId !== ballDrag.id) return;
    const moved = ballDrag.moved;
    ballDrag = null;
    ball.classList.remove('dragging');
    if (!moved) { quick.hidden ? showQuick() : hideQuick(); return; }
    const r = ball.getBoundingClientRect();
    ballSpot = { side: r.left + r.width / 2 < innerWidth / 2 ? 'left' : 'right', y: r.top / innerHeight };
    pref.set('ball', JSON.stringify(ballSpot));
    placeBall();
  }
  ball.addEventListener('pointerup', endBallDrag);
  ball.addEventListener('pointercancel', endBallDrag);
  window.addEventListener('resize', () => { updateUnderBars(); placeBall(); if (!quick.hidden) positionQuick(); });

  // The ball is pale glass, which vanishes over a white screen. Twice a
  // second, read the patch of the frame under it and switch to the dark
  // style when that patch is light. Without a picture it stays pale.
  const ballProbe = document.createElement('canvas');
  ballProbe.width = ballProbe.height = 8;
  const ballProbeCtx = ballProbe.getContext('2d', { willReadFrequently: true });
  setInterval(() => {
    let light = false;
    try {
      const b = player && drawerMode() && !ballDrag ? videoBox() : null;
      if (b && video.readyState >= 2) {
        const r = ball.getBoundingClientRect();
        const kx = b.vw / b.w, ky = b.vh / b.h;
        ballProbeCtx.drawImage(video, (r.left - b.x0) * kx, (r.top - b.y0) * ky,
                               r.width * kx, r.height * ky, 0, 0, 8, 8);
        const d = ballProbeCtx.getImageData(0, 0, 8, 8).data;
        let sum = 0;
        for (let i = 0; i < d.length; i += 4) sum += 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
        light = sum / 64 > 150;
      }
    } catch (_) {}
    ball.classList.toggle('on-light', light);
  }, 500);

  // ── quick controls, opened from the ball ──
  function positionQuick() {
    const b = ball.getBoundingClientRect();
    const q = quick.getBoundingClientRect();
    const gap = 8;
    let left = b.left + b.width / 2 < innerWidth / 2 ? b.left : b.right - q.width;
    let top = b.top - q.height - gap;
    if (top < gap) top = b.bottom + gap;
    left = Math.min(Math.max(left, gap), innerWidth - q.width - gap);
    top = Math.min(Math.max(top, gap), innerHeight - q.height - gap);
    quick.style.left = left + 'px';
    quick.style.top = top + 'px';
  }
  // Connect and Stop live in the drawer, out of reach while the picture is
  // in use; the quick menu carries whichever one applies now.
  const quickConn = document.getElementById('quickConn');
  function showQuick() {
    quickConn.querySelector('span').textContent = player ? 'Stop' : 'Connect';
    quick.hidden = false; ball.classList.add('active'); positionQuick();
  }
  quickConn.addEventListener('click', () => {
    hideQuick();
    if (player) stop(); else connect();
  });
  function hideQuick() { quick.hidden = true; ball.classList.remove('active'); }
  quick.querySelectorAll('[data-act]').forEach(el => el.addEventListener('click', () => setTimeout(hideQuick, 120)));
  document.getElementById('quickMore').addEventListener('click', openDrawer);
  document.addEventListener('pointerdown', e => {
    if (!quick.hidden && !quick.contains(e.target) && e.target !== ball) hideQuick();
  }, true);

  // ── full screen ──
  // The page's own full screen where the browser has one (desktop, iPad,
  // Android); iPhone Safari only offers it for a bare <video>, which would take
  // the controls away, so there it is the same layout without the browser's
  // full screen.
  const root = document.documentElement;
  const fsElement = () => document.fullscreenElement || document.webkitFullscreenElement;
  const standalone = navigator.standalone === true ||
    window.matchMedia('(display-mode: standalone)').matches;
  document.body.classList.toggle('standalone', standalone);
  // A Safari tab on iPhone can't hide the browser's bars. From iOS 26 the
  // toolbar floats over the page, so the picture can run underneath it to the
  // bottom of the screen (updateUnderBars). On older versions the space
  // between the bars is all there is, and it is shorter than the phone's
  // screen: say how to get the whole screen, once per page load.
  const barsStay = !standalone && !(root.requestFullscreen || root.webkitRequestFullscreen);
  let barsHintShown = false;
  const ua = navigator.userAgent;
  const floatingBar = barsStay && /iPhone/.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS/.test(ua) &&
    Number((ua.match(/Version\/(\d+)/) || [])[1]) >= 26;
  // Where the page starts on the screen (the status bar's height), which the
  // browser doesn't expose: by screen size, in points.
  function statusBarHeight() {
    return ({ '375x812': 44, '414x896': 48, '390x844': 47, '428x926': 47,
              '393x852': 59, '430x932': 59, '402x874': 62, '440x956': 62,
              '420x912': 68 })[screen.width + 'x' + screen.height] || 54;
  }
  function updateUnderBars() {
    const portrait = window.matchMedia('(orientation: portrait)').matches;
    // In a Safari tab: under the floating toolbar, when the picture is set to
    // fill the screen. From the Home Screen: the page starts at the top of
    // the screen, but on some iOS versions its viewport is the status bar's
    // height too short, which leaves a black band along the bottom; the same
    // taller page covers it, with no scrolling needed.
    const inTab = floatingBar && fitSel.value === 'cover';
    const on = immersive && portrait && (inTab || standalone) && screen.height > innerHeight;
    // Entering: the status bar must pass through display:none, even with a
    // message up, or its strip stays painted over the bottom of the picture.
    if (on && !root.classList.contains('under-bars')) {
      document.getElementById('status').classList.remove('has-toast');
    }
    root.classList.toggle('under-bars', on);
    // The page is made exactly as tall as the screen and scrolled up by the
    // status bar's height, which puts its top edge at the top of the screen:
    // Safari shows a scrolled page beneath the status bar as well.
    app.style.height = on ? screen.height + 'px' : '';
    underBarsScroll = on && !standalone ? statusBarHeight() : 0;
    if (scrollY !== underBarsScroll) scrollTo(0, underBarsScroll);
  }
  let underBarsScroll = 0;
  // Nothing else should move the page from that position.
  window.addEventListener('scroll', () => {
    if (root.classList.contains('under-bars') && Math.abs(scrollY - underBarsScroll) > 0.5) scrollTo(0, underBarsScroll);
  });
  let inBrowserFs = false;
  function setImmersive(on, restoring = false) {
    immersive = on;
    document.body.classList.toggle('immersive', on);
    document.querySelectorAll('[data-fs]').forEach(el => {
      const label = el.querySelector('span');
      if (label) label.textContent = on ? 'Exit' : 'Full screen';
      else if (el.classList.contains('btn')) el.textContent = on ? '⛶ Exit full screen' : '⛶ Full screen';
      el.title = on ? 'Exit full screen' : 'Full screen';
    });
    pref.set('immersive', on ? '1' : '0');
    if (on && barsStay && !floatingBar && !barsHintShown && !restoring) {
      barsHintShown = true;
      setToast('Safari keeps its bars here. Add to Home Screen to fill the screen.', 'warn', 6000, true);
    }
    closeDrawer(); hideQuick();
    updateDrawerMode();
    try {
      if (on && !fsElement()) {
        const req = root.requestFullscreen || root.webkitRequestFullscreen;
        const r = req && req.call(root);
        if (r && r.catch) r.catch(() => {});
      } else if (!on && fsElement()) {
        const exit = document.exitFullscreen || document.webkitExitFullscreen;
        const r = exit && exit.call(document);
        if (r && r.catch) r.catch(() => {});
      }
    } catch (_) {}
  }
  // Leaving the browser's full screen (Esc, a system gesture) leaves ours too.
  ['fullscreenchange', 'webkitfullscreenchange'].forEach(ev => document.addEventListener(ev, () => {
    if (fsElement()) inBrowserFs = true;
    else if (inBrowserFs) { inBrowserFs = false; if (immersive) setImmersive(false); }
  }));
  document.querySelectorAll('[data-fs]').forEach(el => el.addEventListener('click', () => setImmersive(!immersive)));
  narrow.addEventListener?.('change', updateDrawerMode);
  // A reload can't re-enter the browser's full screen (it needs a tap), but
  // the layout comes back as it was.
  // ?fullscreen=1 (the Home Screen app's start URL) always opens full screen;
  // otherwise the last choice in this browser, and full screen by default when
  // running as a Home Screen app.
  const params = new URLSearchParams(location.search);
  const startImmersive = params.get('fullscreen') === '1' ||
    pref.get('immersive', standalone ? '1' : '0') === '1';
  if (startImmersive) setImmersive(true, true); else updateDrawerMode();

  // ── add to Home Screen ──
  // Chrome and Edge offer an install prompt; Safari has no API for it, so
  // there the page puts the full-screen URL in the address bar (what Add to
  // Home Screen saves) and explains the steps.
  const installBtn = document.getElementById('installBtn');
  const installSheet = document.getElementById('installSheet');
  let installPrompt = null;
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); installPrompt = e; });
  installBtn.hidden = standalone;
  installBtn.addEventListener('click', async () => {
    if (installPrompt) {
      const p = installPrompt; installPrompt = null;
      try { await p.prompt(); } catch (_) {}
      return;
    }
    try { history.replaceState(null, '', '/remote?fullscreen=1'); } catch (_) {}
    if (!/iPhone|iPad|iPod/.test(navigator.userAgent) && !(navigator.maxTouchPoints > 1 && /Mac/.test(navigator.userAgent))) {
      document.getElementById('installSteps').innerHTML =
        '<li>Open the browser menu.</li><li>Choose <b>Install</b> or <b>Add to Home screen</b>.</li>';
    }
    closeDrawer(); hideQuick();
    installSheet.hidden = false;
  });
  document.getElementById('installClose').addEventListener('click', () => { installSheet.hidden = true; });

  // Never connect on load: a connection streams video and polls the device,
  // and a forgotten tab (or every reload) would keep doing that. A saved key
  // just makes Connect one tap.
  const connectCta = document.getElementById('connectCta');
  document.getElementById('ctaBtn').addEventListener('click', connect);
  if (savedKey) {
    document.getElementById('ctaNote').textContent = 'Saved key found — tap Connect to start streaming.';
  }
  // Leaving the tab (or locking the phone) ends the session for the same
  // reason; coming back shows Connect again.
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && player) { stop(); setStatus('stopped while the page was hidden — tap Connect'); }
  });
})();
</script>
</body>
</html>
"""#
}
