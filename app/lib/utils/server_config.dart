// Production URL injected at build time via --dart-define=PARTH_SERVER_URL=https://...
const builtInServerUrl =
    String.fromEnvironment('PARTH_SERVER_URL', defaultValue: '');

/// Quick tunnels (trycloudflare.com) and Tailscale addresses (100.x) are
/// ephemeral — a URL like this saved from a previous session is guaranteed
/// stale by the time the app is reopened, so never trust it.
bool isEphemeralServerUrl(String url) =>
    url.contains('trycloudflare.com') || url.contains('100.125');

/// Resolves the server URL to actually use: prefers a saved URL unless it's
/// known-ephemeral, in which case it falls back to the build-time default.
String resolveServerUrl(String saved) {
  if (saved.isNotEmpty && !isEphemeralServerUrl(saved)) return saved;
  if (builtInServerUrl.isNotEmpty) return builtInServerUrl;
  return isEphemeralServerUrl(saved) ? '' : saved;
}
