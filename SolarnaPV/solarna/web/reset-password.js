(() => {
  "use strict";

  const runtimeConfig = window.SOLARNA_CONFIG || {};
  const i18n = window.SOLARNA_I18N;
  const t = key => i18n?.t(key) || key;
  const nativeShell = runtimeConfig.nativeShell === true;
  const byId = id => document.getElementById(id);
  const status = byId("reset-status");
  const button = byId("reset-button");
  let client = null;

  function apiBase() {
    if (!nativeShell) return runtimeConfig.apiBaseUrl || "";
    try {
      return localStorage.getItem("solarna:api-base") || runtimeConfig.apiBaseUrl || "";
    } catch {
      return runtimeConfig.apiBaseUrl || "";
    }
  }

  async function initialize() {
    try {
      const response = await fetch(`${apiBase()}/api/health`);
      const health = await response.json();
      if (!response.ok || health.authentication_mode !== "supabase") {
        throw new Error("Password reset is not available.");
      }
      client = window.SOLARNA_SUPABASE.createClient(
        health.supabase_url,
        health.supabase_publishable_key,
        { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } }
      );
      const { data, error } = await client.auth.getSession();
      if (error) throw error;
      if (!data.session) {
        status.textContent = "Open the password-reset link sent to your email.";
        button.disabled = true;
      }
    } catch (error) {
      status.textContent = error.message;
      button.disabled = true;
    }
  }

  byId("reset-form").addEventListener("submit", async event => {
    event.preventDefault();
    const password = byId("new-password").value;
    if (password !== byId("confirm-password").value) {
      status.textContent = t("passwords_mismatch");
      return;
    }
    button.disabled = true;
    status.textContent = t("saving");
    const { error } = await client.auth.updateUser({ password });
    if (error) {
      status.textContent = error.message;
      button.disabled = false;
      return;
    }
    status.textContent = t("password_updated");
    window.setTimeout(() => window.location.replace("/login.html"), 800);
  });

  initialize();
})();
