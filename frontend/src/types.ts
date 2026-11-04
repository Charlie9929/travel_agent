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
  time: string;
  title: string;
  type: "sight" | "food" | "hotel" | "transport" | "other";
  detail: string;
  location: string;
  status?: string;
  booked?: boolean;
};

export type Workspace = {
  tripId: number;
  title: string;
  city: string;
  startDate: string;
  endDate: string;
  travelerCount: number;
  version: number;
  members: Member[];
  sharedSummary: string;
  sharedCount: number;
  budget: string;
  activities: Activity[];
  historyTrips: { title: string; dates: string; people: string }[];
};

export type ReplanResult = {
  aiRunId?: number;
  summary: string;
  candidateItinerary?: unknown;
  baseVersion: number;
};
