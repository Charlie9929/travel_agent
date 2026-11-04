import lobbyScene from "../assets/lobby-scene.jpg";
import homeScene from "../assets/home-scene.png";
import avatarLinyu from "../assets/avatar-linyu.png";
import type { Workspace } from "../types";

export { lobbyScene, homeScene };

export const mockWorkspace: Workspace = {
  tripId: 1,
  title: "山行",
  city: "杭州",
  startDate: "2026-11-06",
  endDate: "2026-11-08",
  travelerCount: 4,
  version: 2,
  members: [
    { id: 1, name: "林予", role: "房主", status: "已补充", avatar: avatarLinyu, avatarPosition: "0% center" },
    { id: 2, name: "阿澈", status: "已补充", avatar: avatarLinyu, avatarPosition: "33.333% center" },
    { id: 3, name: "小满", status: "待补充", avatar: avatarLinyu, avatarPosition: "66.667% center" },
    { id: 4, name: "林妈妈", status: "待补充", proxy: "由房主代填", avatar: avatarLinyu, avatarPosition: "100% center" },
  ],
  sharedSummary: "不赶早，留出拍照时间",
  sharedCount: 3,
  budget: "人均预算 ¥1,500",
  activities: [
    { id: 1, day: 2, date: "2026-11-07", time: "09:30", title: "浙博孤山馆", type: "sight", detail: "参观", location: "杭州西湖" },
    { id: 2, day: 2, date: "2026-11-07", time: "12:00", title: "湖畔午餐", type: "food", detail: "已预订", location: "西湖湖畔", booked: true },
    { id: 3, day: 2, date: "2026-11-07", time: "14:00", title: "湖滨漫步", type: "sight", detail: "步行45分钟", location: "杭州湖滨", status: "待调整" },
    { id: 4, day: 2, date: "2026-11-07", time: "18:30", title: "晚餐", type: "food", detail: "已预订", location: "杭州湖滨", booked: true },
  ],
  historyTrips: [{ title: "安吉", dates: "10月3—4日", people: "2人" }],
};
