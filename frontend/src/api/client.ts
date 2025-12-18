const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

type RequestOptions = {
  method?: string;
  token?: string | null;
  body?: BodyInit | null;
  headers?: Record<string, string>;
  retryOnAuthError?: boolean;
};

const ACCESS_KEY = "ai_platform_token";
const REFRESH_KEY = "ai_platform_refresh";

type TokenSyncFn = (access: string | null, refresh?: string | null) => void;
let syncTokens: TokenSyncFn | null = null;

export function bindTokenSync(fn: TokenSyncFn) {
  syncTokens = fn;
}

const getStoredAccess = () => localStorage.getItem(ACCESS_KEY);
const getStoredRefresh = () => localStorage.getItem(REFRESH_KEY);

function storeTokens(access: string | null, refresh?: string | null) {
  if (access) localStorage.setItem(ACCESS_KEY, access);
  else localStorage.removeItem(ACCESS_KEY);
  if (refresh !== undefined) {
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
    else localStorage.removeItem(REFRESH_KEY);
  }
  if (syncTokens) {
    syncTokens(access, refresh);
  }
}

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getStoredRefresh();
  if (!refresh) return null;
  try {
    const res = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) throw new Error("refresh failed");
    const data = (await res.json()) as {
      access_token: string;
      refresh_token: string;
    };
    storeTokens(data.access_token, data.refresh_token);
    return data.access_token;
  } catch {
    storeTokens(null, null);
    return null;
  }
}

async function performFetch(
  path: string,
  options: RequestOptions,
  accessToken: string | null
) {
  const { method = "GET", body, headers = {} } = options;
  return fetch(`${API_URL}${path}`, {
    method,
    headers: {
      ...(body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers,
    },
    body,
  });
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { token, retryOnAuthError = true } = options;
  let accessToken = token ?? getStoredAccess();

  let response = await performFetch(path, options, accessToken);

  if (response.status === 401 && retryOnAuthError) {
    const newAccess = await refreshAccessToken();
    if (newAccess) {
      response = await performFetch(path, options, newAccess);
    } else {
      throw new Error("Unauthorized");
    }
  }

  if (!response.ok) {
    const text = await response.text();
    let message = text;
    try {
      const json = JSON.parse(text);
      message = json.detail || json.message || text;
    } catch {
      // ignore parse errors
    }
    throw new Error(message || `Request failed with status ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export function setAuthTokens(access: string, refresh: string) {
  storeTokens(access, refresh);
}

export function clearAuthTokens() {
  storeTokens(null, null);
}

export { API_URL };

