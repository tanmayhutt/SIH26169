// Sign-in gate for the progress site. GitHub Pages cannot run server-side authentication,
// so this is a client-side gate: the page content is hidden until the visitor enters the
// shared credential, which is checked against a SHA-256 digest (the plain text is not in
// this file). It keeps casual visitors out; it is not a substitute for a real login.
(function () {
  const DIGEST = "2f52e69fb2a70936c78ec72f24de7571f7ed021d3556780903c7929ea318032a";
  const KEY = "sih26169-gate";
  const ok = () => { try { return sessionStorage.getItem(KEY) === "1"; } catch (e) { return false; } };
  async function sha256(text) {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("");
  }
  function show() { document.documentElement.classList.add("gate-open"); const g = document.getElementById("gate"); if (g) g.remove(); }
  document.addEventListener("DOMContentLoaded", () => {
    if (ok()) { show(); return; }
    const g = document.createElement("div"); g.id = "gate";
    g.innerHTML = `
      <form class="gate-card" autocomplete="on">
        <div class="gate-eyebrow">SIH26169 / FSOC Tracker</div>
        <h1>Sign in</h1>
        <p>This progress record is shared with the team only.</p>
        <label>Username<input name="username" autocomplete="username" required></label>
        <label>Password<input name="password" type="password" autocomplete="current-password" required></label>
        <div class="gate-err" id="gate-err"></div>
        <button type="submit">Open</button>
      </form>`;
    document.body.appendChild(g);
    g.querySelector("form").addEventListener("submit", async ev => {
      ev.preventDefault();
      const u = g.querySelector('[name=username]').value.trim(), p = g.querySelector('[name=password]').value;
      if (await sha256(u + ":" + p) === DIGEST) { try { sessionStorage.setItem(KEY, "1"); } catch (e) {} show(); }
      else { document.getElementById("gate-err").textContent = "That username and password do not match."; }
    });
    g.querySelector('[name=username]').focus();
  });
})();
