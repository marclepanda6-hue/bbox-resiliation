import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
  timeout: 20000,
});

export function formatApiErrorDetail(detail) {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .filter(Boolean)
      .join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

/**
 * Translate any axios error into a user-friendly French message.
 * Covers network / CORS failures, timeouts, 4xx / 5xx responses.
 */
export function describeApiError(err, fallback = "Une erreur est survenue. Veuillez réessayer.") {
  if (!err) return fallback;

  // Network error: no response received (CORS block, DNS, offline, server down...)
  if (err.message === "Network Error" || !err.response) {
    if (err.code === "ECONNABORTED") {
      return "La requête a pris trop de temps. Vérifiez votre connexion et réessayez.";
    }
    return "Impossible de contacter le serveur. Vérifiez votre connexion internet, puis réessayez.";
  }

  const status = err.response.status;
  const detail = err.response.data && err.response.data.detail;
  const parsed = formatApiErrorDetail(detail);
  if (parsed) return parsed;

  // Status-based fallbacks
  if (status === 401) return "Identifiants incorrects.";
  if (status === 403) return "Accès refusé.";
  if (status === 404) return "Ressource introuvable.";
  if (status === 429) return "Trop de tentatives. Réessayez dans quelques minutes.";
  if (status >= 500) return "Le serveur rencontre un problème. Réessayez plus tard.";
  return fallback;
}
