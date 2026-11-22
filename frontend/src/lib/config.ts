// NOTE: reconstructed. These files were swallowed by an over-broad `lib/` .gitignore rule and
// never committed; they were rebuilt from how the components use them. Prefer your local
// originals if they differ, and diff before merging.
const env = (import.meta as any).env ?? {};

export const API_BASE: string = (env.PUBLIC_API_BASE as string) || "https://api.videomk.com";
export const AUTH_DOMAIN: string = (env.PUBLIC_AUTH_DOMAIN as string) || "https://auth.videomk.com";
export const COGNITO_CLIENT_ID: string = (env.PUBLIC_COGNITO_CLIENT_ID as string) || "6h06ggqnla3a7ej0i9716jnred";

const u = (id: string) => encodeURIComponent(id);

export const apiGateway = {
  generateVideo: (userId: string) => `${API_BASE}/users/${u(userId)}/videos/generate`,
  listVideos: (userId: string) => `${API_BASE}/users/${u(userId)}/videos`,
  getVideo: (userId: string, videoId: string) => `${API_BASE}/users/${u(userId)}/videos/${u(videoId)}`,
  plan: (userId: string, videoId: string) => `${API_BASE}/users/${u(userId)}/videos/${u(videoId)}/plan`,
  edits: (userId: string, videoId: string) => `${API_BASE}/users/${u(userId)}/videos/${u(videoId)}/edits`,
};

// Legacy "questions" flow (src/pages/questions.astro). Not served by this repo's backend.
export const endpoints = {
  questions: (taskId?: string) =>
    `${(env.PUBLIC_QUESTIONS_API as string) || API_BASE}/questions${taskId ? `/${u(taskId)}` : ""}`,
};
