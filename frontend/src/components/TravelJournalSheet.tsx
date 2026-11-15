import { CalendarDays, Image as ImageIcon, MapPin } from "lucide-react";
import { useMemo, useState } from "react";
import { apiAssetUrl, type ApiHighlight } from "../api/client";
import type { Activity, Workspace } from "../types";
import { ModalSheet } from "./ModalSheet";

function formatDate(date: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "short",
  }).format(new Date(`${date}T00:00:00`));
}

function recordImages(record: ApiHighlight) {
  const urls = record.images.map((image) => image.file_url);
  if (record.image_url && !urls.includes(record.image_url)) urls.unshift(record.image_url);
  return urls.map(apiAssetUrl);
}

function JournalRecord({ record, onPreview }: { record: ApiHighlight; onPreview: (url: string) => void }) {
  const images = recordImages(record);
  return (
    <section className="journal-record">
      <div className="journal-record-copy">
        <strong>{record.title}</strong>
        {record.content && <p>{record.content}</p>}
      </div>
      {!!images.length && (
        <div className={`journal-photo-grid journal-photo-grid-${Math.min(images.length, 3)}`}>
          {images.map((url, index) => (
            <button key={`${url}-${index}`} type="button" onClick={() => onPreview(url)} aria-label={`查看${record.title}的第 ${index + 1} 张照片`}>
              <img src={url} alt={`${record.title} · 照片 ${index + 1}`} loading="lazy" />
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function JournalActivity({ activity, records, onPreview }: { activity: Activity; records: ApiHighlight[]; onPreview: (url: string) => void }) {
  return (
    <article className="journal-activity">
      <div className="journal-time">
        <strong>{activity.time}</strong>
        <span />
        <small>{activity.endTime}</small>
      </div>
      <div className="journal-activity-body">
        <div className="journal-activity-heading">
          <span className="journal-order">{activity.order}</span>
          <div>
            <h4>{activity.title}</h4>
            <p><MapPin size={14} />{activity.location}</p>
          </div>
        </div>
        {activity.detail && activity.detail !== activity.location && <p className="journal-activity-detail">{activity.detail}</p>}
        {records.map((record) => <JournalRecord key={record.id} record={record} onPreview={onPreview} />)}
      </div>
    </article>
  );
}

export function TravelJournalSheet({ workspace, highlights, loading, onClose }: { workspace: Workspace; highlights: ApiHighlight[]; loading: boolean; onClose: () => void }) {
  const [preview, setPreview] = useState<string | null>(null);
  const allImages = highlights.flatMap(recordImages);
  const coverImage = allImages[0];
  const recordsByActivity = useMemo(() => {
    const grouped = new Map<number, ApiHighlight[]>();
    highlights.forEach((record) => {
      if (record.activity_id == null) return;
      grouped.set(record.activity_id, [...(grouped.get(record.activity_id) ?? []), record]);
    });
    return grouped;
  }, [highlights]);
  const unboundRecords = highlights.filter((record) => record.activity_id == null);
  const days = Array.from(new Set(workspace.activities.map((activity) => activity.day))).sort((a, b) => a - b);

  return (
    <ModalSheet title="旅行手帐" onClose={onClose} wide>
      <div className={`journal-cover ${coverImage ? "has-photo" : ""}`} style={coverImage ? { backgroundImage: `url(${coverImage})` } : undefined}>
        <div className="journal-cover-content">
          <span>OUR TRAVEL NOTES</span>
          <h3>{workspace.title}</h3>
          <p><MapPin size={15} />{workspace.city}<i /> <CalendarDays size={15} />{workspace.startDate} — {workspace.endDate}</p>
          <div className="journal-stats"><strong>{days.length}</strong><small>天旅程</small><strong>{workspace.activities.length}</strong><small>项活动</small><strong>{allImages.length}</strong><small>张照片</small></div>
        </div>
      </div>

      {loading && <div className="empty-chat">正在整理旅行回忆…</div>}
      {!loading && !workspace.activities.length && !highlights.length && <div className="empty-chat">这次旅行还没有行程或手帐记录</div>}
      {!loading && (
        <div className="journal-days">
          {days.map((day) => {
            const activities = workspace.activities.filter((activity) => activity.day === day).sort((a, b) => a.order - b.order);
            const date = activities[0]?.date;
            return (
              <section className="journal-day" key={day}>
                <header><span>DAY {String(day).padStart(2, "0")}</span><h3>第 {day} 天</h3>{date && <p>{formatDate(date)}</p>}</header>
                <div className="journal-timeline">
                  {activities.map((activity) => <JournalActivity key={activity.id} activity={activity} records={recordsByActivity.get(activity.id) ?? []} onPreview={setPreview} />)}
                </div>
              </section>
            );
          })}
          {!!unboundRecords.length && (
            <section className="journal-day journal-misc">
              <header><span>MEMORIES</span><h3>旅途随记</h3><p>没有绑定具体活动的文字与照片</p></header>
              <div className="journal-unbound-records">{unboundRecords.map((record) => <JournalRecord key={record.id} record={record} onPreview={setPreview} />)}</div>
            </section>
          )}
          {!highlights.length && <div className="journal-empty-note"><ImageIcon size={21} /><div><strong>这次旅行还没有照片或文字记录</strong><p>行程会完整保留；以后在活动卡片中添加的记录会出现在对应活动下方。</p></div></div>}
        </div>
      )}
      {preview && <button className="journal-lightbox" type="button" onClick={() => setPreview(null)} aria-label="关闭照片预览"><img src={preview} alt="旅行照片大图" /></button>}
    </ModalSheet>
  );
}
