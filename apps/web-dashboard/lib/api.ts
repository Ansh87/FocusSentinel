const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("focussentinel_token");
}

export function setToken(token: string) {
  window.localStorage.setItem("focussentinel_token", token);
}

export function clearToken() {
  window.localStorage.removeItem("focussentinel_token");
}

async function request(path: string, options: RequestInit = {}) {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `Request to ${path} failed with ${resp.status}`);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

export const api = {
  login: (email: string, password: string) =>
    request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string, display_name: string, role: string) =>
    request("/auth/register", { method: "POST", body: JSON.stringify({ email, password, display_name, role }) }),
  createFamily: (name: string, timezone: string) =>
    request("/families", { method: "POST", body: JSON.stringify({ name, timezone }) }),
  myFamilies: () => request("/families/mine"),
  createStudent: (family_id: string, display_name: string, age_range: string, timezone: string) =>
    request("/students", { method: "POST", body: JSON.stringify({ family_id, display_name, age_range, timezone }) }),
  listStudents: (familyId: string) => request(`/students/family/${familyId}`),
  usageToday: (studentId: string) => request(`/students/${studentId}/usage/today`),
  usageWeekly: (studentId: string) => request(`/students/${studentId}/usage/weekly`),
  createRule: (payload: Record<string, unknown>) =>
    request("/rules", { method: "POST", body: JSON.stringify(payload) }),
  listRules: (studentId: string) => request(`/rules/student/${studentId}`),
  updateRule: (id: string, payload: Record<string, unknown>) =>
    request(`/rules/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteRule: (id: string) => request(`/rules/${id}`, { method: "DELETE" }),
  registerDevice: (payload: Record<string, unknown>) =>
    request("/devices/register", { method: "POST", body: JSON.stringify(payload) }),
  createRecipient: (payload: Record<string, unknown>) =>
    request("/notification-recipients", { method: "POST", body: JSON.stringify(payload) }),
  approveExtension: (id: string, minutes?: number, rest_of_day?: boolean) =>
    request(`/extension-requests/${id}/approve`, { method: "POST", body: JSON.stringify({ minutes, rest_of_day }) }),
  denyExtension: (id: string) => request(`/extension-requests/${id}/deny`, { method: "POST" }),
  grantExtension: (student_id: string, rule_id: string, minutes: number) =>
    request("/extension-requests/grant", { method: "POST", body: JSON.stringify({ student_id, rule_id, minutes }) }),
  requestExtension: (payload: Record<string, unknown>) =>
    request("/extension-requests", { method: "POST", body: JSON.stringify(payload) }),
  listExtensionRequests: (studentId: string, status?: string) =>
    request(`/extension-requests?student_id=${studentId}${status ? `&status=${status}` : ""}`),
  deviceHealth: (studentId: string) => request(`/device-health?student_id=${studentId}`),
  websitesCatalog: (familyId: string) => request(`/websites/catalog?family_id=${familyId}`),
  addWebsite: (payload: Record<string, unknown>) =>
    request("/websites", { method: "POST", body: JSON.stringify(payload) }),
  auditLog: (familyId: string) => request(`/audit-log?family_id=${familyId}`),
  loadDemo: () => request("/demo/load", { method: "POST" }),
  resetDemo: () => request("/demo/reset", { method: "POST" }),
  simulateActivity: () => request("/demo/simulate", { method: "POST" }),
  myStudentProfile: () => request("/students/me"),
  usageHistory: (studentId: string, days: number) => request(`/students/${studentId}/usage/history?days=${days}`),
  getStudentLoginStatus: (studentId: string) => request(`/students/${studentId}/login`),
  setStudentLogin: (studentId: string, email: string, password: string) =>
    request(`/students/${studentId}/login`, { method: "POST", body: JSON.stringify({ email, password }) }),
  changePassword: (current_password: string, new_password: string) =>
    request("/auth/change-password", { method: "POST", body: JSON.stringify({ current_password, new_password }) }),
  requestPasswordReset: (email: string) =>
    request("/auth/request-password-reset", { method: "POST", body: JSON.stringify({ email }) }),
  resetPassword: (token: string, new_password: string) =>
    request("/auth/reset-password", { method: "POST", body: JSON.stringify({ token, new_password }) }),
};

export const DEMO_FAMILY_NAME = "Demo Family (Sample Data)";
export function isDemoFamily(name: string | undefined) {
  return name === DEMO_FAMILY_NAME;
}
