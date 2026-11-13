export type Tab = "lobby" | "world" | "functions" | "home";

export type Member = {
  id: number;
  name: string;
  role?: string;
  status: "已补充" | "待补充";
  proxy?: string;
  avatar: string;
  avatarPosition?: string;
};

export type Activity = {
  id: number;
  day: number;
  date: string;
  order: number;
  time: string;
  title: string;
  type: "sight" | "food" | "hotel" | "transport" | "other";
  detail: string;
  location: string;
  latitude: number | null;
  longitude: number | null;
  estimatedPrice: number | null;
  actualPrice: number | null;
  status?: string;
  booked?: boolean;
  openHours?: string;
  openHoursSource?: string;
  priceSource?: string | null;
  priceQueriedAt?: string | null;
  quotedPriceNote?: string;
};

export type Workspace = {
  tripId: number;
  title: string;
  city: string;
  startDate: string;
  endDate: string;
  status: "draft" | "ongoing" | "finished";
  travelerCount: number;
  version: number;
  members: Member[];
  sharedSummary: string;
  sharedCount: number;
  budget: string;
  activities: Activity[];
  historyTrips: { id: number; title: string; dates: string; people: string }[];
};

export type ReplanResult = {
  aiRunId: number;
  summary: string;
  candidateItinerary?: unknown;
  baseVersion: number;
  diff?: { ops: Record<string, unknown>[] };
  retryCount?: number;
  changedItems?: unknown[];
  keptItems?: unknown[];
};

export type AuthUser = {
  id: number;
  username: string;
  nickname: string;
  avatarUrl?: string | null;
};

export type LobbyMessage = {
  id: number;
  tripId: number;
  senderId: number | null;
  senderNickname: string | null;
  senderAvatarUrl?: string | null;
  kind: string;
  content: string;
  visibility: string;
  replyToId: number | null;
  createdAt: string;
};

export type AgentMessage = {
  id: number;
  conversationId: number;
  role: "user" | "assistant";
  content: string;
  status: string;
  errorCode?: string | null;
  structuredData: Record<string, unknown>;
  createdAt: string;
};
