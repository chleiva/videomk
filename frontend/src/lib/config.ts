// NOTE: reconstructed. These files were swallowed by an over-broad `lib/` .gitignore rule and
// never committed; they were rebuilt from how the components use them. Prefer your local
// originals if they differ, and diff before merging.
const env = (import.meta as any).env ?? {};

export const API_BASE: string = (env.PUBLIC_API_BASE as string) || "https://backend.videomk.com";
export const AUTH_DOMAIN: string = (env.PUBLIC_AUTH_DOMAIN as string) || "https://login.videomk.com";
export const COGNITO_CLIENT_ID: string = (env.PUBLIC_COGNITO_CLIENT_ID as string) || "";

const u = (id: string) => encodeURIComponent(id);

export const apiGateway = {
  generateVideo: (userId: string) => `${API_BASE}/users/${u(userId)}/videos/generate`,
  listVideos: (userId: string) => `${API_BASE}/users/${u(userId)}/videos`,
  getVideo: (userId: string, videoId: string) => `${API_BASE}/users/${u(userId)}/videos/${u(videoId)}`,
  plan: (userId: string, videoId: string) => `${API_BASE}/users/${u(userId)}/videos/${u(videoId)}/plan`,
  capabilities: (userId: string) => `${API_BASE}/users/${u(userId)}/capabilities`,
  brief: (userId: string) => `${API_BASE}/users/${u(userId)}/videos/brief`,
  decks: (userId: string) => `${API_BASE}/users/${u(userId)}/decks`,
  deck: (userId: string, deckId: string) => `${API_BASE}/users/${u(userId)}/decks/${u(deckId)}`,
  deckProcess: (userId: string, deckId: string) => `${API_BASE}/users/${u(userId)}/decks/${u(deckId)}/process`,
  feedback: (userId: string) => `${API_BASE}/users/${u(userId)}/feedback`,
  wallet: (userId: string) => `${API_BASE}/users/${u(userId)}/wallet`,
  edits: (userId: string, videoId: string) => `${API_BASE}/users/${u(userId)}/videos/${u(videoId)}/edits`,
};

// Legacy "questions" flow (src/pages/questions.astro). Not served by this repo's backend.
export const endpoints = {
  questions: (taskId?: string) =>
    `${(env.PUBLIC_QUESTIONS_API as string) || API_BASE}/questions${taskId ? `/${u(taskId)}` : ""}`,
};

// Social sign-in switches (build-time, default OFF). Set PUBLIC_AUTH_GOOGLE=1 / PUBLIC_AUTH_APPLE=1
// when the Cognito identity provider is configured for this environment.
const flag = (v: unknown) => ["1", "true", "on", "yes"].includes(String(v ?? "").trim().toLowerCase());
export const AUTH_GOOGLE: boolean = flag(env.PUBLIC_AUTH_GOOGLE);
export const AUTH_APPLE: boolean = flag(env.PUBLIC_AUTH_APPLE);
