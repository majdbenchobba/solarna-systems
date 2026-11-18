(() => {
  "use strict";

  const runtimeConfig = window.SOLARNA_CONFIG || {};
  const i18n = window.SOLARNA_I18N;
  const t = key => i18n?.t(key) || key;
  const nativeShell = runtimeConfig.nativeShell === true;
  const allowInsecureApi = runtimeConfig.allowInsecureApi === true;
  document.body.classList.toggle("native-shell", nativeShell);
  document.body.classList.toggle("web-shell", !nativeShell);

  const byId = id => document.getElementById(id);
  const form = byId("login-form");
  const status = byId("login-status");
  const button = byId("native-connect-button");
  const forgotButton = byId("forgot-password-button");
  let supabaseClient = null;

  function normalizeApiBase(value) {
    const text = typeof value === "string" ? value.trim() : "";
    if (!text) return "";
    const parsed = new URL(text);
    if (!["http:", "https:"].includes(parsed.protocol) ||
        parsed.username || parsed.password || parsed.search || parsed.hash ||
        !parsed.hostname || parsed.pathname !== "/") {
      throw new Error("Enter a complete Solarna server URL.");
    }
    if (nativeShell && parsed.protocol !== "https:" && !allowInsecureApi) {
      throw new Error("The mobile application requires an HTTPS server.");
    }
    return parsed.origin;
  }

  function stored(name, storage) {
    try {
      return storage.getItem(name) || "";
    } catch {
      return "";
    }
  }

  let apiBaseUrl = "";
  try {
    apiBaseUrl = normalizeApiBase(
      nativeShell
        ? stored("solarna:api-base", localStorage) || runtimeConfig.apiBaseUrl
        : runtimeConfig.apiBaseUrl
    );
  } catch {
    apiBaseUrl = "";
  }

  function appUrl() {
    return new URL("index.html", window.location.href).href;
  }

  async function request(path, options, token = "") {
    const headers = new Headers(options?.headers || {});
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${apiBaseUrl}${path}`, {
      ...(options || {}),
      headers
    });
    let payload;
    try {
      payload = await response.json();
    } catch {
      payload = { error: `Server returned ${response.status}` };
    }
    if (!response.ok) {
      throw new Error(payload.error || `Request failed (${response.status})`);
    }
    return payload;
  }

  function configureSupabase(health) {
    if (health.authentication_mode !== "supabase") return null;
    if (!window.SOLARNA_SUPABASE ||
        typeof window.SOLARNA_SUPABASE.createClient !== "function" ||
        typeof health.supabase_url !== "string" ||
        typeof health.supabase_publishable_key !== "string") {
      throw new Error("Login configuration is unavailable.");
    }
    if (!supabaseClient) {
      supabaseClient = window.SOLARNA_SUPABASE.createClient(
        health.supabase_url,
        health.supabase_publishable_key,
        {
          auth: {
            persistSession: true,
            autoRefreshToken: true,
            detectSessionInUrl: true
          }
        }
      );
    }
    return supabaseClient;
  }

  function openApplication() {
    window.location.replace(appUrl());
  }

  async function checkSession() {
    if (nativeShell && !apiBaseUrl) {
      status.textContent = "Enter the Solarna server URL.";
      return;
    }
    try {
      const health = await request("/api/health");
      if (health.authentication_required !== true) {
        openApplication();
        return;
      }
      if (health.authentication_mode === "supabase") {
        const client = configureSupabase(health);
        const { data, error } = await client.auth.getSession();
        if (error) throw error;
        if (!data.session?.access_token) return;
        await request("/api/reports", undefined, data.session.access_token);
        openApplication();
        return;
      }
      if (health.authentication_mode === "login") {
        const token = stored("solarna:session-token", sessionStorage);
        if (!token) return;
        await request("/api/reports", undefined, token);
        openApplication();
        return;
      }
      throw new Error("Email login is not available.");
    } catch (error) {
      try {
        sessionStorage.removeItem("solarna:session-token");
      } catch {
      }
      status.textContent = error.message;
    }
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    button.disabled = true;
    status.textContent = t("signing_in");
    try {
      if (nativeShell) {
        apiBaseUrl = normalizeApiBase(byId("native-api-url").value);
      }
      const email = byId("login-email").value.trim().toLowerCase();
      const password = byId("login-password").value;
      const health = await request("/api/health");
      if (health.authentication_mode === "supabase") {
        const client = configureSupabase(health);
        const { data, error } = await client.auth.signInWithPassword({
          email,
          password
        });
        if (error) throw error;
        if (!data.session?.access_token) {
          throw new Error("Login did not return a valid session.");
        }
        await request("/api/reports", undefined, data.session.access_token);
      } else if (health.authentication_mode === "login") {
        const session = await request("/api/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password })
        });
        if (typeof session.token !== "string" || !session.token) {
          throw new Error("The server did not issue a valid session.");
        }
        sessionStorage.setItem("solarna:session-token", session.token);
      } else {
        throw new Error("Email login is not available.");
      }
      localStorage.setItem("solarna:login-email", email);
      if (nativeShell) localStorage.setItem("solarna:api-base", apiBaseUrl);
      byId("login-password").value = "";
      openApplication();
    } catch (error) {
      status.textContent = error.message;
      button.disabled = false;
    }
  });

  forgotButton.addEventListener("click", async () => {
    forgotButton.disabled = true;
    status.textContent = t("reset_sending");
    try {
      if (nativeShell) {
        apiBaseUrl = normalizeApiBase(byId("native-api-url").value);
      }
      const email = byId("login-email").value.trim().toLowerCase();
      if (!email) throw new Error(t("enter_email"));
      const health = await request("/api/health");
      const client = configureSupabase(health);
      if (!client) throw new Error("Password reset is not available.");
      const redirectOrigin = nativeShell ? apiBaseUrl : window.location.origin;
      const { error } = await client.auth.resetPasswordForEmail(email, {
        redirectTo: `${redirectOrigin}/reset-password.html`
      });
      if (error) throw error;
      status.textContent = t("reset_sent");
    } catch (error) {
      status.textContent = error.message;
    } finally {
      forgotButton.disabled = false;
    }
  });

  byId("login-email").value = stored("solarna:login-email", localStorage);
  if (nativeShell) byId("native-api-url").value = apiBaseUrl;
  checkSession();
})();
